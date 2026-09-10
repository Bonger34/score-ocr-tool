# 提升 OCR 速度优化计划（搜分名单查询工具 · 单文件离线 GPU 版 v2）

## 摘要

对上传的单文件离线 HTML 工具（44MB，内嵌 tesseract.js 回退引擎 + PP-OCRv4 移动版 WebGPU 主引擎）进行纯 JS 层提速改造，**不重新内嵌/替换任何模型**，输出新的单文件交付物。核心发现：当前 `executionProviders` 配置是**死配置**，ONNX 会话实际以 `["cpu"]` EP 创建，OCR 从未真正跑在 GPU 上——修复该配置让 WebGPU 真正生效是最大提速来源；叠加识别参数调优与渲染/识别两阶段流水，预计显著降低 497 个扫描 PDF（约 1000 页）的批量 OCR 总耗时。

## 当前状态分析

### 文件结构

* 源文件：`.archive/uploads_旧版交付物/c748896e-6e8a-4b5d-8bb1-6a150fcecba2_搜分名单查询工具_单文件离线版_GPU.html`（1006 行，44MB）

* 应用脚本：第 208–1004 行（经典 `<script>`，全局变量 `matched`/`textCache` 可被测试脚本直接读取）

* 内嵌资产：`<script type="text/plain" id="gpuassets">` 中 `|` 分隔的 `ORT|MJS|WASM|DET|REC|DICT|PPU` 键值对（base64/gzip），本次不改动

### 引擎架构（已解码 PPU 引擎源码逐一核实）

| 项                 | 现状                                                                                                                                                                                                          | 源码定位                               |
| ----------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------- |
| GPU 引擎            | `PPU.PaddleOcrService` 单例，`svc.recognize(canvas)` 逐张识别                                                                                                                                                      | 主文件 L570–596                       |
| 会话 EP             | 顶层 `executionProviders:['webgpu','wasm']` 为死配置，`deepMerge`（`isObject` 排除数组）后只落到顶层键；库内无任何代码读取顶层键；`_resolveSessionExecutionProviders` 读 `session.executionProviders`（默认 `["cpu"]` 非空即早退）→ **实际以 CPU EP 创建会话** | PPU L307–330、L2021–2029、L2001–2007 |
| 动态批               | rec 模型输入 `x:[-1,3,48,-1]`（batch 维度符号，已用 onnxruntime 实测），`supportsDynamicBatch`=true，`recBatchSize:6` 已生效                                                                                                    | PPU L1665–1669、L298–299            |
| mainThreadYieldMs | 默认 10ms（web 平台），每次 rec 推理批前 `setTimeout(10)`                                                                                                                                                                | PPU L300、L1970–1974                |
| det maxSideLength | `"auto"` = `min(1920, max(960, round(最长边*0.75/32)*32))`，1800px 渲染输入时约 1344px                                                                                                                                | PPU L359–362                       |
| 批识别 API           | `svc.batchRecognize(images,{concurrency,settle})` 存在但未使用；`resolveConcurrency` 对加速器默认 1                                                                                                                      | PPU L1130–1160                     |
| 渲染 cap            | `OC_CAP=1800`                                                                                                                                                                                               | 主文件 L604                           |
| 多页调度              | `mapLimit(ocrIdx, useOcr=3, 渲染→识别混合)`，GPU session.run 串行排队                                                                                                                                                  | 主文件 L628–644                       |
| 文本缓存              | IndexedDB 双级缓存，`TEXT_CACHE_VER='v2'`                                                                                                                                                                        | 主文件 L331                           |
| Tesseract 回退      | worker 池复用，`OCR_CONC=min(2,hc-1)`                                                                                                                                                                           | 主文件 L490–522                       |

### 测试数据

上传的 zip（762 项）含 **497 个 PDF（全部为无文本层扫描件，抽样 8 个 textOps=0、imgRefs>0）**，解压 339MB，估算约 1000 页需 OCR——这正是耗时瓶颈场景。

## 改动方案（6 处，全部在应用脚本区 JS 层）

### 改动 1（核心）：L570 引擎构造参数修正

现状：

```js
var svc=new PPU.PaddleOcrService({model:{detection:detBuf,recognition:recBuf,charactersDictionary:dictBuf},executionProviders:['webgpu','wasm']});
```

改为：

