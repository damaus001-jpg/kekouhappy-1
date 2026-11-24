# Current recovery point: v0.1.32 (2026-11-24)

Archive: [SESSION_ARCHIVE_2026-11-24_v0.1.32.md](SESSION_ARCHIVE_2026-11-24_v0.1.32.md). Local commit/tag only; no remote push. Next recovery version: v0.1.33.

## What changed in v0.1.32

- Incoming-message sender matching in `parse_records` now falls back to normalized phone-key comparison after the exact string path. A formatted header contact such as `+1 (313) 422-3491` and a normalized `+13134223491` both match message captions; contact names keep the plain string path. The previously failing `test_formatted_title_matches_incoming_messages_and_send_fingerprint` now passes; six new parsing tests were added.
- `ViewerStartQueue.discard_ready()` added. Phone reboot and USB re-plug cold starts forget previous readiness so the next first attempt gets the 360-second initial startup timeout; warm reconnects keep the 60-second short timeout. Reboot hint texts no longer assume the phone has a passcode.
- `discover_for_dashboard()` also catches `ValueError`, so a malformed usbmux payload cannot stop the workbench from starting.
- `dashboard.html` and `help.html` (unreferenced, unserved) moved to `iphone_batch/web/legacy/`.
- `workspace.js` clears the local notification-protection marker when `/api/notification-policy` returns a non-2xx response, keeping browser state aligned with the disabled monitor.
- `probe_title` focus condition now uses explicit parentheses around the `recover_first` branches.
- AGENTS.md records the client version display rule: the version badge follows the last packaged installer (currently v0.1.30); `VERSION` and README follow the source version.

## Validation

- 83 tests pass across sms_collect, native_foreground, viewer_start_queue, dashboard, bubble_status, sent_tail_speed, ax_conversation and ax_recheck. The wider suite keeps its pre-existing 8 failures + 2 errors with an identical list before and after. Python and JS syntax checks pass; `git diff --check` is clean.
- No installer was built or installed; the D-drive installed environment and the Pikachu/VNC repos were not touched; no SMS was sent and no phone inputs were issued. The C-drive development backend was restarted through `Backend.stop()`/`Backend.start()` to load the changes.

# Historical recovery point: v0.1.31 (2026-11-23)

Archive: [SESSION_ARCHIVE_2026-11-23_v0.1.31.md](SESSION_ARCHIVE_2026-11-23_v0.1.31.md). Local archive, v0.1.31 tag and remote force push complete. Installer remains v0.1.30 and was not installed. Next recovery version: v0.1.32.

## Current release and device status

- v0.1.30 installer SHA256: `0f488f7aa095709d18c4013146bd93dd9b188fffc53eb2bbfd9e925b05e53745`. Its offline zero-device isolation check passed; existing AppId caused installer verification to stop. User must manually upgrade in place.
- New-device initial viewer start timeout is 360 seconds; subsequent attempts retain 60 seconds. Apple USB service discovery errors no longer prevent the empty workbench from starting. Neither change proves the new-computer WinTun IPv6 connection issue is resolved; screen 30-second timeout remains open.
- Notifications, SMS badge scan, and deselect-to-home remain disabled at runtime. Unread assessment relies on the live device list. Automatic/manual title-number recognition shares a five-element, 200ms-per-element probe.
- `Recover.ps1 -Ref v0.1.31` now selects the GitHub tag archive. Preserve and push the v0.1.31 tag with `master`; do not change GitHub About description.

# Historical recovery point: v0.1.20 (2026-11-21)

Archive: [SESSION_ARCHIVE_2026-11-21_v0.1.20.md](SESSION_ARCHIVE_2026-11-21_v0.1.20.md). Local commit/tag only; no remote push. Next recovery point: v0.1.21.

## Current runtime and release status

- User requested save+Git before completing the new installer. C development backend is currently running through the normal `Backend.start()` control path; D installed v0.1.19 backend was stopped to release port 8070. User reports devices 01–10 have recovered frames and is checking 11–18. Do not interrupt that check or restart/stop either environment until the user finishes.
- Starting the development dashboard directly with `Start.ps1` bypasses the shared USB tunneld and is not a valid reproduction of the normal development setup. The normal backend controller calls `_ensure_tunneld()` first. After switching to that exact control path, video health showed active RTP and decoded frames, and the user confirmed 01–10 restored.
- `controller.ensure_usb_tunnel()` now cancels/recreates only the target UDID tunnel before a new screen session. Old entries can remain listed after a phone disconnect and must not be trusted as live. New v0.1.20 installer has not been built or installed; D remains on v0.1.19. Package only after the user's device 11–18 check is complete and the C/D runtime path has been validated.
- New SMS UI still stores local drafts only. Saving does not enqueue a job; immediate start and scheduled execution are not wired. For future automation, retry only idempotent read/navigation after control recovery and full recipient/conversation/body revalidation; an uncertain send click must pause for status reconciliation and never auto-resend.
- Touch loss during automation must not blindly replay the last action. Revalidate control readiness and the target conversation/body after reconnect; pause if state is ambiguous. No automation implementation was added in this recovery.
- Security packaging requirement remains pending: compiled/protected backend and controlled updates; plaintext Python cannot be called tamper-proof. No direct installed-script replacement is the formal update path.

## Pending release security requirement (user, 2026-11-21)

Formal releases must reduce source exposure and prevent ordinary-user replacement of backend code, using compiled backend distribution, protected installation permissions, signature/integrity verification and controlled updates. The current plaintext Python distribution does not meet this requirement; wrapping scripts in an EXE alone is insufficient, and local administrator access cannot be represented as absolutely tamper-proof. Direct replacement of installed scripts was used for this diagnosis (controller.py USB-tunnel recovery), but must not be the formal update mechanism. Security packaging work is deferred until the current video/connection timeouts are resolved. No new commit, tag, archive or version increment is created by this note.

# Historical recovery point: v0.1.19 (2026-11-21)

Archive: [SESSION_ARCHIVE_2026-11-21_v0.1.19.md](SESSION_ARCHIVE_2026-11-21_v0.1.19.md). Local tag v0.1.19; no remote push. Pikachu menu-only companion commit: `f467dc6c66a7cef9a9a7fe518146019b3c300a98`. Previous recovery: v0.1.18; next recovery was v0.1.20.

## Work record before archiving

User authorized direct collaboration with the new Pikachu session `01a1ff4d-45db-7b82-b017-d38f46a6750c`. Both “打新增” icons share status/start/stop; no open-page menu item. See PIKACHU_8070_CONTROL_PROTOCOL.md. 8070 provides registry-discovered, per-installation signed stdin JSON commands, atomic nonce replay protection and command locking. Host-only installed startup requires a separate serve grant; source development remains available without the installation policy. New installer mode omits Electron/standalone shortcuts; Apple driver/trust/developer mode/UAC remain external. Existing development backend and phones are not used for joint tests. 37 Python regression checks pass, including real process/grant transfer with USB tunnel mocked. Pikachu reports build, cross-language fixture, actual menu interactions and theme tests passing. Existing installed Pikachu and Signal trial were not overwritten/restarted. Current changes are uncommitted; previous recovery point remains v0.1.18. No remote push.

# Historical recovery point: v0.1.18 (2026-11-20)

Archive: [SESSION_ARCHIVE_2026-11-20_v0.1.18.md](SESSION_ARCHIVE_2026-11-20_v0.1.18.md).
Independent 8070 Windows installer bundles Python, Node and an Electron desktop entry with per-computer HMAC access. Relocated-runtime and final EXE installation checks use zero devices. Apple drivers and phone-side trust/developer mode remain external requirements. No remote push. Next recovery version: v0.1.19.

# Historical recovery point: v0.1.17 (2026-11-20)

Archive: [SESSION_ARCHIVE_2026-11-20_v0.1.17.md](SESSION_ARCHIVE_2026-11-20_v0.1.17.md).
User authorized a local archive and Git commit/tag only; no remote push is authorized for this delivery. Screenshot modes and device 01 reboot/control recovery were exercised; the new-message UI currently saves configuration drafts only. Multi-device scheduling, automatic banner patrol, Windows notifications, and daily statistics remain pending. Detailed evidence and limits are recorded in the archive and recovery/VALIDATION.md. Next archive version: v0.1.18.

# Current recovery point: v0.1.16 (2026-11-19)

Archive: [SESSION_ARCHIVE_2026-11-19_v0.1.16.md](SESSION_ARCHIVE_2026-11-19_v0.1.16.md).
User authorized local archive, Git commit/tag and remote force push. This entry supersedes older current-version notices below; historical records remain unchanged. The send/page-scroll fix was accepted by the user. Recovery checks and known test limits are recorded in recovery/VALIDATION.md. Next archive version: v0.1.17.

# 会话存档：2026-11-05 · v0.1.4

最新恢复点为 **v0.1.4**，详见 [2026-11-05 存档](SESSION_ARCHIVE_2026-11-05.md)。用户要求存档、存本地 Git，随后授权强推远端、清空仓库简介及清理远端品牌文字。完成本次存档和已授权远端操作后停止开发与验收，不关机。下次新恢复点为 **v0.1.5**。

本次保存此前全部未提交进度，包括授权客户端签名访问、按需文字/图片粘贴、设备信任与完整重连、画面预热和订阅恢复，以及正式依赖升级到11.49.5。坐标触控的偶发失效仍未根治；最近295项模拟回归、6台实际出帧及未签名访问403均已在存档前完成。存档期间不继续手机测试或性能调参。

下文保留各阶段记录；“未提交”、旧版本及“尚未升级”等描述为当时状态，本次代码统一纳入v0.1.4。历史存档保留原版本，以最新详细存档为准。

## 本轮最新：8070 改为原文模式（未提交）

用户随后要求阅读区英文气泡行间距减半：原文 15px 字体的 line-height 从 1.8（27px）调整为 1.4（21px），即字号之外的额外行间空隙由 12px 减为 6px。

用户已明确要求立即移除 8070 的旧翻译调用和输入框中文误发拦截，不等待宿主项目接入；中文、英文等由用户自行测试原样发送。宿主项目 `C:\xiangmu\baishihappy-2-main` 将另行适配，用户明确其识别与处理范围仅限阅读区。用户已要求删除过于复杂的提示词 MD，`HOST_INTEGRATION_PROMPT.md` 已删除，不再重建。

