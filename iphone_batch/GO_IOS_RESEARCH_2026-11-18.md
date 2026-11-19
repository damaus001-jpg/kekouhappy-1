# go-ios 源码研究与本项目适用性

研究日期：2026-11-18。优先研究 AX，同时覆盖连接、输入、画面、应用管理和测试运行。

研究基线：官方仓库 main 的提交 `99f98ba773b2123690f30b367db13107e3d77224`。下文源码链接固定到该提交，避免 main 继续更新后结论失去依据。检索时 GitHub latest release 指向 v1.3.2；**main 的能力不等于该发行版全部具备的能力**。临时研究源码位于 `.tmp/go-ios-research-20261118/`。

本次为源码阅读和本地代码对照。没有安装 go-ios、Runner 或 DeviceKit，没有操作手机，没有运行 go-ios 实机测试，也没有更改正式采集逻辑。上游注释中的设备测试结果属于上游报告，不能视为设备9验收结果。

## 1. 结论与优先级

最有价值的是学习协议事件管理、生命周期和故障处理，而不是把 Python 换成 Go 后期待自动不漏读。

1. 优先：AX 全事件观测、单一接收入口、移动与事件等待分离、超时后的状态核验。
2. 同时防止：为避免阻塞而丢弃历史焦点事件。上游 DTX 队列采用保留最新状态的策略，与完整采集的要求不同。
3. 次优先：借鉴设备热插拔监听、连接超时、服务能力探测和资源释放。
4. 按需参考：截图诊断、应用进程管理、开发镜像准备。
5. 另列条件：WDA/DeviceKit 的 UI 接口需要对应手机端程序；较新的 CoreDevice HID/截图接口有明确版本和开发镜像限制。

## 2. AX 使用的协议与能力边界

### 2.1 与当前项目是同类系统服务

`ios/accessibility/accessibility.go` 通过 usbmuxd 打开 `com.apple.accessibility.axAuditDaemon.remoteserver`，再使用 DTX 全局通道。当前本地 pymobiledevice3 的 `AccessibilityAudit` 也声明同一服务，并提供 RSD shim 服务名。

这意味着 go-ios 可以作为协议实现的对照，但切换语言或客户端并不会自动获得另一套完整的 Messages 数据源。