```js
var svc=new PPU.PaddleOcrService({
  model:{detection:detBuf,recognition:recBuf,charactersDictionary:dictBuf},
  session:{executionProviders:['webgpu','wasm']},   // 修复死配置：EP 必须放 session 键下才被 _resolveSessionExecutionProviders 读取
  detection:{maxSideLength:960, minimumAreaThreshold:12}, // det 输入 1800→960；阈值 20→12 补偿小框在 0.51 倍缩放空间下的面积缩水
  recognition:{mainThreadYieldMs:0}                  // 去掉每次 rec 推理前 10ms 主动让出
});
```

要点：`deepMerge` 对数组整体替换、对 `ArrayBuffer` 整体替换（已核实）；`initialize()` 用 `this.options.detection/recognition` 构造 detector/recognitor，per-call `recognize` 不重注入，故必须在构造期设置。若 WebGPU 在用户机器不可用，`createSessionWithFallback` 自动回退 wasm（`ALWAYS_AVAILABLE_FALLBACKS` 含 `wasm`），不破坏回退链。

### 改动 2：新增批识别入口（保留单张路径）

在 `gpuRecognize`（L587）之后追加：

```js
// 批识别：并发 2-3，settle 吸收单项失败；返回按输入顺序对齐的文本数组（失败项为 null）
function gpuRecognizeBatch(canvases, concurrency){
  return gpuInit().then(function(svc){
    if(!svc) return null;
    return svc.batchRecognize(canvases,{concurrency:concurrency,settle:true}).then(function(res){
      return res.map(function(it){
        if(!it||it.status!=='fulfilled'||!it.value||!it.value.text) return null;
        return String(it.value.text).replace(/\s+/g,'');
      });
    }).catch(function(){ return null; });
  });
}
// 内置 Tesseract 池批识别（GPU 不可用/显式选内置时走此路）
function ocrImageTessBatch(canvases){
  return mapLimit(canvases, OCR_CONC, ocrImageTess);
}
```

`batchRecognize` 每项返回单张 `recognize` 结果（`{text,lines,confidence}`），顺序由 `result.index` 保持，页映射 1:1。`ocrImage` 单张入口保留（`__gpuSelfRecognize` 钩子与兜底仍引用）。

### 改动 3：渲染 cap 下调

`var OC_CAP=1800;` → `var OC_CAP=1600;`（注释同步更新）。1600px 长边对名单表格（大字号）识别率无实质影响，det 输入随之从 \~1344 降至 \~1216，且 rec 行图变窄。

### 改动 4：readPdfText OCR 段改为"渲染/识别两阶段分块流水线"

将 L628–644 的混合流水（`mapLimit(ocrIdx, useOcr=3, 渲染→识别)`）替换为：

```js
var REND_CONC=6, REC_CONC=2, OCR_CHUNK=8; // 渲染 6-8 并发；识别 2-3 并发；分块控内存
var done=0;
for(var ci=0; ci<ocrIdx.length; ci+=OCR_CHUNK){
  var chunk=ocrIdx.slice(ci, ci+OCR_CHUNK);
  // 阶段 A：高并发批量渲染（CPU 密集，pdf.js 多 worker 并行）
  var canvases=await mapLimit(chunk, REND_CONC, function(pg){
    return renderPageToCanvas(pgObjs[pg-1],2).catch(function(){ return null; });
  });
  var valid=[], pages=[];
  canvases.forEach(function(c,i){ if(c){ valid.push(c); pages.push(chunk[i]); } });
  // 阶段 B：批识别（GPU 优先；整体失败则全部走内置池）
  var texts=null;
  var wantGpuB=!($('eng')&&$('eng').value==='tess') && !!window.__GPU_OCR_ENABLED__;
  if(valid.length && wantGpuB){ texts=await gpuRecognizeBatch(valid, REC_CONC); }
  if(valid.length && !texts){ texts=await ocrImageTessBatch(valid); }
  // 回填文本 + 进度：每页恰一步（含渲染失败页），done 不溢出 total；GPU 空文本/异常项逐个回退内置
  for(var k=0;k<chunk.length;k++){
    var ti=valid.indexOf(canvases[k]);
    var t = (ti>=0 && texts && texts[ti]) ? texts[ti] : '';
    if(ti>=0 && (!texts||!texts[ti])) t=await ocrImageTess(canvases[ti]).catch(function(){ return ''; });
    outs[chunk[k]-1]=t||'';
    done++; if(ctl) ctl.step('第'+chunk[k]+'/'+n+'页·OCR ('+done+'/'+ocrIdx.length+')');
  }
  canvases=valid=null; // 块尾置空，依赖 GC
}
```

