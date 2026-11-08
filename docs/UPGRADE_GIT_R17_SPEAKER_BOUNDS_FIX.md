# git-r17 升级说明：Sherpa-ONNX 原生访问冲突修复

## 本次现场结论

用户在 git-r16 启动后仍看到：

- Ollama ASR：`HTTP 500 / OLLAMA_INTERNAL`
- Sherpa：无活动说话人/空分段日志后，Windows `0xC0000005`
- 日志随后报告 `SHERPA_WORKER_EXITED:0xC0000005`，但 Uvicorn 仍监听 127.0.0.1:8765，后续 `/asr` WebSocket 仍可建立。

因此 r16 的进程隔离已经阻止原生故障带走主服务，但 Sherpa 原生库本身仍会崩溃。

## 根因方向与代码修复

原工程 `server/requirements-speaker.txt` 固定 `sherpa-onnx==1.12.34`。上游更新记录还显示，1.12.39 修复了 pyannote speaker diarization 的 offset-by-one 错误，1.13.1 又增加 bounds checks 以防止 SIGSEGV。原工程固定在 1.12.34，早于这两项修复。该修复与现场的空说话人结果后访问冲突高度吻合。

本版：
1. 固定 Sherpa-ONNX 到 `1.13.8`。
2. 运行时要求最低安全版本 `1.13.1`；低版本或无法读取版本时，`/health` 明确报告不可用，不会加载旧原生库。
3. 安装器严格核对实际安装版本为 `1.13.8`。
4. 安装模型自检也放到隔离子进程，避免本机原生 DLL 故障杀死安装器。
5. 新增 `CHECK_SPEAKER_RUNTIME.bat` 方便核对依赖版本和模型状态。
6. 保留 r16 的子进程隔离与 ASR 降级机制。

## Windows 升级步骤

请在原项目目录升级，避免改变笔记、SQLite 音频缓存、模型与扩展数据。

1. 先运行 `STOP_LOCAL_ASR.bat`，确认旧服务已停止。
2. 解压本版 ZIP，覆盖项目源码；不要删除 `.venv`、`models`、`cache`、`notes`、`ASR_SETTINGS.bat`。
3. 运行 `INSTALL_SPEAKER_MODEL.bat`。该入口会使用现有 `.venv` 将 Sherpa 更新到 `1.13.8`，并在隔离子进程中检查模型加载；已有模型文件会复用，不要求重新下载。
4. 运行 `CHECK_SPEAKER_RUNTIME.bat`，确认 `version` 为 `1.13.8`、`version_safe` 与 `available` 均为 `true`。
5. 重新运行 `START_LOCAL_ASR.bat`，访问 `http://127.0.0.1:8765/health`，检查 `speaker_diarization.version` 为 `1.13.8`。
6. 用授权的静音、单人和多人样本做现场复测。

如果安装器报告 `SHERPA_VERSION` 或下载失败，先不要删除 `.venv` 或模型目录；保留安装报告，按错误继续诊断。

## Ollama HTTP 500 是另一条问题线

本次没有把 `HTTP 500` 宣称为修复。它由本机 Ollama `/api/chat` 返回，与 Sherpa 的 Windows 原生访问冲突不是同一模块。

先运行 `CHECK_OLLAMA_ASR.bat` 查看版本和模型清单。若要进一步定位，可用一段 5–15 秒、16kHz/mono/PCM16 的授权 WAV：

```powershell
.\.venv\Scripts\python.exe scripts\diagnose_ollama_asr.py --wav "D:\path\short-test.wav" --output "diagnostics\ollama-asr-check.json"
```

若仍为 HTTP 500，请提供 `%LOCALAPPDATA%\Ollama\server.log` 中与测试时间对应的错误片段（建议前后各 30–60 行）。分享前可遮去 Windows 用户名、私有目录和任何敏感信息。诊断脚本不把音频或识别文本写入 JSON 报告。

## 验收边界

- 自动化测试只能证明版本门禁、错误隔离和业务回退机制。
- 当前开发容器不是用户 Windows；本次没有加载用户的 Windows DLL、模型或真实音频。
- 必须在目标 Windows 上安装 1.13.8 后，才能判断原生 `0xC0000005` 是否已消失。
- 说话人分组准确率、不同角色/旁白/系统音色的真实区分能力仍需真实视频验收。
- Ollama HTTP 500 根因仍待对应 `server.log` 与短 WAV 诊断结果。