- 阅读、首次完整读取和增量读取的默认归档器改为不联网的原文归档，生成 `-reading.json`，不再调用短信翻译。历史 `-translated.json`、私有译文和缓存文件保留；当前阅读区仅显示原文，不显示旧译文或重译按钮。
- 中译英、回译的模型调用移除；旧 `draft` 入口仅作为原文草稿兼容入口。前端统一使用 `direct_draft` 的 `text` 正文，中文、英文、混合文字等第一次有效 Enter 均按原文提交。Shift+Enter 换行、输入法确认、重复按键处理及不确定发送防重保留。
- 后端 `validate_send_text` 不再判断语言，不删除用户首尾空白；仅校验非空、长度、有效编码和不可传输控制字符。回复记录新增 `text`，暂保留 `english` 字段兼容原生发送器，它不再代表仅允许英文。手机真实号码、完整正文、现有草稿归属、发送前落记录、只点一次及新增我方气泡核验保持。
- `/api/message-translation`、`/internal/translation` 返回 410；工作台不再创建 `TextTranslationService`。投屏脚本不再注入 `translation.js`。`/api/state` 返回 `translation_enabled=false` 供核实运行态。
- Python 全量回归 **259 项通过**；设备前端 Node 回归及真实隐藏浏览器原文回复回归通过，覆盖中文、英文、混合文字、空白保留、第一下回车单次发送、无翻译 UI、IME/重复键和不确定结果不重试。测试使用模拟发送，不代发真实短信。
- 已重载 8070 后台和它管理的投屏进程加载新模块，保留信任记录与私有资料，自动遍历仍关闭。重载初次枚举顺序与原顺序不同，随后依据原设备对应表显式恢复设备顺序，保持原设备 01 与 8080 的对应；选中手机仍为原 UDID。此处应以最后运行态核对为准。
- 当前手机发送流程待用户对原文模式实测。版本仍 `0.1.2`，未提交、未建立新恢复点、未推送。

## 2026-11-01 最新实机结果：用户手动发送已确认（未提交）

在等待一次测试授权时，只读核对发现用户已自行完成真实发送，故先前 HI/ok 测试授权问题已无需确认；Codex 不额外外发。设备 01、`+13372880228` 的记录：

- `ea5d06fa82e342ca950a85713aef3770`：21:35:19 创建，21:35:28 确认 `sent_verified`，该条 `delivered=true`。
- `70920c89870042afa858b1fdecb724c7`：21:36:10 创建，21:36:21 确认 `sent_verified`，该条 `delivered=false`（尚未确认送达，不能说未发送）。
- 第二条直接使用第一条生成的 `sms-sent-ea5d06fa82e342ca950a85713aef3770-translated` 会话，证实同一会话后续发送无需每条重新读取或刷新；两条均有发送后阅读归档。
- 单条实机发送阻断已打通。当前每条记录从创建到确认约 9–10 秒；这段时间回复框仍随 `workspaceBusy` 锁定。用户提出短时间连续多条的担忧有效，连续输入/排队体验尚未优化，不能把它宣称为已实现。用户随后强调先解决单条；本轮没有新增发送队列。
- 以上为用户手动发出的消息，Codex 仅核对已有记录。版本仍为 `0.1.2`，未提交或建立新恢复点。

## 2026-11-01 最新续办：真机发送按钮样式与已填正文（未提交）

用户再次反馈仍无法发送。本轮通过 Windows UI Automation 只读读取用户正在使用的 Chrome（`127.0.0.1:8070`），确认实际提示为“未定位到唯一可用的手机发送按钮，未执行发送”，回复框仍为 `ok`，发送按钮因此前失败被锁定。新的回复记录 `fdadea4e0f1941df9ed4463ad81aa97d` 于 20:49 创建，设备 01、`+13372880228`、正文 `ok`、状态 `failed`；此次已通过会话与手机输入核验，但尚未到 `send_requested`。它是在本轮排查期间用户重试产生的，不能一直沿用此前“没有新增记录”的初始观察。

- 实际视频帧中发送控件是绿色短横向圆角按钮（约 54×39），此前近圆形宽高比限制将其排除。`visual_composer.py` 支持此类形状，同时要求输入框内的紧凑圆角轮廓、高度、颜色、面积及唯一候选；矩形色块和多候选仍拒绝。
- 在持久化 `send_requested` 前记录 `prepared_body_verified`，证明正文已经过原生核验。只有用户发起新的手动请求，且已有 `failed` 记录证明同一设备、号码、正文、上下文在发送前失败时，才能复用手机上的相同正文，避免再次粘贴变成重复正文。兼容本次旧记录的明确发送按钮定位失败；不修改、重试旧记录。未知手机草稿、正文不同，以及 `send_requested` / `send_uncertain` / 已发送记录均不能提供复用依据。
- 前端仅对明确“发送按钮未定位、未执行发送”的错误解除发送锁，保留正文，允许下一次手动发送；不会自动重试，未知或不确定结果继续锁定。
- 最新相关 Python 49 项、设备 UI Node、真实隐藏浏览器回复区回归通过。实机完成发送前核验：号码一致、当前手机正文 `ok` 一致、唯一启用 Send 控件及视频坐标均通过，`unsent_body_owned=true`，按钮坐标约 `(0.8656, 0.9379)`；`send_attempted=false`。未点击发送，不能宣称真实发送已通过。
- 本轮为定位问题保存了一张本地诊断帧 `iphone_batch/.device-data/diagnostics/composer-current-debug.png`，位于被 Git 忽略的私有目录；普通程序仍不保存手机图片。其他诊断见 `reply-send-ready-check.json`。无需重启工作台，原生脚本按调用加载，前端刷新加载。版本仍为 `0.1.2`，未提交。
- 已调用用户现有 Chrome 工作台窗口的原生“重新加载”按钮加载前端修复，UI Automation 确认回复文字保留（2 字符）且“发送回复”按钮可用，`sent=false`。没有另开用户工作台或重启后台。此前尝试获取窗口焦点与按完整名称寻找重载按钮均安全中止，未发出 F5；最终按实际按钮名称成功刷新。
- 本轮随后捕获用户改为发送 `HI` 的新请求 `fd85b58bc3ba45a795b826f2d8561d12`：旧 `ok` 仍留在手机，草稿保护阻断。已将“证明是程序未发送的旧正文”与“本次请求的新正文”分开：下一次新的手动请求可在同号码、上下文及旧正文再次核验后聚焦输入框、Command+A 替换为新正文，再核验完整新正文和唯一 Send；非程序草稿、正文在聚焦后变动、未知/不确定发送仍保留并停止。最新相关 Python **51 项**通过，含改变正文的恢复和聚焦后正文变化保护；此前 Node/浏览器回归同样通过。
- 新正文衔接修复后，再次通过原生“重新加载”更新用户当前页面并清除失败锁定，确认文字仍保留、发送按钮可用。已在会话中提示用户可按一次 Enter，由用户发起实际发送；Codex 未触发发送或回车。
- 补齐旧视口与遗留正文的组合路径：先按号码、原生精确正文和失败记录确认程序留下的内容，再定位最新消息并核验本次及原失败基准，不能在尚未定位最新时提前把它当成未知草稿。最新 **52 项**相关 Python 回归通过；`reply-edited-body-ready-check.json` 实机确认针对 `HI` 的请求能匹配尚未发送的 `ok`，号码/上下文/按钮核验通过，`needs_body_update=true`、`send_attempted=false`。此检查未改手机正文。
- 用户担心同一会话短时间多条发送，随后明确仍要先解决单条。尚未实现连续发送队列，不得把队列说成已完成。已提出明确的一次实发授权问题（设备 01、`+13372880228`、HI 或 ok），回复前不实际外发。

## 2026-11-01 会话中断后续办：刷新按钮与回复前定位（未提交）

用户说明整批 USB 退出是主动关闭拓展坞，随后四台手机显示信任提示；不能将这次整批断连记为无故掉线，也未确认弹窗四台的编号或具体请求来源。被动日志观察范围内未记录到配对文件修改/删除，不能据此断言手机端信任一定正常。

随后用户反馈：控制连接不可用时提示刷新设备列表，但刷新按钮暂时不可点击；恢复可点后，在设备 01、`+13372880228` 会话输入 OK 回车未发送。查到实际回复记录 `30b7922cd6164192962c315a629f6bdd`，正文为 `ok`，状态 `failed`，错误为“最新会话消息已变化，请重新读取并生成回复”，尚未持久化 `send_requested`、未到发送点击步骤。未修改或重试此记录。

- 前端刷新入口不再随选择/工作台任务的 busy 状态被禁用；任务中点击会明确登记刷新，待任务结束自动执行一次。执行中的重复刷新仍禁止；设备选择、刷新及状态请求有超时，避免永久占用按钮。没有改动后台刷新锁，也没有为此重启工作台/投屏进程。
- 输入健康回执现在同步到回复区；当前设备控制连接未确认可用时，按钮和 Enter 均阻止发送，保留正文并提示恢复。连接恢复不会自动补发。
- 只读原生检查复现同一号码会话只暴露较早视口的两条消息（最新基准有 12 条），并非基准末尾；原校验在这种视口下正确阻断。新增发送前最多三次、总计 25 秒内的向最新消息定位，再以原有号码、输入框空草稿、最新 incoming/outgoing/末条消息规则核验，未放宽 `validate_snapshot`。仍不一致或换号码则停止，不输入正文、不发送。
- 验证：37 项 Python（原生发送状态机、工作台、输入）通过；设备 UI/刷新排队与请求超时 Node 回归通过；真实隐藏浏览器回复区回归通过，包括连接不可用时保留 OK、禁止请求和原有两次 Enter/防重复逻辑。设备 01 实机仅核验会话上下文：当前四条原生消息与原基准的最新消息吻合，号码一致，`verified=true`、`sent=false`。未填入正文、未执行真实发送；不能称真实短信发送已验收。
- 前端文件由现有 8070 按请求读取，用户 F5 后加载；原生脚本下次调用加载。设备 01 长时间控制仍待体验。版本仍为 `0.1.2`，未提交、未创建新恢复点。

## 2026-11-01 最新：全局性能与输入生命周期修复（未提交）

用户反馈设备 1 实际反复失控，切到别台再切回短暂恢复，后明确授权全局检查优化；随后反馈 CPU 过高并关闭网页，最后要求重新打开。已打开现有 http://127.0.0.1:8070/，没有新开工作台服务；当时保留当前选择为 07。

