# 项目环境重建验证

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
