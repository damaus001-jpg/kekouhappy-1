# 项目环境重建验证

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
