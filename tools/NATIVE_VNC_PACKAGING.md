# 原生 VNC Windows 安装包

版本与根目录 VERSION 一致。构建输出在 releases/，生成文件不提交到 Git。

在已安装锁定依赖和 PyInstaller 的 Windows x64 开发环境运行：

```powershell
.venv/Scripts/python.exe tools/build_native_vnc_installer.py
```

需要 Inno Setup 6.7.4，编译器路径为 `iphone_batch/.device-data/build-tools/InnoSetup/ISCC.exe`。
官方下载：https://github.com/jrsoftware/issrc/releases/download/is-6_7_4/innosetup-6.7.4.exe 。执行前检查 Authenticode 签名为 Valid，签名人为 Pyrsys B.V.。

构建脚本保存新构建目录，不覆盖开发环境。复制 Python 3.13、完整已安装依赖、原生前端、项目 Python 模块、参考源码和 Viewer；不复制运行数据。运行环境通过 `python313._pth` 隔离，不能借用开发机注册表或 PYTHONPATH 的依赖。前端 EXE 和隔离 Python 都做离线导入检查，参考投屏入口仅运行 --help，不连接手机。

安装包适用于 Windows 10/11 x64，默认按当前用户安装到 `%LOCALAPPDATA%\Programs\PhoneWorkbench`，提供桌面、开始菜单快捷方式和卸载功能，安装结束不自动运行。默认图形模式：两排、总览 1fps、大屏 5fps；GPU 关闭，内存优化开启。

Apple USB 驱动和服务未捆绑。新电脑缺少时需先安装 Apple 官方 iTunes 移动设备组件；首次开发者镜像准备也可能需要联网。安装说明包含可选 winget 指令，不静默下载驱动。

安装版与开发版目录独立，不复制配对私钥、API 配置、短信与联系人。不要同时运行两版操作相同手机。卸载不主动删除运行后产生的用户数据。安装包未做代码签名，Windows 可能提示未知发布者。

交付文件包括 Setup.exe、SHA-256 文件和构建清单。离线检查不能替代新电脑驱动、USB 信任、多路画面及短信发送验收。不要把构建成功描述成实机功能已经验收。

安装包生成后，可运行 `.venv/Scripts/python.exe tools/check_native_installer.py`，在独立临时目录安装、调用 EXE 的离线检查并卸载。该脚本不启动手机 UI，发现已有安装注册记录或临时目录时会停止以免覆盖。首次 v0.1.6 已通过此流程；已在源码发布清单中记录哈希和验收边界。