详细复查见 [PROJECT_REVIEW_2026-11-01.md](PROJECT_REVIEW_2026-11-01.md)。本轮新增 `video_idle.py`：媒体按需启动，取消每台服务启动时 eager 音视频；无视频/音频/JPEG 订阅且近期无需求后暂停媒体并清理 HID，需要时唤醒。原始流 EOF 可释放订阅。媒体替换与输入/健康检查共用锁，旧输入不重放。249 项全量 Python 及 Node 输入/视频/设备/滚轮专项通过，11 台已就绪且验证信任的设备已加载。

重要更正：当前健康检查已移除定期 `connectedServices` 枚举，改为在空闲且无按住键时建立实际键盘服务并派发空按键状态；它不是纯只读查询，但不输入文字、不点击、不备份、不配对。增加了取消半连接时关闭资源、4 秒派发检查、同一设备/隧道内服务目录更新及分阶段日志。此前只读检查的描述属于历史实现，不应沿用。

实测 CPU：此前整机一次采样 100%，多个未显示设备后台进程仍占明显 CPU。用户关闭页面、最终优化加载后一次采样 11.2%；按用户要求重开页面后一次采样 28.1%。不是同负载对照，不宣称长期数据。当前设备 1 实际持续操控仍未完成最终用户验收；不得把接口 ready 或测试通过当成实机操控已稳定。

信任被动记录器继续运行，USB 与配对数据未清除。06/09/13/15 仍须先建立有效信任，本轮未重新配对。没有发送短信。保持 VERSION 不变，未提交 Git 或建立存档。

## 2026-11-01 当前测试：日常使用信任稳定性（未提交）

用户今天要持续观察信任弹窗并反馈。测试说明见 [TRUST_TEST_2026-11-01.md](TRUST_TEST_2026-11-01.md)。不要在观察期间无故重载设备、清空配对或更改电源基线。

- 发现普通 CLI 重连默认可能自动配对，已在 `pmd_entry.py` 接入 `prevent_automatic_pairing()`：强制先以已有记录验证，拒绝时抛出 `NotPairedError` 而不调用自动 pair；显式 `lockdown pair` 不受阻。`controller.py` 和重试策略识别该失败为需要人工处理。5 项配对、5 项重试、12 项控制器相关回归通过。
- Windows 当前睡眠/休眠超时均为 0（从不），USB 选择性暂停开启；本机支持 S3，不支持 Modern Standby。查询近两天未找到睡眠/唤醒事件，不能断言昨晚一定休眠，也不能仅凭锁屏屏幕亮推断。
- 被动记录器已启动 24 小时：实际脚本 PID 18792（启动器 PID 27572），日志 `iphone_batch/.device-data/diagnostics/trust-watch/events-20261101-082300.jsonl`，当前信息 `trust-watch/current.json`。停止/检查方式见测试文档。原生 Windows 事件注册已实测成功；被动观察 USB 枚举、锁屏/电源通知、本地配对文件和工作台状态，不主动连接手机服务，不阻止睡眠。不把起始已故障四台算作新回归。
- 备份元数据核对：06/09/13/15 当前无 `sms-backup/<UDID>` 备份目录及短信库；09 有保存读取记录但未见备份来源，其余三台未找到保存读取记录。当前有备份的是 01/10/11，10 有含备份短信的保存记录。只证明当前留存资料，不排除外部备份或删除的历史资料。
- 苹果官方指出 iOS 11 及以后配对超过 30 天未使用可能过期；昨日刚信任/使用不能以此解释。还原位置与隐私、抹掉设备可撤销信任；iOS 16 及以后备份可能再次提示授权。身份拒绝结果已确认，原因仍未查明，避免声称一定由锁屏、USB 重启或备份造成。

## 2026-11-01 最新续办：自动检测输入与刷新兜底（未提交）

用户明确授权自动检测并恢复，刷新列表作为手动兜底。当前仍是未提交工作区，未建立新存档，`VERSION` 不递增。

- 新本地 `/input-health` 只读查询 UHS `list_connected_services`，不发送空按键、点击、文字，不执行备份、不新建信任配对。只为当前选中、持有控制权的投屏页面启用监测；空闲约 5 秒检查，拖动、按住键、近期输入或读取/发送等工作台任务时延后。
- 失效连接在同一输入锁内清理，最多重建一次并重新验证。连续 3 轮失败后停止自动重试，刷新按钮重置重试预算；手动刷新会检查当前设备输入，必要时恢复其控制权。失败/恢复期间有状态提示。
- 恢复增加连接代次，拒绝恢复期间和修复前排队的旧输入；旧按键快照也丢弃。输入失败不自动重放，不补发短信。原手动输入失败清理已移到锁内，避免清理另一个请求刚建好的连接。输入派发超时有上限。
- 投屏 `/viewer.js` 改为按请求读取本地文件，今后前端修复可 F5 加载；Python 后端修改仍需要投屏进程重载。真实浏览器暴露了原生定时器绑定问题，已修正并添加真实浏览器回归。
- 本轮先无自动配对验证已有信任，再分批重载 11 台原本就绪的投屏子进程；保留 8070 工作台、所选设备和本地资料。最终 01、02、03、04、05、07、08、10、11、12、14 均就绪，逐台确认最终脚本及健康接口存在。当前设备只读健康检查实际返回 `ready`、`recovered=true`，证明完成过一次真实输入连接重建；没有点击手机或发送短信。独立隐藏浏览器确认一个投屏页、无脚本错误、`inputReady=true`。
- 相关验证：`test_input_health` 7 项、`test_viewer_patch` 17 项、`test_video_compat` 3 项、`test_dashboard` 7 项；Node 输入监测、设备 UI、视频积压测试通过；真实浏览器监测定时器及回复输入测试通过。不是完整项目验收，真实鼠标操作仍由用户体验。
- 06、09、13、15 未就绪，本轮未重载它们。最终只读诊断：项目本地配对文件存在且必要字段完整，但 `StartSession` 返回 `InvalidHostIDError`；苹果 usbmux 服务和苹果本地文件内的其他现有记录也同样被拒绝。06 在较早一次验证曾通过，后来也未通过；目前尚未确定身份失效原因，不可断言为 USB、开发者模式或十几小时自动过期。不得为排查清空配对记录或重置信任。
- 用户另问备份是否会再次弹出信任：苹果官方 https://support.apple.com/en-gb/109054 说明 iOS 16 及以后备份时会出现信任提示；本项目完整短信读取会用备份服务，应对照弹窗时间与读取操作，不能仅凭弹窗判断配对丢失。
- 忽略目录中的诊断：`existing-trust-report.json`、`unready-device-report.json`、`viewer-reload-report.json`；只记录布尔状态和错误类别，没有记录配对证书/密钥。重载过程曾因 Windows conhost 身份检查而安全中止一次，核对后仅终止项目 Python 子进程；最终 11 台全部加载成功。

## 存档后恢复工作：按选中设备投屏（未提交）

用户已恢复工作并要求降低解码资源占用：仅人工选中的设备持续投屏，其他设备保持连接待命。当前修改未建立新恢复点，`VERSION` 仍为 `0.1.2`。

- `dashboard.js` 仅给选中且就绪的设备创建 iframe；切走先释放旧页，停止它的网页解码、订阅、音频和恢复定时器。轮询及临时暂停控制不重建当前页面。底层 USB、设备服务、后台扫描/读取规则保持原实现。
- 兼容视频接收与图片解码分离，只留一个待解码的最新 JPEG；HEVC 解码队列达到 6 帧后先让出 16ms，仍积压才重建并等待新关键帧，避免任意丢弃依赖帧。
- JPEG 服务监听客户端 EOF，最后一个客户端离开时，即使手机静止没有新帧也停止软件解码；后台任务另有 JPEG 订阅时按引用计数保留。
- 设备前端回归含 20 台仅一个 iframe、切换/重选、轮询复用及断开；`test_video_latency.cjs` 含慢图片解码追新、退出清理、HEVC 过载与正常突发；`test_video_compat` 3 项和 `test_viewer_patch` 12 项通过。尚未实机测量资源下降及操作画面延迟，没有发送短信。
- 运行中的 8070 按请求读取 `dashboard.js`，用户刷新网页即可加载单设备页面策略。投屏进程缓存 `viewer.js` 模板和 Python 模块，新的防积压及静止断开修复需投屏进程重建后加载。本轮没有重启服务或操作手机，以免打断现场；不要宣称全部运行中投屏服务已更新。

以下为此前恢复点说明。

本轮用户 F5 后反馈设备 1 有画面但无法操控。运行态后台选中/控制权均为设备 1、扫描关闭；独立隐藏浏览器只读检查显示一个 iframe、无点击遮挡、子页面 `batchActive=true`。对设备 1 `/manual-key` 发送空 `usages` 检查时返回 500，日志为 `ConnectionTerminatedError`；现有失败清理逻辑清除 HID 后，再次空按键检查返回 `{"ok":true}`。输入连接已重建，未执行真实鼠标点击、未输入文字、未发送短信；实际控制恢复仍待用户体验。诊断脚本保存在被忽略的 `.device-data/diagnostics/check-preview-control.cjs`。

最新本地恢复点 **v0.1.2**，详见 [SESSION_ARCHIVE_2026-10-31.md](SESSION_ARCHIVE_2026-10-31.md)。用户已确认主动拔下 USB，并要求“今天先到这里，明天继续，存档，存 git”。完成本地提交与对应标签后停止开发、测试和验收，不推送远端、不自动关机。下次恢复点为 **v0.1.3**。

续办重点：发送输入通道曾中断，而旧接口只确认入队，造成手机未出现英文。当前已改为同步输入，实机已验证测试英文填入并清除、未点击发送且消息数未增加；发送按钮定位仍待实机验收。最后修改会跳过兼容视频中粘贴前的缓存帧，其模拟测试通过，但用户拔下全部 USB 后未完成实机复测。不要宣称两次 Enter 的真实短信发送已验收，不要运行旧发送演示或重试历史不确定发送记录。保留另一个 Codex 会话加入的 `selected` / `active` / `controlOwner` 改动。

## 2026-10-23 及更早历史记录

