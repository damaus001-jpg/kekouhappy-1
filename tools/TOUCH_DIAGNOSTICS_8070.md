# 8070 开发版触控诊断

源码开发版在设备获得控制权时自动启动手机日志采集，撤销控制权或退出投屏服务时停止。只对具有 `.git`、`.venv` 且没有 `8070-host-policy.json` 的开发目录启用。`IPHONE_BATCH_TOUCH_TRACE=0` 可关闭；安装环境不因继承环境变量而启用。

日志在 `iphone_batch/.device-data/diagnostics/touch/<完整UDID>.jsonl`，每份最多约 2 MiB，另保留两份轮转文件。重连新会话使用新 session，继续追加而不清空旧文件。文件与导出包均在 Git 忽略范围内，不进入源码存档。手机日志解析在独立子进程执行，写盘使用有界队列和单独线程；队列溢出、采集失败和写盘失败可在状态中查看，不阻塞点击。

## 开发人员入口

在仓库根目录运行，`--number` 使用工作台设备编号：

```powershell
.venv\Scripts\python.exe iphone_batch\touch_diagnostics.py status --number 5
.venv\Scripts\python.exe iphone_batch\touch_diagnostics.py mark --number 5 --label left-click-dead
.venv\Scripts\python.exe iphone_batch\touch_diagnostics.py export --number 5 --label left-click-dead
```

`status` 查看采集状态、丢弃数、写盘错误与最近事件。`mark` 在时间线中标记现场并等待已入队日志落盘。`export` 同时标记并生成 ZIP，默认放在同目录的 `exports`；后端已离线时，仍可按设备编号存档表导出已有文件，`status.json` 会说明实时查询失败。可用 `--output` 指定新文件路径，已有 ZIP 不覆盖。这些命令不发送触控、按键或短信，不执行重连。

发现“右键可用，左键无效”时先标记、导出，再恢复连接。不要为抓日志先重连，否则会丢失现场的服务状态。开发版网页需要刷新以加载左键事件记录；后端模块需要重新启动相应投屏服务以加载采集器。调度器修改需要重新启动开发后台。两者与安装版分开生效。

## 时间线内容与判断

- `browser`：左键按下、松开、被未就绪状态拦截、被旧指针占用、右键 Home，以及当时的前端输入就绪和队列状态。
- `http-request`、`input-decoded`、`input-wait-lock`、`hid-dispatch`、`hid-return`、`http-response`：以 request_id 关联一个输入请求，保存耗时、坐标、手指数及连接代次。按键只记录数量，不保存键码。
- `phone-log`：动态查询 `backboardd` 和 `dtuhidd` PID，只读取新日志，过滤触控、触摸屏服务、认证和 unsupported service 等关键词。启用系统 NO_SENSITIVE 标志，消息截断至 1800 字符。不保存截图、剪贴板、短信正文或收件号码。
- `health-result` 明确标记 `keyboard-only`。健康检查或 HTTP 200 只能证明对应调用完成，不能单独证明触控已经作用到界面、短信已经送达。
- `incident-marker`、`session-start/end`、`collector-start/stopped/retry`：用于区分故障标记、连接恢复和采集器重启。

主机 `at` 和手机 `phone_at` 均输出带时区的 UTC 时间，并保留主机 monotonic 时间。手机日志有缓冲延迟，不能只靠日志条数或关键词出现就断定当前某次点击失败；缺少日志也不能证明手机拒绝输入。`collector=listening` 表示已取得目标 PID，`streaming` 表示已实际收到匹配日志；应同时检查 phone_lines、collector_error、io_error、dropped。

## 2026-11-22 实机记录与业务边界

设备 05 曾出现右键 Home 可用、键盘健康检查 ready、触控按下/松开返回成功，但截图仍停在主屏幕。单设备重连仅用于恢复，左键失效根因尚未解决。新记录器已在该设备实测取得 dtuhidd 触摸屏日志，并验证停止后采集子进程及写入线程退出。

另一次空短信列表读取，在指定检查目标之前返回零元素；在同一连接中设置实时 MobileSMS PID 后，底部三元素读取约 0.15 秒成功。这是原生检查目标的独立线索，不能当作触控失效的根因。此轮临时脚本只在已现场确认短信界面后指定 PID；尚未把强制读取后台 MobileSMS 当作通用页面可操作性证明。

用户已验收设备 05 的新建流程：列表 → 新建 → 输入号码 → 回车确认收件人 → 再回车进入正文 → 输入 Hi → 发送一次 → 侧滑返回短信列表。手机显示 Not Delivered，操作流程通过不代表运营商送达。原生 `Cancel` 是未发送新建页右上角 ×；发送后的会话返回与关闭新建页分别处理。

待跟进号码使用同样的新建/号码确认/进入正文流程，打开后由用户自行输入和发送，不因没有历史消息而判失败，不自动返回列表。自动任务发送后则需返回列表；返回失败时保留已发送状态并停止任务，避免重发。

发送间隔从本条发送请求时刻开始，到同一设备下一次新建会话为止，核对和返回列表耗时计入间隔。间隔中状态为“等待下一次新建”，不占在途名额。新建、输入、发送、核对、返回列表期间持有在途名额，最多同时 3 台。并发资源排队及导航可能使实际间隔长于抽取的随机值，调度器不补发或追赶。结果不明仍保持禁止自动重发。
