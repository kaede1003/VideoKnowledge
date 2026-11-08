# git-r16 · Sherpa 原生崩溃隔离与 ASR 失败恢复

适用基线：扩展 `0.12.1`、本地服务 `0.12.0`、安装器 `0.8.4`、VKN5 协议 `5`。

本包更新后：扩展保持 `0.12.1`，本地服务更新为 `0.12.1`；安装器、音频协议、已安装模型和用户数据格式不变。

## 本轮现场错误

截图中有两类独立错误：

1. `ASR_OLLAMA_SERVER_ERROR: HTTP 500`：Ollama `/api/chat` 已接收请求但模型服务端返回 5xx。客户端无法修复 Ollama 内部模型 runner，但必须保留音频、不能推进处理水位，也不能让服务工作循环退出。
2. Sherpa-ONNX 输出 `No speakers found in the audio samples` 后，Python 调用栈停在 `OfflineSpeakerDiarization.process()`，最终 Windows 退出码 `0xC0000005`。这是 C/C++ 原生扩展访问冲突，普通 Python `try/except` 无法捕获或保护当前进程。

Sherpa-ONNX 的这条 `No speakers found` 日志本身表示该音频窗口没有检测到活动说话人，应该被当作空分段结果；不应该因此删除转写，也不应该猜测说话人。

## 本包改动

- **原生隔离**：Sherpa-ONNX 与 ONNX embedding 在独立、持久的 Python 子进程中加载和推理。主 ASR/FastAPI 进程不再直接调用这段原生代码。
- **崩溃保护**：若子进程访问冲突、异常退出、初始化失败或推理超时，父进程检测 IPC EOF/退出码/超时，终止残留子进程，并在本次服务运行期间关闭声学分组，避免每个音频窗口反复触发相同崩溃。
- **安全降级**：声学分组失败时，原始完整音频仍交给已选 ASR 引擎识别；结果标记为 `unavailable` / `uncertain`，不生成虚假说话人编号。若 Ollama ASR 本身返回 HTTP 500，仍按既有错误处理保留音频和处理水位。
- **空音频保护**：静音、极短、非有限数值或无活动说话人结果不进入 embedding；空结果返回空分组，不当成致命异常。
- **生命周期**：本地服务停止时终止可选 Sherpa 子进程。`/health` 的 `runtime.speaker_backend` 会显示 `not_started`、`ready` 或 `disabled_after_failure` 等状态。
- **Ollama 500 回归**：新增工作循环测试，验证两次 HTTP 500 后 ASR worker 仍存活，15 分钟冷却生效，音频包仍在 SQLite 中且 `processed` 水位不前进。

## 原地升级

1. 点击插件“停止全部采集”，等待正在写入的音频确认；重要笔记可先导出。
2. 在原工程目录运行 `STOP_LOCAL_ASR.bat`。
3. 将本 ZIP 解压后合并覆盖到原工程根目录。
4. **保留** `.venv`、`.venv-qwen`、`models/`、Ollama 已下载模型、SQLite 缓存、`ASR_SETTINGS.bat`、笔记和扩展加载目录；不要卸载扩展或删除缓存。
5. 运行 `START_LOCAL_ASR.bat`。扩展代码没有变化，不需要重新安装扩展；若 Edge 仍显示旧连接状态，刷新视频页即可。
6. 打开 `http://127.0.0.1:8765/health`，确认 `version` 为 `0.12.1`。`runtime.speaker_backend` 首次使用前显示 `not_started`；成功加载后显示 `ready`。若原生 worker 崩溃，则显示 `disabled_after_failure`，服务仍应保持 `ok: true`。

## 故障时的预期行为

- Sherpa 子进程崩溃：当前窗口不进行说话人归属，使用完整音频进行原 ASR；后续窗口不再自动启动 Sherpa，直到重启本地服务。
- Sherpa 未安装/模型文件缺失：直接降级，不启动子进程。
- Ollama HTTP 500：不把它误报成 Sherpa 问题；原音频保留，连续失败后按现有策略暂停自动重试15分钟。Ollama 内部原因仍需查看 `%LOCALAPPDATA%\Ollama\server.log`，不能靠 VideoKnowledge 客户端修复上游 runner。

## 验证边界

本包新增构造测试，模拟子进程原生崩溃、空分段、静音/短音频、正常 IPC 返回和 Ollama HTTP 500 工作循环。**本开发容器没有用户 Windows 环境、实际 sherpa-onnx 模型文件或 Ollama Qwen3-ASR 模型**，因此没有声称复现/验证真实 Windows `0xC0000005`、真实声纹准确率或修复 Ollama 内部 HTTP 500。目标机仍需按上面健康接口和真实授权音频验收。

测试报告：`qa/GIT_R16_SPEAKER_ISOLATION_TEST_REPORT.md`。
