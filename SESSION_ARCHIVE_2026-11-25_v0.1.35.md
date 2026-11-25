# 8070 项目存档 · v0.1.35 · 2026-11-25

本次在 v0.1.34 基础上递增至 **v0.1.35**（用户于 2026-11-25 指定版本号规则：所有版本号跳过含数字“4”的版本；v0.1.35 为 v0.1.34 之后第一个可用版本）。本地提交与标签后按用户授权**强推远端**；不改 GitHub 仓库项目描述（About description）。

## 本次归档源码

### 1. 媒体会话 churn 修复（v0.1.34 遗留专项主修复 A）

- 根因：dashboard 的周期就绪探测（`/codec`、`/input-readiness`）会唤醒每台未选中设备的媒体，而 idle 策略 5 秒后暂停，形成每 6–8 秒一轮的“暂停→唤醒”媒体会话 churn；10 台并发时每小时约 600 次 stop_all_streams、1200 次 start，是 viewer 偶发掉线的主要嫌疑。AAC-ELD 解码失败只是每轮唤醒的伴随噪音，不是根因。
- 修复：`/codec` 缓存参数集直接应答不唤醒；`/input-readiness` 三态门控（选中设备唤醒并探测；未选中但媒体活跃只探测不唤醒；已暂停返回 standby）；待机暂停保留 codec 缓存。
- `dashboard.py`：重连完成验收只对选中设备要求输入就绪，未选中设备（合法待命）不再误报失败。

### 2. Windows 音频无解码 keepalive（防御 B）

- 新增 `video_idle.audio_recv_keepalive`，在非 macOS 上替换上游 `_audio_udp_recv`：持续消费 AAC-ELD RTP、维护 RTCP 计数后丢弃，不再创建解码器、不再报错、不再广播。设备端音频会话保留作视频配对信号。

### 3. 坐标触控失效的被动检测 + HID 重建（新模块）

- 新模块 `iphone_batch/hid_rebuild.py`：检测 backboardd 日志中 `ignoring digitizer event … unsupported service`（设备 5 左键失效的现场证据，历史第三次复现：11-04、11-22、本次），有界地自动重建 HID 服务（clear_input + 重连 UHS/Indigo + 重注册键盘表面 + 0.5 秒认证等待），30 秒冷却、输入锁最多等待 3 秒、绝不重放输入；不碰媒体会话。
- `touch_diagnostics.py` 新增 phone-log 观察器钩子；`viewer_patch.install()` 接线。尚未在实机复现中验证“仅 HID 重建是否足以恢复授权”（下次 5 号失效时观察）。
- 新增 `test_hid_rebuild.py` 7 项；相关回归共 170 项通过；顺手修复 `test_device_reconnect.py` 夹具缺 `discard_ready` 的 v0.1.34 遗留。

### 4. 压测验证

- 1 小时自动切换压测：90 次切换 0 失败，10 台 ready/control_ready 100%，0 恢复事件，CPU 均值 66.9%、峰值 91.7%。
- 手动快速随机切换：34 次切换 0 掉线、0 强制重启；控制就绪短暂过期 4 秒内自愈。观察记录在忽略目录 `iphone_batch/.device-data/diagnostics/`（switch-stress-*.jsonl、switch-manual-*.jsonl、keepalive-accept-*.jsonl）。

### 5. 皮卡丘协作：webview 后台节流修复

- 现象：8070 页面在宿主多开切换（CSS 隐藏）后，10 台设备画面订阅在 15–20 分钟内陆续断流（`/video-health` forwards 时间戳证据）。
- 皮卡丘侧实施：仅对 apple/8070 分区 webview 设 `backgroundThrottling=false`（will-attach + did-attach 兜底），其余平台不动；自验证 6 个隔离场景通过。
- 8070 侧验收：两条标准（① 页面后台化 60 分钟；② 页面可见、画面静止 60 分钟）各 60 轮每分钟采样，**均为 0 断流**。协作记录见 `PIKACHU_CHAT.md` 与 `PIKACHU_PAGE_KEEPALIVE_2026-11-24.md`。

### 6. USB 枚举丢失问题（用户操作解决）

- 根因：Apple 用户态驱动（WUDF）在 18 台同时枚举时崩溃（系统事件 10116，历史 11-19/11-21 也有同类记录），部分设备 usbmux 接口脱机，与音频隔离修改无关（崩溃发生在代码重载之前）。
- 用户通过爱思助手“驱动修复”安装 538.0.0.0 版驱动后 18/18 稳定；iPhone 6、9 的信任问题由用户手动确认恢复。

## 安装包 v0.1.35

- `releases/皮卡丘手机工作台-0.1.35-安装.exe`，204,276,304 字节，SHA256 `241ef287a9c966ad74404fae22f1f1733df4e9f756df073130353a1ccbcc31e4`。
- 全新 stage + `--host-only`；隔离验证全过（isolated runtime、依赖 imports、零设备工作台签名 200/未签名 403、版本 v0.1.35、启停拒绝、直接启动拒绝）；载荷 17,877 项逐文件 SHA256，`hid_rebuild.py` 已纳入，无 `.device-data`/测试/业务数据。
- 用户已手动安装升级（验证器因已有同 AppId 安装登记按规范停止，未覆盖安装）。
- `releases/` 按用户 2026-11-25 指定只保留当前交付安装包及配套文件；旧包已删除，回退靠 Git 历史重新构建（已写入 PACKAGING_8070.md）。

## 版本与规则更新

- 版本号跳过含“4”的规则写入 `AGENTS.md`；VERSION、客户端版本显示、README 同步为 v0.1.35。
- 构建白名单加入 `iphone_batch/hid_rebuild.py`。

## 已知遗留

- 设备画面持续 30 秒超时仍未解决；未宣称相关修复。
- 5 号坐标触控偶发失效（backboardd 拒绝 digitizer）未根治；被动检测 + HID 重建已上线但未实机复现验证。
- 上游 pymobiledevice3 锁定 11.50.3（最新 11.61.1 未评估升级）。
- 皮卡丘宿主安装包由皮卡丘项目另行交付；8070 新包实机长期运行由用户后续体验。

## 边界

- 未发送短信、未代发真实输入；切换压测仅调用工作台 select/只读接口（AUTO_HOME_ON_DESELECT 关闭，无 Home 按键注入）。
- 未修改平级 VNC 项目；皮卡丘代码由皮卡丘会话实施，本仓库未改动其源码。
- 远程强推由用户明确授权；不改 GitHub About description。
