# V0.11.0 ASR接入预览 · 实际验证记录

日期：2026-11-07。基线：实际0.10.2/git-r7完整源码；扩展/本地服务0.11.0，安装器0.8.2，协议5。

## 明确结论

已接入Qwen原生Transformers调用、隔离worker、可选安装与安全回退，并完成代码回归。**没有运行真实Qwen权重、没有安装Windows CUDA环境、没有取得真实识别准确率或用户机器速度。** 不能宣传为正式质量验收版本。

## 执行环境与结果

当前为Linux/Python3.13.5/Node22/Chromium。PyTorch2.10.0+cpu，CUDA不可用。产品目标Qwen环境为独立Python3.11/3.12、torch2.9.1/cu128、Transformers5.13.0；目标环境未在此安装运行。

| 检查 | 最终实际结果 | 边界 |
|---|---|---|
| 仓库、版本、依赖任务引用、私有文件门禁 | 通过 | 不等于完整安全审计 |
| 全部JavaScript语法/Python编译 | 通过 | 不加载模型 |
| JavaScript单元/模拟集成 | 263/263通过 | 基线262＋1项引擎元数据；浏览器接口/模型模拟 |
| Python单元/模拟集成 | 308/308通过 | 基线272＋36项适配/安装/IPC/语言/窗口/评测测试 |
| 浏览器DOM | 10组通过 | 跨视频阅读、下载界面、断句、字幕、修订、写作、设置、停止、原工具、排版；Chrome/音频/模型替身 |
| 真子进程标准输入输出 | 新Python测试内通过 | 使用合成固定响应程序，不是真Qwen模型 |
| ZIP CRC、源码哈希与私有文件边界 | 交付打包时检查 | 不包含权重、笔记、音频或环境 |

单元套件最终运行：`python scripts/run_checks.py --suite unit`。浏览器套件：`python scripts/run_checks.py --suite browser`。原始日志生成在被忽略的`artifacts/checks/`，本包只携带无用户正文的结构化`qa/V0110_CHECK_SUMMARY.json`。

## 新增回归覆盖

1. 不选新profile时保持旧ASR_SETTINGS环境参数；无未知profile静默回退。
2. Qwen与原服务Python环境隔离；下载或同worker加载检查失败时不激活、不清空旧配置；切换前备份。
3. legacy回退不进行网络探测、权重下载或环境安装。
4. 仅加载官方原生`-hf`模型目录；录制时禁联网下载、禁远程自定义Python代码。
5. PCM16字节、16kHz、时长、所属区间、base64和消息大小有界。
6. 支持语种名称/代码传递；西语和葡语保持原语言，提交SQLite后翻译仍为待处理，不伪称中文翻译完成。
7. 对齐文本完整覆盖与时间合法性验证；按词中点归属窗口；对齐失败只重新识别新增音频，不生成均匀伪词时间戳。
8. 缺失置信分数保持null；引擎、模型、设备、时间精度随记录保存。
9. 子进程退出、握手异常、响应ID错误、超时、关闭等路径可辨别，只终止本项目worker。
10. 识别输出超过上限不提交不完整结果；原缓存游标在识别失败时不前进；重复串只标记不删除。
11. 新评测工具只读取用户指定短WAV；有参考稿才算规范化CER，不能用文本通顺程度冒充准确率。

## 测试过程中的失败与修正

初次测试的模拟会话遗漏必需correct字段，按真实会话格式补齐。后来新增legacy回退测试中，默认MagicMock返回值不能JSON序列化，改为模拟真实command的None返回值后，完整单元套件重新通过。未将这些失败轮次计为通过。

浏览器套件在最终安装器回退调整前通过；该调整仅触及安装器/Python测试，不改变任何浏览器产品文件。调整后完整单元/编译/仓库检查重新通过。无需伪称执行过单一整套命令。

## 必须在目标机器验收

- 真Windows启动、CUDA驱动/Blackwell内核、模型加载和合成运算检查。
- 实际30秒至3分钟中文/中英混合/西语/葡语音频的字错、漏词、循环、数字与否定保真。
- 真实Qwen/对齐器的word coverage和窗口边界；抢话与声音分组延迟。
- 与本机Ollama视觉/翻译同时运行的峰值显存、积压、RTF和连续稳定性。
- 原生Edge采集、尾音、重连与用户视频内容端到端。

没有实现完整中文译稿重译、姓名身份推理、长文100秒超时重构、全局GPU调度或全部音频永久保存。ASR新引擎不等于这些问题已解决。只做短块增量，不能称为原生vLLM流式。

## 上游API核对

- https://huggingface.co/Qwen/Qwen3-ASR-1.7B-hf
- https://huggingface.co/Qwen/Qwen3-ForcedAligner-0.6B-hf
- https://raw.githubusercontent.com/huggingface/transformers/v5.13.0/src/transformers/models/qwen3_asr/processing_qwen3_asr.py
- https://pytorch.org/get-started/previous-versions/

上游说明与源码核对不等于本机模型实测。
