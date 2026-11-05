# 短信工作台

Windows x64 本地 iPhone 短信工作台，当前版本 **v0.1.4**。本恢复点保存授权客户端访问校验、投屏预热与重连、按需粘贴、单设备会话恢复及上游依赖 11.49.5 升级。8070 保持原文模式；坐标触控偶发失效仍待独立验收。最新状态见 [2026-11-05 存档](SESSION_ARCHIVE_2026-11-05.md) 和 [会话记录](SESSION_NOTES.md)。

## 全新电脑安装

下载 GitHub 项目 ZIP 并完整解压，在项目根目录打开 PowerShell：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Install.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\Start.ps1
```

安装程序会准备 Python、Node.js、苹果驱动及锁定版本的项目依赖，不需要从原电脑复制虚拟环境，也不要求预装 Git。

启动脚本仅启动后台。请通过已接入请求签名的授权客户端“苹果”入口访问工作台；普通浏览器直接访问 8070、手机投屏端口或 API 将被拒绝。两边使用当前 Windows 用户的 `%LOCALAPPDATA%\PikachuSmsBridge\workspace-access.key` 保存本机共享凭据，凭据不进入网页、URL 或仓库。更新程序应保留该用户目录。两边源码升级后需要重新启动对应应用，旧版翻译器没有请求签名能力。

完整步骤与恢复边界见 [RECOVERY.md](RECOVERY.md)。工作台地址为 <http://127.0.0.1:8070/>。

项目安装、启动不会自动发送短信。

设备通信与投屏依赖固定为 `pymobiledevice3==11.49.5`，安装清单已同步。此依赖升级不代表偶发坐标触控失效已经解决，左键稳定性仍需独立验收。
