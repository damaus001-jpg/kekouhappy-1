# 短信工作台

Windows x64 本地 iPhone 短信工作台，当前版本 **v0.1.8**。本目录现在只作为原 8070 工作台的开发工作区；原生 VNC 开发版已迁到平级独立项目 [qunkong-vnc](../qunkong-vnc/README.md)，独立维护源码、环境、数据和本地 Git。以后开发“手机群控－开发版”，请从 `C:\xiangmu\qunkong-vnc` 打开 Codex，不在本目录修改 VNC。原 v0.1.7 双源码恢复点仍保留在本仓库 Git 标签中。拆分范围见 [2026-11-13 存档](SESSION_ARCHIVE_2026-11-13_v0.1.8.md) 和 [会话记录](SESSION_NOTES.md)。本次只存本地 Git，未推送远端。

## VNC 项目迁移说明

VNC 开发、启动、打包和后续本地存档均在平级 `qunkong-vnc` 项目进行，见其 [项目说明](../qunkong-vnc/README.md) 和 [打包说明](../qunkong-vnc/tools/NATIVE_VNC_PACKAGING.md)。本目录不再维护 VNC 源码或运行副本。原 `releases/PhoneWorkbench-0.1.6-Setup.exe` 仅作为历史安装产物保留。

## 原项目源码环境安装

下载 GitHub 项目 ZIP 并完整解压，在项目根目录打开 PowerShell：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Install.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\Start.ps1
```

安装程序会准备 Python、Node.js、苹果驱动及锁定版本的项目依赖，不需要从原电脑复制虚拟环境，也不要求预装 Git。

启动脚本仅启动后台。请通过已接入请求签名的授权客户端“苹果”入口访问工作台；普通浏览器直接访问 8070、手机投屏端口或 API 将被拒绝。两边使用当前 Windows 用户的 `%LOCALAPPDATA%\PikachuSmsBridge\workspace-access.key` 保存本机共享凭据，凭据不进入网页、URL 或仓库。更新程序应保留该用户目录。两边源码升级后需要重新启动对应应用，旧版翻译器没有请求签名能力。

也可双击 `BackendControl.cmd` 打开独立后台控制窗口，查看进程状态、启动后台或彻底关闭本项目的后台及相关子进程。关闭控制窗口会保留后台运行。请等待手机操作和短信发送完成后再关闭后台。启动失败日志位于 `iphone_batch/.device-data/logs/dashboard-8070.err.log`。该工具依赖本项目安装后的 Python 环境；桌面快捷方式在项目移动后需要重新创建。

完整步骤与恢复边界见 [RECOVERY.md](RECOVERY.md)。工作台地址为 <http://127.0.0.1:8070/>。

项目安装、启动不会自动发送短信。

工作台顶部增加全局监看：桌面宽度默认每排 10 台，每台每 3 秒生成一次缩略图；窄屏自动减少列数。点击卡片选中设备并滚动到下方原有操作区，左侧设备列表保留；支持独立全屏监看及 Esc 退出，点击设备也会退出监看全屏。连接失败的手机显示原因，视频尚未返回时显示等待提示。缩略图复用既有投屏连接，未选中设备的绘制预热同步降为每 3 秒一帧，底层视频仍持续接收和解码，尚未实现源分辨率或解码降频。刷新授权客户端页面加载新界面即可。

设备通信与投屏依赖固定为 `pymobiledevice3==11.49.5`，安装清单已同步。此依赖升级不代表偶发坐标触控失效已经解决，左键稳定性仍需独立验收。
