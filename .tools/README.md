# `.tools/` —— 源码、构建与校验

这个目录是项目真正的源码所在。**成品 HTML 不手工编辑**,一律由 `.tools/build.py`
按固定顺序拼接生成。

## 目录

```
.tools/
├── build.py                ← 唯一构建入口（纯字节拼接，见下）
├── src/                    ← 手写源码（日常只改这里）
│   ├── template.html       约 1KB 骨架，含 9 个槽位占位符 @@SLOT:name@@
│   ├── app/                应用源码，16 个模块（见下表）
│   ├── style.css           整站样式
│   ├── body.html           页面标记
│   └── specimen.html       视觉样张（历史留档，非运行时代码）
├── assets/                 ← 构建资产（约 42MB，进 git）
│   ├── pdfworker.js  pdf.js  jszip.min.js  tesseract.min.js
│   ├── ocr-assets.js       window.__OCR_ASSETS__={CHI_B64:…}
│   └── gpuassets.txt       ORT|<base64>
├── history/                ← 已退役的一次性工具（本机留档，不进 git）
├── build_v24.py            历史：往更早的基线上注入模型（需 ONNX 资产，仓库未含）
├── demo/ui_demo.html       ← 合成数据 UI 预览页（可截图、可给贡献者看效果）
├── render_unit.js          Node 单测（27 项，无需浏览器）
├── launcher_check.py       启动器编码自检（.cmd 纯 ASCII / .ps1 带 BOM）
├── syntax_check.py         成品 JS 语法检查
├── ui_static_check.py      成品静态结构断言（38 项）
├── ui_contrast.py          配色对比度（WCAG 2.1，25 项）
├── ui_a11y.py              无障碍专项（键盘可达、焦点、语义，11 项）
├── ui_barsync.py           进度条宽度与百分比逐帧一致
├── ui_nbsp_check.py        状态行分隔符 NBSP 核对
├── ui_cssom.py             状态行 CSSOM 是否真正生效
├── ui_shot.py              浏览器实跑：截图 + Excel/材料包真实下载校验
├── ui_zipcheck.py          材料包字节级校验（与源文件逐字节比对）
├── ui_progcheck.py         进度 / 倒计时真机采样（需浏览器 + 本地服务）
├── prog_report.py          把采样 JSON 重算成统一指标表
├── ui_ocrcheck.py          端到端 OCR 验收（需自备扫描件）
├── verify_share.py         分享包内的 HTML 与工作区成品逐字节比对
├── ui_pii_check.py         成品隐私自检：不得出现真实姓名 / 学号
├── ui_pii_scan.py          成品格式类隐私扫描：本机路径 / 邮箱 / 手机号 / 身份证
├── publish_check.py        发布门禁：扫描将要提交的文件
├── shot_demo.py            给 README 出图（截合成数据预览页，无 PII）
├── rebuild_share_zip.py    重新打包分享 zip
├── extract_ppu.py          从成品解出 PPU 引擎源码（更新引擎时用）
├── extract_models.py       从成品解出 REC / DET / DICT 模型
├── extract_assets.py       从成品解出 ORT 运行时 JS
└── onnx_tool.py            极简 ONNX 读写（改造模型用）
```

## 应用模块(`src/app/`)

| 模块 | 职责 |
|---|---|
| `00-boot.js` | IIFE 开头与 `$` 工具 |
| `10-engine.js` | 引擎状态 / GPU 名称 / 界面同步 |
| `20-cache.js` | IndexedDB 文本缓存 |
| `30-files.js` | 文件接入 / 清空 |
| `40-parse.js` | `parseOccurrences` / `activityKey` / `ext` |
| `50-ocr-worker.js` | base64 工具 + OCR worker 池 |
| `60-gpu.js` | GPU 状态机与初始化 |
| `62-ppu-patch.js` | `patchPPU` + 批量识别 |
| `65-ocr-image.js` | 单页 OCR 图像 |
| `70-pdf.js` | pdf.js 取文 / 渲染 / xlsx |
| `75-concurrency.js` | `mapLimit` / `entryBytes` / `parseOne` |
| `80-progress.js` | 进度引擎 + 去重 / 类型判断 |
| `85-render.js` | 数值工具 + `render`(五育上限 `YU_CAP`、顺序 `YU`) |
| `90-export.js` | 导出「加分证明清单 / 五育汇总」两张表 |
| `95-material.js` | 材料包(`YU_DIR` 目录名、体积守卫) |
| `99-tail.js` | IIFE 收尾与全局挂载 |

**顺序即 IIFE 内部顺序**,由 `build.py` 的 `SOURCES` 清单唯一决定——新增/删除模块要同时改清单。

## 构建

```bash
python .tools/build.py
```

构建只做三件事,全部**幂等**——反复执行结果一致:

1. 按 `SOURCES` 顺序拼接 `src/app/*.js` → 应用块;
2. 把 9 个槽位(`style` / `body` / 6 个资产 / `app`)填进 `src/template.html`;
3. 断言产物 sha256 == 期望值,不符即报错退出——**绝不静默写出坏文件**。

