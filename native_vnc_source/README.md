# 原生 VNC 开发版源码 · v0.1.7

这是第二套方案的可追踪源码存档，与原项目 `iphone_batch/` 一起保存在同一个本地 Git 提交中。

- `client/`：当前开发版、兼容解码启动、键盘与单台控制、气泡读取、针对性检查和恢复设备工具。
- `upstream/`：参考 GitHub `pymobiledevice3` 的完整已追踪工作树。包含本机 Windows socket 修复；准确基线提交见 `SOURCE_METADATA.json`，改动另存 `upstream-working-tree.patch`。
- `viewer/`：当前使用的 TightVNC Viewer 和许可文件。
- `legacy_experiment/`：曾内嵌 8070 的错误实验，仅供追溯，不是开发版入口。
- `SHA256SUMS.json`：本目录文件的 SHA-256 清单。

## 恢复运行位置

当前快捷方式运行 `iphone_batch/.device-data/` 中的开发版。该目录含本机数据，整体不进入 Git。本目录只保存源码及必要客户端依赖。

在项目根目录执行：

```powershell
py -3.13 native_vnc_source/restore_runtime.py
```

脚本校验存档文件后，把源码复制回运行目录，不启动程序、不操作手机。已存在且不同的文件会停止恢复；确定要切回本恢复点时加 `--overwrite`。保留本机配对记录、短信、联系人和其他运行数据。

环境恢复使用根目录的 `Install.ps1` 与 `requirements-windows.lock.txt`。开发版无需打包；Tkinter 属于 Python 安装组件。需要构建 EXE 时额外安装 PyInstaller 6.22.3 和 pyinstaller-hooks-contrib 2026.10。

运行源码：

```powershell
.venv/Scripts/pythonw.exe iphone_batch/.device-data/start_native_vnc_dev.pyw
```

第一版安装包构建入口为 `tools/build_native_vnc_installer.py`，说明见 `tools/NATIVE_VNC_PACKAGING.md`。安装版自带 Python，不借用开发版虚拟环境；安装包不包含配对记录和业务数据。

完整当前状态和未验收项见根目录 `NATIVE_VNC_STATUS_2026-11-11.md` 与 `SESSION_ARCHIVE_2026-11-12_v0.1.7.md`。程序保持关闭；恢复源码不等于手机功能已完成验收。
