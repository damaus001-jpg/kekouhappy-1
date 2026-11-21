# 8070 Windows 安装包

目标：Windows 10/11 x64，无需目标电脑预装 Python、Node、Git 或其他桌面客户端。8070 与平级 VNC 项目使用不同 AppId、目录和快捷方式。

使用项目 Python 3.13 虚拟环境运行：

```powershell
.venv\Scripts\python.exe tools/build_8070_installer.py --electron <Electron-dist目录> --iscc <ISCC.exe路径>
.venv\Scripts\python.exe tools/check_8070_installer.py releases/PhoneWorkbench8070-0.1.18-Setup.exe
```

Electron 参数仅指定开源运行时目录，不复制其上层应用源码、用户资料或登录。生成目录为 `releases/`，构建缓存和逐文件 SHA256 清单位于忽略的 `iphone_batch/.device-data/installer-build/`。安装包包含 Python/Tcl、项目依赖、Node、Electron、官方 x64 VC143 CRT 和独立桌面启动页；安装目录内 Python 通过 `_pth` 隔离加载，不使用目标电脑 Python。CRT 默认取 Visual Studio BuildTools 的可分发目录，也可通过 `--crt` 指定同类官方目录。桌面入口沿用本机 HMAC 校验，各电脑自行创建凭据。

验证包括：清理开发环境 PATH，加载主要原生依赖、核对锁定版本及实际加载的 CRT DLL 路径，启动零设备临时端口工作台，检查签名请求 200、未签名请求 403、页面版本及新建短信入口。随后将最终 EXE 实际安装到含中文和空格的独立目录，重复上述检查，再卸载。额外使用安装后的 Python 和真实后台管理代码启动隔离的模拟服务及子进程，验证状态查询、彻底关闭和进程退出；仅替换 USB 隧道入口及模拟脚本目录。验证不会发现或操作手机，也不使用开发后台端口。已有同 AppId 安装时验证器拒绝运行，避免覆盖用户安装。

Apple USB 驱动与服务不内置；新电脑需通过 Apple 官方安装程序准备，手机需解锁、信任电脑及开启开发者模式。首次开发者镜像准备可能需要网络；共享隧道需管理员授权。当前安装器未进行发行商代码签名。隔离安装测试不代替另一台物理电脑的 Apple 驱动、USB 和手机实机验收。

安装器按当前 Windows 用户安装，不自动启动。卸载不递归清理业务数据。首次使用点击“启动并打开工作台”；关闭桌面窗口保留后台，可通过“后台管理”关闭。本版本新建短信仍为配置草稿，尚未接入自动群发调度。
