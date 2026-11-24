# 项目环境重建验证

## v0.1.31 存档检查 · 2026-11-23

- 版本从 v0.1.30 递增；本次源码提交与标签使用 v0.1.31。远端强推由用户授权。详见 `SESSION_ARCHIVE_2026-11-23_v0.1.31.md`。
- v0.1.30 安装包全新 stage 构建，离线零设备隔离检查、载荷清单核对和 53 项目标专项检查通过；包内 17,876 个文件，不含运行时数据。安装器未运行，因为已有同 AppId 安装，按项目规则交由用户原目录覆盖升级。
- 该包尚未在新电脑完成手机投屏实机验收。初次设备启动等待延长不能证明 IPv6/WinTun 失败已修复；设备画面持续 30 秒超时仍待解决。
- 灾备入口已补充 `Recover.ps1 -Ref v0.1.31` 标签恢复路径；已强推 `master` 并推送标签，确认固定版本可由 GitHub 标签恢复。未改变 GitHub About description。
- `master` 与 `v0.1.31` 已回读确认指向本次恢复点；此前版本标签保留。

## v0.1.19 皮卡丘集成后台检查 · 2026-11-21

- 37 项 Python 回归通过：host_control、backend_control、workspace_access、dashboard。覆盖动作/目录/时间绑定、并发 nonce 防重放、操作互斥、未授权启停提前拒绝、安装缺失统一提示、真实后台方法向隔离子进程传递 serve 凭据并彻底关闭。USB 隧道入口在测试中被隔离。
- 最终 `PhoneWorkbench8070-0.1.19-Setup.exe` 已在中文、空格目录实际安装，移除开发机 PATH 后运行。内置 Python/Node/Tcl/C++ 原生依赖均在安装目录加载，零设备临时端口工作台签名请求 200、未签名 403，UI 显示 v0.1.19。
- 签名 status 返回 stopped；无授权 start/stop 返回 AUTH_REQUIRED；直接运行安装目录 dashboard 在发现设备前拒绝。包内无独立客户端和启动器。当前用户 64 位注册表 InstallDir 与协议 1 正确；卸载后 Python、策略文件、安装登记均已清理，测试副本没有保留为正式安装。
- 皮卡丘会话报告正式目录编译通过，Node/Python 联合隔离调用和签名固定向量通过，菜单真实 Electron 隔离交互/四主题/忙态/原左键回归通过。皮卡丘没有重新打包安装版，当前在用 1.16.28 Signal 隔离版不会自动得到这些改动；需使用配套正式源码构建。未自动启动完整宿主或重启已安装客户端。
- 没有通过真实手机验收新安装目录的 USB 共享隧道/管理员授权/控制重连，也未在另一台物理电脑端到端试装；Apple 驱动、信任、开发者模式仍需用户准备。现有开发后台未用于包级或联合测试，不发送短信。
- 用户验收前要求本地存档及 Git 恢复点，本次统一 v0.1.19 并建立对应标签，不推送远端。存档不重复执行实机操作。皮卡丘菜单专属提交为 `f467dc6c66a7cef9a9a7fe518146019b3c300a98`；后续 Signal 工作不属于本次 8070 存档范围。最终包哈希与范围见 `recovery/RELEASE_8070_0.1.19.json`；v0.1.18 标签保留。

## v0.1.17 本地存档检查 · 2026-11-20

- 本次只建立本地 Git 提交及标签，不推送，不为存档重启后台、点击手机或发送短信。
- 六个相关 Python 模块合计 94 项通过：test_device_reboot、test_device_reconnect、test_input_readiness、test_input_health、test_viewer_patch、test_native_ui_scan。日志中的连接错误为故障模拟用例的预期日志，最终结果 OK。
- 六项 Node 回归通过：test_pointer_input.cjs、test_two_finger_input.cjs、test_control_release.cjs、test_input_health.cjs、test_screenshot_ui.cjs、test_device_reboot.cjs。
- dashboard.js、viewer.js、pointer_input.js 的 node --check 通过。归档的两份诊断脚本通过 Python 编译和 --help 检查，没有执行其真实手机入口。
- 本会话已完成真实无头 Edge 配置界面检查：795 个号码、50 条文本、20 台模拟设备、定时与独立间隔草稿保存/恢复通过；窗口 1280×720、1366×768、1024×600、1600×900 检查均确认保存按钮在视口内、弹窗和表单无外层滚动，较小两档额外检查任务名称输入框无横向越界。这些是界面模拟，不能作为 20 台手机实际并发验收。
- 两种截屏保存已获用户验收。设备 1 重启及普通控制恢复已实测。新号码三条实验发送、底部控件识别、持续通知横幅读取属于本会话此前已完成的实机探索，未在存档时重跑。
- 正式号码任务仍只有配置草稿界面；后台调度、原子领取、Windows 通知、自动横幅巡查及日统计尚未接入。旧 v0.1.16 记录的前台读取测试不一致仍保留，本次没有宣称 Python 全量测试通过。
- Git 排除 `.tmp`、`.device-data`、号码 TXT、截图、浏览器资料、配对及签名密钥、业务数据库。未复跑全新 Windows 安装或全部手机恢复演练。

下文保留历史环境和旧版本检查结果。

此次仅增加项目层面的安装材料，客户端页面、服务接口及浏览器存储逻辑保持 v0.1.0 原状。

已验证：

- 将源文件与依赖锁定清单复制到独立目录，不复制原 `.venv`。
- 在该目录执行 `Install.ps1 -SkipSystemInstall`，从零创建 Python 虚拟环境并安装 118 项依赖，退出码为 0。
- `pip check` 通过，锁定版本无不一致项。
- Python 3.13 x64、Node 24+、浏览器与苹果驱动检测通过；独立目录中没有翻译密钥，检测如实报告未配置。
- 使用独立虚拟环境运行原有 84 项 Python 测试，全部通过。
- 独立目录工作台成功启动，首页及 `/api/state` 均返回 HTTP 200。

边界：本次复用本机现有 Windows、Python、Node 和苹果驱动，Python 下载包部分使用 pip 缓存；没有执行 Windows 重装或在全新实体电脑上安装系统软件。首次新电脑安装路径和权限仍需现场确认。

没有使用真实手机发送短信。项目恢复不自动复制客户端业务记录、登录状态或配对信任。

## v0.1.16 存档检查 · 2026-11-19

- Recover.ps1、Install.ps1、Start.ps1 的 PowerShell 语法解析通过；此次未运行安装或重启后台。
- tools/environment_check.py：Python 3.13 x64、锁定依赖、模块导入、Node 24+、浏览器和 Apple 驱动检测通过；pip check 无损坏依赖。
- 五项真实无头浏览器回归通过：test_send_scroll.cjs、test_reading_stability.cjs、test_outgoing_receipts_browser.cjs、test_foreground_progress.cjs、test_followup_selection.cjs。不连接手机发送短信。
- 七个 Python 测试模块合计 58 项，48 项通过，test_foreground_reader 中 8 项失败及 2 项错误。失败路径均首先返回 awaiting_tap，旧测试预期 tick 直接识号；新流程要求先 probe。其余遍览、双向采集、状态、进度、未确认读取和短尾部速度模块通过。此存档保留该测试不一致，不能报告 Python 全量通过。第一次从根目录启动这些测试时有模块导入错误，改到 iphone_batch 目录后得到上述结果。
- 未在全新 Windows 电脑重装演练，未验证重新安装授权客户端或重新配对全部手机；不将本机环境检查等同于灾难恢复全链路实测。
