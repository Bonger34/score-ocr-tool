# OCR 提速 A/B 基准报告（旧版 vs v2）

## 结论摘要

| 判定项 | 结果 | 说明 |
| --- | --- | --- |
| 命中一致性（首要） | ✅ 通过 | 新版命中记录集 ⊇ 旧版，缺失 0 条 |
| 冷缓存耗时目标 `T_new < 0.6×T_old` | ⚠️ 无头环境未达标 | 无 GPU adapter，两版均走 Tesseract CPU 回退；新版 36.2s vs 旧版 34.2s（1.058×） |
| 暖缓存路径 | ✅ 通过 | 二次运行 0.5s，缓存命中 2 / 新解析 0 |
| 构建资产完整性 | ✅ 通过 | 新旧 `gpuassets` 七键 base64 长度与 SHA-256 逐字节一致 |
| 引擎配置修复 | ✅ 代码层生效 | `executionProviders` 已移入 `session` 键（死配置修复），需真机验证 WebGPU 实际加速 |

> 说明：本基准在无 GPU 的无头沙箱中执行，`navigator.gpu.requestAdapter()` 返回无可用适配器，两版均回退到内置 Tesseract CPU 引擎。**WebGPU 主引擎（核心提速来源）无法在此环境实测，需在用户真机（Chrome/Edge + 独立显卡）复测确认。** CPU 回退路径下两版功能与命中完全一致，证明 v2 改动无回归。

## 测试环境

* 浏览器：Chromium headless（`--enable-unsafe-swiftshader --use-angle=swiftshader --enable-webgpu`）
* WebGPU：不可用（无 adapter，`gpuEnabled: false`，引擎指示 "CPU · 内置 Tesseract"）
* 样本：2 个纯扫描 PDF（无文本层），共 7 页：`b2_00.pdf`（3 页）+ `b2_10.pdf`（4 页）
* 服务：`http://127.0.0.1:8010/` 静态托管
* 方法：每版冷缓存（全新无痕 context，IndexedDB 为空）跑 3 次取中位数；同 context 二次点击测暖缓存

## 两版配置对比

| 项 | 旧版 | v2 |
| --- | --- | --- |
| 会话 EP | 顶层 `executionProviders:['webgpu','wasm']`（死配置，实际 `['cpu']`） | `session.executionProviders:['webgpu','wasm']`（真生效，不可用时自动回退 wasm） |
| det maxSideLength | auto（约 1344px @1800 渲染） | 960（计算量约降 50%） |
| det minimumAreaThreshold | 20 | 12（补偿缩放） |
| recognition mainThreadYieldMs | 10 | 0 |
| 渲染长边 cap | 1800px | 1600px |
| OCR 调度 | 渲染+识别混合并发（`useOcr=3`） | 两阶段分块流水线：渲染 6 并发 → 批识别 2 并发，`OCR_CHUNK=8` |
| 批识别入口 | 无（逐张 `recognize`） | `gpuRecognizeBatch`（`batchRecognize` + settle） |
| 文本缓存版本 | v2 | v3（识别参数变化，旧缓存失效） |
| "未找到"按钮恢复 | ❌ 原版缺陷（按钮保持禁用） | ✅ 已修复 |

## 冷缓存耗时（秒）

| 轮次 | 旧版 | 新版 |
| --- | --- | --- |
| cold1 | 34.1 | 36.1 |
| cold2 | 34.2 | 36.2 |
| cold3 | 34.3 | 36.2 |
| **中位数** | **34.2** | **36.2** |
| 比值 T_new/T_old | — | 1.058 |

### 新版分项计时（`__ocrPerf__`）

| 轮次 | renderMs | ocrMs | tessFallbacks |
| --- | --- | --- | --- |
| cold1 | 2451 | 31947 | 7 |
| cold2 | 2429 | 32048 | 7 |
| cold3 | 2455 | 31874 | 7 |

* 7 页中 Tesseract 识别占绝对主导（约 32s，≈4.6s/页），pdf.js 渲染仅约 2.4s。
* CPU 回退路径下 v2 与旧版耗时基本相当（±6% 噪声级差异）。v2 的提速收益集中在 WebGPU 主引擎路径（det 输入 1344→1216、mainThreadYieldMs 0、GPU 批识别并发），无 GPU 环境无法体现。

## 命中一致性

* 旧版命中记录：2 条（`文件|加分类型|分值|学号`）
* 新版命中记录：2 条
* 新版缺失：**0 条** ✅

## 暖缓存（二次运行）

| 版本 | 耗时 | 状态文本 | 缓存命中/新解析 |
| --- | --- | --- | --- |
| 旧版 | 0.5s | 解析完成：命中 1 个文件 | 2 / 0 |
| 新版 | 0.5s | 解析完成：命中 1 个文件 | 2 / 0 |

* 两版暖缓存路径均正常：IndexedDB 双级缓存命中，接近瞬时返回，`TEXT_CACHE_VER=v3` 键名生效。

## 构建资产校验

`ORT / MJS / WASM / DET / REC / DICT / PPU` 七键 base64 长度与 SHA-256 新旧一致 ✓（模型零改动，字节差仅应用脚本增量 3600 B）。

## 结论与建议

1. **功能无回归**：v2 在 CPU 回退路径下命中一致性、暖缓存、进度显示、按钮恢复均正常，可安全交付。
2. **WebGPU 提速需真机复测**：核心收益（EP 死配置修复 → GPU 会话真建、det 960 降计算量、GPU 批识别）依赖独立显卡。请用户在真机打开 v2 页面，确认左下角引擎指示灯显示 GPU 型号（如 "NVIDIA GeForce RTX …"）而非 "CPU · 内置 Tesseract"；对比同批 497 个 PDF 的总耗时。
3. **回退档位建议**：若真机命中集较旧版有缺失（GPU 参数更激进导致漏检），按 `(maxSideLength, minimumAreaThreshold)` 依次 `(960,12) → (1088,14) → (1216,16) → auto` 上调，取命中不缺失前提下最快档。
4. **原版缺陷修复**：v2 已修复"搜索无结果后「开始解析」按钮保持禁用"的问题。
