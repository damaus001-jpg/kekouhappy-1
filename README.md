# 短信工作台

Windows x64 本地 iPhone 短信工作台，当前版本 **v0.1.7**。本恢复点保存两套源码：原 8070 工作台保留在 `iphone_batch/`，原生 VNC 开发版及参考项目工作树保存在 [native_vnc_source/](native_vnc_source/README.md)。开发版使用原生桌面控件和 VNC，不内嵌 8070 网页；气泡只读界面结构，不用截图或 OCR。多机性能、输入与发送仍待实机验收。当前范围见 [2026-11-12 存档](SESSION_ARCHIVE_2026-11-12_v0.1.7.md)、[VNC 状态记录](NATIVE_VNC_STATUS_2026-11-11.md) 和 [会话记录](SESSION_NOTES.md)。本恢复点只存本地 Git，未推送远端。

## 原生 VNC 客户端安装包

首个安装包为 `releases/PhoneWorkbench-0.1.6-Setup.exe`，自带 Python 和运行依赖，供其他 Windows 10/11 x64 电脑安装；本机已有开发版可继续直接使用。安装版与开发版目录独立，请勿同时连接同一批手机。Apple USB 驱动及手机首次信任需要在目标电脑准备，不包含开发电脑的私钥或业务数据。构建、离线检查和验收边界见 [打包说明](tools/NATIVE_VNC_PACKAGING.md)。

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