[源码：AX 连接](https://github.com/danielpaulus/go-ios/blob/99f98ba773b2123690f30b367db13107e3d77224/ios/accessibility/accessibility.go)

### 2.2 移动命令与焦点事件是两个动作

`Move` 发送异步移动命令；`AwaitElementChanged(ctx)` 等待下一条焦点变化事件。方向 Previous/Next/First/Last 对应 3/4/5/6，移动参数包含 `allowNonAX=false`、`includeContainers=true`。

因此：

- 发送成功不能证明焦点移动成功，更不能证明气泡已完整读取。
- 焦点事件不能简单视为带有业务请求编号的逐条回复；仍需处理启动事件、迟到事件、外部焦点变化。
- 当前正在等待的移动尚未确认时，不应盲目连续发送 Next/Previous。
- 非文本元素属于遍览路径，不能因为没有可解析文本就判定到头。

上游接口没有现成的短信时间线拼接、重复消息保留、顶部判定或卡片绕行策略，这些仍由本项目实现。

[源码：移动、事件等待及解析](https://github.com/danielpaulus/go-ios/blob/99f98ba773b2123690f30b367db13107e3d77224/ios/accessibility/accessibility_control.go)

### 2.3 字段读取值得比较，但不是新的文本保证

上游解析优先使用 `SpokenDescriptionValue_v1`，为空时回退 `CaptionTextValue_v1`；保留元素原始字节的 Base64，用于属性查询和动作。支持 Label、Identifier 和通用属性查询。

本项目当前正式遍览主要使用 caption 与 platform_identifier。本地依赖已经暴露 spoken_description，无需先引入 Go 才能对比两个字段。

适合做的改进：同时记录 caption、spoken_description、Label 查询结果，保留来源与冲突。不能不加判断就用较长字段覆盖正文，也不能推断它必定含时间。此前设备9部分样本的 caption 与 spoken_description 相同，Label 查询曾出现截断，所以该差异尚不能解释漏项。

元素句柄是会话内操作依据，不能直接充当永久消息 ID。滚动复用问题仍需用正文、方向、时间和相邻消息的出现位置综合验证。

### 2.4 上游确实修过“能发送，收不到事件”的死锁

PR #823 记录：监听模式变化事件已注册，但缺少持续接收者；旧版 DTX 分发向无缓冲队列写入时会阻塞唯一接收线程，导致同一连接上的回调停住，而发送仍可继续。

修复包括为 `hostInspectorMonitoredEventTypeChanged:` 设置持续接收者，避免临时接收者与它争抢同一事件。

**与本项目的关系需要分开看：**本地 Python 创建的是默认无上限的 `asyncio.Queue()`，当前扫描循环也会取出并跳过非焦点事件。尚无证据证明它存在同样的无缓冲通道死锁。可以借鉴事件分类和持续观测，不能据此宣布找到了设备9漏读根因。

[上游问题与修复说明：PR #823](https://github.com/danielpaulus/go-ios/pull/823)

### 2.5 当前上游的防阻塞策略会主动丢事件

`ios/dtx_codec/channel.go` 为每个已注册 selector 设置容量 16 的队列。队列满时 `deliverEvent` 丢弃最旧事件并记录警告，以保留最新状态。源码明确说明这是有损队列，不适合每条回调都必须保留的场景。

对焦点显示，这种取舍可以理解；对气泡全量采集，直接复用会引入缺口。建议：

- 原始事件先进入快速接收/记录层，解析和数据库工作移到后续处理。
- 每个设备会话只有一个底层事件接收者，由它向不同用途分发，避免多个读取者争抢。
- 设置队列上限时，溢出必须留下缺口标记，停止继续推进并恢复核验；不能静默丢失后仍标记完整。
- 记录本地接收序号、时间、队列深度和移动序号；本地序号只能帮助排查，不能假装成为手机提供的请求关联编号。
- 不应为避免丢失而无限堆积；采用快速持久记录、限制推进速度或显式中断。

[源码：DTX 事件路由和队列](https://github.com/danielpaulus/go-ios/blob/99f98ba773b2123690f30b367db13107e3d77224/ios/dtx_codec/channel.go)

### 2.6 元素坐标与完整树不能想当然

`ax_audit.go` 的上游注释报告：在 iPhone 13 / iOS 18.4.1，Label 查询可用，但单元素 AXFrame/AXBounds/AXPosition/AXSize 没有返回值；按坐标取元素也返回空。审计结果中的问题元素可以携带矩形。

这是特定设备版本的上游测试记录，不是所有 iOS 的统一结论。但足以说明：不能从“支持审计矩形”推导成“每条气泡都能查询坐标”，也不能把审计结果当作完整界面元素树。

`RunAudit` 返回对比度、点击区域、描述充分性等无障碍问题，未发现它承担全会话消息枚举的实现。

[源码：审计实现及真机限制说明](https://github.com/danielpaulus/go-ios/blob/99f98ba773b2123690f30b367db13107e3d77224/ios/accessibility/ax_audit.go)

### 2.7 CLI 示例不是成熟的聊天遍览器

该提交 `main.go` 的 `startAx` 是选择模式演示入口，调用 `GetElement` 三次，每次 sleep 一秒，随后等待中断；并没有循环采集整段聊天。它使用的 `NewWithoutEventChangeListeners` 也不能视为完整事件初始化范例。研究应以库接口、事件初始化和测试相互对照，不能直接把 `ios ax` 当作对照采集器。

此外，部分初始化/关闭路径使用 `context.Background()` 等待事件，异步移动包装不返回发送错误，若干解码路径仍有直接类型断言或 panic。若嵌入长期运行的工作台，应额外加超时、错误上报和解码保护，不能整段照搬。

[源码：CLI AX 入口](https://github.com/danielpaulus/go-ios/blob/99f98ba773b2123690f30b367db13107e3d77224/main.go)

## 3. AX 之外的能力

| 领域 | 已核查的实现 | 对本项目的价值与条件 |
| --- | --- | --- |
| 设备热插拔 | `ios/listen.go` 监听 usbmuxd Attached/Detached | 按 UDID 管理设备；断开后应作废旧会话，重连后重新校验。系统服务路线，不依赖 WDA |
| 服务连接 | `ios/connect.go` 区分 lockdown、shim、XPC；检查 RSD 服务端口并限制连接时间 | 区分未连接、缺少开发镜像、服务不支持、连接超时，避免所有异常都归结为重连 |
| Windows 隧道 | `tunnel_windows.go`、`userspace_tunnel.go` | 内核 TUN 路线涉及管理员权限与 Wintun；用户态路线使用 gVisor 网络栈，需由支持该路线的客户端访问，不能视为系统通用网络接口 |
| HID 触摸 | `ios/hid/session.go`、`digitizer.go` | 持续跟踪按下状态；关闭时释放触点；边缘手势与普通触摸分开。当前源码标注 iOS 27+、开发镜像等条件，未验证设备9适用性 |
| 硬件键及方向 | `ios/hid/controls.go` | 发送和动作完成分开；退出前留出发送完成时间。接口和版本限制需逐设备核验 |
| 常规截图 | `ios/instruments/screenshot.go` | 通过 Instruments 取得截图，可作为异常诊断证据；实际服务可用性和时延需测 |
| MJPEG | 同上 | 反复截图、PNG 解码及 JPEG 编码后发送。不是高效 H.264 屏幕流，未发现足以据此替换现有投屏的性能证据 |
| 新截图服务 | `ios/screencapture/screencapture.go` | CoreDevice PNG 截图，可选择显示器；源码标注 iOS 27+ 与开发镜像，不能当作通用后备 |
| 应用管理 | `cmd_device_apps.go` | 已安装应用列表、进程、启动等；启动命令调用 Instruments。适合恢复前核验应用状态，不直接解决聊天内容读取 |
| WDA / DeviceKit UI | `cmd_ui.go`、`cmd_device_ui_run.go` | 点击、滑动、source、视频等通过对应后端 HTTP 接口；运行入口启动 XCTest bundle。不是只装电脑端即可免手机端部署 |
| WebInspector | `ios/webinspector/webinspector.go` 及 README 命令 | 用于可检查的 Safari/WebView 页面。不能据此读取原生 Messages 气泡 |
| REST API | `restapi/README.md` | 文档明确称实验性接口，另有独立模块；适合参考接口组织，未做稳定性验收 |
| 开发镜像 / XCTest | `ios/imagemounter/`、`ios/testmanagerd/` | 可研究环境准备、镜像挂载与测试启动；能在 Windows 启动已准备的测试，不等于无须签名和安装 |

输入层最值得复用的是**中断也释放触点、关闭幂等、单会话串行操作、发送成功与画面结果分离**。这些设计可以用于现有输入通道，不以启用 go-ios 的新 HID 服务为前提。

画面层最值得保留的边界是：帧新旧与焦点事件应独立观测；视频允许丢旧帧以降低延迟，消息采集不能沿用相同的丢弃策略。

主要源码：

- [设备监听](https://github.com/danielpaulus/go-ios/blob/99f98ba773b2123690f30b367db13107e3d77224/ios/listen.go)
- [服务连接](https://github.com/danielpaulus/go-ios/blob/99f98ba773b2123690f30b367db13107e3d77224/ios/connect.go)
- [Windows 隧道](https://github.com/danielpaulus/go-ios/blob/99f98ba773b2123690f30b367db13107e3d77224/ios/tunnel/tunnel_windows.go)
- [用户态隧道](https://github.com/danielpaulus/go-ios/blob/99f98ba773b2123690f30b367db13107e3d77224/ios/tunnel/userspace_tunnel.go)
- [触摸会话](https://github.com/danielpaulus/go-ios/blob/99f98ba773b2123690f30b367db13107e3d77224/ios/hid/session.go)
- [HID 服务与版本限制](https://github.com/danielpaulus/go-ios/blob/99f98ba773b2123690f30b367db13107e3d77224/ios/hid/hid.go)
- [截图与 MJPEG](https://github.com/danielpaulus/go-ios/blob/99f98ba773b2123690f30b367db13107e3d77224/ios/instruments/screenshot.go)
- [CoreDevice 截图](https://github.com/danielpaulus/go-ios/blob/99f98ba773b2123690f30b367db13107e3d77224/ios/screencapture/screencapture.go)
- [UI 客户端](https://github.com/danielpaulus/go-ios/blob/99f98ba773b2123690f30b367db13107e3d77224/cmd_ui.go)
- [UI Runner 启动](https://github.com/danielpaulus/go-ios/blob/99f98ba773b2123690f30b367db13107e3d77224/cmd_device_ui_run.go)

## 4. 与当前项目代码的直接对照

| 当前代码 | 已看到的事实 | 下一步验证，不等于已确认缺陷 |
| --- | --- | --- |
| `native_ui_scan.py:scan` | 直接读取私有 `_event_queue`；非焦点事件被取出后跳过 | 保留所有事件及监听状态，以便判断超时前发生了什么 |
| 同上 | 初始化有清空队列；取事件列表第一项；以元素 ID 和 caption 检查重复 | 记录清空数量与内容，检查是否丢了有用启动事件；发现多项时保留原始载荷；重复不能一律解释为到头 |
| 同上 | 已有“等待 Next 未确认时不继续发 Next”的保护 | 保留此保护；go-ios 的异步发送拆分不构成放宽保护的依据 |
| `native_foreground.py:read_window` | 仍是单次有界逆向读取，见号码标题可停止 | 与用户最新 Text Message 后三个元素内号码标题的顶部规则不同；新流程尚未正式接入 |
| 本地 `AccessibilityAudit` | caption、spoken_description 均可获取；默认无上限 asyncio 队列 | 能直接补齐观测字段；不能把 Go 队列死锁当作本地已证实原因 |

## 5. 建议的验证顺序与验收

### A. 先回答“漏在哪里”

保留设备9两遍方案：底→顶 160ms，顶→底 210ms，完成时留在实际底部；实验期间按用户要求不切换鼠标键盘控制权限。

为每次移动记录发送前后时间、方向、预期旧焦点、所有收到的事件、原始字段、解析结果、丢弃/合并原因。优先追踪曾漏掉的 12:55 `Live in N J`：

1. 焦点事件没有出现：导航或系统返回路径问题。
2. 原始事件出现、采集结果没有：队列处理或筛选问题。
3. 已采集、消息记录没有：解析或时间线合并问题。

### B. 再比较读取策略

先增加观测，不同时更换驱动、等待时长和衔接算法。完整记录所有非文本节点；不为无时间的片段猜时间；重复正文保留出现次数与上下文。

若要做 Go/Python 协议对照，应在分开的实验中独占同一设备 AX 会话，禁止两个采集器同时操作焦点。Go 侧使用库接口并补齐超时/事件保护，不能直接拿三步 CLI 演示当完整采集器。

### C. 完整性验收

- 单独证明抵达顶部与底部，不把号码标题单独出现当作到顶。
- 两遍结果做保留顺序与出现次数的核对；已知内容集合一致只说明未发现已知缺口，不能证明没有未知缺口。
- 对链接卡片、图片、纯非文本连续段和语音条逐类验证；没有语音条样本不能写语音验收通过。
- 发现队列溢出、焦点失联或衔接不确定时，结果标为未完整并保留恢复位置。
- 统计含准备和最终定位的总耗时，避免只报告扫描用时。

## 6. 本次尚未完成的验证

未编译或执行 go-ios，未比较 Go/Python 的真实漏读率，未在设备9验证新的 HID、截图或隧道接口。已阅读的上游测试覆盖 DTX 分发防阻塞、响应等待、触点释放、审计解析等，但不能替代本项目 Messages 场景的验收。

因此本次交付是可追溯的研究与实施依据，不是对“漏气泡已修复”或“go-ios 比当前驱动更稳”的结论。

后续已按用户认可补齐本地逐事件观测，并完成设备9两组160/210ms对照，结果见 [AX_EVENT_OBSERVATION_2026-11-18.md](AX_EVENT_OBSERVATION_2026-11-18.md)。该实验不涉及运行 go-ios；研究与设备9当前驱动的实验结论须分开看。
