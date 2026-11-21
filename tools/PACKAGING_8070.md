# 8070 Windows 安装包

当前交付为 v0.1.19 皮卡丘集成后台包。目标：Windows 10/11 x64，无需目标电脑预装 Python、Node 或 Git；需使用已接入后台控制协议的皮卡丘客户端。8070 与平级 VNC 项目使用不同 AppId 和目录。

当前后台专用构建与验收：

```powershell
.venv\Scripts\python.exe tools/build_8070_installer.py --host-only
.venv\Scripts\python.exe tools/check_8070_installer.py releases/PhoneWorkbench8070-0.1.19-Setup.exe
```

新模式无 Electron、独立启动器、桌面或开始菜单启停入口。安装器将实际路径、版本和控制协议写入当前用户 64 位注册表；卸载清理登记。升级时清理固定的旧客户端程序目录及快捷方式，不清理业务数据。皮卡丘通过三种固定 JSON/stdin 命令控制后台，安装模式下直接启动 dashboard.py 或无授权启停被拒绝。具体约定见 [接入协议](../PIKACHU_8070_CONTROL_PROTOCOL.md)。注册表验证使用隔离测试目录临时登记，结束后卸载；不覆盖已有同 AppId 的安装。

当前检查除了内置运行时、实际加载的 C++ DLL 路径、零设备签名 HTTP、版本和短信入口，还核验签名 status、无授权 start/stop 拒绝及无授权 dashboard 启动拒绝。37 项 Python 回归包含真实后台方法通过 stdin 传递 serve 凭据并关闭隔离服务子进程。双方跨语言与菜单交互测试由皮卡丘项目完成。实机 USB 启停尚未在新安装目录验证，不自动操作正在使用的手机后台。

以下保留 v0.1.18 独立桌面包的重建说明；其桌面入口不用于当前集成模式。

使用项目 Python 3.13 虚拟环境运行：

```powershell
.venv\Scripts\python.exe tools/build_8070_installer.py --electron <Electron-dist目录> --iscc <ISCC.exe路径>
.venv\Scripts\python.exe tools/check_8070_installer.py releases/PhoneWorkbench8070-0.1.18-Setup.exe
```

Electron 参数仅指定开源运行时目录，不复制其上层应用源码、用户资料或登录。生成目录为 `releases/`，构建缓存和逐文件 SHA256 清单位于忽略的 `iphone_batch/.device-data/installer-build/`。安装包包含 Python/Tcl、项目依赖、Node、Electron、官方 x64 VC143 CRT 和独立桌面启动页；安装目录内 Python 通过 `_pth` 隔离加载，不使用目标电脑 Python。CRT 默认取 Visual Studio BuildTools 的可分发目录，也可通过 `--crt` 指定同类官方目录。桌面入口沿用本机 HMAC 校验，各电脑自行创建凭据。

验证包括：清理开发环境 PATH，加载主要原生依赖、核对锁定版本及实际加载的 CRT DLL 路径，启动零设备临时端口工作台，检查签名请求 200、未签名请求 403、页面版本及新建短信入口。随后将最终 EXE 实际安装到含中文和空格的独立目录，重复上述检查，再卸载。额外使用安装后的 Python 和真实后台管理代码启动隔离的模拟服务及子进程，验证状态查询、彻底关闭和进程退出；仅替换 USB 隧道入口及模拟脚本目录。验证不会发现或操作手机，也不使用开发后台端口。已有同 AppId 安装时验证器拒绝运行，避免覆盖用户安装。

Apple USB 驱动与服务不内置；新电脑需通过 Apple 官方安装程序准备，手机需解锁、信任电脑及开启开发者模式。首次开发者镜像准备可能需要网络；共享隧道需管理员授权。当前安装器未进行发行商代码签名。隔离安装测试不代替另一台物理电脑的 Apple 驱动、USB 和手机实机验收。

安装器按当前 Windows 用户安装，不自动启动。卸载不递归清理业务数据。v0.1.18 首次使用点击独立启动页的“启动并打开工作台”；当前 v0.1.19 改由皮卡丘“打新增”右键菜单启停，页面通过原有苹果入口打开。关闭宿主窗口保留后台。本版本新建短信仍为配置草稿，尚未接入自动群发调度。
