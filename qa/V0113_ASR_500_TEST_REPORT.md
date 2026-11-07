# V0.11.3 Ollama 500 故障处理：测试报告

日期：2026-11-07；环境为容器 Python3.13 / Node22 / 模拟HTTP响应，不是用户 Windows Edge。

- 单元与仓库一致性检查：`python scripts/run_checks.py --suite unit`，**339项Python、263项JavaScript通过**；源码编译、Git安全门禁通过。
- 新增9项模拟测试：Ollama 500 runner中断/音频投影器/内存/未知错误分类、响应隐私、正常转写无回退、durable音频数据未删且可手动重试、WAV16kHz校验。
- 设置页面回归：`python tests/browser_asr_settings_v0112.py` 通过（真实DOM，但扩展权限/模型为替身）。
- 未在用户Windows运行真实 `frozenlab/qwen3-asr:1.7b`，没有他的Ollama server.log，不知道现场500具体原因；本包**不修复Ollama内核/显卡运行器崩溃**。未运行全浏览器套件，不应声称已全部通过。
- 本版未修改ASR数据表、VKN5报文、音频采集格式、模型权重、用户笔记；现有失败任务保留，遇连续5xx仅延长下一次重试时间，明确重试控制可清除。
