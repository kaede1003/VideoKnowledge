# 当前数据与接口约定

本文件描述代码现状；不是新增API，也不保证外部长期兼容。真实类型和限额以对应源码及单测为准。

## HTTP/WebSocket

| 路径 | 方式 | 当前用途 |
|---|---|---|
| `/health` | GET | `service/version/protocol/model/device/compute/loaded`等诊断；会包含本地缓存路径，分享前脱敏 |
| `/asr` | WebSocket | 增量PCM和结果事件；要求扩展Origin |
| `/diagnostics` | POST | 本地服务及Ollama模型清单状态；有Origin检查 |
| `/lora/plan` | POST | 保存多轮自然语言规则，不在此步运行视觉推理 |
| `/lora/session` | POST | 创建图片采集会话并检查模型 |
| `/lora/stream/{session_id}` | WebSocket | 候选图片输入及处理事件 |
| `/lora/export-link` | POST | 生成带会话token的导出地址 |
| `/lora/export/{session_id}` | GET | 带token下载候选图片ZIP，链接属于敏感会话信息 |

服务默认只监听`127.0.0.1:8765`。现有Origin检查接受合法格式的扩展来源，不等于精确绑定单一扩展；需强化时见VK-020。Ollama来源许可是另一层，二者不要混为一谈。

## VKN5音频帧

来源：`server/stream_protocol.py`和`extension/stream-client.js`。

| 偏移 | 类型 | 含义 |
|---|---|---|
| 0 | 4字节 | ASCII `VKN5` |
| 4 | uint32 LE | 严格递增序号，从1开始，控制包也占号 |
| 8 | float64 LE | 播放器起始时间（秒） |
| 16 | float64 LE | 播放器结束时间（秒） |
| 24 | uint32 LE | 0=音频，1=边界，2=结束 |
| 28 | PCM16 LE | 16kHz单声道；控制包无PCM |

每个包最多2秒音频。会话ID在JSON hello中协商，不从URL猜测；hello包含`sessionId`、`videoKey`和`options`。WebSocket处理器先发ready并校验协议；ping/pong是健康检查，不表示模型已识别内容。

## 听写设置现状

`normalize_options`允许`language`自动或指定语种；`translate`默认true，`correct`默认false，`chunkSeconds`为6/12/18之一、默认12，`textModel`默认`qwen2.5:3b`，`diarize`默认false，`maxSpeakers`可选2–8，`hotwords`保留用户术语。ASR模型/设备/量化从`VKN_ASR_*`环境变量或本地批处理设置读取。

## 文字记录

合成示例，字段取自当前`core.cleanCue`；并非真实音频结果：

```json
{
  "id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa:1:0",
  "revision": 1,
  "time": 12.0,
  "end": 15.2,
  "source": "local-asr",
  "text": "原文或当前允许展示的译文",
  "original": "This might be incorrect.",
  "translation": "这可能不正确。",
  "language": "en",
  "translationStatus": "done",
  "needsReview": false,
  "qualityFlags": [],
  "verificationStatus": "machine_unverified",
  "asrModel": "small"
}
```

可选原始诊断字段包括`confidence`、`languageProbability`、`asrAvgLogprob`、`asrNoSpeechProb`、`asrCompressionRatio`。这些不是经校准的正确率。`needsReview:false`也不等于人工核验通过。

人工修订保存在会话`textOverrides[id]`，角色命名和逐句覆盖保存在`speakerNames`/`speakerOverrides`；筛选保存在`contentFilter`、`filterOverrides`、`filterAssessments`。不要直接把原文字段改成“已核实”的机器推测。

## 浏览器存储

- `chrome.storage.local`：`vkn:session:`前缀保存笔记、段落、阶段摘要、结果历史；`vkn:index`是索引，不因为索引缩短就删除旧笔记。
- `vknAiConfig`与`vknSpeechConfig`：摘要及听写配置，统一解析器优先保留明确用户设置。
- IndexedDB `vkn-stream-v5`：`sessions`和`packets`存放待确认音频与恢复元数据。
- `documents`/`activeDocumentId`：成品历史与当前选择；旧`aiMarkdown`兼容字段仍在。旧成品是快照，不随原文变化自动改写。

## 服务端持久化

SQLite `stream.sqlite3`使用WAL和FULL同步。主要表：`sessions`、`packets`、`events`、`segments`，会话包含`speaker_state`增量迁移字段。默认位置是`%LOCALAPPDATA%\VideoKnowledge\asr-cache`；可用`VKN_CACHE_DIR`覆盖。

确认后和识别完成后的清理是不同步骤：识别成功才删除不再用于重叠的旧PCM；已有文字不能保证重听旧音频。默认待处理PCM预算256MiB、最小余量128MiB，失败告警不静默确认。完整策略见`StreamStore`，不要从这些数字推导“无限缓存”。

## 导出

核查JSON格式`vkn-audit-1`含原文、候选译文、修订、筛选、角色与文档，不含音频；设计上排除API Key、声纹向量、浏览器账户信息，但仍含节目链接和个人笔记。当前并无已经验收的“导入该JSON恢复所有浏览器状态”保证。