当时的本地恢复点 **v0.1.1**，详见 [SESSION_ARCHIVE_2026-10-23.md](SESSION_ARCHIVE_2026-10-23.md)。当时用户要求“存档，先不验收，存 git，我要关机了”：只建立本地提交与标签，不继续开发、测试或验收，不推送远端。联系人资料功能待用户验收。当时的下次恢复点版本为 **v0.1.2**，规则见 [AGENTS.md](AGENTS.md)。

联系人资料卡片支持按固定字段接收 GPT 网页汇总结果、填写和保存；仍由用户在 GPT 网页确认发送，没有新增 GPT API。此前 90 项 Python 测试、资料导入、卡片交互、输入框与五种宽度布局检查通过；这些不代表用户验收或真实手机链路已通过。

## 以下为本次存档前的工作记录

版本推进规则（用户于 2026-10-23 指定）：今后每次 Git 提交或存档恢复点递增补丁号，下次为 **v0.1.1**。同次提交、存档及推送共用一个版本；具体规则见 [AGENTS.md](AGENTS.md)。当前仍为 v0.1.0，最新已推送提交为 `37d8714`，包含项目环境重建材料；客户端备份功能已撤回。

2026-10-23 工作区新增（尚未提交/存档）：联系人资料卡片加入姓名、年龄、工作（在职/退休）、地区、婚否、兴趣爱好、其他信息、资料依据和待确认字段。“去汇总”仍使用 ChatGPT 网页，提示词要求输出对应 JSON；用户复制结果回卡片，点击填入、检查后保存。资料保存在 `.device-data/workspace/contact-profiles`，按设备及规范化号码隔离，同一联系人不同读取记录共享资料；未知号码按记录隔离。没有新增 GPT API 调用。90 项 Python 测试、资料导入和卡片浏览器检查通过；没有操作真实手机或发送短信。

最新详细存档见 [SESSION_ARCHIVE_2026-10-19.md](SESSION_ARCHIVE_2026-10-19.md)。本地恢复版本为 **v0.1.0**，根目录 `VERSION` 为 `0.1.0`。当前工作目录是 `C:\xiangmu\qunkong`，下方 D 盘路径、旧 PID、旧未读数和旧任务属于历史记录。

当前采用授权客户端闪电深色主题，两列设备图标；后台最多 4 台连续公平轮询，按通知卡片计数并提示音，当前控制手机暂停扫描。待跟进数量按阅读区勾选的联系人去重统计，可按号码快捷打开。中文第一次 Enter 原地转英文，第二次 Enter 在当前已核验会话直接发送，禁止中文和不确定结果自动重试。资料“去汇总”导出双方纯文字并打开 ChatGPT，只填入、不发送。

存档前 USB 设备为 0；8070 工作台运行，8080 无投屏监听。84 项 Python 回归及浏览器交互检查通过。本轮没有发送真实短信；ChatGPT 实际网页返回 `page_not_ready`，自动填入仍需复验。不要运行旧发送演示脚本或删除防重发记录。用户本轮要求本地 Git 恢复点，没有要求推送远程。

## 以下为 2026-10-10 及更早历史记录

最新详细存档见 [SESSION_ARCHIVE_2026-10-10.md](SESSION_ARCHIVE_2026-10-10.md)。下方 2026-10-09 的暂停说明、旧进程编号和旧任务属于历史记录；当前状态以详细存档和最后新增记录为准。用户要求将当前代码与详细文档提交为 Git 恢复点。最新规则：后台只扫描并提示，人工点击对应提示后才打开短信会话；需要继续验证多条及系统分组通知。

## 2026-10-09 历史记录

用户要求：先存档、休息、下班。当前任务已暂停，不继续操作手机或发送短信。待用户恢复工作后再继续。

## 当前状态

- 工作目录 `D:\qunkong`；Python 为 `.venv\Scripts\python.exe`。
- 工作台固定地址 http://127.0.0.1:8070/；手机画面 http://127.0.0.1:8080/。
- 当前手机 UDID `00008030-001119CE0A93402E`。
- UI 已提高短信与译文面积，增加上方横向未读列表、当前会话读取、资料汇总和人工回复。
- 中文 Enter 翻译、再次 Enter 发送；粘贴无中文的英文、链接、数字或 emoji，Enter 直接发送；Shift+Enter 换行，输入法确认不触发。后端和手机发送流程禁止中文，发送前核验号码和正文，结果不确定不能自动重发。
- 原生遍历不用截图/OCR，收到元素回执后推进。两次完整遍历且结果一致才标记完成；超时或列表变化提示不完整。同名同预览的不同联系人保留，跨遍历原生编号变化不会重复计数。
- 密钥和手机数据保存在忽略提交的 `iphone_batch/.device-data` 内，不在存档中记录密钥。

## 最近核验的列表

统一联系人名称后：当前短信列表有 **49 个联系人、6 个未读会话**；具体未读短信条数不由列表提供，不应把会话数称为短信数。

未读联系人：

1. +1 (877) 409-8532
2. +1 (952) 356-5358
3. +1 (315) 360-2544
4. +1 (315) 430-3119
5. +1 (304) 573-8800
6. +1 (270) 315-0908

最新列表核验：56 个原生元素，两遍扫描约 6.07 秒，接口约 7.98 秒，`complete=true`，未读数 6。之后目标会话曾被打开，其未读状态可能已改变；恢复后必须重新读取，不能沿用这个数量。

## good night 任务尚未完成

用户明确授权：打开其中一名联系人，回复精确小写 `good night`，自动发送，要求快且准确。选择目标 **+1 (952) 356-5358**。

- 首次打开成功并核验号码，但发送前因历史消息快照变化被阻断；未触发真正的发送操作。
- 回复记录 `iphone_batch/.device-data/workspace/replies/73cc09856c094abf9211409b29905450.json` 状态为 `failed`，正文 `good night`。不能把旧尝试诊断中的 `sending` 当成已发送；以回复记录及原生气泡核验为准。
- 已读取目标会话，确认没有 `good night` 气泡。历史气泡在滚动后有不同的原生表示，导致全历史指纹变化。
- `native_workspace.py` 的会话读取已提速，并要求完整遍历。`validate_snapshot` 允许早期气泡的展示差异，但最新对方消息、最新我方消息及最后一条气泡均须保持一致；新消息变化仍阻断发送。该变化通过单元测试，但尚未完成真实成功发送验证。
- 续办尝试在重新读取阶段返回其他收件人 **+1 (430) 314-2530**，目标号码校验再次阻断；没有创建第二条发送草稿，也没有发送。
- 原因尚未确认：需核查手机当前会话及切换行为，不能假定是用户操作或解析问题。
- 最后只读进程核验：没有残留的 `send_good_night_once.py`、`finish_good_night_once.py`、`native_workspace.py` 或 `inspect_list.py` 执行任务；查询输出列出的两个 `python -c` 是核验本身。

诊断文件在 `.device-data/diagnostics`：

- `authorized-good-night-19523565358.json`
- `authorized-good-night-resume-19523565358.json`
- `list-speed-check.json`（会被最近检查覆盖，不必然仍是联系人列表）
- `sms-live-0A93402E-a1a7195304a34c20ab28c57dd0a95b01.json` 及译文文件：最后捕获的是 +1 (430) 314-2530。

两份执行脚本有防重复标记，不能删除标记或直接重复运行来重发。用户恢复后，先核验实际发送记录与当前会话，再修复切换和号码核验问题，最终完成单次授权发送。

## 验证及运行

- 最近全面回归 30 项通过；之后新增跨遍历编号变化和最新消息校验测试，相关扫描及工作台测试 17 项通过。
- 浏览器模拟的 9 项检查通过，包括中文两次 Enter、粘贴数字直接发送、输入法和 Shift+Enter、不确定发送禁止重试。
- 实时视频恢复验证：10 秒解码 209 帧，832×1808。
- 本地工作台重启后的根进程曾为 6580，后端为 5672；恢复时重新核验 PID 和命令，不能盲用旧 PID。
- 所有改动已写入文件，未提交 Git。详情见 `iphone_batch/WORKSPACE.md`。

## 2026-10-10 通知并行检查

- 通知监控改为最多 4 台并行，每台检查结束后间隔 30 秒；初次检查仅错开 0.3 秒。独立设备操作锁避免同一台手机扫描和人工操作重叠，草稿保护仍跳过自动扫描。
- 后台控制权限按设备临时授予，不再关闭其他手机的人工控制；只有选中手机自身正在扫描时，前端暂停它的触控。选中扫描中的手机或切离它不会中断其扫描权限，结束后恢复正确权限。
- 66 项回归通过，包括实际多线程扫描重叠、忙碌设备跳过和控制切换；前后端语法检查通过。新服务单手机一次扫描实测 2.38 秒，API 显示 interval_seconds=30、parallel_limit=4。10 台实机尚未接入验证。
- 通知点击后进入短信气泡仍缺少解锁状态的新通知实机验证，不能宣称已验证成功。没有为本次测试发送短信。

## 2026-10-10 通知 Open 实机验证

- 用户发送 `good morning`，Messages 通知号码 `+19562154700`。初次通知触控没有直接进入会话；用户指出需要先展开，再点 Open，并在手机上展开。展开后画面左侧出现 Open，但原生元素遍历没有单独返回该按钮。
- 增加与目标通知号码/正文相邻的唯一 Open 文字位置识别，并允许非分组通知两步打开；通知分钟标签变化不再影响已核验的 ID、号码、正文及分组身份。68 项回归通过。
- 真实点击 Open 成功进入该号码会话并读取/归档 4 条消息：`sms-live-0A93402E-05847e7508054142a25a7d0f3b415757-translated`。本次实机成功依赖用户先手动展开通知，自动首步展开还不能宣称已实测通过。没有发送短信，临时通知保护已恢复 false。
- 原生通知元数据没有坐标字段；手机声明支持 `deviceElement:valueForAttribute:`，但 Label、AXFrame、Frame、AXPosition、AXSize、AXActivationPoint 查询均为空，未收到异步属性回调。不能宣称当前接口已获取可用原生坐标；当前 Open 点击采用本地 OCR 几何位置加原生短信来源、号码、正文核验。

## 8070 投屏 Ctrl+V 按需粘贴

