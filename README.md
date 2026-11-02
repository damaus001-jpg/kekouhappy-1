# 短信工作台

Windows x64 本地 iPhone 短信工作台，当前版本 **v0.1.3**。本恢复点已按用户要求移除 8070 的中英翻译及中文发送拦截：读取显示原文，中文、英文等均原样提交。手机号码、正文、单次发送及结果核验保留；用户确认移除翻译后整体更流畅，具体多语言实发仍按用户验收结果判断。最新状态见 [2026-11-01 存档](SESSION_ARCHIVE_2026-11-01.md) 和 [会话记录](SESSION_NOTES.md)。

## 全新电脑安装

下载 GitHub 项目 ZIP 并完整解压，在项目根目录打开 PowerShell：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Install.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\Start.ps1
```

安装程序会准备 Python、Node.js、苹果驱动及锁定版本的项目依赖，不需要从原电脑复制虚拟环境，也不要求预装 Git。

完整步骤与恢复边界见 [RECOVERY.md](RECOVERY.md)。工作台地址为 <http://127.0.0.1:8070/>。

项目安装、启动不会自动发送短信。
