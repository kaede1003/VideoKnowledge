> **安装器0.8.4补充：** 此文是0.11.1接入时的说明。现在如果本机还没有 `frozenlab/qwen3-asr:1.7b`，统一安装器会通过 Ollama 自动下载，再做音频自检；已有则跳过。详见 [统一安装器0.8.4](UPGRADE_INSTALLER_084.md)。

# V0.11.1 · 使用已安装的 Ollama Qwen3-ASR-1.7B

此版本基于 V0.11.0/git-r8，**新增** `ollama-qwen3-asr` 后端。安装时不会重新下载已有的 Ollama 模型，也**不需要 PyTorch、CUDA wheel 或 `.venv-qwen`**。使用 Windows + Edge 原来的音频采集、缓存、WebSocket、翻译和字幕核对协议 VKN5。原生 Transformers Qwen 和 Whisper 两条路径继续保留。

## 适用版本与保护

- 扩展 **0.11.1**，本地服务 **0.11.1**，安装器 **0.8.3**，传输协议 **5**。
- 不升级/清空 `asr_profile.local.json`（安装选择时才原子写入）、`ASR_SETTINGS.bat`、`.venv`、`.venv-qwen`、Whisper/Qwen/Ollama权重、SQLite音频缓存、浏览器笔记及音视频缓存。
- 配置文件由安装器或本地设置接口写入；写入前先探测确切模型名称并发送**合成静音音频**验证所需音频接口。不查询视频内容、不上传云端。失败不改已有选择。
- 实际ASR加载成功与否需看 `/health` 的 `asr_backend.status.loaded` 或成功转写后的新记录标记；安装器的静音检查不表示真实节目准确率已经验证。

## 安装和切换

1. **先导出重要笔记**；停止采集/采图，等可处理的缓存完成，再运行 `STOP_LOCAL_ASR.bat`。不要删除旧缓存。解压升级包，**将里面的文件与子目录合并覆盖**到原项目根目录（例如 `D:\VideoKnowledge_Git_Project`），不要套成 `extension\extension`。
2. 在普通 PowerShell 中检查 Ollama：

   ```powershell
   ollama list
   curl.exe http://127.0.0.1:11434/api/tags
   ```

   确保存在 `frozenlab/qwen3-asr:1.7b`（或实际已安装的其他同类 ASR 模型标签）。**不要把语音模型名写到用于知识总结的 `qwen2.5:3b` 输入框。**
3. 在工程根目录选择 ASR，复用现有安装入口：

   ```powershell
   .\INSTALL_ALL.bat -Profile asr -AsrProfile ollama17
   ```

   使用不同 Ollama 标签时：

   ```powershell
   .\INSTALL_ALL.bat -Profile asr -AsrProfile ollama17 -OllamaAsrModel frozenlab/qwen3-asr:0.6b
   ```

   **不会调用 PyTorch 下载路径，也不会启动独立 Transformers worker**。现有 `.venv` 仍安装/保留基础 Whisper 依赖作为回退。选择前本机端口11434必须能连接并返回语音响应。若模型加载不支持音频，安装器报告失败且不切换。
4. `START_LOCAL_ASR.bat` 启动当前配置；在 `edge://extensions/` 重新加载原扩展至0.11.1并刷新视频页。确认 `http://127.0.0.1:8765/health` 中 `asr_backend.backend` 为 `ollama-qwen3-asr`，`asr_backend.configured_model` 是你安装的标签。首次成功听写后新记录包含 `asrEngine: ollama-qwen3-asr`。
5. 也可打开插件“设置 → 本地听写 → 识别引擎”，选择 `Ollama · Qwen3-ASR`，选择从本机列表读取的模型并点击“验证并保存为下次启动”。**这只修改下次启动选择，不中断当前录音**；随后停止服务再启动才生效。

## 回退

```powershell
.\STOP_LOCAL_ASR.bat
.\INSTALL_ALL.bat -Profile asr -AsrProfile legacy
.\START_LOCAL_ASR.bat
```

原生 Transformers Qwen 也仍可通过 `-AsrProfile qwen17` 选择（需要原先的 `.venv-qwen`、PyTorch/权重和官方强制对齐模型），**不与 Ollama 下载的模型权重互换**。

## 这条 Ollama 路径如何处理时间轴与说话人

- Edge继续产生16kHz、单声道PCM16有序音频包；本地SQLite提交后确认，断线按现有序号重放。Ollama适配器将当前**独占的非重叠窗口**封装为标准WAV、Base64发往 `http://127.0.0.1:11434/api/chat`，请求 `stream:false`、`messages[0].content:""`、`images:[wavBase64]`，解析语言和 `<asr_text>`。不发到远程API或使用API Key。
- 由于社区 Ollama 模型当前接口没有可靠逐词时间戳，**不杜撰等距词时间**；结果使用整个已处理音频窗口的真实媒体起止时间，`asrTiming=audio_window`，`confidence=null`，`asrScoreStatus=unavailable`。语音切块边界仍可能导致漏词/断词；只有真实对齐器才能提供逐词归属。
- 自动声音分组遇无词时间戳时，标记说话人归属为不确定，避免把多人对话全段随意归给一个人。原先的声学模型和字幕时间证据、纠词、外语翻译仍可使用，但不要把 Ollama 窗口时间当作逐词证据。
- 原文入库后，外语片段沿原有异步翻译队列处理；翻译失败时保留原文。任何 Ollama异常不推进 `processed` 游标，不删除未处理音频，不静默改用Whisper或更换原有模型。

## 验收与限制

安全/离线测试涵盖：WAV元数据、JSON载荷、语言识别、无词级时间戳、窗口所有权、原文与翻译分离、缓存不推进、模型缺失、HTTP超时、非ASR文本模型误用、配置失败保护和扩展来源限制。

**未在此环境对真实 Ollama/Qwen 权重、Windows Edge原生录音、说话人模型或你实际节目进行端到端测试。** 要在Windows用30～60秒真实中文、西班牙语或葡语片段与Whisper对比CER/WER、漏句和延迟。静音自检不构成准确率证据。还没有修复独立存在的完整整理100秒超时、非流式生成及断点续跑问题。

模型接口依据：<https://ollama.com/frozenlab/qwen3-asr>；配套模型GGUF是第三方打包，不等于官方Transformers权重或ForcedAligner。