- 用户要求将投屏里的手机短信输入框作为阅读区发送失败时的人工兜底，并询问图片粘贴。本轮已实现 Ctrl+V 按需读取 Windows 电脑剪贴板，传输成功后向当前手机发送一次 Command+V 并释放；无需开启同步。中文、英文、换行、表情按原文传输，粘贴后由用户检查并手动发送。
- 本地剪贴板读取扩展为同一快照的文字和图片；支持 PNG、CF_DIBV5、CF_DIB，图片优先，转换为 PNG 后复用手机现有图片剪贴板接口。限制为 16 MiB PNG、3200 万像素；复制图片文件引用不等于复制图片内容。手机端是否允许发送图片取决于其消息服务支持，尚未进行真机图片粘贴验收。
- 读取/传输失败不会触发手机粘贴键；焦点、目标触控或控制连接变化时取消未执行的粘贴。快捷键重复按住不重放，失败不自动重试、不自动发送。8070 内嵌投屏不恢复旧的后台双向同步开关，当前页面可看到进度和失败原因。
- 40 项 Python 测试通过，覆盖本地图片转换、接口权限、键盘和输入健康；Node 快捷键、剪贴板及新增粘贴流程测试通过，包含图片优先、重复内容、失败后人工重试、失焦/断连取消和 HID 失败释放。未读取真实电脑剪贴板进行测试，未向真实手机填入内容或发送短信。
- 仅重载当时运行的 9 个投屏服务，8070 管理服务未重启，设备注册顺序/编号保留，当前选择与控制恢复至 01 号，自动遍历仍关闭。运行记录位于被 Git 忽略的 `.device-data/diagnostics/manual-paste-reload-current.json`。客户端需刷新页面加载前端；本轮未提交 Git、未递增版本。

## 2026-11-04 切换画面与视频订阅恢复

- 后台预热画布使用定时器每秒绘制一次，避免隐藏 iframe 的 requestAnimationFrame 被暂停；切换选中时立即绘制最新缓存帧。页面先切换目标画面，控制权等待后台确认后才开放，避免画面被控制请求的等待拖慢。
- JPEG 订阅断开后首次立即重试，后续失败限速退避，选中可唤醒等待；原生 HEVC 读取结束或失败后也重新订阅并释放旧 reader/decoder。静止画面不再直接等同于网络断开，已确认持续断开的状态仍显示提示。
- 真实 7 台手机连续切换 21 次：原 iframe 全部保留，切换期间新增视频订阅为 0，HTTP 失败为 0，中断提示为 0，目标画面选中状态确认最大 38ms（测试窗口自动检查时间，不代表物理显示器测量）。主动取消单条 JPEG 测试订阅后 383ms 恢复新帧，无需刷新。结果见忽略目录 `.device-data/diagnostics/warm-switch-result.json`。
- Node 针对性检查通过：test_preview_switch、test_video_connection、test_warm_render、test_video_latency 及前端语法。真实测试只切换控制归属和取消测试视频订阅，没有向手机发送触控、键盘或短信。不能据此保证物理 USB 故障永不发生。
- 当前运行服务动态读取前端文件，授权客户端内刷新一次工作台可加载本次代码。本轮未提交 Git、未递增版本。

## 2026-11-04 设备5坐标触控及上游升级评估

- 用户报告设备5单独失去左键控制，Home右键仍有效。项目左键点击、拖动和滚轮均使用UniversalHID坐标触控；右键使用Indigo Home按钮事件，两条输入路径不同。直接向设备5发送坐标滑动时，HTTP均返回成功，但手机backboardd出现unsupported service/externalAccessory日志；现有idle-keyboard健康检查不能证明坐标触控有效。
- 通过现有/api/devices/reconnect完成设备5重连，首次耗时22.3秒，随后滚动日志出现正常Digitizer事件。不能据此宣称长期稳定性已解决。
- 用户授权独立验证上游11.49.5。测试环境为忽略目录`.device-data/diagnostics/upstream-11.49.5-env`，只读复用原环境公共依赖，独立安装新版pymobiledevice3及必要依赖；原`.venv`仍为11.22.0，requirements.txt未改。官方发布记录存于upstream-releases-20261104.json，当前及候选依赖的离线wheel分别保存在upstream-rollback-wheels和upstream-candidate-wheels。
- 值得关注的上游更新：11.24.0修正RemoteXPC请求编号导致第二次请求崩溃；11.29.0键盘初始化和serve-web任务清理；11.33.1延长旧机型touch_session认证等待、降低用户态隧道空闲唤醒；11.43.0连接资源生命周期；11.49.5用户态隧道传输修复。不可将Linux专用收益当作Windows实测收益。
- 已将本项目媒体初始化等待对齐上游，至少0.5秒，仅媒体实际启动时执行，正常点击和暖流不增加等待。新增顺序/暖流不重复等待检查。新版原始HTTP处理新增_http_tasks，测试夹具补充该字段。新旧核心回归81项均通过；新版全套模拟回归295项通过。
- 独立设备5试运行在18084端口，临时暂停设备5旧viewer，结束后恢复并走正常单设备重连；其它viewer PID保持不变。还测试了只保留请求签名保护的原始上游媒体/HID实现。所有试验仅做主页导航、设置图标点击尝试、媒体重建，没有输入正文或发送短信。
- 重要限制：backboardd日志混有旧服务销毁时的合成事件，包括旧keyboard/Home服务，不能仅凭unsupported service总数判定当前触控失败。按手势统计的日志也有缓冲延迟。后续增加操作前后截图；点击后的画面未稳定确认进入Settings，部分前置画面仍在主页翻页过渡，不能把简单像素变化当作点击成功，也未建立画面时效证据。现有试验不足以证明新版根治断控或证明故障均在上游。
- 曾试验媒体重建时清理音视频/HID并更换共享会话ID，未建立有效改进证据，已撤回该实验代码；保留诊断结果，不作为正式修复交付。
- 最后设备5旧服务恢复完成，重连21.9秒，API显示ready/control_ready，未残留暂停项目进程。此状态仍只是连接与空键盘检查通过，不能等同于左键真机验收。工作台仍运行11.22.0，未全量升级、未提交Git、未递增版本。
- 用户倾向后续跟进上游更新。建议跟进正式发布版、固定验收版本，在兼容和真机验证后启用，升级收益与左键故障结论分别记录。

### 用户明确要求“先升级”后的正式接入

- 按用户最新指示，正式`.venv`已升级到pymobiledevice3 11.49.5，连同其必要依赖pmd-pytcp 0.3.9、opack2 0.2.0、ipsw-parser 1.9.0、pykdebugparser 1.10.0、ansilogs 1.1.0、bytestruct 0.2.0。先关闭已核验身份的项目后台/投屏进程，再从本地wheel离线安装并启动后台，避免运行中的旧服务混用更新中的库文件。运行记录为`.device-data/diagnostics/runtime-upgrade-11495.json`及同名log。
- 已同步根requirements-windows.lock.txt、iphone_batch/requirements.txt、README及单机说明，后续安装仍固定该版本；保留旧版wheel便于回退。无新增客户端备份功能，无Git提交及版本号递增。
- 正式升级后完整模拟回归295项通过，pip check通过，environment_check依赖差异为空。当前在线01、02、04、05、13、14共6台，均已取得实际JPEG解码画面；API连接/空键盘就绪均正常。未发现11号在线，不将设备减少归因于升级。
- 后台已重启生效，设备编号映射保留。未签名访问8070和8084根页面均为403，授权客户端访问认证保持。用户端可刷新一次加载当前连接状态。
- 本次是用户明确授权的依赖升级，不作为左键偶发失效已修复的结论；坐标触控稳定性仍需独立验收。
# 2026-11-07 手动粘贴与电脑键盘

- 用户明确要求两种入口：投屏 Ctrl+V，以及阅读区“粘贴到手机”按钮。按钮使用阅读区原文，定位当前手机短信输入框后粘贴；保留阅读区正文，由用户点击手机发送。不会核验阅读区号码与手机当前号码一致，用户需核对目标会话。
- 两条入口共用粘贴队列；单次 `/manual-paste` 在输入锁内执行 Command+V 与释放，不发送 Return、不自动重试。保持中文、换行、表情和图片原有支持；切换设备、焦点或控制连接变化取消未发出的按键。
- 阅读区粘贴成功后阻止原自动发送入口，避免同一正文既手动发送又自动发送；重新读取会话可恢复自动发送。保留正文是有意行为，重复点击粘贴仍会追加，需人工核对。
- 手动触控及按钮定位前确保外接键盘已注册，复用已有键盘连接，不盲目切换软键盘显示。按钮定位跳过 JPEG 缓存首帧，减少键盘收起后点击旧位置。不能据此宣称所有手机软键盘已永久禁用，需实机验收。
- 79 项后端模拟测试通过；手动粘贴、按钮消息来源/目标验证、快捷键前端测试通过。设备界面旧测试 `test_dashboard_devices.js:121` 仍要求未选中设备不挂载投屏，与存档的预热机制不一致；对照 HEAD 的原 workspace.js 同样失败，未在本次修改该测试。
- 本轮不执行真实短信发送、不提交 Git、不建立新存档，版本保持 v0.1.4。真实粘贴速度、各台软键盘表现仍需用户验证。

## 2026-11-07 本地存档 v0.1.5

用户随后要求“存档，存本地git”，本次保存全部未提交源码及文档，版本递增为 v0.1.5 并创建同名本地标签；不推送远端。当前恢复点见 `SESSION_ARCHIVE_2026-11-07.md`，实际提交号以 `git log -1 --oneline v0.1.5` 为准。历史阶段的“不提交/未递增”说明保留。同步 VERSION、客户端版本、README、WORKSPACE 与 AGENTS；本次存档完成后停止开发及验收，不关机，不为存档重启服务。真实粘贴速度及手机软键盘表现仍待验收，下次新恢复点 v0.1.6。


## 2026-11-12 本地双源码存档 v0.1.6

用户要求把原 8070 与原生 VNC 两套源码一起存本地 Git。原项目保留原目录，原生开发版、参考项目工作树及 Viewer 纳入 native_vnc_source，并生成校验清单和恢复脚本。当前说明见 SESSION_ARCHIVE_2026-11-12.md；实际提交号以本地 v0.1.6 标签为准。不推送，不为存档重启后台；完成后停止开发与验收。

用户随后追加首个原生 VNC 客户端安装包，要求其他 Windows 电脑也能安装。本次沿用同一 v0.1.6；安装版自带隔离 Python 和依赖，按用户安装，保留开发版目录，不自动启动手机画面，不导入本机私钥和业务数据。Apple USB 驱动仍需目标电脑准备。打包及离线检查源码纳入同次本地存档。


