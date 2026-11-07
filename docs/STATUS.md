# 当前状态 · V0.11.3 / git-r11

本次发现用户Windows上的Ollama `/api/chat` 持续返回 HTTP 500，本地WebSocket已建立，持久化音频任务未提交，也未丢失。旧代码每数秒重试并重复打印完整异常，且遮蔽Ollama返回的错误类别。本版加入有限归因、慢重试和诊断，不试图通过重新下载安装模型掩盖运行时不兼容。**尚无现场Ollama server.log，无法确认根因是音频编码器、GPU资源、模型runner还是其他问题**；人工需查看 `%LOCALAPPDATA%\Ollama\server.log` 并做独立短音频测试。扩展与服务0.11.3，安装器0.8.3。

# 当前状态 · V0.11.2 / git-r10

本轮仅修复Windows STOP_LOCAL_ASR 路径实参及ASR配置GET/POST的扩展来源兼容问题。保留扩展Origin约束和无Origin时的扩展身份请求头；未知网站来源不能借此调用配置接口。两处已通过构造单元、CORS和模拟浏览器测试，但没有在用户Windows Edge上执行。

**不改变识别模型、现有缓存、已保存笔记或100秒深度整理等待机制。** 真实Ollama Qwen语音质量仍需原生目标环境测试。

---

# 当前状态 · V0.11.1 Ollama ASR接入 / git-r9

基于V0.11.0/git-r8新增本机Ollama适配：安装器选择 `ollama17` 后只复用本机已安装模型，走 `http://127.0.0.1:11434/api/chat`；不安装 PyTorch 或额外 `.venv-qwen`。原Whisper/native Qwen仍存在。设置页面可保存“**下次启动**”的识别引擎选择，旧缓存不被修改。

扩展0.11.1、服务0.11.1、安装器0.8.3、音频协议5。合成WAV与HTTP API测试通过；**没有真实Windows Edge、RTX5080、Ollama Qwen权重的端到端验收**。Ollama只有已处理音频窗口时间戳，没有可靠逐词对齐，说话人不强行归属；外文继续送既有翻译流程。更详尽边界见[升级说明](UPGRADE_V0111_OLLAMA_ASR.md)。

原有P0问题——长文整理100秒、非流式/无断点续跑——依然未修；ASR精度和现场服务稳定性仍待真实节目测量。

---

# 当前状态 · V0.11.0 ASR接入预览 / git-r8

之前0.10.2只完成模型调研；本版已写入Qwen3-ASR-1.7B-hf/0.6B-hf与ForcedAligner的真实原生Transformers调用、独立worker、单入口安装和手动回退。**未下载/运行真实模型，未做用户RTX5080上的识别质量验收。** 默认保留原引擎，只有目标机安装/加载/合成运算检查全部成功才切换。

扩展0.11.0、本地服务0.11.0、安装器0.8.2、音频协议5。新引擎以短块增量接入现有缓存、翻译及说话人流水线，不是原生逐token流式。不能宣称更换ASR已修复翻译、姓名绑定、长文100秒超时或可靠续跑。

入口：`docs/UPGRADE_V0110_ASR.md`；验证：`qa/V0110_ASR_TEST_REPORT.md`。计划VK-044/AC-051保持in_progress/target_pending。既有下载/阅读/字幕保护不回退，无关内容过滤仍移除。
