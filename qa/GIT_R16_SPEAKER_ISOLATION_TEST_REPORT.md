# git-r16 · Sherpa 原生崩溃隔离测试报告

日期：2026-11-08
基线：`VideoKnowledge_v0.12.1_FULL_GIT_PROJECT_git-r15(1).zip`
目标版本：扩展 `0.12.1`（未变）/ 本地服务 `0.12.1` / 安装器 `0.8.4` / VKN5 协议 `5`

## 本轮修复范围

- `server/speaker.py`：静音/短音频/非有限输入检查；Sherpa 空结果处理；新增持久 `IsolatedSherpaBackend`，用 spawn 子进程执行 sherpa-onnx；异常退出、访问冲突、初始化失败、IPC错误或超时后关闭 worker，并在本次服务运行期间 fail-closed。
- `server/stream_service.py`：服务健康快照增加 speaker worker 状态；停止服务时终止隔离 worker；WebSocket ready 版本同步为服务 `0.12.1`。
- `server/app.py`：`/health` 服务版本更新为 `0.12.1`。
- `START_LOCAL_ASR.bat`：启动提示版本更新为 `0.12.1`。
- `tests/test_speaker_isolation_v0122.py`：模拟原生子进程退出、正常空结果 IPC、静音/短音频跳过、原 ASR 完整音频回退，以及 Ollama HTTP 500 时 ASR worker 存活/缓存不推进。
- 任务/验收JSON、生成Markdown、README、状态、已知问题、CHANGELOG与升级说明同步更新。

## 自动化结果

执行命令：

```powershell
python scripts/run_checks.py --suite unit --timeout 180
```

运行环境：Linux 容器，Python `3.13.5`、Node `22.16.0`。结果：

| 检查 | 结果 | 数量/说明 |
|---|---|---|
| Repository checks | PASS | 退出码 0 |
| JavaScript syntax | PASS | 退出码 0 |
| JavaScript tests | PASS | 278 passed |
| Python compileall | PASS | server/scripts/tests |
| Python unittest | PASS | 373 passed |
| 总体 | PASS | 全部 unit 套件通过 |

新增定向回归：

- 8 项通过：子进程模拟异常退出后父进程仍运行；从 `asyncio.to_thread` 启动 worker；worker 初始化失败被隔离；native worker 超时会被终止；崩溃后不反复重启；完整原音 ASR 回退且不生成 speakerId；Sherpa 空结果与静音/短音频跳过；Ollama HTTP 500 两次失败后 ASR worker 仍存活、原始音频与 received/processed 水位正确、15分钟冷却生效。
- 既有 Ollama 声学分段测试 14 项通过。
- 既有 Ollama HTTP 500 分类/缓存测试 9 项通过。

详细当次日志：`artifacts/checks/20261108T153442033421Z/`（该目录被 `.gitignore` 忽略；完整报告留在本次构建环境）。

## 未执行 / 不能宣称通过

- 未在用户 Windows 机器运行；容器没有 Windows Python 3.11/3.12、Sherpa ONNX DLL/模型或真实音频。
- 未真实复现 `0xC0000005`；通过模拟子进程非正常退出验证隔离边界。真实 Windows 原生错误仍需目标机复测。
- 未运行真实 sherpa-onnx 分段/声纹模型，未验证多人视频的 diarization 准确率、速度或内存。
- 未连接真实 Ollama Qwen3-ASR。HTTP 500 是上游 Ollama 模型服务端错误；本次验证的是服务不退出、音频不丢失和冷却机制，不是修复 Ollama runner。
- 未运行 browser suite；本轮无前端业务改动。

## 验收结论

**源码与构造回归通过，可以交付给目标 Windows 环境试用；真实 Windows/Sherpa/Ollama 验收仍为 pending。** 若 Sherpa 子进程失败，当前服务会在 `/health` 的 `runtime.speaker_backend.phase` 显示 `disabled_after_failure`，原文继续走 ASR，直到重启本地服务才重新尝试声学分组。
