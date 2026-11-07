# V0.11.4 · Ollama声学分段回归测试

- 根因：Ollama 不提供 `_words`，旧 `SpeakerAnnotator.annotate()` 无法对整窗文字分配发言人，前端显示「不强行分配说话人」。
- 修复入口：`StreamManager.transcribe_and_label -> SpeakerAnnotator.transcribe_and_annotate`；其他Whisper/原生Qwen仍走旧的词级时间戳路径。
- 新增14个构造测试：单人独白、跨窗口声纹ID稳定、多人换声、同时说话只转写一次、未知声音仍保留、频繁切换退让、低覆盖不乱标、缺失声学模型、第二个子任务失败不推进SQLite游标、分段结果与声纹状态原子提交、音频重叠只归属于新区域、旧Whisper路径保持、媒体时间按源包换算、分段空结果回退整窗。
- 测试使用人为设置的声学区间/向量与ASR返回值，验证数据结构和故障边界，**没有真实模型推理、声纹准确率、音频流失率统计或 Windows Edge 原生验收**。
- 长文100秒超时、Ollama runner内部异常、自动实名身份绑定等不在此补丁的覆盖范围；不能将这些列为已修复。

## 最终自动测试结果

- Python：362/362通过（包含本次14项新增构造测试）。
- JavaScript：263/263通过（沿用原有扩展测试，没有修改前端JS）。
- 仓库检查与Python编译检查通过；没有真实`sherpa_onnx`声学模型、Ollama Qwen权重和目标Windows Edge环境，所以本报告不构成实际说话人识别准确率验收。
