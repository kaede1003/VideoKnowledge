# V0.11.3 Ollama Qwen3-ASR 500 与异常重试修复

适用：V0.11.2 / git-r10 → **扩展和本地服务0.11.3**，安装器仍0.8.3，VKN5协议5。

## 从日志确认了什么

- Edge → `/asr` WebSocket 显示 accepted，表示浏览器与本地服务连接成功。
- `server/ollama_asr.py` 中的 `/api/chat` 返回 HTTP 500，这是**Ollama 服务器端的模型请求失败**，不能直接断定Python WebSocket或字幕模块有问题。
- `ASR job retained for retry` 表示处理游标没有确认成功，音频仍保存在本地SQLite。它不表示识别成功。
- 仅凭上述Python traceback无法确认 Ollama 内部是模型运行器退出、音频投影器不兼容、显存不足还是其他原因。

## 本版代码改动

1. 当Ollama返回HTTP 5xx，读取JSON `error` 字段、只保留**分类提示**，不把原始机器路径/响应正文写入UI或报告。诊断类别：RUNNER_EXITED、AUDIO_PROJECTOR、INSUFFICIENT_MEMORY、MODEL_LOAD、GPU_RUNTIME或OLLAMA_INTERNAL。
2. 同一音频会话连续2次出现5xx后，暂停自动重试15分钟。音频包、已保存笔记、`processed` 游标、模型选择均不变。修复Ollama后可在插件里点击“重试”，立即清除等待时间；若仍失败，继续保护音频。其他偶发传输异常保持原有有限退避策略。
3. `CHECK_OLLAMA_ASR.bat` 提供一次本地诊断：无参数只读取Ollama版本、已安装模型和当前加载模型；带上16kHz/单声道/PCM16 WAV路径时，再用与插件一致的请求格式试识别一次。报告写入被Git忽略的 `diagnostics/ollama-asr-check.json`。报告**不含原始音频和转写正文**。

## 立即排查：请先停止听写

先点击插件“停止全部采集”，暂停继续新增音频。不要清空缓存、删除笔记或重新安装模型。

PowerShell：

```powershell
ollama --version
ollama list
ollama ps
Get-Content "$env:LOCALAPPDATA\Ollama\server.log" -Tail 100
```

Ollama官方Windows故障日志位于 `%LOCALAPPDATA%\Ollama\server.log`。在尾部寻找 `model runner`、`projector`、`unsupported`、`CUDA`、`out of memory`、`failed to load`；不要单看HTTP 500。分享前删除日志里的账号、路径或其他私密内容。

### 复现同一个模型请求

若已经有一段5–15秒的、自己有权使用的 **16kHz单声道PCM16 WAV**（例如 `D:\test.wav`），升级后在项目目录执行：

```powershell
.\CHECK_OLLAMA_ASR.bat "D:\test.wav"
```

不带参数只检查连接/模型：

```powershell
.\CHECK_OLLAMA_ASR.bat
```

- 若短音频独立请求仍返回500，问题在Ollama/模型运行时，应先看其server.log、确认模型tag和运行配置；不要重复重装VideoKnowledge扩展。
- 若独立短音频成功、插件仍500，下一步对比单次音频长度/格式、并发模型负载和GPU使用。可以临时暂停LoRA图像识别及AI整理任务，避免争抢显存。**不能先认定是显存不足**。
- 模型发布说明使用 `messages[].images` 传base64 WAV、`content`为空、`stream=false`；本版请求格式与其一致。发布方注明需要支持 `qwen3a` 音频投影器的 Ollama 版本，但没有现场版本日志时不能将兼容性当作已确定原因。

## 原地升级

1. 停止新录音，导出重要笔记；停止本地服务（已更新的`STOP_LOCAL_ASR.bat`）。
2. 将升级ZIP**合并覆盖**到原工程根目录，例如`D:\VideoKnowledge_Git_Project`，保留`.venv`、`.venv-qwen`、`ASR_SETTINGS.bat`、SQLite缓存、模型、所有笔记；不要卸载原扩展。
3. 运行`START_LOCAL_ASR.bat`，再到`edge://extensions/`重新加载原扩展，刷新视频页；两个版本应为0.11.3。
4. 等Ollama本身能独立转写后，再点击插件里的“重试”，恢复积压的录音处理。

## 本次验证边界

在Linux容器中使用构造Ollama HTTP响应完成单元回归，没有运行真实Ollama Qwen3-ASR权重或用户Windows Edge。**该补丁能防止无意义的频繁重试并提供诊断，但不能修复Ollama内部HTTP500本身。**

参考：
- Ollama官方Windows日志说明：https://docs.ollama.com/troubleshooting
- frozenlab社区模型用法：https://ollama.com/frozenlab/qwen3-asr
