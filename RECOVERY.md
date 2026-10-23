# 项目灾难恢复：在全新电脑重建环境

目标是原电脑损毁后，使用 GitHub 下载的项目 ZIP，在联网的 Windows 11 x64 电脑上重新安装依赖并运行项目。恢复措施位于项目目录，客户端没有新增备份页面、按钮或浏览器资料同步功能。

## 1. 下载项目

从 GitHub 下载最新分支 ZIP，完整解压到普通可写目录，例如 `C:\qunkong`。不要在压缩包预览窗口中运行。无需安装 Git；ZIP 不包含提交历史，需要历史记录时再使用 Git 克隆仓库。

## 2. 安装环境

在项目根目录打开 PowerShell：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Install.ps1
```

安装脚本会检测或安装：

- Python 3.13 x64，创建项目自己的 `.venv`。
- Node.js 24 或更新版本，用于打开 ChatGPT 并填入资料的本机助手。
- Apple 移动设备驱动：已有服务时复用，否则通过 Apple iTunes 安装包准备。
- `requirements-windows.lock.txt` 中的 118 项固定版本 Python 依赖。

完成后运行 `pip check` 和环境检测。安装需要网络和软件安装权限，Windows UAC 或首次安装许可可能需要人工确认。安装失败会停止，修正后可重试。驱动安装可能需要重启电脑。

如果系统没有 `winget`，先安装微软 [App Installer](https://apps.microsoft.com/detail/9nblggh4nns1)，再运行脚本。安装参数依据微软 [WinGet 安装说明](https://learn.microsoft.com/en-us/windows/package-manager/winget/install)。依赖从软件供应方和 Python 包源下载，本仓库不包含 Windows 镜像或离线软件安装包。

Python 补丁版本可能与原机不同；固定的是 Python 3.13 x64 和锁定依赖。原机 Node 为 24.19.0，要求主版本至少 24。Windows ARM、macOS、Linux 未验证。

可选参数：`-SkipAppleDriver` 用于暂时只运行无手机界面；`-SkipSystemInstall` 只复用已安装的系统软件，但仍安装项目 Python 依赖。正常新电脑请不加这些参数。

## 3. 启动项目

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Start.ps1
```

访问 `http://127.0.0.1:8070/`。无手机时可先检查界面；20 台图标预览地址为 `http://127.0.0.1:8070/#preview-devices`。

原手机通过 USB 接入，解锁并信任新电脑，按设备要求确认开发者模式。接入后重新启动工作台加载设备。开发者镜像、手机服务准备和连通性检查见 [SINGLE_DEVICE.md](iphone_batch/SINGLE_DEVICE.md)。安装、检查和启动脚本均不会自动发送短信。

## 4. 重新配置本机凭据

翻译使用的 DeepSeek 密钥不进入 Git。可在现有配置入口重新填写，或重新设置 `DEEPSEEK_API_KEY` / `DEEPSEEK_MODEL` 环境变量。ChatGPT 需重新登录。手机与新电脑的信任和配对也需重新建立。这些人工授权不能由 GitHub 代码代替。

本方案恢复的是项目代码、素材、依赖和运行环境，不恢复客户端历史业务数据：已保存短信、回复记录、浏览器里的编号/备注/待跟进标记、Cookies、原机登录状态均不包含在仓库中。手机本身的数据仍由手机保存。

## 检查与演练记录

```powershell
.\.venv\Scripts\python.exe tools\environment_check.py
```

环境检测只读，不连接手机或调用付费 API，输出不包含密钥。驱动服务或配置文件“存在”不等于手机已经信任或 API 可用。

本机已创建独立目录及全新虚拟环境进行依赖重装演练；实际结果见 [VALIDATION.md](recovery/VALIDATION.md)。本机演练复用操作系统、Python/Node 安装和苹果驱动，不能等同于一台未安装过软件的新电脑验证。首次新电脑使用仍应核对系统安装及真机投屏、读取、翻译是否正常。
