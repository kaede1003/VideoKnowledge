# 统一安装器 0.8.4 · Ollama Qwen3-ASR 自动补装

这次**仅更改安装器**；Edge 扩展与 VideoKnowledge Server 仍是 **0.11.3**。不需要重新下载已经安装好的模型。安装器不删除用户笔记、SQLite音频、`.venv`、Whisper/Transformers权重、`ASR_SETTINGS.bat` 或 `asr_profile.local.json`。

## 默认行为

- 双击 `INSTALL_ALL.bat`，依次检查运行依赖、文字模型、视觉模型、**Ollama Qwen3-ASR**、本地 ASR 及说话人等组件。
- `-Profile models` 只补本地三类 Ollama 模型；`-Profile core` 包括 Qwen3-ASR 下载。即使当前使用 Whisper，也只预装模型，**不会修改实际 ASR 引擎选择**。
- `-Profile asr -AsrProfile ollama17`：若模型缺失就先下载，检查标签和元数据，继续执行之前已有的合成静音音频测试；只在后者成功后激活选定的 Ollama 引擎。任何失败保留原配置和缓存。
- 安装器默认模型 `frozenlab/qwen3-asr:1.7b`。支持选择同发布者的 `:0.6b`；对其他自定义标签，只检查本地已安装的模型，不自动从未知来源拉取。
- 检测项目中已保存的 `ollama17` 标签时优先沿用原选择；CLI `-OllamaAsrModel` 显式指定时优先级更高。

## 推荐命令

```powershell
cd D:\VideoKnowledge_Git_Project
.\INSTALL_ALL.bat

# 已有完整工程，仅补 ASR 并选择 Ollama：
.\INSTALL_ALL.bat -Profile asr -AsrProfile ollama17

# 轻量选择：
.\INSTALL_ALL.bat -Profile asr -AsrProfile ollama17 -OllamaAsrModel frozenlab/qwen3-asr:0.6b

# 仅安装 Ollama 三类模型，不切换 ASR：
.\INSTALL_ALL.bat -Profile models

# 只预览，不运行下载：
.\INSTALL_ALL.bat -Plan
```

安装前先停止当前听写服务（8765），尽量让已缓存任务完成；**不要停止或清空 Ollama 自身的模型缓存**。若安装器检测到8765仍在使用，会提示先停止并记录失败，不会强杀服务。恢复日常使用仍启动 `START_LOCAL_ASR.bat`。本次不必重新加载扩展；如需切换 ASR，引擎在服务下次启动时生效。

## 下载与回退边界

模型下载统一通过 `127.0.0.1:11434/api/pull`（可指定其他本机回环端口）并显示进度；已存在标签则不下载。成功要求收到完整成功状态，再通过 `/api/tags` 和 `/api/show` 校验。下载失败会保留已有 Ollama 缓存，重试仅有上限；Fake-IP / 证书 / 磁盘不足等可识别错误不无限重试，也不绕过 TLS/地址安全检查。

模型元数据完整只说明已下载，不代表模型能推理；切换 ASR 的合成静音验证是额外一步，不能替代真实节目准确率验收。默认预装不会修改 `asr_profile.local.json`，当前 Whisper 和原生 Transformers Qwen 回退仍可使用：

```powershell
.\INSTALL_ALL.bat -Profile asr -AsrProfile legacy
```

错误、重试与检查结果写入 `diagnostics/install/install-*.json` 和 `.log`（Git忽略）；**不会把私人音频或笔记上传到远程**。下载需访问所选公开 Ollama 模型源，但推理走本地 Ollama。没有改变旧的长文整理超时机制。

## 验证范围

已通过本地假 Ollama HTTP 服务对 `/api/pull` 流式下载、已安装跳过、1.7B/0.6B、失败不切换、Fake-IP拒绝和旧数据保留的代码测试。**尚未在用户的 Windows Ollama 环境执行真实模型拉取/推理。**
