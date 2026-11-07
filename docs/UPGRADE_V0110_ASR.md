# V0.11.0 · 可选 Qwen3-ASR 接入预览（git-r8）

**这轮已进入代码接入，不再只有模型调研。** 扩展/服务0.11.0、安装器0.8.2、音频协议5。基于0.10.2/git-r7修改，保留下载/阅读来源隔离、字幕校对、原文与修订历史；没有重写前端，也没有恢复无关内容过滤。

## 交付状态

- 已写入真实推理调用：Qwen官方原生Transformers模型 + ForcedAligner；通过独立本地子进程接回现有音频/缓存/翻译流程。
- 已执行接口、进程通信、时序归属、失败保留和旧功能回归；模型回复为替身。
- **未下载/运行真实Qwen权重，未在用户RTX5080/Windows上测试。** 当前容器为CPU PyTorch，没有CUDA。工程接入完成不等于质量、显存与实时速度验收完成。
- 不会仅因覆盖此包就更换现有模型。新模型必须由用户选择安装，并在目标机器通过加载和合成输入运算检查后才激活。

## 只保留一个安装入口

先停止采集、导出重要笔记、运行原目录 `STOP_LOCAL_ASR.bat`。把升级包全部内容合并覆盖到原目录（例如 `D:\VideoKnowledge_Git_Project`）。不要卸载扩展或删除`.venv`、旧模型、音频缓存及`ASR_SETTINGS.bat`。

在原目录PowerShell运行：

```powershell
.\INSTALL_ALL.bat -Profile asr -AsrProfile qwen17
```

它会：

1. 检查原服务依赖；在新`.venv-qwen`隔离安装PyTorch CUDA12.8/Transformers，不把Qwen依赖塞进原`.venv`。
2. 下载官方 **`Qwen/Qwen3-ASR-1.7B-hf`** 和 **`Qwen/Qwen3-ForcedAligner-0.6B-hf`** 到工程`models/`。注意`-hf`检查点与旧`qwen-asr`包的无后缀检查点不是随便互换的；不是`ollama pull`模型。
3. 用与服务相同的worker验证CUDA、加载两个模型，并对合成静音执行少量生成/对齐运算。输出不保存，不把这个测试当成真实识别准确率验证。
4. **只有以上全部通过才原子保存`asr_profile.local.json`**，备份旧profile；不改`ASR_SETTINGS.bat`。失败保留旧选择和下载缓存。

完成后运行原来的`START_LOCAL_ASR.bat`，重新加载Edge原扩展并刷新视频页。`START_ACCURATE_ASR.bat`也可以运行，但显式保存的Qwen选择优先于其旧small覆盖。两个服务启动脚本仍只开一个。

新权重与PyTorch依赖需要额外磁盘空间，包内没有权重；网络失败不能靠重装插件解决。不自动修改代理、DNS、TLS、驱动或终止其他GPU任务。本轮提供官方Hugging Face下载及本地完整模型目录复用；**没有实现ModelScope下载器或证明其存在同名原生`-hf`仓库**。

## 如何确认真的用上了

服务控制台会分别打印选择的引擎/模型/设备。第一次实际成功转写后出现：

```text
[VKN] Qwen ASR active: Qwen/Qwen3-ASR-1.7B-hf on cuda:0; original-language transcription.
```

`http://127.0.0.1:8765/health`返回`asr_backend`：包含profile、configured_model、loaded、phase、实际dtype、加载时间、最近识别耗时/RTF、对齐状态。`loaded:false`表示还没有成功载入，不是已经在推理。`ASR model: base`不是Qwen已经启用。

每条新记录保留`asrEngine/asrModel/asrDevice/asrTiming`；ASR没有提供的置信分数记为缺失，不伪造0或100%。历史记录的引擎字段不重写。

## 可选档位和回退

