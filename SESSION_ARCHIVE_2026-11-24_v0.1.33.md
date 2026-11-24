# 8070 项目存档 · v0.1.33 · 2026-11-24

本次在 v0.1.32 基础上递增至 v0.1.33，统一用于本地提交与标签。按用户当次授权**不推送远端**；不改平级 VNC 项目或 GitHub About description。

## 本次归档源码

- 修复设备 5 会话对方号码识别失败：AX 焦点遍历落在 SpringBoard 状态栏（时间/信号/Wi-Fi/电池元素循环），未进入 MobileSMS，标题识别为空转。对照诊断显示设备 1/2/3 的 iMessage（蓝色）会话默认遍历即正常（Back → FaceTime → 标题 → `Your iMessage` 气泡 → Delivered）；设备 5 为 SMS（绿色）会话（Back → 标题 → `Your Text Message` 气泡 → Send failure/Not Delivered → `Message, Text Message, SMS`）。
- 新增 `lock_sms_audit_target()`：经 OsTraceService 查询实时 MobileSMS PID 并执行 `deviceSetAuditTargetPid`，仅当 PID 唯一时生效，失败静默返回。
- `ForegroundAXSession` 建立时锁定一次目标；`probe_title` 检测到遍历结果全部为状态栏特征时自动锁定并重试一次。正常设备路径零变化、零额外开销。
- 每元素 200 毫秒预算保留：它是卡住时的放弃上限而非停留时间（实测元素响应 0.03–0.15 秒），命中标题立即返回。
- 新增 3 项测试：状态栏判别、锁定后重试成功、锁定失败保持原返回。

## 构建和验证记录

- `test_native_foreground` 21 项全过；核心组 65 项全过；Python 语法检查通过。
- 经用户授权重启 C 盘开发后台加载改动；用户实机验证：设备 5 之前无法识别的会话现已识别对方号码。
- 诊断脚本与结果保留在 `.tmp/`（忽略目录）：`diag_title_05.py`、`diag_title_010203.py` 及对应 JSON。
- 本次没有构建安装包；安装包仍为 v0.1.30。设备画面持续 30 秒超时仍未解决，未宣称任何相关修复。

## 边界

- 不访问或操作手机内容、不发送短信；未更新 D 盘安装环境，未修改平级 VNC 或皮卡丘项目。
- 未推送远端（本次明确不强推）；远端 `master` 与 `v0.1.32` 标签保持原状。
- 客户端版本显示保持 v0.1.30（跟随最后打包版本），历史存档保留原版本。