## 2026-11-12 再次本地存档 v0.1.7

用户再次要求“存档，存本地git”。开始时工作区干净，按约定从 v0.1.6 递增到 v0.1.7，同步版本、设备列表显示、说明和源码快照。首个安装包保持 v0.1.6，不重新打包。两套源码一并创建本地提交和标签，不推送，不启动或重启后台，不继续手机验收。当前恢复点见 SESSION_ARCHIVE_2026-11-12_v0.1.7.md。
# 2026-11-12 · 大屏自动寻号（工作区开发变更，未提交）

- 用户指定：只在当前手机大屏时，每隔 1 秒从 First 起最多检查 3 个原生控件；找到“会话详情”标题的完整手机号后立即停止，按设备和号码打开本地已识别历史。没有历史显示暂无记录，不自动采集气泡或备份。
- 退出重进大屏、切换手机、再次点击手机画面会重新寻号。点击通过原生 Viewer 窗口命中判断，排除其他窗口遮挡；手势期间及手动手机操作时暂停。后台保持单一目标连接，过期结果不更新阅读区。
- 新模块为 `native_title_probe.py`、`native_title_watch.py`；同步开发运行位置与 `native_vnc_source/client/`。现有手动气泡读取及可选自动气泡遍历保留。设备列表选中项随大屏手机同步。
- 当前 75 项原生相关检查通过。设备 01 英文标题在第 3 项命中，约 0.25–0.26 秒；设备 11 中文标题在第 2 项命中，约 0.227 秒。修复原先只匹配英文而导致反复检查的问题。
- First 已在首项时可能无新回执：零项超时后下一轮做一次受控 Next/First/Next 恢复，仍最多 3 项，不连续向下扫描。设备 11 实机复现零项超时后恢复轮第 1 项命中，约 0.077 秒；再次触发正常第 2 项命中，命中后停止。该号码暂无已保存历史，显示暂无记录。
- 电脑键盘改为可操作 Viewer 连接后后台预热，点击前刷新空键盘状态；拖动或按住修饰键时不重复刷新。Ctrl+V 保留中文、换行、表情，不附带 Return。现场仅发送空按键状态准备键盘，未代发短信、未备份。VERSION 保持 0.1.7，未提交。
- 用户要求客户端阅读区对方气泡靠左、我方靠右：改为每条消息独立背景与左右边距，按文字宽度限宽；时间和正文同侧，窗口变宽窄会重排，保留原生文本选择、复制和导出。
- 2026-11-13 继续修复电脑输入：实测鼠标点设备 03 的手机搜索框后，Windows 键盘焦点仍是 TkChild，未进入 TvnWindowClass。已在真实手机画面鼠标按下时转移原生焦点，阅读区/其他窗口及只读设备不抢焦点；本地阅读区草稿单独保存，正常重载时恢复。
- 确认 VNC SDK 的按键回调是 `(client, down, keysym)`，原包装参数写反导致 Ctrl+V 分支不触发。已修正并让 Ctrl+V 复用粘贴按钮的 `paste_current_input()`，连续重复 key-down 不重复粘贴；不附带 Return。
- 自动寻号、历史列表和读取结果统一按 `19495265268` 这样的纯数字显示，匹配先规范化；底层原记录和发送校验号码不改写。相关检查当前共 85 项通过。
- 实机打字、删除、Ctrl+V 尚未完成验收：设备 03 及原先第一排 10 台已被手动断开，保留用户设备开关；切换测试设备时遇到当前选择变化即取消。需固定一台已接入手机的短信搜索框继续验证，不应把模拟检查通过称为实机可用。两个协作子任务的挂起批准已中断，后续由主任务处理。


## 2026-11-13：原项目与 VNC 整理为平级独立项目

用户明确要求拆为两个平级项目。VNC 唯一开发源迁到 `C:\xiangmu\qunkong-vnc\src`，独立 .venv、vendor、data 和本地 Git；新仓库 v0.1.8 提交 0578c23efd143d9bf7d7bb0fd38dd90dd399b789。
桌面开发版入口和正在运行的 8 台 VNC 服务已切到新项目；设备顺序与禁用状态保持一致，数据单独保留且不进 Git。旧工作副本迁出，原 v0.1.7 标签保留。
89 个原有检查、4 个隔离检查、依赖路径、VNC --help 和离线 UI 检查通过。当前聊天工作区仍是原项目；后续 VNC 开发请在新目录开启 Codex，会话接续见新 STATUS.md。
自动底部增量尚未实现，键盘/粘贴/软键盘抑制仍待实机验收。此交付只拆分和本地存档，不推送远端。

## 2026-11-14 单台画面两侧收紧（工作区变更）

- 用户要求将单台大屏左右多余宽度收紧并落代码。仅修改原 8070 前端：桌面手机列按原始画面宽高比和实际可用高度计算，保留原普通/放大上限及工具栏最小宽度，剩余横向空间给短信阅读区。窄屏保持上下排列。
- 投屏只在画布尺寸变化时向管理页上报宽高；管理页核验 iframe 来源和 origin，按设备缓存比例。切换设备、旋转、放大/恢复、调整窗口或展开设置时重算，不重建投屏连接。工具栏取消固定高度，避免收窄后按钮重叠。
- JavaScript 语法、现有 20 台模拟设备浏览器检查、切换/预热/缩略图检查通过。额外使用实际画面适配函数核验八种窗口尺寸的普通/放大模式，以及横竖屏和设备切换；布局稳定，无横向页面溢出。1920×1080 模拟窗口放大模式的手机列从原 620px 收紧为 436px，每侧约 8px。
- 未操作真实手机或重启后台；模拟检查不等于真机验收。客户端刷新工作台加载。未提交 Git、未建立新存档，VERSION 保持 0.1.9。

## 2026-11-14 版本号右侧显示整机 CPU（工作区变更）

- 用户要求在 v0.1.9 右侧显示当前 CPU 占比，以便按负载减少手机显示和操作。增加整台电脑 CPU 百分比，与版本号固定同排；80% 起黄色、90% 起红色，悬停说明可断开暂不使用的手机。
- 后台独立线程每秒采样并丢弃首个预热值，状态接口只读取缓存，不等待采样；前端复用约每 2 秒的状态刷新，操作手机期间也更新 CPU。采样失败、数据超过 5 秒或状态请求失败时显示 `CPU --%`，避免把未知值显示为 0%。
- CPU 采样首值、零值、故障恢复、过期及原设备选择等 10 项后端检查通过；真实电脑只读采样及线程退出检查通过。模拟浏览器检查通过，覆盖四种窗口宽度下版本与 CPU 同排、警示颜色、手机操作期间刷新、未知/过期数据及断线恢复，20 台模拟设备检查无页面异常。未重启运行后台，生效需重启本项目 8070 后台并刷新客户端。未提交 Git，VERSION 保持 0.1.9。

## 2026-11-14 设备 06、09 信任连接修复及可见错误提示

- 用户报告两台已启用但无画面，重新连接也无效，并确认手机均已解锁且 USB 未断开。现场两台 enabled=true、ready=false、control_ready=false，投屏进程不存在，先前重连分别约 83 秒后失败。接入菜单反映启用策略，不代表实际连接成功。
- 只读对比确认 01 号现有信任验证通过，06、09 均未通过；两台项目记录及 Apple 服务记录分别验证也都未通过。故障在投屏启动前的信任连接阶段，不是 CPU 或浏览器解码结论，也不要求停在手机主页。
- 经本次工具批准，仅对 06、09 调用已有 /api/devices/trust 修复信任。两台均返回本地配对身份验证成功并启动投屏，随后 ready/control_ready=true，codec 配置正常。连续两次只读健康检查中，06 的 RTP 包数 2517→2759、客户端解码帧数 269→592；09 的 RTP 包数 1741→1869、解码帧数 136→304，均无解码错误且已有绘制记录。未发送触控、键盘或短信，未重启整个后台。配对资料与诊断仍留在忽略目录，不进入 Git。
- API 保留此前重连任务的失败历史；修复后的当前连接状态应结合 ready、control_ready 和新视频进度判断，不能把旧任务失败当作仍未连接。
- 前端监看卡片无图时直接显示断开、等待信任、重连中或实际失败原因，替代统一的“暂无画面”，不恢复卡片底栏、不改变启用开关语义。6 项既有信任修复回归、语法检查和 20 台模拟设备浏览器检查通过；额外核验六种占位状态及重连覆盖旧错误。刷新工作台加载提示改动。未提交 Git，VERSION 保持 0.1.9。

## 2026-11-14 将信任修复整合到页面重连

- 用户明确要求将 06、09 的恢复能力做到页面功能。增强现有右键“重新连接此设备”：停止目标旧连接后，检查现有信任；有效则直接继续，未通过时复用原有定向信任修复流程，验证成功才继续清理会话和启动投屏。独立“重新建立信任”入口保留，共用同一执行器。
- 页面和卡片增加“检查并修复信任”进度，改为只有手机出现提示时才要求确认，不宣称每次都需要手机操作。操作只持有目标设备锁，信任等待期间释放全局手机锁与设备列表锁，其他设备仍可用；普通后台启动和自动重试保持禁止自动配对。
- 信任修复与会话清理分别有 90 秒及 28 秒执行上限，画面就绪的 75 秒预算从准备完成后开始。超时或关闭后台时清理该任务及 Windows Python 子进程，避免延迟配对/清理操作。沿用 Apple 记录写入失败后只凭本地身份实际验证成功才接受的分支。
- 56 项定向后端回归通过，覆盖信任失败、目标隔离、其他设备可用、超时/关闭、等待信任不提前耗尽画面预算、旧身份有效不重复配对等。20 台模拟设备浏览器检查通过，覆盖右键点击、信任阶段提示、成功状态和其余投屏连接复用。
- 本轮仅实现与离线/模拟检查，没有再次操作真实手机或重启后台；新重连流程需要重启本项目 8070 后台并刷新客户端后加载。未提交 Git、未建立存档，VERSION 保持 0.1.9。

## 2026-11-15 本地存档 v0.1.10