关键约束（保持现状语义）：每页恰好一次 `ctl.step`；渲染失败/GPU 空文本/GPU 异常 → 逐项回退 `ocrImageTess`；块尾释放画布引用控制内存峰值（约 58MB/块画布 + ImageData 拷贝峰值 150–200MB，低配机可将 `OCR_CHUNK` 调为 4）。

### 改动 5：缓存版本 +1

`var TEXT_CACHE_VER='v2';` → `var TEXT_CACHE_VER='v3';`（OCR 渲染/识别参数变化会改变识别结果，旧缓存必须失效；首次升级会全量重 OCR 一次，属预期，暖缓存路径随后恢复）。

### 改动 6：新增只读验证钩子

在 L599 附近追加：

```js
window.__gpuSvcInfo__=function(){ return gpuInit().then(function(s){
  return s? { ep:s.options.session&&s.options.session.executionProviders,
    det:s.options.detection&&{maxSideLength:s.options.detection.maxSideLength,minimumAreaThreshold:s.options.detection.minimumAreaThreshold},
    rec:s.options.recognition&&{mainThreadYieldMs:s.options.recognition.mainThreadYieldMs,recBatchSize:s.options.recognition.recBatchSize} } : null; });
};
window.__ocrPerf__={renderMs:0,ocrMs:0,pages:0,tessFallbacks:0};
```

`__ocrPerf__` 在改动 4 的阶段 A/B 处累加 `Date.now()` 差值，`tessFallbacks` 在回退处 +1。不改变任何行为，供 Playwright 断言。

### 改动 7：修复"未找到"分支未恢复 runBtn（原版缺陷）

`if(matched.length===0){ …; return; }` → 增加 `$('runBtn').disabled=false;`。原版该分支直接 return，按钮停留在禁用态；A/B 暖缓存二次运行会卡死。

### 改动 8：缓存层自愈加固

背景：若浏览器中已存在结构损坏/旧版残留的 `bonus_text_cache`（缺 `t` 存储，如外部脚本用空 `onupgradeneeded` 提前建库），原 `cacheOpen`/`cacheGet` 会在 transaction 处抛 `NotFoundError`，使缓存 Promise 链拒绝并**静默短路 OCR**——用户只看到"未找到"，识别被吞。

* `cacheOpen` 的 `onsuccess` 检测库存在但缺 `t` 存储 → 本次会话禁用缓存（返回 `false`），OCR 照常执行并告警。
* `cacheGet` 对 transaction 异常兜底：丢弃坏连接（`_db=null`、`_ready=null`）并按未命中返回 `null` → 走解析，OCR 永不因缓存问题丢失。

### 改动 9（v3 稳定性加固）：真机 WebGPU 崩溃/无响应防御

背景：修复 EP 死配置后 WebGPU 真正生效，真机（Windows + NVIDIA 笔记本）暴露新的稳定性风险：① shader 首次编译长时间占用 GPU/主线程 → 页面"无响应"；② ORT WebGPU EP 与驱动组合存在 GPU 进程崩溃/挂起风险，崩溃时 Promise 永不 settle → `await` 永久挂起 → 按钮禁用、页面假死；③ 4GB 显存（RTX 2050）高并发下显存峰值超限 → 驱动重置 → GPU 进程崩溃。

加固（6 处子改动）：

* **9-A 全局兜底**：`window.addEventListener('unhandledrejection', …)` 捕获 GPU/ORT 相关异步异常 → 置 `__GPU_OCR_ENABLED__=false`、`gpuState=3`，提示"GPU 异常，已自动回退内置引擎"，防真机静默死锁/白屏无提示。
* **9-B 适配器超时**：新增 `withTimeout(p, ms, tag)` 工具（`Promise.race` + 定时器，任一 settle 即清理）；`requestAdapter` 5s 超时，防驱动枚举挂起。
* **9-C 初始化超时**：`svc.initialize()`（模型加载 + 首次编译）30s 超时，超时抛错走内置回退。
* **9-D 单张推理超时**：`svc.recognize` 90s 超时；失败置 `gpuState=3`、`gpu=null`、`__GPU_OCR_ENABLED__=false` 并返回 `null`。
* **9-E 批推理超时**：`batchRecognize` 整批 90s 超时；首次推理前提示"GPU 首次编译着色器，可能需数秒…"；超时/崩溃置 `gpuState=3` 回退内置——否则后续每块都会重复挂起 90s，页面表现为长期"无响应"。
* **9-F 降并发**：`REND_CONC 6→3`、`REC_CONC 2→1`、`OCR_CHUNK 8→6`（REC_CONC=1 时 batch 内动态批仍合并 4 线，吞吐损失有限）。

