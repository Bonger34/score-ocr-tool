## 搜分名单查询工具 v2.11

**启动器更名为 `打开工具.cmd`**，内容不变。

v2.10 把入口收敛成一个之后，「直接打开页面」里的「直接」已经没有对比对象了，
名字改成一目了然的直白说法：解压后看到 HTML 和它，双击即可。

- `直接打开页面.cmd` → `打开工具.cmd`（仍是 `file://` 打开 + `--force_high_performance_gpu` 强制独显，
  不起服务、不占端口、不留后台进程）
- 成品里的 `file://` 状态提示同步更新为「想用独显请双击 打开工具.cmd」

### 附件说明

本 Release 只有**一个附件** `score-ocr-tool.zip`（约 28 MB；显示名「搜分名单查询工具.zip」），
解压后包含：

| 文件 | 用途 |
|---|---|
| `搜分名单查询工具.html` | 成品，双击即用；OCR 模型与第三方库全部内嵌 |
| `打开工具.cmd` | 唯一启动器：用 `--force_high_performance_gpu` 打开，让 WebGPU 走独显 |

> 直接双击 HTML 也能用，只是浏览器会自选 GPU（双显卡笔记本上通常是核显）。
> 构建底座 `.tools/v24_ui_baseline.html` **不在本 Release 里**——它随源码仓库提供。

### 校验

成品大小与哈希：

```
size   44120082
sha256 55ad8f466eaa62d45d0e3446bb6b4b2617f387e0a87167ade879ec8e8d3c6db8
```

PowerShell 核对：

```powershell
(Get-FileHash '搜分名单查询工具.html' -Algorithm SHA256).Hash.ToLower()
```
