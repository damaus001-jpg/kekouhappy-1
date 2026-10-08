**iOS 27：先验证 1 台，再扩展到 10 台 USB 手机**

2026-10-04: USB device iPhone12,1 / iOS 27.0 / build 24A437 verified. Developer Mode is enabled. Cryptex DDI 27.1.5228.8 (27A5228h) is installed and mounted at /System/Developer. Media capability query passed. User confirmed live video, clicks and swipes work after the screen server restarted with motion-IDR disabled. Long-duration stability and multiple-device operation remain unverified.

当前执行环境访问 PyPI 返回 WinError 10013。请在你自己的 PowerShell 中执行：

```powershell
cd D:\qunkong
.\.venv\Scripts\python.exe -m pip install -U pymobiledevice3
```

安装后先核对是否包含本工具使用的 session、serve-web 和 iOS 27 Cryptex DDI 处理。项目当前源码将 iOS 27 的自动开发者镜像准备转到 Cryptex1 路径，需 RSD 隧道。依据：[源码](https://github.com/doronz88/pymobiledevice3/blob/master/pymobiledevice3/services/mobile_image_mounter.py)、[排错说明](https://doronz88.github.io/pymobiledevice3/guides/troubleshooting/)。旧版是否支持要实际检查，不能只看安装成功。

控制器只枚举 USB 设备。只接一台时可以省略 --udid；多台时必须明确指定，最多 10 台。通过每设备子进程隔离执行，避免在一个进程打开多条 userspace 隧道。

```powershell
.\.venv\Scripts\python.exe iphone_batch\controller.py check
.\.venv\Scripts\python.exe iphone_batch\controller.py info
.\.venv\Scripts\python.exe iphone_batch\controller.py inspect
```

info 不需要第三方库，也不配对；只读基础信息。inspect 需要依赖，依次查询设备信息、开发者模式及媒体能力。缺开发者镜像时媒体检查可能失败。需要安装/挂载镜像时显式执行 prepare，它可能下载内容并在完成后继续媒体检查：

```powershell
.\.venv\Scripts\python.exe iphone_batch\controller.py prepare
```

工具不会自动重启手机或修改密码。开发者模式需按手机系统提示开启。

投屏与手动控制：

```powershell
.\.venv\Scripts\python.exe iphone_batch\controller.py screen --port 8081
```

看到 viewer_http_ready 后打开 http://127.0.0.1:8081/。该状态只表示页面响应，不表示视频已成功解码。先在手机主屏幕观察连续画面并测试点击与拖动。设备锁阻止本工具其他任务同时占用这台手机；它不能阻止其他软件操作手机。投屏期间可通过上游投屏页面手动操作，运行脚本前先停止投屏。

脚本先预览，再在合适的测试页面执行：

```powershell
.\.venv\Scripts\python.exe iphone_batch\controller.py run iphone_batch\example.json --udid DEMO --dry-run
.\.venv\Scripts\python.exe iphone_batch\controller.py run iphone_batch\example.json
```

示例包含中心点击与向上拖动；不要在有不可撤销业务操作的页面使用。坐标 0..65535 为屏幕归一化位置。脚本失败或超时后不自动重试，因为前面的动作可能已完成。命令退出成功不等于界面效果正确。

USB 在线观察可另开终端并与投屏同时进行：

```powershell
.\.venv\Scripts\python.exe iphone_batch\controller.py monitor --seconds 1800 --interval 5
```

monitor 统计在线采样、缺失样本、查询错误和观察到的断线，仅衡量 USB 枚举；采样之间短暂断线可能漏检，不衡量帧率、视频卡顿或触控成功率。

建议验收目标（尚未达成）：

| 阶段 | 验证内容 |
| --- | --- |
| 1 台基础 | 系统/build、开发者模式、DDI、投屏、点击、拖动 |
| 1 台稳定 | 30 分钟投屏；100 次可确认效果的动作；3 次拔插后重新连接 |
| 2 台 | 设备隔离、同脚本并行、单台断线不影响另一台 |
| 5 台 | 主机 CPU/内存、动作延迟、屏幕按需开启 |
| 10 台 | 逐台加入并重复稳定性测试，按测量结果决定并发 |

当前脚本不自动恢复断线后的业务任务；投屏进程退出后需重启命令。下一阶段基于真机结果设计长期 worker 与恢复状态机，避免误重放动作。

扩展到 10 台时重复指定 --udid；使用 --concurrency 10 才会让十台任务同时进入执行，默认并发为 4。并行下发同脚本不保证手机动作在同一毫秒发生。USB 数据传输、供电和总线负载需要实际验证。

**当前实测状态（2026-10-04）**

已安装 pymobiledevice3 11.22.0，触控 session 和 serve-web 命令存在。USB 信息查询与配对连接成功；此前 15 秒 USB 采样 5 次，未观察到掉线。开发者模式查询返回 false，检查已在该条件下停止，尚未开始投屏、触控或开发者镜像安装。12 项无设备测试通过。

控制器通过 pmd_entry.py 将上游缓存目录放在 iphone_batch/.device-data 中；该目录含本地配对数据，应留在当前机器，已加入本目录的 .gitignore。没有修改 Python 的 HOME，也没有修改已安装的上游包文件。requirements.txt 记录本次验证的主包版本；这只是环境版本记录，不代表已通过 iOS 27 的全部功能验收。

Screen stability adjustment: controller.py screen now passes --no-motion-idr. Initial default session went black; root cause is not established. The upstream option removes motion-triggered keyframe pressure at the cost of slower resolution recovery. Screen startup/stream logs are stored in .device-data/diagnostics/screen.log. The first diagnostic installation retry succeeded, despite the syslog watcher later reporting an abruptly terminated connection.

中文投屏页面与文本复制粘贴：

- 浏览器强制刷新后，右侧点“同步”开启双向文本同步，开关会在本浏览器保存。
- 手机到电脑：开启同步后，在手机复制新文字，等待“已复制到电脑”，再切换电脑应用按 Ctrl+V。
- 电脑到手机：电脑复制文字，切回投屏页面，点手机输入框后按 Ctrl+V，或在手机长按选择“粘贴”。
- 开启同步之前已经复制的手机文字，用“从手机获取”读取；面板内容可点“复制到电脑”。手动发送文字用“发送到手机”。
- 当前 Windows 电脑的文本通过本地系统剪贴板通道传输，支持中文、换行和表情。图片仍使用上游浏览器剪贴板路径。
- 双向同步会替换双方当前剪贴板内容。多手机同时开启同步时会竞争同一个电脑剪贴板，因此批量模式需另行设计每台手机的文本发送与接收。
- 本地定制资源位于 web/，pmd_entry.py 在启动投屏时加载 viewer_patch.py，不修改已安装的上游库。

短信气泡复制兼容：观察到部分手机复制内容的主类型为 com.apple.uikit.attributedstring，普通文本仅作为未随快速读取返回的次要类型。pasteboard_text.py 为该 UIKit 归档增加纯文本提取；普通文本仍优先。只读取归档正文 NSString / NS.string 字段，不拼接字体、链接等属性。已通过中文、换行、表情、循环引用与普通文本优先等测试。仍需使用短信气泡复制在手机上验证最终效果。诊断接口只返回类型、长度及归档字段结构，不返回复制正文。

电脑键盘快捷键：点击投屏画面使其获得焦点后，Ctrl+C/V/X/A 转为 iPhone 的 Command+C/V/X/A。Ctrl+V 在双向同步开启时先读取电脑文本并同步到手机，再发送粘贴键。点击面板或离开页面时释放所有按键，电脑应用仍使用原快捷键。复制、剪切需要手机上存在选中的文字，短信气泡仍通过长按“复制”操作。键位转换已通过模拟测试，应用端实际响应需在对应手机输入框验证。

两台准备状态：已发现第二台 00008030-001225443E33C02E，iOS 27.0 / iPhone12,1。开发者模式已查询为 true；开发者镜像还未成功安装，当前执行环境访问 gs.apple.com 签名请求被 WinError 10013 阻止，需在用户自己的 PowerShell 执行：

```powershell
.\.venv\Scripts\python.exe iphone_batch\controller.py prepare --udid 00008030-001225443E33C02E --timeout 600
```

双画面管理程序 dashboard.py 已完成，默认页面 http://127.0.0.1:8070/，每台手机独立投屏进程。所有手机起初只读，选择手机时先关闭上一台的控制权限，再打开下一台。未选中手机的输入和文本剪贴板写入受服务端限制。切换时清空排队输入，释放键盘和已记录的触摸接触。已通过切换顺序、失败路径与只读限制测试；两路实际投屏尚未验证。

准备成功后，需要停止旧的单台投屏再启动管理程序：

```powershell
.\.venv\Scripts\python.exe iphone_batch\dashboard.py --udid 00008030-001119CE0A93402E --udid 00008030-001225443E33C02E
```

界面名称为“皮卡丘手机群控”。缩略图同样使用完整视频流，尚未实现手机端低帧率或低分辨率切换。

2026-10-04 更新：第二台镜像已确认安装并挂载（Cryptex 27.1.5228.8 / 27A5228h），媒体能力查询通过。双画面管理页已启动于 http://127.0.0.1:8070/。两路视频接口同时读取 10 秒均持续收到数据；控制权限按 1→2→1 切换成功；选中手机的系统剪贴板接口返回 200，未选中手机返回 403。浏览器双画面呈现、真实点击切换及长时间稳定性仍需用户验证。
