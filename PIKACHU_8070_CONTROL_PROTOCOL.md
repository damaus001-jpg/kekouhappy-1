# 皮卡丘 / 8070 后台接入协议 v1

当前协作：8070 会话 `01a1faf1-25cd-7853-9c07-a91085868b3a`；皮卡丘会话 `01a1ff4d-45db-7b82-b017-d38f46a6750c`。本次修改不操作真实手机，不重启现有开发后台，不推送远端。

## 宿主界面

两处“打新增”图标使用同一菜单：状态、启动后台、彻底关闭后台。没有“打开苹果工作台”项。沿用现有苹果页面入口。启动/关闭中禁用重复操作，两个位置共享状态。缺少安装注册记录、运行时或控制脚本均显示“安装文件缺失”。关闭影响该安装目录的全部设备连接。

## 安装发现和进程调用

正式安装器将向 HKCU（64 位视图）的 `Software\PhoneWorkbench8070` 写入 `InstallDir`（REG_SZ）、`Version`、`ControlProtocol`（REG_DWORD，1），卸载时清除。宿主不猜固定目录，不执行用户传入的命令。校验安装目录内 `runtime/python.exe`、`iphone_batch/host_control.py` 及 `8070-host-policy.json` 存在，策略为 `{"protocol":1,"mode":"pikachu-only"}`，然后使用参数数组、`shell:false`、`windowsHide:true` 启动：

```
<InstallDir>/runtime/python.exe <InstallDir>/iphone_batch/host_control.py status|start|stop
```

cwd 为 InstallDir；清除 PYTHONHOME/PYTHONPATH；PATH 首位为 InstallDir/runtime，设置 PYTHONUTF8=1、PYTHONIOENCODING=utf-8。操作仅在 Electron 主进程中执行，渲染层 IPC 只接受三种固定动作。宿主自行维护 starting/stopping 状态并串行化请求，失败后重新查询；进程返回前不能报告“已关闭”。status 不启动服务、不连接手机。建议状态查询超时 15 秒，start/stop 120 秒，stdout/stderr 均限制大小。

## stdin 授权信封

复用现有 `%LOCALAPPDATA%/PikachuSmsBridge/workspace-access.key`（64 位十六进制文本，解码为 32 字节 HMAC key）。凭据由皮卡丘现有模块创建，不向渲染层返回，不放命令行/日志。每次调用向 stdin 写一行 UTF-8 JSON 并关闭 stdin：

```
{"v":1,"timestamp":"<Unix秒>","nonce":"<随机16字节hex>","signature":"<HMAC-SHA256 hex>"}
```

签名原文为下列字符串（UTF-8，无结尾换行）：

```
pikachu-8070-control-v1\n<action>\n<canonicalInstallDir>\n<timestamp>\n<nonce>
```

`canonicalInstallDir` 是真实绝对目录，小写，反斜杠替换为 `/`，无末尾 `/`（如 `c:/users/用户/appdata/local/programs/phoneworkbench8070`）。宿主用 `realpathSync.native(InstallDir).replace(/\\/g,'/').toLowerCase()`；Python 用 `Path.resolve()` 后相同转换。签名绑定动作和安装目录，允许时间偏差 30 秒，nonce 原子落盘防重放。不会把网页请求签名直接当作启停签名。

## stdout 与退出码

只输出一行 UTF-8 JSON；业务日志仍写各自日志目录：

```
{"protocol":1,"ok":true,"action":"status","state":"running","version":"0.1.18","process_count":3,"message":"后台运行中"}
{"protocol":1,"ok":false,"action":"start","state":"unknown","code":"AUTH_REQUIRED","message":"请通过皮卡丘操作8070后台"}
```

state 为 `running`、`stopped`、`residual`、`unknown`；`residual` 表示主服务停止但仍有本安装目录相关进程，可彻底关闭。开始/结束操作前后均由后台核验实际进程。残留或已有外部隧道时保留现有拒绝接管规则。

退出码：0 成功，1 操作失败，2 安装文件缺失，3 授权失败，4 其他启停操作进行中。code 分别为 `OPERATION_FAILED`、`MISSING_FILES`、`AUTH_REQUIRED`、`BUSY`。宿主不能把非零退出码或不合法 JSON 当成功。

## 页面主题联动（独立于后台启停）

工作台在样式表加载前提供 `window.pikachuWorkspaceTheme.apply({version:1, theme})`，返回布尔值。主题仅接受 `pink`、`blackGold`、`murongPurple`、`clearWaterBlue`；非法请求返回 false，不更改显示或存储。粉色强调色为 `#FF70B6`，紫色 `#B48EAD`，蓝色 `#4AADE8`。金色撤销全部主题覆盖，精确沿用原配色。仅调整装饰性强调色，深色底和错误、资源警告等语义色保留。

皮卡丘通过已有 Apple webview 的 executeJavaScript 桥发送主题；仅在 `http://127.0.0.1:8070` 顶层页面调用，主题切换时广播全部已挂载的 Apple 页面，并在 dom-ready/did-finish-load 后补发。工作台以 `pikachu-workspace-theme-v1` 为 localStorage 键记忆主题，同源窗口通过 storage 事件同步。首次无记录默认金色；存储不可用不阻断即时换色。独立浏览器没有额外跨客户端通信服务。安装器固定黑底加 `#FF70B6`，不跟随主题，不提供主题切换。

验证：`node tools/test-workspace-theme.cjs`；隔离浏览器验证使用 `<Electron.exe> tools/test-workspace-theme-electron.cjs <皮卡丘项目目录>`，通过内存 HTTP 协议处理器加载实际工作台样式和双方桥接脚本，不连接真实后台或手机。

## 启动约束与交付边界

新安装包移除独立 Electron 客户端、桌面及开始菜单启停入口，部署上述策略文件。安装模式下 Backend.start/stop 与 dashboard.main 均检查授权；后台子进程使用独立短期启动凭据，直接运行 dashboard.py 在发现设备前拒绝。普通浏览器仍受原有网页签名校验。

这用于限制常规绕过入口，不是同一 Windows 用户或管理员之间的安全隔离：能读取同用户密钥、修改安装文件的人仍可仿造调用。现有 0.1.18 独立安装包不具备此约束，源码开发模式保留现有启动方式，待两边联调后才生成新安装包。用户取消 UAC 时正常返回失败，不报告启动成功。共享 USB 隧道的 Windows 管理员授权无法通过菜单整合取消。