用户要求“存档，存git”。本次从 v0.1.9（bf073e4）递增为 v0.1.10，保存上述原 8070 工作区修改，创建本地提交及同名标签，不推送远端。VERSION、网页版本、AGENTS、根说明及单机说明/工作区说明同步更新；历史存档保留原版本。详细范围、证据及恢复边界见 [本次存档](SESSION_ARCHIVE_2026-11-15_v0.1.10.md)。提交号以 `git rev-parse v0.1.10^{commit}` 为准，交付时另行报告。本次存档不启动或重启服务、不操作手机、不触碰平级 VNC；私有运行数据与配对资料不进入 Git。完成后停止存档工作，下次新恢复点为 v0.1.11。

## 2026-11-19 阅读区气泡中文状态（工作区变更）

- 用户要求把未送达、已送达、已读及已读时间、以短信形式发送、以 RCS 形式发送附在对应气泡下方。新增独立 AX 状态解析；发送方式和送达状态可同时显示，未送达用红字。只处理明确状态元素，不根据正文、会话顶部协议或数据库 is_read 推测对方已读。
- 双向遍览按连续访问及气泡 occurrence 关联；自动尾部读取按顺序关联。日期、无关控件、未确认气泡及访问缺口阻断关联，发送失败按钮可作为同一气泡的相邻控件。唯一衔接的历史消息更新状态并保留消息身份；状态纳入观察指纹，正文与发送上下文指纹保持原规则。
- 既有阅读记录有完整 traversal 时，在读取接口中按唯一完整气泡特征恢复状态，不改写原保存文件。设备 08 最新保存记录的两轮遍览均确认第一条旧气泡为 Sent as SMS、最新气泡为 Not Delivered；正式 8070 接口已验证两条分别返回对应状态。
- 7 项状态/历史兼容检查、13 项遍览检查、4 项双向采集检查、6 项历史账本检查通过；真实无头浏览器验证中文文本、位于气泡之后、失败样式及对方气泡不误标，JS 语法和差异空白检查通过。另运行 31 项旧 foreground 回归出现 8 个失败及 3 个错误，在独立进程加载 Git HEAD 原版模块后完全复现相同失败；本次不修改这些旧测试和既有行为。RCS 状态仅完成明确文本规则及模拟显示验证，尚无真实 RCS 元素样本验收。
- 经工具批准重启已核验身份的 8070 后台及其子进程以加载改动，原启动参数及设备策略保留；6 号经现有单设备重连流程恢复。期间 13 号已被停用，重连接口拒绝后保留停用状态；最后 01–10 均 enabled/ready=true，11–18 均停用。客户端需刷新加载前端。未触发短信发送，不修改平级 VNC，不提交 Git、不建立恢复点，VERSION 保持 v0.1.15。

## 2026-11-19 设备 01 识号后未显示单条气泡

- 用户报告设备 01 当前会话只有一条气泡，号码已识别但阅读区未显示。经正式 /api/workspace 普通 capture 接口（持有现有手机锁）现场采集成功，耗时约 14.62 秒，当前号码 +16084124605，唯一气泡及 Sent as SMS 状态完整保存。记录为 sms-live-1E79402E-a5d63c7b8fad4b14b66af94ab8b42f93-reading；没有发送、键盘输入或数据库备份。
- 找到并用测试复现一个可导致该现象的恢复漏洞：前端取消进行中的读取时递增 generation，但保留 number；后台对新 generation 建立空任务，tick 返回 awaiting_tap。旧前端仍因本地 number 非空反复请求 tick，不重新 probe，无法继续读取。没有客户端当时的完整事件轨迹，因此不把这一复现路径称为现场唯一已确认触发原因。
- 前端在已持有号码却收到 awaiting_tap 时，复用现有最多三次识号重试，重新核验当前会话再读取；到达上限后清除旧号码并提示重新点击。保留滚动暂停、过期结果丢弃和人工操作优先。新增回归先在原逻辑上失败，再在修复后通过，覆盖取消后的单气泡恢复、滚动取消重试及次数上限。
- 读取恢复、识号重试、滚动/底部恢复、发送后核对四个前端脚本通过；包含新增单条我方气泡及状态检查的五项双向采集检查通过。JS 语法、差异空白及正式接口验证通过：/foreground.js 已提供修复代码，/api/messages 返回当前会话一条消息及短信发送方式。无需重启后台，客户端需刷新加载。未提交 Git、未建立恢复点，VERSION 保持 v0.1.15。

## 2026-11-19 回车发送即时上屏与后台尾部核对加速

- 用户明确要求：准备好已知发送正文，第一次回车粘贴成功后暂存，第二次回车提交成功就放入阅读区，显示“已提交，待核对”；原生气泡识别放到后台。现有 8070 已移除翻译，未恢复翻译功能；在现有正文粘贴入口预备记录，并支持投屏 Ctrl+V 获取明确文字后预备。
- 回执含义：剪贴板写入与粘贴按键请求成功不能单独证明手机输入框最终内容；Enter 按下与释放成功也不等于运营商已送达。因此临时气泡仅标“已提交，待核对”，后续按真实气泡补上送达/失败状态。手机编辑键会废弃预备的已知正文，改由原生识别核对，避免把旧正文当作实际发送内容。
- 新增 Enter 开始/完成关联标记，在按下时冻结本次正文，按下与释放回执均成功后即时上屏，移除旧的固定 300ms 等待。用户已开始输入下一条时仍保留上一条成功回执；按键失败、控制 epoch 变化、设备/号码不匹配不即时上屏。下一条草稿和现有防重复发送状态保留。
- 待核对气泡按设备、号码及发送标记保存在浏览器本地，独立于手机历史和导出数据。正常历史衔接使用旧记录唯一后缀及新消息顺序核对，逐条替换临时气泡；相同正文连续发送按次数保留，重复回执不再追加。只有成功的原生发送核对可以按具体发送标记清除未确认项。没有基准或衔接歧义时继续保留待核对，不按正文相同就断言已发送。
- 发送核对请求向原生读取传递 expected_text；找到匹配的新我方气泡并完成唯一历史衔接后即可停止尾部扫描，不再必须凑满六条消息，保留号码确认、空输入框和底部确认。模拟同一场景由扫描六条缩短为三条，未承诺所有手机的固定秒数。
- 前端即时气泡模型、发送后核对、取消后恢复、识号重试、滚动恢复、原始粘贴/Enter 回执检查通过；真实无头浏览器验证待核对气泡立即呈现、下一条草稿保留、重复回执及连续相同正文只逐条合并、最终显示未送达/已送达。粘贴草稿浏览器检查和日期/状态浏览器检查通过；旧日期测试浏览器启动锁通过独立进程目录隔离解决。尾部加速测试、正文传递测试、七项状态检查、六项账本检查及五项双向采集检查通过。仅模拟发送，没有代发真实短信。
- 经工具批准重载核验身份的 8070 后台及投屏子进程，保留原命令和设备策略；重载前 01–10 全部 ready=true，11–18 停用。诊断记录在忽略目录 reload_outgoing_backend.json，正式 8070 前端及设备 01 viewer.js 已验证提供回执代码。客户端需刷新加载。未修改平级 VNC，未提交 Git、未建立恢复点，VERSION 保持 v0.1.15。

## 2026-11-19 设备 02 单条 RCS 气泡被重复上墙

- 用户报告当前会话只有 Are u around tomorrow? 一条气泡，阅读区出现十多条。现场实时进度文件确有 13 条相同正文、时间及控件编号，occurrence 为 12、21、30……120，每九步重访同一气泡；当时尚无该号码的保存账本，重复仅出现在本轮实时结果中。
- 现场普通采集确认顶部实际是 `Text Message • RCS \ufffc Encrypted`。原 TOP_MARKERS 没有 RCS 加密标题，遍览越过会话顶部后循环，逐条上墙把重复访问当作新出现的气泡。本轮补充 RCS/加密 RCS 顶部标记；另在起始输入框边界返回并再次确认下一控件时，判定 focus_cycle_verified，停止本轮访问。未按正文或单个控件编号全局去重，真实相邻相同气泡继续保留。
- 新增两类回归：一条气泡绕圈四轮仍只产生一条；同一路径内真实相同气泡仍保留两条。完整双向采集还验证未知顶部标记下实时快照最多一条。16 项遍览检查、7 项完整采集检查、4 项进度显示检查通过。真实设备 02 普通采集约 18.605 秒，已确认只返回一条 Are u around tomorrow?，两轮均只记录一次。正确记录为 sms-live-0132402E-f4b5201e522b40f691a0f60b6ca6480c-reading，正式 /api/messages 已确认本号码一条记录。
- 经工具批准重载本项目后台以让自动读取也加载修复，保留设备开关和选中的 02；重载前 01–10 全部就绪。用户需刷新前台替换旧的实时十三条画面。未输入或发送短信、不修改平级 VNC、不提交 Git、不建立恢复点，VERSION 保持 v0.1.15。
- 用户此前暂停的其他开发及验收不自动恢复。本轮只处理设备 02 重复气泡；此前设备 09 边读边上墙实机验证仍以实际后续验收为准。

## 2026-11-19 阅读区历史优先与显示稳定（前端变更）

- 用户报告设备 02 发送后虽立即上墙，但阅读区在本地待核对气泡、短实时快照、保存记录间来回变化，并一直显示正在检查。用户明确要求历史作为显示底座，后续仅在此基础上补充，不能反复清空历史显示少数最新气泡。
- 现场保存数据确认同一会话已有数据库 UTC 时间记录，而实时读取使用手机本地 AM/PM 时间。旧前端按整批来源替换列表、每次清空重建 DOM，并在每轮后台轮询开头显示检查中，放大了格式及数据窗口差异。
- 新增仅作用于界面显示的有序窗口合并：优先保留已显示历史，用唯一上下文对应原气泡后补充新消息、时间和状态；短窗口不删除长历史。通过 UI 日期分隔器的手机时间区分同文异时消息，避免把 UTC 与本地时间差异误认为新消息。不按正文全局去重，不改变已保存历史或发送判定。
- 阅读区改为复用原气泡和日期节点，仅插入新节点及更新变化字段。待核对气泡与真实气泡沿用显示身份，已有明确方向/时间不会被较差的部分回执退回未知。完整核对或保存文件编号变化不会重建正文、清除选中文字、覆盖草稿；已知历史日期时间保持稳定，今天跨日到昨天仍可按新证据更新。
- 重新识号时暂时保留旧阅读内容，待新号码确认后才切换；确认不同会话时仍隔离显示和草稿。同设备刷新保存记录期间不清空旧内容。后台无变化轮询不再切到检查中，完成后显示“已同步，等待新消息”。
- 浏览器复现数据库旧气泡+新发气泡，按即时回执、最新一条快照、完整快照、较差/较短快照、最终保存记录的顺序送入，消息数量始终为两条，原历史/新气泡 DOM、选中文字和草稿均保留。既有连续相同正文及防重复回执、UTC/中文日期、跨日标签、取消读取恢复、手动进度与后台安静轮询检查通过。语法和差异格式检查通过。
- 本轮只修改前端及验证脚本，不重启后台、不触发手机输入/发送/重连，不恢复此前暂停的其他验收。刷新前台加载；未提交 Git、未建立恢复点，VERSION 保持 v0.1.15。

