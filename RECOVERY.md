# 项目灾难恢复：在全新电脑重建环境

目标是原电脑损毁后，使用项目源码，在联网的 Windows 11 x64 电脑上重新安装依赖并运行项目。恢复措施位于项目目录，客户端没有新增备份页面、按钮或浏览器资料同步功能。

当前本地版本为 v0.1.7，保存原 8070 与原生 VNC 两套源码。原生 VNC 的运行目录原先被 Git 忽略，现另存到 [native_vnc_source](native_vnc_source/README.md)。恢复本地 v0.1.7 标签后，准备根目录依赖，再按该目录说明恢复开发版。本次恢复点没有推送 GitHub，远端 ZIP 不包含本次本地存档。

## 1. 下载项目

从 GitHub 下载最新分支 ZIP，完整解压到普通可写目录，例如 `C:\qunkong`。不要在压缩包预览窗口中运行。无需安装 Git；ZIP 不包含提交历史，需要历史记录时再使用 Git 克隆仓库。

## 2. 安装环境

在项目根目录打开 PowerShell：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Install.ps1
```

可用`Install.ps1 -Start`在安装完成后直接启动后台，合并为一次命令。首次系统软件安装、UAC和手机信任仍可能需要人工确认。

安装脚本会检测或安装：

- Python 3.13 x64，创建项目自己的 `.venv`。
- Node.js 24 或更新版本，用于打开 ChatGPT 并填入资料的本机助手。
- Apple 移动设备驱动：已有服务时复用，否则通过 Apple iTunes 安装包准备。
- `requirements-windows.lock.txt` 中的完整固定版本 Python 依赖，当前设备通信依赖为pymobiledevice3 11.49.5。

完成后运行 `pip check` 和环境检测。安装需要网络和软件安装权限，Windows UAC 或首次安装许可可能需要人工确认。安装失败会停止，修正后可重试。驱动安装可能需要重启电脑。

如果系统没有 `winget`，先安装微软 [App Installer](https://apps.microsoft.com/detail/9nblggh4nns1)，再运行脚本。安装参数依据微软 [WinGet 安装说明](https://learn.microsoft.com/en-us/windows/package-manager/winget/install)。依赖从软件供应方和 Python 包源下载，本仓库不包含 Windows 镜像或离线软件安装包。

Python 补丁版本可能与原机不同；固定的是 Python 3.13 x64 和锁定依赖。原机 Node 为 24.19.0，要求主版本至少 24。Windows ARM、macOS、Linux 未验证。

可选参数：`-SkipAppleDriver` 用于暂时只运行无手机界面；`-SkipSystemInstall` 只复用已安装的系统软件，但仍安装项目 Python 依赖。正常新电脑请不加这些参数。

## 3. 启动项目

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Start.ps1
```

安装并授权兼容的授权客户端，从其“苹果”入口进入`http://127.0.0.1:8070/`。普通浏览器直接打开将被拒绝；预览界面也受同一访问校验保护。

原手机通过 USB 接入，解锁并信任新电脑，按设备要求确认开发者模式。接入后重新启动工作台加载设备。开发者镜像、手机服务准备和连通性检查见 [SINGLE_DEVICE.md](iphone_batch/SINGLE_DEVICE.md)。安装、检查和启动脚本均不会自动发送短信。

## 4. 重新配置本机凭据

工作台当前保持原文模式；翻译配置由授权客户端负责，不要求给8070重新配置旧翻译密钥。授权客户端需要重新安装和授权；使用ChatGPT助手时需要重新登录。手机与新电脑的信任和配对也需重新建立。这些人工授权不能由GitHub代码代替。

工作台与授权客户端在同一Windows用户下使用本机新生成的共享签名凭据。该凭据不进入Git，也不从旧电脑复制。另一客户端的完整源码和安装包不包含在本仓库中，接口模板见`tools/bridge-client/workspace-access.ts`。

本方案恢复的是项目代码、素材、依赖和运行环境，不恢复客户端历史业务数据：已保存短信、回复记录、浏览器里的编号/备注/待跟进标记、Cookies、原机登录状态均不包含在仓库中。手机本身的数据仍由手机保存。

## 检查与演练记录

```powershell
.\.venv\Scripts\python.exe tools\environment_check.py
```

环境检测只读，不连接手机或调用付费 API，输出不包含密钥。驱动服务或配置文件“存在”不等于手机已经信任或 API 可用。

本机早期已创建独立目录及全新虚拟环境进行依赖重装演练；实际结果见 [VALIDATION.md](recovery/VALIDATION.md)。本机演练复用操作系统、Python/Node安装和苹果驱动，不能等同于一台未安装过软件的新电脑验证。11.49.5已在当前电脑升级并通过295项模拟回归、依赖检查及6台实际出帧核对，尚未在全新Windows电脑完整演练首次安装。首次使用仍应核对系统安装、授权客户端入口及真机投屏、读取、发送是否正常。
