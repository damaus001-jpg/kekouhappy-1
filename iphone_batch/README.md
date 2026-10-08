**iOS 27 single-device validation**

Start with [SINGLE_DEVICE.md](SINGLE_DEVICE.md). USB-only discovery, exclusive device ownership, device info, developer-image preparation and USB monitoring are available.

**苹果手机批量控制原型**

Windows 本地命令行工具，使用 pymobiledevice3。支持只读设备发现、批量点击/拖动、ASCII 输入、JSON 动作脚本，以及单台浏览器投屏。多台设备操作由不同子进程并行执行；每台设备脚本按顺序执行，相邻触控动作共用一次媒体会话。它是技术验证原型，尚无图形化群控界面，也没有真机验证。

当前环境（2026-10-04）：Python 3.13，Apple Mobile Device Service 正在运行，发现 1 台 USB 手机（iOS 27.0，Build 24A437）。用户已安装 pymobiledevice3 11.22.0；开发者模式目前关闭，投屏和触控尚未验证。代码可以独立执行设备发现和操作预览。

安装后先检查命令帮助。此原型对应本次研究的 master CLI；若安装版没有 universal-hid-service、session 或 serve-web，需要安装具备这些功能的版本。不要把普通连接成功当成触控可用。

在 D:\qunkong 中运行：

```powershell
.\.venv\Scripts\python.exe -m pip install pymobiledevice3
.\.venv\Scripts\python.exe iphone_batch\controller.py check
.\.venv\Scripts\python.exe iphone_batch\controller.py devices
```

手机应通过 USB 连接，解锁并信任电脑；开发者功能还需对应开发者模式、DDI 与服务支持。默认隧道根据项目版本和 iOS 版本选择，iOS 17.0–17.3.1 在 Windows 上可能需要管理员权限的 tunneld。

先预览，不会操作设备，也不要求已安装 pymobiledevice3：

```powershell
.\.venv\Scripts\python.exe iphone_batch\controller.py run iphone_batch\example.json --udid DEMO-A --udid DEMO-B --dry-run
```

执行时将 UDID 换成 devices 输出中的真实值：

```powershell
.\.venv\Scripts\python.exe iphone_batch\controller.py run iphone_batch\example.json --udid 手机A的UDID --udid 手机B的UDID --concurrency 2
```

这表示并行下发同一脚本，不保证手机端动作发生在完全相同的时刻。连接创建、设备负载和系统调度均会产生时间差。每台独立脚本可在不同终端指定对应 UDID 执行。

投屏（保持此命令运行，看到 viewer_http_ready 后在浏览器打开输出 URL）：

```powershell
.\.venv\Scripts\python.exe iphone_batch\controller.py screen --udid 手机A的UDID --port 8081
```

第二台另开终端并换为 8082 端口。投屏与批量脚本是独立媒体会话，目标设备能否同时支持需实测；本原型未实现把投屏窗口的点击广播到其他设备。建议先分别验证投屏与动作脚本。

脚本格式是 JSON 数组：

```json
[
  {"op": "tap", "x": 32768, "y": 32768},
  {"op": "sleep", "seconds": 0.5},
  {"op": "drag", "x1": 32768, "y1": 52000, "x2": 32768, "y2": 18000, "duration": 0.6},
  {"op": "type", "text": "Hello"}
]
```

坐标为屏幕归一化值 0..65535，不是像素；32768 为中点。不同手机布局可能不同。手指滑动使用 drag。type 仅支持 ASCII，中文需其他输入路线。sleep 与其他触控动作被发送到同一次 session；它也需要媒体会话，不是纯主机等待。

整个脚本在执行前校验。失败后停止该台手机后续命令，其他手机继续。超时不自动重试，因为动作可能已经部分执行。默认每组命令超时 120 秒，包含隧道启动和该组脚本执行时间，长脚本应使用 --timeout 提高。退出码只能说明命令完成，不能证明界面效果。

Ctrl+C 会取消当前任务并结束所属子进程，已经执行的动作不会撤销。每次批量调用采用子进程隔离，避免同进程多条 userspace 隧道冲突；不同控制器实例不要同时操作同一台手机。

无设备验证：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s iphone_batch -p test_controller.py -v
```

依据：[项目](https://github.com/doronz88/pymobiledevice3)、[HID/屏幕命令](https://doronz88.github.io/pymobiledevice3/cli/developer/)、[隧道](https://doronz88.github.io/pymobiledevice3/guides/ios17-tunnels/)。

