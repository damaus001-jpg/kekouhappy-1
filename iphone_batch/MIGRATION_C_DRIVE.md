# C 盘迁移检查（2026-10-13）

当前项目目录：`C:\xiangmu\qunkong`。

## 启动

连接 USB 手机、解锁并信任电脑后，在项目目录运行：

```powershell
& .\iphone_batch\start_workspace.ps1
```

默认管理页为 `http://127.0.0.1:8070/`，投屏从 8080 端口开始。
可通过 `-Udid`、`-Port`、`-BasePort` 指定设备和端口。
脚本根据自身位置定位项目，可从其他工作目录使用绝对路径调用。
启动日志位于 `iphone_batch\.device-data\logs\dashboard-<端口>.*.log`。

## 已修复

- 重启脚本根据自身目录匹配进程，并调用新的启动脚本。
- 两个粘贴诊断脚本将截图保存到脚本所在目录下的数据目录。
- 虚拟环境创建配置、激活脚本、命令入口中的项目路径已改为当前 C 盘路径。
- 已同步受影响依赖的 RECORD 哈希和大小，未升级或重新安装依赖。
- 环境修改前的备份：`.device-data\diagnostics\venv-before-path-repair.zip`。

## 验证与限制

- C 盘 Python、pip、pymobiledevice3 命令运行成功；`pip check` 通过。
- PowerShell 激活环境后，Python 解析到 C 盘虚拟环境。
- dashboard、controller、viewer_patch 的 20 项现有测试通过。
- 两个 PowerShell 启动脚本语法检查通过。
- 使用空设备枚举模拟，实际启动 C 盘 HTTP 服务，首页和 `/api/state` 返回 200；验证进程已关闭。
- 当前 USB 设备发现结果为空。真实启动明确报缺少设备，因此真机投屏和控制尚未验证。
- 历史文档、浏览器历史日志和 D 盘原文件保留；原 D 盘后台进程未停止。

接入手机后，可先运行 `.\.venv\Scripts\python.exe iphone_batch\controller.py check`，再启动工作台。
若旧服务仍占用默认端口，可使用 `-Port 18070 -BasePort 18080`。
