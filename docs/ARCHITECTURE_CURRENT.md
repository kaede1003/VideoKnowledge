> git-r18补充：文字稿模式（短文和长文）现在有独立外语→简体中文翻译阶段，再进入标点/断句。按轮次/片段保留来源ID与说话人，可信的ASR译文可复用，待核对译文重新翻译；翻译校验失败时不发布外语原文冒充中文。原始ASR和历史文稿不覆盖。详见 `UPGRADE_GIT_R18_TRANSCRIPT_TRANSLATION.md`。

> git-r17补充：Sherpa-ONNX 运行库固定为 1.13.8（最低安全门槛1.13.1）；旧版本在 `/health` 被标记不可用，避免加载已知缺少 speaker diarization bounds checks 的旧原生库。安装器加载检查同样在隔离子进程完成。Ollama HTTP 500 仍独立待查。详见 `UPGRADE_GIT_R17_SPEAKER_BOUNDS_FIX.md`。\n\n> git-r16补充：Ollama/Whisper ASR 主进程不再直接执行 sherpa-onnx 原生说话人分段。`SpeakerAnnotator` 将 PCM 交给 `IsolatedSherpaBackend` 的独立 spawn 子进程；父进程只接收 IPC 结果。子进程崩溃/超时后本轮服务禁用声学分组并回退完整音频，不推进失败任务的持久水位。静音和空说话人结果正常返回空分组。详见 `UPGRADE_GIT_R16_SPEAKER_ISOLATION.md`。

> V0.11.1补充：`server/asr_profiles.py` 按本地profile选择 `StreamingWhisperEngine`、`QwenEngine`（独立Transformers worker）或 `OllamaASREngine`（本机HTTP）。新 `server/ollama_asr.py` 只编码非重叠owner PCM窗口，并经本机Ollama识别；`server/asr_settings.py`提供下次启动配置，失败不删除缓存/切换运行引擎。见 `UPGRADE_V0111_OLLAMA_ASR.md`。下述某些主干仍是历史0.7.2架构描述。

> 0.10.1补充：caption-buffer.js在offscreen保存有限易失字幕裁剪，推理中仍采样；caption_review.py英文整词校验；生成前复核已存证据。文字稿短单元→逐条校验→原文锚点重试→还原发言。见UPGRADE_V0101.md。

> 0.10.0补充：caption-review.js/content.js管理时间对齐证据，caption-background.js向本机路由，offscreen.js只裁剪已授权视频；server/caption_review.py本机视觉读取与局部同音守卫。无关内容过滤已退休，旧字段只保留不执行。详见UPGRADE_V0100.md。下面历史架构若冲突以当前状态为准。

> 下文主干为git-r1历史架构；V0.8.0变更与当前边界见 [UPGRADE_V080.md](UPGRADE_V080.md)。在线字幕自动采集已移除。新增server/video_cache.py管理下载/TTL，server/context_review.py负责短语规则校验，stream_service.py增加监督，启动器run_local_service.py收集日志；均不替代长文RFC。

# 当前系统架构（从0.7.2源码整理）

## 进程与职责

```text
视频网站页面
  └─ content.js：紧凑面板、播放器时间、字幕、记录/结果显示
       ↔ Chrome消息 ↔ background.js：配置、存储、整理请求、字幕接口
                            ├─ asr-background.js：授权、采集指令、状态管理
                            └─ lora-background.js：规则/图片会话与导出
                                 ↕ offscreen.js：共享媒体流、音频/画面处理
                       audio-processor.js → stream-client.js → IndexedDB
                                                      ↕ WebSocket /asr
本地Python 127.0.0.1:8765
  app.py → stream_service.py → stream_store.py（SQLite持久队列）
                 ├─ recognition.py → faster-whisper
                 ├─ speaker.py → 独立 Sherpa 子进程（可选声学分组）
                 └─ text_enrichment.py → 本机Ollama翻译/纠错建议
  lora_service.py → 本机视觉模型 → 图像候选、caption、元数据

完整整理/阶段AI摘要：当前仍由 background.js 直接请求配置的聊天接口
  默认 http://127.0.0.1:11434/v1/chat/completions
```

## 模块导航

| 文件 | 主要职责 | 更改时重点测试 |
|---|---|---|
| `extension/core.js` | 纯函数：字幕清理、记录合并、质量、筛选、写作提示、导出 | `core`、`quality_v071`、`filter_v072`、`writing_v070` |
| `extension/content.js` | 主面板、折叠、人工修订、实时/阶段/完整结果交互 | 当前5组browser测试 |
| `extension/ai-config.js` | 统一配置解析、离线/本地/自定义区分 | `ai_config_v051` |
| `extension/background.js` | 本地存储、模型请求、取消、结果拼接 | `ai_config`、`stop_origin`、`writing`、`filter` |
| `extension/asr-background.js` | 授权与采集启动/停止状态 | `asr_extension`、`stop_origin` |
| `extension/offscreen.js` | 共享音视频流、停止时轨道释放、尾音 | `stream_v05`、合成轨道browser测试 |
| `extension/stream-client.js` | IndexedDB、序号、确认、重连、事件回放 | `stream_v05` |
| `server/stream_protocol.py` | VKN5二进制音频包 | `test_stream_v05` |
| `server/stream_store.py` | SQLite队列、结果和原子进度、清理 | `test_stream_v05`、`test_speaker_v060` |
| `server/recognition.py` | 重叠窗口解码、词归属、质量标记 | `test_quality_v071`＋真实原音评测 |
| `server/text_enrichment.py` | 原文翻译、候选纠错、数字/否定等保守保护 | `test_quality_v071` |
| `server/speaker.py` | 可选声学分段与本轮声音匹配 | `test_speaker_v060`＋真实对话评测 |
| `server/lora_service.py` / `lora_core.py` | 自然语言要求保留、视觉筛选、去重、导出 | `test_lora_core`、`lora_extension` |

## 数据可靠性

浏览器先持久化音频包；服务端SQLite提交后确认；浏览器释放已确认包。识别结果与处理水位在同一事务提交，结果有稳定ID及修订号。传输确认不等于识别完成，也不等于识别正确。磁盘故障、未落盘尾音、从未采到的声音不能由重传机制恢复。

默认约12秒新音频窗口加邻近重叠；使用词时间戳分配归属，暂停/跳播需要边界。当前解码禁止把上一段机器文字无条件当提示继续传播；用户主动提供术语仍可使用。不是Whisper原生逐token实时流。

## 停止和后台处理

停止首先切断新输入，不等待全部识别/翻译结束。停止前缓存可继续处理，UI必须区分录制、暂停、停止、补录、失败。LoRA可能共享视频流，“停止听写”和“停止全部采集”语义不同。面板×仅隐藏，不能当录音停止证据。

## 模型和输入可信边界

转写、字幕、视觉说明和导入文本都是待处理材料，不是执行指令。云端摘要只在用户配置并授权后发送；录制中可选主题分类限定本机文字模型。人工修订不代表程序已核实原音。说话人标签是本轮声音分组，不是身份认证。

## 尚待重构的长任务

当前完整整理在MV3后台函数中顺序调用非流式聊天；单请求默认100000ms，正常正文无统一输出token预算；中途结果保存在局部数组而不是持久检查点。可取消当前请求，但没有可靠的跨后台重启续跑。

这些是现状，不是最终架构。拟议持久任务设计在`RFC_LONG_TASKS.md`，不能把未来接口写成已经存在。