配套：`gpuState=3` 后 `gpuInit()` 直接返回 `null`，本次会话不再触碰 GPU，避免反复挂起；新增诊断钩子 `window.__gpuTimeline__` 记录 `adapter/init/rec` 各节点时间戳，真机异常时可在控制台 `copy(__gpuTimeline__)` 定位挂起点。

### 改动 10（v3 稳定性加固·续）：GPU 会话冲突检测 + 全局推理互斥

背景（真机日志佐证）：用户贴出控制台错误 `Error during model inference: Session already started` 与 `Error during text detection: Session already started`。排查确认故障链：

* ORT 会话不允许并发 `run()`（报 `Session already started`）。
* 引擎内部 det/rec 的 catch **吞掉该错误并返回空结果**（`detector.run` 返回 `[]`、`recognitor.run` 返回 `[]`），`recognize` 正常 resolve 空文本 → `batchRecognize(settle:true)` **永不 reject** → 工具层完全感知不到 GPU 已状态错乱。
* 于是工具继续用坏会话跑后续每一块：每块 det/rec 全失败、逐张回退内置 Tesseract，页面长时间"看似在跑实则全废"，GPU 队列持续积压可升级为 GPU 进程崩溃/浏览器无响应。

加固（4 处子改动）：

* **10-A 全局互斥链**：`gpuChain` + `gpuEnqueue(fn)`——所有 GPU 推理入 promise 链，任何时刻至多一个 `session.run` 在途（防钩子/重复触发/未来路径并发）；统一禁用入口 `gpuDisable(reason)` 置 `gpuState=3` 并提示。
* **10-B 批内失败检测**：`gpuRecognizeBatch` 解析 settle 结果——`rejected>0` 或批全空 → 立即 `gpuDisable`；批 ≥4 张时空文本率连续 2 块 >70% → `gpuDisable`。避免坏会话被静默复用。
* **10-C 单张互斥**：`gpuRecognize` 同样入链（防 `__gpuSelfRecognize` 等手动调用与批识别并发 run 同一会话）。
* **10-D file:// 提示**：`location.protocol==='file:'` 时状态区提示"建议本地服务打开"（Chrome/Edge 对 file:// 禁 worker/blob，pdf.js 退化为主线程 fake worker、Tesseract worker 加载受限）。

## 构建与交付

1. **构建脚本**（中间产物，不入 workspace）：`/data/user/work/build_ocr_v2.mjs`

   * 读源文件 → 按上述 10 处**锚点字符串精确替换**（每处断言恰好匹配 1 次，失败即退出）→ 写出交付文件。

   * 完整性校验：提取新旧 `gpuassets` 文本，比对 `ORT/MJS/WASM/DET/REC/DICT/PPU` 七键 base64 长度与 SHA-256 逐字节一致；输出新旧文件字节差（应仅为应用脚本增量）。
2. **交付物**（最终）：`搜分名单查询工具.html`（单文件、离线、不联网，原版保留不动）；分享包同步更新：`.trae-html-share-packages/搜分名单查询工具.zip`。
3. **本地服务启动器**（解决 file:// 限制）：`启动工具.cmd` + `serve_ocr.ps1`。把两个文件与 html 放同一文件夹双击运行，python 优先、无 python 时用 PowerShell TcpListener（无需管理员）。

## 验证方法（webapp-testing skill / Playwright A/B 基准）

### 环境

* 基准脚本（中间产物）：`/data/user/work/ocr_ab_bench.py`，`sync_playwright` + Chromium headless；WebGPU 用 `--enable-unsafe-swiftshader`（软件 WebGPU，绝对耗时偏慢但相对对比有效，最终以用户真机复测为准）。

* 服务方式：用 skill 的 `scripts/with_server.py` 起静态服务（WebGPU 需安全上下文、IndexedDB 在 `file://` 下不稳），访问 `http://127.0.0.1:<port>/…`；交付物本身仍为离线单文件。

* 样本：从 497 个 PDF 选 10–20 个（约 40–120 页）覆盖清晰印刷/模糊扫描/表格/手写批注/低对比度；先单 PDF 冒烟。

### 单轮流程

