# V0.2 架构 — Edge标签声音 → 本地ASR → 知识文档

```text
用户主动点击 Edge 扩展图标
         │
         ▼
Manifest V3 service worker (tabCapture/getMediaStreamId)
         │ 有效期很短的 stream ID
         ▼
Offscreen document (getUserMedia)
         ├── AudioContext -> 扬声器（继续播放原声）
         └── AudioWorklet -> 单声道16kHz PCM16
                             │
                             ▼
                 WebSocket 127.0.0.1:8765/asr
                             │
                             ▼
                  FastAPI + faster-whisper
               6秒分段 / CPU INT8 / base多语言
                             │
                             ▼
               [{time,text,end}, ...] 回传
                             │
                             ▼
             content.js 与字幕文字合并、去重
                             │
                             ├── chrome.storage.local
                             ├── 离线规则摘要、原文时间线
                             └── 可选本地 Ollama qwen2.5:3b
                                       │
                                       ▼
                           Markdown / HTML 下载
```

## 安全边界

- 采集必须由用户主动启动；不允许后台静默监视所有标签。
- Python server 只监听 loopback，WebSocket 检查 extension Origin，且只有一个活动会话；生产化需考虑更强的配对认证。
- 除使用者主动选择的 LLM API 外，音频、识别文字均不被服务器上传；首次加载 ASR 模型需要下载权重。
- WebSocket 音频采用固定`VKN2`协议：4字节标识、两个little-endian float64 播放时间、16kHz mono PCM16 数据。每个包最多2秒。
- Server队列最多4个分段，落后时返回错误并丢掉分段，绝不无限积压音频数据。
- 6秒窗口以当前播放位置估计时间轴。拖动进度时会刷新音频窗口，不拼接不连续内容；本版未进行声纹分离与精确时间轴强制对齐。
- AI 总结模型与ASR模型分离；离线规则摘要只挑选关键原话，不能声称完成专业语义验证。

## 开发注意

- 保留原版字幕导入及AI服务配置；本版 ASR 活跃时停止读取页面实时字幕，以避免重复；获取整段字幕和导入 SRT 仍能手动操作。
- WebSocket断开 / 标签停止 / 浏览器退出均需停止采集；不允许收集其他标签声音。
- CPU 默认可运行，在 Windows / RTX 5080 上启用 CUDA 需额外验证 CTranslate2、驱动与 cuDNN 版本，不能直接默认GPU可用。
- 下一版重点：语音断句更自然、可选 VAD、长视频分块AI总结进度、视频画面OCR和用户可控的录音历史。