期望产物:

```
size   44120082
sha256 55ad8f466eaa62d45d0e3446bb6b4b2617f387e0a87167ade879ec8e8d3c6db8
```

> 改界面 = 编辑 `src/` 下的对应文件;改逻辑 = 编辑 `src/app/` 下的对应模块。
> 构建脚本只在模块增删时才需要动。

## 校验

| 脚本 | 依赖 | 说明 |
|---|---|---|
| `render_unit.js` | Node | 27 项渲染单测,含德育 > 25 / 智育 > 10 / 负分 / 无学号等真机跑不出的分支 |
| `syntax_check.py` | Python | 成品内嵌 JS 语法检查 |
| `ui_static_check.py` | Python | 38 项静态结构断言 |
| `ui_contrast.py` | Python | 直接读 `src/style.css` 算对比度,25 项 |
| `ui_pii_scan.py` | Python | 成品里本机路径 / 邮箱 / 手机号 / 身份证 |
| `verify_share.py` | Python | 分享包内的 HTML 与工作区成品逐字节一致 |
| `ui_nbsp_check.py` | Python | 状态行分隔符 NBSP 核对 |
| `ui_cssom.py` | 浏览器 | 状态行 CSSOM 是否真正生效 |
| `ui_progcheck.py` | 浏览器 | 进度 / 倒计时真机采样 |
| `prog_report.py` | Python | 采样 JSON → 统一指标表 |
| `ui_ocrcheck.py` | 浏览器 + 语料 | 端到端 OCR 验收(需自备扫描件) |
| `launcher_check.py` | Python | 启动器编码约束(见下方「约定」) |
| `ui_pii_check.py` | Python + 语料 | 成品里真实姓名 / 学号(需 `--corpus` 指到本地语料) |
| `publish_check.py` | Python + 语料 | **发布门禁**:扫描将要提交到 git 的文件 |
| `ui_a11y.py` | 浏览器 | 需本地服务 `127.0.0.1:18010` |
| `ui_barsync.py` | 浏览器 | 同上 |
| `ui_shot.py` | 浏览器 + 语料 | 同上,且需要 `target/` 下的真实语料 |
| `ui_zipcheck.py` | 浏览器 + 语料 | 同上 |

浏览器类脚本用 Playwright(`pip install playwright && playwright install chrome`),
先起本地服务:

```bash
python -m http.server 18010 --bind 127.0.0.1
```

## 隐私门禁怎么用

```bash
# 最权威：扫 git 索引里真正要提交的文件
git add -A
python .tools/publish_check.py

# 未初始化 git 时按目录遍历（会扫到被 .gitignore 排除的数据目录，命中属预期）
python .tools/publish_check.py --walk
```

真值(真实姓名 / 学号)从本机语料抽取并缓存在 `.tools/pii_truth.json`——
**该缓存含真实姓名,已被 `.gitignore` 排除,禁止提交**。
公开仓库里没有语料,这个脚本只能做格式类检查,这是有意的设计。

`assets/` 里的第三方库会命中「本机绝对路径」这类误报(如 pdf.js 自带的 Node 路径检测正则),
因此该目录跳过格式类检查,但**姓名 / 学号照常检查**。

## 约定

- 目录名 `.tools` 被 80 多个脚本硬编码引用,**不要重命名**
- 不要手工编辑 44 MB 成品 HTML——改 `src/` 后重新构建
- **`src/app/` 的模块顺序不能随意调整**:拼接顺序即 IIFE 内部顺序,顺序一变产物 sha 就变
- 新增校验脚本请用 `BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))`
  推导路径,不要写死本机绝对路径
- 新增源码若含示例姓名/学号,用"某姓名 / AB / C / 2024000001"这类占位
- **启动器(v2.10 起只有一个)**:
  - `打开工具.cmd` 直接用 `file://` 打开成品并强制独显,不起服务、不占端口、不留后台进程。
    实测 `file://` 与 `http://` 功能等价(pdf.js worker、Tesseract 回退、IndexedDB、导出均可用),
    因此 v2.10 删掉了原来的服务类启动器 `启动本地服务.cmd` 与 `本地服务_无Python.ps1`。
  - 历史教训留档:v2.8 曾用 `start /min` 把服务甩到后台,窗口一关提示就没了、服务却继续常驻,
    用户根本不会发现(v2.9 改成前台窗口,v2.10 索性去掉服务)。
    **若将来重新引入服务类启动器,必须与窗口同生命周期,禁止 `start /min`。**
  - `*.cmd` 必须保持**纯 ASCII**——cmd.exe 按控制台代码页逐行解析批处理,
    中文字节会被当成双字节字符吞掉换行,导致后面整行代码失效;
    `.cmd` 里要引用中文名文件,用 `for %%f in ("%~dp0*.ps1") do set "PS=%%~fs"` 这类通配符发现。
  - `*.ps1`(若重新引入)必须带 **UTF-8 BOM**——Windows PowerShell 5.1 对无 BOM 文件按系统代码页(GBK)解析,
    中文注释会破坏语法,脚本直接报 `Unexpected token`。
