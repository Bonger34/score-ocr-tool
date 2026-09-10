# Handoff 交接文档：搜分名单查询工具 · 单文件离线 OCR（GPU v2）

## 任务背景

对单文件离线 HTML 工具（44MB 内嵌 Tesseract.js 回退引擎 + PP-OCRv4 WebGPU 主引擎）做纯 JS 层提速与稳定性加固，**不内嵌/替换任何模型资产**。核心目标是让 497 个扫描版 PDF（含中文字名单）的批量 OCR 更快且真机不崩溃。

## 交付物清单（均已就绪）

| 文件 | 路径 | 说明 |
|---|---|---|
| 最终单文件工具 | `搜分名单查询工具.html`（44,048,562 字节） | 已含改动 1-10 |
| 分享压缩包 | `.trae-html-share-packages/搜分名单查询工具.zip` | 已随最新版本同步 |
| Windows 启动器 | `启动工具.cmd` | 双击一键起本地服务（python 优先） |
| PowerShell 服务器 | `serve_ocr.ps1` | 无 python 时兜底，无需管理员 |
| 优化计划文档 | `docs/maintainer/提升OCR速度优化计划.md` | 记录全部 10 处改动与验证方法 |
| 源文件（不改） | `.archive/uploads_旧版交付物/c748896e-6e8a-4b5d-8bb1-6a150fcecba2_搜分名单查询工具_单文件离线版_GPU.html` | 原始交付 |
| 构建脚本（中间产物） | `/data/user/work/build_ocr_v2.mjs` | 锚点精确替换生成交付物 |
| PPU 引擎源码（只读分析） | `/data/user/work/ppu_engine.js` | 定位引擎行为用 |
| 冒烟测试 | `/data/user/work/smoke_test.py` | 无头全链路校验（默认走 Tesseract 回退，PASS） |

## 已完成的改动（详见计划文档，勿重复撰写）

- **改动 1**：修复 `executionProviders` 死配置——EP 必须放 `session.executionProviders` 键下才会被读取（原实现实际以 `['cpu']` 建会话，WebGPU 从未启用）。这是最大提速来源。
- **改动 2-4**：批识别入口 `gpuRecognizeBatch`/`ocrImageTessBatch`；渲染 cap 1800→1600；流水线分阶段 A/B 并行 + 过程提示。
- **改动 5**：缓存版本 `v2`→`v3`。
- **改动 6-7**：性能/基准钩子 `__ocrPerf__`；修复"未找到"分支未恢复 runBtn 的原版缺陷。
- **改动 8**：缓存层自愈——缺 store/事务异常时禁用缓存并放行 OCR，防止缓存损坏静默短路识别。
- **改动 9（真机加固）**：全局 `unhandledrejection` 兜底；`requestAdapter` 5s / 初始化 30s / 推理 90s 三级超时（`withTimeout`）；初次 shader 编译提示；降并发 `REND_CONC 6→3`、`REC_CONC 2→1`、`OCR_CHUNK 8→6` 护 4GB 显存；诊断钩子 `window.__gpuTimeline__`。
- **改动 10（会话冲突加固，本次核心新增）**：真机日志出现 `Session already started`。根因——ORT 会话并发 `run()`，且引擎内部 catch 会**吞掉该错误返回空结果**，`batchRecognize(settle:true)` 永不 reject，工具层感知不到、继续用坏会话跑后续每一块（表现为"看似在跑实则全废"+ 崩溃风险）。修复：全局互斥链 `gpuChain`/`gpuEnqueue`（任何时刻至多一个 `session.run` 在途）+ `gpuDisable(reason)` 统一禁用入口 + 批内失败检测（rejected>0 / 批全空 / 连续 2 块空文本率>70% 即永久回退内置）+ file:// 运行提示。

## 构建流程（重要）

```bash
cd /data/user/work && node build_ocr_v2.mjs
```

- 每次改动先在此脚本追加 `rep(...)` 锚点替换（断言每处恰好匹配 1 次，失败即退出），再重建。
- 脚本内置资产完整性校验：七键 `ORT/MJS/WASM/DET/REC/DICT/PPU` 的 base64 长度与 SHA-256 逐字节一致。
- 修改交付物后必须重新 `zip` 覆盖 `.trae-html-share-packages/` 下分享包（zip 用 `-j` 仅收纳 html）。

## 尚未验证 / 待办

1. **真机复测（最高优先级）**：用户是 RTX 2050（4GB 显存）+ Windows，之前直接双击 file:// 打开导致 worker/blob 受限。须让用户用启动器（或本地 http）打开 → Ctrl+F5 强刷 → 重跑同一批扫描件，确认 GPU 路径不再报 `Session already started`、页面不崩溃、速度达成。
2. 若无头环境全链路已 PASS，但**真机 GPU 路径的 A/B 基准尚未重跑**——改动 10 的互斥链串行化后，GPU 并发吞吐可能略降（REC_CONC 本就 1，det/rec 交替），需在真机量化是否可接受。
3. 若真机仍崩：收集 `window.__gpuTimeline__` + `window.__ocrPerf__` + `performance.getEntries()`，据此定位挂起点。

## 文件打开方式（对用户说明）

- 优先：把 `启动工具.cmd` 和 `serve_ocr.ps1` 与 html 放同一文件夹，双击 `启动工具.cmd`（python 优先，无 python 自动用 PowerShell TcpListener，无需管理员）。
- 避免直接双击 html（Chrome/Edge 对 file:// 禁 worker/blob，pdf.js 退化 fake worker、Tesseract worker 受限，会变慢变卡）。

## Suggested Skills

下一会话（续做真机复测/优化）建议调用以下技能：

- `webapp-testing`：用 Playwright 对本地 http 服务做 GPU 路径的 A/B 基准与崩溃回归。
- `html-report`（如需生成最新基准报告）：产出可视化性能对比页。
- `research-guide`（如需调研 ORT WebGPU session 并发/崩溃官方 issue 与规避）。

## 安全注意事项

无 API 密钥/口令。文档与交付物可安全共享。涉及真机个人信息（学号名单）仅存在于用户本地样本 PDF，交接文档不含任何人信息。