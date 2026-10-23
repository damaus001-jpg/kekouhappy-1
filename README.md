# 皮卡丘短信工作台

Windows x64 本地 iPhone 短信工作台，当前版本 **v0.1.0**。

## 全新电脑安装

下载 GitHub 项目 ZIP 并完整解压，在项目根目录打开 PowerShell：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Install.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\Start.ps1
```

安装程序会准备 Python、Node.js、苹果驱动及锁定版本的项目依赖，不需要从原电脑复制虚拟环境，也不要求预装 Git。

完整步骤与恢复边界见 [RECOVERY.md](RECOVERY.md)。工作台地址为 <http://127.0.0.1:8070/>。

项目安装、启动不会自动发送短信。