1. 断言配置生效：新版 `__gpuSvcInfo__()` 返回 `ep=['webgpu','wasm']`、`rec.mainThreadYieldMs=0`、`det.maxSideLength=960`；旧版应显示 `ep=['cpu']`（证实死配置缺陷）。断言失败则该轮作废。
2. 冷缓存基线：删除 IndexedDB `bonus_text_cache` → reload → 预热 `__gpuSelfTest()`（初始化不计时）→ 上传样本 → 勾选"识别扫描件" → 输入关键词 → 点运行 → 轮询 `#bar` 隐藏且 `#resultCard` 可见 → 记录总耗时。
3. 采集指标：`window.matched`（命中记录集）、`textCache.stats`（命中/新解析）、`__ocrPerf__`（renderMs/ocrMs/fallbacks）、`__gpuSvcInfo__`、控制台日志（`Using user-provided executionProviders: ["webgpu","wasm"]` 即 EP 生效佐证）。
4. 每版冷缓存跑 3 次取中位数，再各跑 1 次暖缓存验证 v3 缓存命中路径。

### 判定规则

* **命中一致性（首要）**：新版命中三元组 `(activityKey(name), score, serial)` 集合必须包含旧版集合（允许新增、不容缺失）。

* **耗时达标**：冷缓存中位总耗时 `T_new < 0.6 × T_old` 为目标（≥40% 提速）；`0.6–0.8` 为部分达标并记录分项；`>0.8` 检查 EP 是否真生效、`REC_CONC` 调 3、`REND_CONC` 调 8。

* **回退档位**（仅当命中集缺失时启用）：`(maxSideLength, minimumAreaThreshold)` 依次 `(960,12) → (1088,14) → (1216,16) → auto/OC_CAP1600`，取命中不缺失前提下最快档。

* 输出基准报告：`docs/maintainer/ocr_ab_bench_report.md`（两版配置、耗时对比表、命中集 diff、缓存统计、GPU/EP 信息、结论与推荐档位）。

## 假设与决策

| 决策                                  | 值                   | 理由                                               |
| ----------------------------------- | ------------------- | ------------------------------------------------ |
| session EP 修复                       | `['webgpu','wasm']` | 让 WebGPU 真正生效（最大提速来源），失败自动回退 wasm                |
| mainThreadYieldMs                   | 0                   | 去掉每 rec 批前 10ms 让出；收益 = 10ms × 每页批次数             |
| det maxSideLength                   | 960                 | PP-OCR 官方移动端标准；det 计算量约降 50%                     |
| det minimumAreaThreshold            | 12（原 20）            | 补偿 0.51 倍缩放空间下小框面积缩水，防漏检                         |
| OC\_CAP                             | 1600（原 1800）        | 表格大字号场景识别率无实质影响，rec 行图变窄                         |
| REND\_CONC / REC\_CONC / OCR\_CHUNK | 6 / 2 / 8           | 渲染 CPU 并行最大化；GPU 队列串行下 2–3 让 CPU 预处理重叠；分块控内存     |
| TEXT\_CACHE\_VER                    | v3                  | 识别参数变化致结果可能不同，旧缓存失效（首次全量重 OCR 属预期）               |
| Tesseract OCR\_CONC                 | 不变（min(2,hc-1)）     | 回退路径，内存敏感，本轮不动                                   |
| 解析/去重逻辑                             | 禁止改动                | `parseOccurrences`、`activityKey`、`dedupe` 与本优化无关 |

## 实施顺序

1. 编写 `build_ocr_v2.mjs`（构建脚本，锚点替换 + 资产校验）
2. 生成 v2 交付物，跑资产完整性校验（七键 SHA-256 一致）
3. 单 PDF 冒烟：引擎状态、批路径无报错、`__gpuSvcInfo__` 断言通过
4. 编写 `ocr_ab_bench.py`（A/B 基准脚本）
5. 旧版/新版 A/B（冷/暖缓存各测）
6. 命中一致性判定 + 回退决策（如需）
7. 输出基准报告
8. 用户真机复测确认后定版交付

## 验证步骤清单（Verification）

* [ ] 构建脚本 6 处锚点均"恰好匹配 1 次"替换成功，无残留旧代码

* [ ] 新旧文件 `gpuassets` 七键 base64 长度 + SHA-256 逐字节一致（模型零改动）

* [ ] 单 PDF 冒烟：勾选 OCR 后正常出结果，`__gpuSvcInfo__()` 断言 `ep=['webgpu','wasm']`、`mainThreadYieldMs=0`、`maxSideLength=960`

* [ ] 新版命中集 ⊇ 旧版命中集（无缺失）

* [ ] 冷缓存中位耗时 `T_new < 0.6 × T_old`（≥40% 提速）

* [ ] 暖缓存二次运行接近瞬时（缓存路径正常）

* [ ] 基准报告输出至 `docs/maintainer/ocr_ab_bench_report.md`