| 参数 | 作用 |
|---|---|
| `-AsrProfile qwen17` | 1.7B原生模型，CUDA；本轮质量候选 |
| `-AsrProfile qwen06` | 0.6B原生模型，CUDA；较小的测试候选，不保证准确率一样 |
| `-AsrProfile whisper-large` | faster-whisper large-v3 / CUDA int8_float16；加载时验证本机CTranslate2依赖 |
| `-AsrProfile whisper-turbo` | faster-whisper turbo / CUDA int8_float16；同上 |
| `-AsrProfile legacy` | 恢复原ASR_SETTINGS/环境选择；不下载、不删除任何模型 |
| 不指定（keep） | 保持已有选择，不悄悄从Qwen换回base |

所有档位都使用同一个`INSTALL_ALL.bat -Profile asr`入口。回退前停服务，然后：

```powershell
.\INSTALL_ALL.bat -Profile asr -AsrProfile legacy
.\START_LOCAL_ASR.bat
```

选定Qwen后，显存不足、worker崩溃或CUDA不可用会明确失败，并保留待识别音频，不会悄悄降级成base冒充Qwen。整机强杀/磁盘故障仍不能保证所有数据完整。

## 时间与语言处理

- 使用现有有序16kHz PCM缓存、6/12/18秒窗口设置及边界；这是**短块增量**，不是vLLM原生流式。
- Qwen输出**原语言**；西班牙语映射`es`、葡萄牙语`pt`后交给原翻译流程，不把它们误标为中文。
- 支持的语言调用ForcedAligner，验证对齐字词覆盖，然后按音频窗口的词中点归属去除重复上下文。不按句子相似度删除真实重复发言。
- 对齐不可用/不支持/字词不完整时，只重读本次新音频区间并标记“音频窗口时间”；没有伪造词时间戳，不把整段混合发言塞给最长讲话的人。
- 日本语/韩语对齐还需上游可选分词组件，本轮未自动安装；此时保留文字、提示词时间戳缺失。ASR可支持的语种多于对齐器，不能混为一谈。
- 对齐验证只证明字词与位置数据格式一致，**不证明原音被准确听懂**。输出达到token上限明确失败、不提交处理游标；循环重复保留并标注，不删除。
- 上游模型有自己的解码/规范化行为；“原始文字”指当前ASR解码结果，不是经人工核验的逐字真值。

## 本机短样本比较

优先使用自己有权处理的30秒至3分钟片段，先关闭文字润色和字幕纠词，分别评测引擎。可用新增脚本（只接收最多5分钟、16kHz单声道PCM16 WAV）：

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_asr.py "D:\samples\clip.wav" --engine qwen17 --language auto
```

有人工核对参考稿时追加`--reference "D:\samples\reference.txt"`，才计算规范化字错率CER。没有参考稿只记录耗时、原语言结果和窗口处理状态，不能宣称准确率。报告在`diagnostics/asr-eval/`，**含原文，分享前检查隐私**；工具不上传音频/文本。

输送的音频包处理完成≠每个字都听对≠每句话都翻译完成。与原`base/small`使用同一片段对照，重点看遗漏、循环、专名、数字、否定、语言切换、RTF及稳定性。

## 本轮不声称完成

没有修好长文100秒超时、持久续跑、翻译不完整、自我介绍自动姓名绑定或整个GPU资源调度。继续使用既有翻译/说话人/字幕系统；更换ASR不是这些环节的验收。停止后的缓存仍可能补录；旧笔记没有原音时不能自动重听。不要因换引擎清除旧笔记。

官方接口依据（不等于本机已实测）：

- https://huggingface.co/Qwen/Qwen3-ASR-1.7B-hf （原生Transformers与时间对齐API）
- https://huggingface.co/Qwen/Qwen3-ForcedAligner-0.6B-hf
- https://pytorch.org/get-started/previous-versions/ （Windows CUDA12.8 wheel）
- https://pypi.org/project/transformers/5.13.0/
