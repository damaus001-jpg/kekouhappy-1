# 已提取短信自动翻译

`sms_collect.py` 提取结束后默认调用 DeepSeek 翻译已分类的文字短信，生成独立的 `*-translated.json` 和中英对照 `*-translated.html`。使用 `--no-translate` 可仅提取。翻译失败时保留原始提取文件，可用以下命令重新翻译；已有译文复用本机缓存。图片不翻译，不发送短信，不合并重复记录。

```powershell
.\.venv\Scripts\python.exe iphone_batch\sms_translate.py iphone_batch\.device-data\diagnostics\sms-collected-3C32802E.json
```

密钥保存在 Git 忽略的 `.device-data/deepseek.json`，也支持 `DEEPSEEK_API_KEY` 环境变量。模型采用 `deepseek-flash`。

2026-10-08 真实调用完成 76 条已提取文字记录的翻译，API 请求两次。含重复遍历记录，不代表 76 条独立短信；完整历史与时间顺序仍需按原提取记录核对。