## 2026-11-22 开发版触控诊断、新建短信与间隔约定（工作区变更）

- 用户在设备 05 的空短信列表现场确认“搜索”仍存在。底部三元素读取成功；重连后的另一轮原生读取先返回零元素，在已目视确认短信页面的临时测试连接中指定实时 MobileSMS PID 后，约 0.15 秒恢复识别。尚未把强制读取后台进程作为通用前台页面证明；该线索也不能直接解释触控失效。
- 经本次明确授权向示例号码段中的号码发送 Hi 一次，手机显示 Hi 气泡及 Not Delivered，未重发。用户验收新建操作成功，并最终确认已通过左边缘右滑返回短信列表。未发送的新建页右上角 × 对应原生 Cancel；不可把它说成左上角按钮。
- 用户确认新建流程为列表→新建→号码→回车确认收件人→再回车进入正文→正文→发送→返回列表。待跟进号码前半段相同，打开后停在正文输入框，由用户自行输入/发送，不自动返回。代码补充第二次回车、空历史兼容；待跟进入口不再触发历史补读/备份导航。自动任务返回列表失败时保留已发送状态并停止，禁止重发。
- 间隔从发送请求时刻起算，至同一设备下一次新建，核对和返回列表耗时计入间隔；等待状态称“等待下一次新建”，不占在途名额。前后端限制最多 3 台在途，历史任务大并发配置也受限制；等待期间其他设备可获得名额。持久记录支持恢复后继续剩余等待，结果不明不自动重试。
- 开发版新增按设备轮转的触控记录器，关联浏览器左键、HTTP、HID 返回及 backboardd/dtuhidd 新日志。手机日志在独立子进程解析，有界队列异步写盘，最多三份约 2 MiB 文件；不记录短信/剪贴板或键码。提供 status、mark、export 命令，见 tools/TOUCH_DIAGNOSTICS_8070.md。Windows Selector 事件循环不能使用 asyncio 子进程 transport，已使用后台线程启动/读管道并验证取消和退出清理。
- 经工具批准只重载核验身份的 C 盘开发后台，保留共享隧道及设备策略。重载前确认没有待执行/运行中的短信任务，旧失败任务没有重跑。最后 01、02、03、05 均就绪，选中恢复为 01；01 的日志接口实际 streaming、收到 30 条匹配手机日志、无丢弃或写盘错误，并实测导出。页面刷新加载新增状态与前端记录；最新前端把客户端时间单独命名，避免覆盖主机时间。
- 相关 Python 回归 120 项通过，后续对日志 Windows 兼容与取消清理继续专项检查；Node 输入/日志/指针/健康检查及语法检查通过。新间隔和三台并发仅做模拟回归，未额外发送短信做压力验收；不能据此宣称左键偶发失效或投屏 30 秒超时已根治。
- 用户关注 5 台时 CPU 偶发 90%。停止回归测试后持续采样 24 个点，整机平均约 42.1%、最高 71.7%，用户明确表示可接受；未捕捉到 90% 现场。峰值包含短命 Python 进程与 Defender；代码存在每次横幅检查重新启动 Python 的开销，未擅自改变巡查频率。采样时内存约 15.9 GiB、使用 51%、可用 7.8 GiB，UHD 620；历史 GPU/内存独立开关属于已拆出的 VNC 方案，当前 8070 为浏览器 WebCodecs 自动选择，hevc 模式不等于已证明硬解。
- 未提交 Git、未建立新恢复点，VERSION 保持 v0.1.23；未打包、未更新 D 盘安装环境、未修改平级 VNC 或皮卡丘源码。

### 2026-11-22 后续：8070 硬解检查、进程复用及两次回车修正

- 用户明确只继续查看 8070 的实际硬解路径与复用横幅读取进程；保持持续解码、每 3 秒后台绘制、预热及切换机制。只读确认皮卡丘 GPU 进程 PID 13616 的 VideoDecode 引擎约 4.85%–5.19%，证明宿主存在视频硬解活动，不能逐路保证所有手机均硬解。没有修改宿主、驱动或强制硬解设置。
- 横幅按设备复用只读 worker，每次仍建立并关闭原生会话、恢复审计目标；超时/错误回执丢弃进程，不重放当次调用；空闲 30 秒、父管道 EOF、断开和关闭清理。相关 73 项回归通过，开发后台已加载且设备策略与当时选中的 05 保留，未执行待发送短信任务。
- 两段各 15 点采样，同四台就绪，整机 CPU 平均 67.8%→46.6%、峰值 85.8%→72.4%；横幅约 2.5 秒→0.75–0.91 秒。进程 RSS 合计约 91.7→254.0 MiB，前后选中设备不同且系统负载变化，不能当作严格性能收益或新增物理内存。详见 tools/PERFORMANCE_8070.md。
- 用户随后新建立即任务 d871a38180394ba2a33f6c1d6ba31fbf，01/03/05 在号码阶段失败，任务终态 failed、3 项失败、16 项 queued，三个单元均 ready 且没有 send_requested_at。没有重跑该任务。01 原生结果只有 New iMessage、To 与号码标签，正文实际为空但 AX 未返回；03/05 最终号码字段与任务匹配，不能把此前即时不匹配归咎于历史号码重复。用户已手动为 03/05 回车两次，未再补按。
- 用户明确流程：新建→粘贴号码→回车→回车→粘贴正文→回车发送一次→返回列表。发送脚本已移除两次号码回车之间的正文/草稿判断；只重试有界的页面读取，不重复粘贴或回车。号码方向标记和 To/chip 格式兼容；正文后以单次 Enter 发送，移除该任务的图像发送按钮定位/点击。发送前持久防重发标记，失败的按键回执仍保留不确定状态并松键，不重发。
- 为新任务持久记录准备阶段及无正文内容的检查摘要。相关 66 项回归通过；新建任务会重新加载发送脚本，无需为此重启后台。还没有用新脚本完成新的三台并发真实发送验收；当前失败新建页保留，用户新建任务前需从短信列表开始。版本仍为 0.1.23，未提交、未打包。

### 2026-11-22 后续：原 19 号码任务断点继续并完成

- 用户明确要求任务 3c5a5c0e6d754c44ac5d683cb2ac0e0f 的 19 个号码全部执行。起始为设备 02 已确认发送 1 条、设备 01 发送前失败、17 项 queued。01 的空会话截图显示正文为空且有光标，原生 AX 只暴露顶部三个元素；按本任务正文仅粘贴一次，核对实际号码及正文后先持久发送标记，再 Enter 一次。发送后原生读到匹配的我方气泡及空输入框，用户也确认已发送。没有重跑旧 d871 任务。
- 返回列表不再调用要求存在历史气泡的 context 检查；仍保护未发送草稿。新增显式 resume_unsent 与签名 /api/sms-tasks/<id>/resume 接口，先匹配单元身份与持久发送记录，已确认发送项保留，确定未发送项继续；遇到发送标记而结果未确认、记录损坏或身份不符时拒绝。前端在失败原任务旁显示“继续未发送”，无需重新创建任务。已重载 C 盘开发后台，保留设备开关和选中项；没有更新安装环境。
- 首轮续跑到 5/19 时，设备 01 已发送但右滑未生效，任务按既定保护停止。新触控日志实际记录 backboardd 拒绝 CoreDevice touchscreen 的 digitizer 事件（unsupported service），对应 HTTP/HID 返回仍为 200。只重连 01，验证恢复返回列表，再次从原任务续跑；没有重发这条已确认短信。这是手机端触控拒绝的现场证据，尚未根治偶发左键失效。
- 最终原任务 completed，19 个独立单元均 sent_verified、有 send_requested_at/sent_at、身份与原分配匹配，无失败/结果不明/排队项。01/02/03 各 5 条，05 为 4 条；原 02 第一条的发送标记时间保持不变。此次真实配置同时在途 2 台、每台间隔 15–25 秒，不能称为三台同时在途验收。最终再读取四台底部控件，均为 message_list 且新建按钮可用，保留选中的 05。核对摘要见 .tmp/authorized_campaign_acceptance.json；确认发送气泡不等同全部对端已送达。
- 相关发送/续跑/草稿/空历史导航回归共 70 项通过，前端 JS 语法检查通过。未提交 Git、未建立恢复点、未打包，VERSION 保持 0.1.23。

### 2026-11-23 · v0.1.28 打包与存档

- 用户指定版本 v0.1.28；从 v0.1.23 跳至指定版本。打包加入触控诊断、只读横幅 worker、SpringBoard 短信 App 角标，以及全局遍览隐藏高亮；未读角标末端最多读 6 个 AX 元素，设备间隔 2 秒。
- 全新 host-only stage 编译安装包 `releases/皮卡丘手机工作台-0.1.28-安装.exe`，204,274,386 字节，SHA256 `9e8ae732e18afffd856d191da6fa16cf283ed62c4c7cf0aa1698012d6c2cf9a3`。零设备隔离检查、签名和运行时检查通过，载荷清单 17,876 项，未打入 `.device-data`。
- 全量 unittest 565 项中 8 fail、33 error；修复测试替身兼容后定向 107 项有 1 error、106 通过。Node 触控诊断/手动输入及前端语法检查通过。具体边界见 v0.1.28 存档。
- 安装验证器因检测到相同 AppId 的既有安装登记而拒绝运行；没有覆盖、卸载或修改现有安装。用户将自行安装。未更新安装目录、开发后台、手机或平级皮卡丘项目。
- 设备 3 会话漏气泡按用户要求留到 v0.1.29；8070 持续 30 秒画面超时及设备触控间歇失效仍待解决。详细记录见 [v0.1.28 本地存档](SESSION_ARCHIVE_2026-11-23_v0.1.28.md)。
