# `.tools/` —— 源码、构建与校验

这个目录是项目真正的源码所在。**成品 HTML 不手工编辑**，一律由这里的脚本从基线生成。

## 目录

```
.tools/
├── ui/                     ← 手写的界面源码（日常只改这里）
│   ├── style.css           整站样式
│   ├── body.html           页面标记
│   ├── render.js           检索结果渲染（台账 + 明细清单）
│   ├── export.js           Excel 导出（加分证明清单 / 五育汇总）
│   ├── zip.js              材料包导出（学号姓名/五育测评/+分值 (事由)）
│   └── specimen.html       视觉样张（历史留档，非运行时代码）
├── demo/ui_demo.html       ← 合成数据 UI 预览页（可截图、可给贡献者看效果）
├── build_v25_ui.py         ← 唯一构建入口
├── build_v24.py            历史：往更早的基线上注入模型（需 ONNX 资产，仓库未含）
├── render_unit.js          Node 单测（27 项，无需浏览器）
├── launcher_check.py       启动器编码自检（.cmd 纯 ASCII / .ps1 带 BOM）
├── syntax_check.py         成品 JS 语法检查
├── ui_static_check.py      成品静态结构断言（38 项）
├── ui_regress.py           与 v2.4 基线的行为回归
├── ui_contrast.py          配色对比度（WCAG 2.1，25 项）
├── ui_a11y.py              无障碍专项（键盘可达、焦点、语义，11 项）
├── ui_barsync.py           进度条宽度与百分比逐帧一致
├── ui_shot.py              浏览器实跑：截图 + Excel/材料包真实下载校验
├── ui_zipcheck.py          材料包字节级校验（与源文件逐字节比对）
├── ui_pii_check.py         成品隐私自检：不得出现真实姓名 / 学号
├── ui_pii_scan.py          成品格式类隐私扫描：本机路径 / 邮箱 / 手机号 / 身份证
├── publish_check.py        发布门禁：扫描将要提交的文件
├── shot_demo.py            给 README 出图（截合成数据预览页，无 PII）
└── rebuild_share_zip.py    重新打包分享 zip
```

## 构建

```bash
python .tools/build_v25_ui.py
```

构建脚本只做三件事，全部**幂等**——反复执行结果一致：

1. 用 `ui/` 里的源码**整块替换**基线 HTML 的 `<style>`、body 标记、`render()`、
   进度引擎、Excel 导出块；
2. 对 33 处精确锚点做 `count == 1` 断言，命中数不对就报错退出；
3. 把 5 处示例姓名匿名化（正则锚点，对未匿名与已匿名基线都成立）。

**基线**：`v24_ui_baseline.html`（约 42 MB）。它是**构建输入，不是成品**——里面装着
应用内核（`parseOccurrences` / `gpuRecognize` / `onFiles` / `activityKey` 等）与内嵌的
OCR 模型、第三方库；构建时它的旧界面会被整块替换掉，其余部分继承并打补丁。

它随仓库提供（`.gitattributes` 里标为 `binary`），clone 下来即可构建，无需额外下载。
注意它本身是一个**旧版界面**，双击能打开——但那是 v2.4 的界面，别拿它当成品用。

期望产物（v2.8）：

```
size   44120092
sha256 0e7c105baca9b3702e008ed8c06e573e40eed913e5d29f53e4a1cd840440dc24
```

对外的基线已做过匿名化，可自行复算：

```bash
python .tools/build_v25_ui.py --sanitize-baseline   # 幂等；对已匿名基线是空操作
```

## 校验

| 脚本 | 依赖 | 说明 |
|---|---|---|
| `render_unit.js` | Node | 27 项渲染单测，含德育 > 25 / 智育 > 10 / 负分 / 无学号等真机跑不出的分支 |
| `syntax_check.py` | Python | 成品内嵌 JS 语法检查 |
| `ui_static_check.py` | Python | 38 项静态结构断言 |
| `ui_contrast.py` | Python | 直接读 `ui/style.css` 算对比度，25 项 |
| `ui_pii_scan.py` | Python | 成品里本机路径 / 邮箱 / 手机号 / 身份证 |
| `launcher_check.py` | Python | 启动器编码约束（见下方「约定」） |
| `ui_pii_check.py` | Python + 语料 | 成品里真实姓名 / 学号（需 `--corpus` 指到本地语料） |
| `publish_check.py` | Python + 语料 | **发布门禁**：扫描将要提交到 git 的文件 |
| `ui_a11y.py` | 浏览器 | 需本地服务 `127.0.0.1:18010` |
| `ui_barsync.py` | 浏览器 | 同上 |
| `ui_shot.py` | 浏览器 + 语料 | 同上，且需要 `target/` 下的真实语料 |
| `ui_regress.py` | 浏览器 + 语料 | 同上 |
| `ui_zipcheck.py` | 浏览器 + 语料 | 同上 |

浏览器类脚本用 Playwright（`pip install playwright && playwright install chrome`），
先起本地服务：

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

真值（真实姓名 / 学号）从本机语料抽取并缓存在 `.tools/pii_truth.json`——
**该缓存含真实姓名，已被 `.gitignore` 排除，禁止提交**。
公开仓库里没有语料，这个脚本只能做格式类检查，这是有意的设计。

## 约定

- 目录名 `.tools` 被 80 多个脚本硬编码引用，**不要重命名**
- 不要手工编辑 44 MB 成品 HTML——改 `ui/` 后重新构建
- 新增校验脚本请用 `BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))`
  推导路径，不要写死本机绝对路径
- 新增源码若含示例姓名/学号，用"某姓名 / AB / C / 2024000001"这类占位
- **启动器（v2.10 起只有一个）**：
  - `直接打开页面.cmd` 直接用 `file://` 打开成品并强制独显，不起服务、不占端口、不留后台进程。
    实测 `file://` 与 `http://` 功能等价（pdf.js worker、Tesseract 回退、IndexedDB、导出均可用），
    因此 v2.10 删掉了原来的服务类启动器 `启动本地服务.cmd` 与 `本地服务_无Python.ps1`。
  - 历史教训留档：v2.8 曾用 `start /min` 把服务甩到后台，窗口一关提示就没了、服务却继续常驻，
    用户根本不会发现（v2.9 改成前台窗口，v2.10 索性去掉服务）。
    **若将来重新引入服务类启动器，必须与窗口同生命周期，禁止 `start /min`。**
  - `*.cmd` 必须保持**纯 ASCII**——cmd.exe 按控制台代码页逐行解析批处理，
    中文字节会被当成双字节字符吞掉换行，导致后面整行代码失效；
    `.cmd` 里要引用中文名文件，用 `for %%f in ("%~dp0*.ps1") do set "PS=%%~fs"` 这类通配符发现。
  - `*.ps1`（若重新引入）必须带 **UTF-8 BOM**——Windows PowerShell 5.1 对无 BOM 文件按系统代码页（GBK）解析，
    中文注释会破坏语法，脚本直接报 `Unexpected token`。
