# git-r28 · 2026-11-09 · 访谈被称呼者命名与正文去推测尾注

- 根据直接致谢/称呼与前后声音轮次，自动把“玛丽安”这样的被称呼姓名分配给对话对象而非正在致谢的人；邻居分组冲突时不强行命名。兼容西语原文与中文译文，姓名+履历介绍的 Sergio Marina 命名仍生效。
- 新生成的文字稿和旧标签清洗不再显示“（根据介绍推测）”；声学分组/原文保留，姓名与角色依据记录在内部 `speakerEvidence` 中，不要求人工批准。
- 拦截翻译模型把插件内部提示词回显为所谓中文正文，旧的翻译成功缓存也重新校验并自动重试；不把模型指令记作视频台词。
- 身份缓存 schema 升级至5；构造回归覆盖直接称呼、第三人称误判、歧义角色、无模型降级、短视频完整生成与旧标签；真实 Windows Edge/Ollama 待现场验收。

---

# git-r27 · 2026-11-09 · SSE 结束帧识别与本机一次自动恢复

- 修复 r26 `AI_STREAM_INCOMPLETE`：识别跨包 SSE、CRLF、UTF-8、EOF 未附空行的最终帧；终止的 `finish_reason=stop` 即使缺 `[DONE]` 也按可信完成处理。
- 真正缺失终止标志时，对本机 Ollama 同配置执行一次有界 `stream:false` 请求，只接受重取结果、不拼接旧半截稿。非本机服务不自动重试；失败保留原分段检查点。
- `length` 继续自适应拆分，内容过滤或工具调用不能作为完整文稿；设置页严格验证真实流式响应，不以非流式兜底虚报验证成功。
- 新增合成流协议/中断/HTTP失败/续跑/取消边界测试；目标 Windows Edge + Ollama 两小时实测待验。

---

# git-r26 · 2026-11-09 · 中西混合翻译分段补救、断句边界及受访者姓名映射

- r25 仍能看到 `Sergio Marina ... guiando数以千计...`：模型连续漏译后只是保留原文继续生成；现在对长句采用有界短语段补译并单片段保存检查点，只有合格中文才能标记 `translated`。模型完全失败则以 `〔未译原文：...〕` 明确标注，无人工审批，不冒充成功。
- 修复分离的极短“我们”被独立显示：在时间连续、前一说话人已结束、下一声纹可靠时将碎片接到后一位发言，不改变原音和原始 speakerID。
- 识别 `姓名 + 多项学历/职业介绍` 的访谈开场：相邻不同声纹的应答者自动显示 `Sergio Marina（根据介绍推测）`；不会误标介绍者或将任意姓名提及当作本人。
- 短/长视频正文共用改动；翻译策略检查点升至4、身份识别缓存 schema 升至4。新增 8 项 r26 重点测试；目标 Windows / Edge / Ollama 及实际访谈的质量仍待验收。见 `docs/UPGRADE_GIT_R26_TRANSLATION_SENTENCE_SPEAKER_BIO.md`。

---

# git-r25 · 2026-11-09 · 防止西班牙语/中文混排进入最终文字稿

- 现场截图中的 Sergio Marina 发言带有长段西班牙语，仅末尾接中文；r24 的“至少20%汉字”规则可误判为合格中文译文，导致外语片段被缓存。现在识别长段未译外语与明显过度压缩，允许保留短专名，自动按原发言重译。
- 上游 ASR 如把不完整中西混合译文标为 `done`，有原始 ASR 原文时将原文送进文字稿翻译，不覆盖存储的原始资料。
- 翻译检查点策略从2升级到3：旧的错误“成功”行重新校验，旧的保底原文及耗尽次数重新处理；修正译文后，凡内容已变化的断句分片自动失效并重做，不重复使用旧外语断句缓存。
- 若本地模型仍无有效译文，继续自动保留原文并在详情说明；分片之间不再将外语最后一个词与中文直接黏连。不使用外部翻译服务、不要求人工逐条审批。
- 新增短/长视频、旧缓存和截图同类语句的构造回归；真实 Windows/Edge/Ollama 翻译质量仍待现场确认。见 `docs/UPGRADE_GIT_R25_TRANSLATION_INTEGRITY.md`。

---

# git-r24 · 2026-11-09 · 翻译失败自动恢复，无人工审核阻断

- 修复 r23 `AI_TRANSLATION_INVALID`：模型返回缺少多数 ID 或 JSON 格式不完整时，已翻译行复用，其他按有界批次自动重试；最后单条发言改用非 JSON 的纯文本中文翻译，以适配格式控制较弱的本地模型。
- 完全无法取得可用中文时保留原文并继续完成文稿，结果详情标记未译数量而不要求人工确认；不把外文冒充中文、不放行数字冲突；外部服务 HTTP 403/500 等真正故障仍会报告。
- r23 已成功译文继续缓存，旧耗尽的重试计数不会直接使 r24 失败；长视频保存新策略版本和保底标记。短/长文生成使用同一机制，不修改声学识别与原始录音。
- 构造回归包含普通/长视频 JSON 失败后自动单条译文、旧检查点迁移、无译文时结果完整、数字防护与断点续跑；目标 Windows Edge 和真实 Ollama 输出质量仍需现场确认。见 `docs/UPGRADE_GIT_R24_AUTO_TRANSLATION_RECOVERY.md`。

---

# git-r23 · 2026-11-09 · 进度不跳变与外语文字稿缺项自动补译

- 根因：长文重入时扫描全部缓存已完成章节也发送了 `phaseProgress`；仅真正开始的新模型调用才发进度，记录轮次号；保留分片检查点与 r22 自适应来源拆分。
- 固定高度的当前阶段进度面板：视频标题、阶段 X/N、合并轮次、当前批次与已完成批次数、阶段完成率；不伪造全流程百分比或 ETA。
- 进度仅增量更新相关 DOM，减少长视频 UI 卡顿；收起视频面板后任务继续。使用原有 `chrome.action` 展示 Edge 工具栏 AI 角标、视频/阶段标题，按 tab 隔离；取消/完成后清除。
- 翻译模型漏返回 ID 时不再整批丢弃：独立校验并保留合格译文，只重试缺失/重复/未译或数字冲突的条目；重试最多 4 次并按 8→4→2→1 条缩小请求。长视频每条部分译文与尝试数分片持久保存，下一次同源任务只补译剩余 ID；旧 r22 翻译检查点兼容。
- 自动化覆盖阶段内进度单调、缓存阶段不重播、多轮转变、翻译缺项/错误/中断续跑；目标 Windows Edge/Ollama 两小时真实现场仍待验收。详见 `docs/UPGRADE_GIT_R23_TASK_PROGRESS.md`。

---

# git-r22 · 2026-11-09 · 两小时知识整理持续长度截断修复

- 定位 `AI_DOCUMENT_TOO_LARGE：章节多轮续写仍无终点`：r21 的通用续写在模型连续返回 `finish_reason=length` 时，会重复最多32次并最终失败。其根因不是章节数阈值，而是未收敛的续写策略以及部分阶段的输出预算与提示不匹配。
- 长文取材、主题索引、正文和最终主题合并改为按原始输入自适应拆分：仅在截断或确实过长/HTTP413时缩小来源并重试；已完成子项按分片检查点保留，递归层数有上界。不给未完成模型片段“已完成”标签。
- 极端情况下模型持续截断时，最小分片保留对应原始来源文字，审计注明未充分编辑，而非丢弃、无限续写或发布被截断的模型正文。r21 已完成分片继续复用；attempt32未完成草稿归档后重新按来源生成，不删除原始转写、音频或旧文稿。
- 缩短内部取材/索引和章节单次目标篇幅，使之与 `max_tokens` 更匹配。403/401/429/5xx 仍作为真实服务错误返回，不绕过授权。
- 新增完整来源切分、长文持续截断、部分失败后续跑、r21兼容、HTTP413及原403保护回归；真实两小时 Edge/Ollama/RTX 环境与主题内容质量仍待现场测试。

# git-r21 · 2026-11-09 · 长文流式 HTTP 403 诊断与验证补强

- 修复长文 HTTP 非 2xx 时只返回“请求失败”的问题：统一普通与长文请求状态码分类，区分本机 Ollama 来源拒绝和自定义服务权限/额度/策略拒绝；不回显令牌、URL 查询参数、原文、服务响应体。
- 设置页“保存并验证”现在分别验证 `stream:false` 普通聊天和 `stream:true` 长文调用；两项均成功才显示通过，返回实际 SSE/JSON 模式。仅发送固定短测试提示，不发送用户视频笔记。
- 403 不盲目重试、跳过鉴权、自动切换供应商或模型。已有分片检查点、原始记录和旧文稿保持不变；失败后可在权限/来源修复后从相同视频、范围和模型续跑。
- 增加构造回归（普通成功/流式 403、本地与自定义拒绝、敏感信息脱敏、错误码、SSE、检查点续跑）；真实目标机服务端 403 根因仍需用户日志/现场设置确认。

## 扩展 V0.12.1 · git-r20 · 2小时视频稳定性、自动角色及疑点决策

- 对超过1小时的实时摘录：流式ID记录优先增量合并；实时面板只渲染可见末尾，点击加载更早片段再扩展；合并频繁事件的重绘与存储写入，定时强制落盘，不删除整段历史或影响导出。
- 长文生成：按一次本地模型调用拆分为多个 MV3 短消息，由当前视频页自动接力；首次输入只存一次，接力消息不再复制数千条长转写。单次模型请求有空闲/总耗时上限，错误保留已完成分块。
- git-r19 的超大单体检查点升级为分块键，首次续跑原地迁移；证据→索引→章节→跨章节整合阶段各自持久化。最终主题整合按有界章节组处理；无法无损进一步压缩时保留已完成的全部材料并说明可能仍有少量重复，避免整篇失败或假称完全去重。
- 角色标签自动显示本地模型结合对话推断的具体内容身份；新上下文可自动修正。只有原文/字幕支持时才绑定真实姓名，无法判断的身份不虚构；不把角色判断变成用户必须审批的流程。
- 对一般技术性告警和模型可复核的小问题尽量自动处理；真正会改变语义的否定/数字/不可信翻译仍保留提醒，保留原始听写与机器建议，不假称无需核对即可证明真实。
- 新增模拟2小时长文续跑、r19检查点迁移、合并收敛以及增量说话人/提示回归。真实 Windows + Edge + Ollama 运行超过2小时的延迟、断点及生成质量仍待目标环境验收。

---

## 扩展 V0.12.1 · git-r19 · 知识主题合并与上下文角色命名

- 知识文档生成增加最终主题级统稿：跨长文分批章节递归合并重复主题，按“大主题 → 子主题”重排；相同定义/解释/例子/结论合并，保留独特细节、数字、条件、反例及不同发言者观点归属。短文统稿提示也同步强化，避免仅按时间窗口堆叠。
- 长文检查点 schema 升为3，单独保存每层主题合并结果；失败可从已完成章节/合并检查点续跑，不把未完成合并标记为完成。
- 说话人角色推理改为读取同一声音多条台词及前后相邻对话，允许输出经证据约束的内容称呼（如主持人、受访专家、提问者、医生、母亲、主人公）；姓名与角色称呼分离。
- 姓名绑定新增“紧邻明确嘉宾/人物介绍后由该声音接话”的证据路径；第三人称提及、普通称呼和猜测仍不绑定。角色/姓名分析缓存版本升级，旧会话会重新检查。
- 新增主题合并、角色上下文、描述性称呼校验、主持人介绍姓名等回归测试。自动化测试通过；真实 Ollama 模型的去重质量和声纹聚类准确率仍需目标 Windows 视频验收。

## 扩展 V0.12.1 · git-r18 · 外语文字稿自动翻译

- 修复“文字稿”模式只做标点整理、直接输出西班牙语等原文的问题：短文与长文两条生成路径都增加独立翻译阶段，外语发言逐条翻译为简体中文后再做断句。
- 翻译按声音轮次/短片段保留 ID 与说话人顺序；原始 ASR、原始语言、时间戳和历史文稿不覆盖。ASR 侧已完成且仍可信的中文译文可复用；待核对/失败/关闭的翻译会重新翻译。
- 对翻译返回执行 JSON、ID、中文输出及阿拉伯数字校验。模型仍返回外语、缺项或数字不一致时明确失败，不再把未翻译原文静默发布成“中文文字稿”。长文翻译结果按来源指纹保存检查点；升级检查点版本，旧的未翻译结果不会被误复用。
- 新增短文/长文端到端模拟、语言识别、ID/数字/未翻译拒绝测试。自动化测试通过；真实模型的翻译忠实度仍需人工双语验收。

## 本地服务 0.12.1 · git-r17 · Sherpa-ONNX 版本缺陷修复

- 根据 Windows 现场日志与上游变更记录，确认 git-r16 仅隔离了原生崩溃，没有修复底层 Sherpa 运行库。原工程固定 `sherpa-onnx==1.12.34`；上游 1.12.39 修复 pyannote 分离的 offset-by-one，1.13.1 又加入说话人分离边界检查以防止 SIGSEGV。
- 将可选说话人运行库固定升级到 `1.13.8`；该版本提供 Python 3.11/Windows x64 预编译 wheel。运行时低于 1.13.1 或无法确认版本时，禁用声学分组并明确提示升级，不再加载旧原生库。
- 安装器版本核验改为严格检查 1.13.8；模型加载 smoke test 改在隔离子进程执行，原生故障不会杀死安装器。
- 新增 `CHECK_SPEAKER_RUNTIME.bat`，/health 返回 Sherpa 版本、安全门槛和可用性；新增版本门禁及 worker 启动测试。
- Ollama HTTP 500 与 Sherpa 原生访问冲突仍是两个独立故障；本版不声称修复 Ollama runner。真实 Windows 1.13.8 运行和真实 Ollama server.log 仍需现场验收。

## 本地服务 0.12.1 · git-r16 · Sherpa 原生崩溃隔离与 ASR 容错

- 将 sherpa-onnx 声学分段与 embedding 推理移入持久独立子进程；Windows 原生访问冲突/进程退出不再直接终止 FastAPI/ASR 父进程。
- 对静音、极短、非有限数值及无说话人输出增加保护；空 diarization 作为正常未归属结果，不调用空 embedding。
- 子进程异常退出、初始化失败或推理超时后关闭本轮声学分组，直到本地服务重启；完整音频继续走已选 ASR，不猜说话人。
- 服务停止时清理隔离 worker；`/health` 暴露 speaker worker 生命周期状态；同步更新 HTTP 与 WebSocket 服务版本。
- 新增原生子进程崩溃模拟、空结果、线程调用、ASR fallback 与 Ollama HTTP 500 缓存/worker 生命周期测试。
- Ollama 内部 HTTP 500 仍属于上游运行时故障，本版不声称修复 Ollama runner；验证服务不崩溃、原音保留及既有冷却策略。
- 扩展保持0.12.1、服务升至0.12.1、安装器0.8.4与协议5不变；真实 Windows sherpa/Ollama模型和声纹准确率仍待目标机验收。

## V0.12.1 · Automatic narrative role labels for acoustic speaker groups

- 区分声纹分组（谁发出声音）与剧情类型（旁白、系统播报、剧情角色、主持人、嘉宾）。
- 新增本地 LLM 角色推理，跨同一声纹多条发言采样、引用校验与冲突保留；未知不猜。
- 新音频记录累计后自动触发有限频率角色检查；展开角色区仍可补检。
- 音色编号、姓名证据、类型标签分别持久化，不重写任何原始文字或已有文稿。
- 扩展版本 0.12.1，本地服务保持 0.12.0，安装器保持 0.8.4。
- 构造数据与浏览器 DOM 测试通过；真实影视多角色准确率和跨窗口声纹质量仍待目标 Windows 验收。

# V0.12.0 · git-r14 · 长文检查点、剧情人物姓名证据、视觉500降级

- 大型整理任务按 token 预算切分，按模式保留原始台词/证据，主题分层汇总、章节分次输出，stream SSE 进度与 `finish_reason=length` 续写；逐阶段保存来源ID、输入指纹与已完成章节，同源同配置再次生成会续跑，错误不能标完成。旧小任务逻辑保留以兼容旧输入。
- 修复角色姓名分析每次新增记录使整体指纹变化、从头重扫的游标问题；允许同步字幕的姓名标签先作为候选参与推理，防止纯字幕信息在文字筛选阶段被遗漏。字幕绑定至少两条不同时间记录，直接自报姓名可绑定；剧情旁白不猜真实身份。
- 针对已有 Ollama 日志的 `Unexpected empty grammar stack`，字幕 OCR 与 LoRA 视觉筛选不再请求强制 JSON Grammar，改为非约束返回后严格验证。结构化文字标点仅在明确 grammar/GBNF 5xx 时单次去格式重试；视觉失败不会阻塞 ASR 或覆盖原文。
- 扩展/服务均升0.12.0，安装器0.8.4、音频协议5不变。新增定向与完整回归，真实 Windows/长视频及新日志仍需验收。

---

# V0.11.4 · git-r13 · Ollama声学分段与自动说话人编号

- 修复 Ollama Qwen3-ASR 没有词级时间戳时，旧 `SpeakerAnnotator` 对全部转写一律标为「无法归属」的问题。
- 优先利用可选 sherpa-onnx 本地声学分段/声纹模型判断发言区间，单一声音覆盖整个识别窗口时保守分配会话内编号；多人依次发言则按声学边界分别向 Ollama 发送音频，再给出不同编号。**没有推断真实姓名/身份**。
- 重叠发言、声音太短、声纹不确定、模型缺失、切换过快时标记「待确认」；既不虚构词级时间戳，也不把重叠录音复制进两个人的发言。未安装 speaker 模型时保留原文字。
- 分段识别结果先汇总、再由旧 `StreamStore.commit()` 原子提交：中途错误不推进 SQLite 音频水位，也不写入半成品声纹状态；非静音片段没有输出时退回整窗原文。
- 此版本只更新本地服务，不更新 Edge 扩展或音频协议，不影响本地模型、已保存笔记、缓存或翻译。新增14个合成测试；真实 Windows/sherpa/Ollama 多人语音精度仍待实测。

---

# Installer 0.8.4 · Ollama Qwen3-ASR 自动下载（业务组件仍0.11.3）

- `INSTALL_ALL.bat` 默认全量安装及 `-Profile models/core` 增加本地 Qwen3-ASR 模型检查与缺失自动拉取。
- `-Profile asr -AsrProfile ollama17` 不再只验证已安装模型：缺少时使用本地 Ollama `/api/pull` 流式下载，完成校验后才执行原有合成音频自检与选择切换。
- 复用现有断点缓存、有限重试、进度报告、Fake-IP/证书/磁盘错误分类；已装模型跳过。自动拉取仅支持 `frozenlab/qwen3-asr:1.7b` 和 `:0.6b`，其他自定义标签需先手动安装。
- 不修改 Edge/Server 音频协议、听写、缓存、已存偏好或模型文件；没有执行真实 Windows Ollama 模型下载/推理。

---

# V0.11.3 · git-r11 · Ollama HTTP 500 backoff and diagnostics

- Preserve durably cached audio when the Ollama `/api/chat` backend returns HTTP 5xx. After two consecutive 5xx failures in one session, cool down for 15 minutes instead of flooding the server. Existing explicit retry can resume after fixing Ollama.
- Categorize Ollama runner exit, audio projector incompatibility, memory failure, or generic server error from sanitized HTTP 5xx body; do not store raw error paths or transcripts in the telemetry.
- Add a local-only diagnostic launcher (`CHECK_OLLAMA_ASR.bat`) that checks Ollama version/model status without audio by default, and optionally sends a short user-provided WAV. Never includes raw audio or generated transcript in its output report.
- This is a failure-handling and diagnosis fix, NOT proof that the frozenlab Qwen3-ASR model can run on the user's Windows GPU. No PyTorch download, model reinstallation or notebook migration.

# V0.11.2 · git-r10 · STOP_LOCAL_ASR 与 ASR配置403修复

- 修改STOP_LOCAL_ASR.bat的PowerShell项目根路径传递，避免末尾反斜杠/引号造成GetFullPath参数非法。
- `/asr/config`接受没有Origin但携带合法扩展身份头的本机配置请求；同时校验Origin与ID一致，拒绝网站来源或伪造不匹配来源。新增仅限扩展来源的CORS预检支持；不向所有网站开放API。
- 设置页GET/POST都携带`X-VKN-Extension-ID`，403显示服务端错误原因，避免误认成Ollama API Key问题。
- 原Whisper、Ollama、Transformers Qwen、VKN5缓存/笔记/翻译路径不变；未实测用户Windows Edge。

# V0.11.1 · git-r9 · Ollama Qwen3-ASR adapter

- Reuse previously downloaded local `frozenlab/qwen3-asr:1.7b` through `127.0.0.1:11434/api/chat`, sending standard 16kHz mono PCM16 WAV as Base64 `images`. Parse `language` / `<asr_text>`; no API key or PyTorch needed for Ollama path.
- Keep VKN5 audio buffer, durable SQLite/ack/retry and translation; use owner-window time only, no invented word timestamps or forced speaker labels. Preserve old Whisper/native Qwen options and rollback.
- `INSTALL_ALL` opt-in `-AsrProfile ollama17` validates local tag + synthetic audio before changing profile; browser options allow saving next-start selection. No model download, no notebook deletion, no silent runtime switch.
- Added contracts and fallback tests; real Windows/Edge/Ollama inference and measured accuracy remain target-pending. Summary100s timeout unchanged.

# 0.11.0 · ASR adapter preview

- Added opt-in native Qwen3-ASR/ForcedAligner worker, isolated runtime, engine provenance, timing validation and explicit rollback.
- Integrated setup in existing INSTALL_ALL; activate only after target runtime checks; preserved old settings/notes.
- Added local short-audio evaluation tool; real model accuracy and Windows/CUDA acceptance remain pending.
- Did not fix summary timeout, complete translation or speaker-name reasoning in this release.

# 变更记录

## git-r29 · 2026-11-10 · 语义断句、自报姓名、精简整理模式

- 文字稿标点任务现在包含同一发言轮次内、相邻子单元的只读语境；严格按ID验收正文，只允许增删标点/换行，不允许修改词语、数字和否定。
- 成稿前新增句流二次衔接：处理独立条件引导词和紧随其后的依赖从句，例如错误句界“再打不赢。行的话，再请……”改为连续句；不修改词语“行”本身，以免擅自篡改ASR原文。
- 长视频已缓存的旧标点分块在r29自动按新策略失效并重算，翻译成功片段与来源缓存不删除。
- “大家好，我是社长”“我叫小雨”“my name is Sergio Marina”“me llamo Sergio Marina”等明确自报姓名直接绑定当前声纹，模型漏报或返回空候选时仍能识别；多声音冲突保留中性标签，引用他人介绍不冒充自报。
- 整理入口只保留「知识文档」「文字稿」「按我的要求」，移除「小说」「剧本」两种新建模式。旧版成品仍可查看/导出，并保留历史文稿名称；旧配置迁移到知识模式。
- 补充r29专项单元、浏览器DOM验收；尚未运行真实Windows Edge / 两小时Ollama / 原音说话人准确率对照，相关任务仍为in_progress。



## 0.10.2 · git-r7

- 旧源码复现切换页面前点击完整阅读可开错视频；同步隔离、代号防迟到加载、保存快照及来源校验。
- 预览签名包含视频与完整正文哈希；新文稿绑定来源，阅读/复制/导出沿用选中快照。
- 删除单项下载冗余max_downloads=1，防止直接extract_info将首项完成视为错误。
- 失败分类、匿名重试、显式单次YouTube会话重试、可选权限撤销。默认匿名，凭据只在内存与子进程管道，不保存文件。
- 缓存失败不显示仍在下载的进度；20MiB传输量不当作已保存。原有效缓存TTL不延长。
- 构造测试和真实DOM验收；Windows/YouTube真实下载与模型未实测。未改变100秒长任务/ASR模型。

# 0.10.1 / git-r6

- 实际字幕证据下的英文词拼写校正，不再只限等长汉字；保留画面英文行。
- 已授权字幕采样与视觉推理分离，有限内存队列、跳过状态、停止释放。
- 生成前复核已存字幕，无证据不凭名称常识替换。
- 文字稿短单元逐项校验，失败项有限标点位置重试，基础排版回退保留全部字词。
- 无新依赖/权限，原文/数字/否定保护、移除过滤的行为保留。详见docs/UPGRADE_V0101.md与qa/V0101_TEST_REPORT.md。

# 0.10.0 · 2026-11-07 · git-r5

- 活动字幕优先、已授权视频底部两帧本机视觉后备；按会话/时间/边界核对同音局部词，独立修订可撤销。
- 移除无关内容过滤UI/调用/排除行为，旧存储惰性兼容不生效。
- 单字残句衔接与独立回答保护；跨片段上下文同音推断，保持原文。
- 内容尺寸面板、无结果区隐藏、结果定位仅内部滚动，失败保留旧结果。
- 真实模型/目标Windows Edge未测试；长文100秒问题未修复。

# V0.9.0 · git-r4

- 页面听写增加显式标签页音频选择器；原生Alt+Shift+V开始/停止；取消和迟到回调受会话代际保护，不默认开启录音。
- 连续同人碎片合并成发言轮次，保留原始ID/时间；未知、换人、长停顿、跨会话和过滤缺口分开。
- 文字稿用有字符保护的标点编辑，不用通用摘要生成器；HTML硬换行保留在同一发言段。
- 五种模式定义不同成品格式；知识跨块最终统稿，剧本/小说按内容衔接；删除应用添加的机械分块标题。
- 正文导出与来源/校对详情分离，历史结果/原文不删除；审核信息仍随审计JSON保存。
- 服务0.8.0及安装器0.8.1未改。100秒总等待/非流式/持久续跑仍待独立解决。

---

# V0.8.0 · 2026-11-06

## git-r3 · 安装器0.8.1（业务组件保持0.8.0）

- 增加INSTALL_ALL.bat统一入口；五个旧安装入口改为兼容转发。
- Ollama已有模型检查、流式进度、空闲/无进展/总期限、有限退避、错误分类与元数据复核。
- 真实下载返回非公网重定向时停止无效重试；只生成诊断，不修改DNS/TLS/hosts或代理安全策略。
- 复用项目venv和缓存；Whisper预下载/加载；有确认的WinGet系统工具安装；结果逐项报告。
- 新增安装器单元/真实回环HTTP测试；仍未在目标Windows/真实CDN完成验收。
- 不改扩展/后端算法，不声称修复100秒长文推理问题。


- 自动声音分组默认流程、证据型主持人/嘉宾标签，取消命名表单。
- 显式公开视频下载、72小时本机缓存、取消/播放/删除与容量/路径保护。
- 整理前本地上下文短语校验、修订对照、原文保留。
- 移除在线字幕按钮、平台字幕接口与后台自动扫描；手动SRT/VTT保留。
- SESSION_BUSY可重试、缓存拒写后有序重放、发送任务监督、心跳与握手期限、工作任务监督。
- 启动器保存退出码、有限日志和故障堆栈；新增CHECK_LOCAL_SERVICE.bat。
- 未修复长文100秒、非流式或可靠续跑；真实Windows/模型/网站待验收。

---

# 变更记录

## git-r1 · 2026-11-06 · 工程归档

- 以已有扩展0.7.2/服务0.7.1/协议5归并源码，不改变`extension/`与`server/`业务代码。
- 并入独立超时诊断脚本和9项测试；100秒长文机制保持现状并列P0待修。
- 重写README、加入AGENTS、需求、当前架构、数据协议、已知问题、开发、验收、迁移、隐私及发布资料。
- 加入25项任务和32项验收场景的JSON/Markdown；只有本次工程交接项标done。
- 补齐Git忽略、换行、暂存检查、CI和Issue/PR模板；不附带用户笔记、模型、环境和数据库。
- 统一测试入口自动发现全部用例；不再默默跳过缺失工具；不在测试命令中隐式安装依赖。
- 开发浏览器测试的路径改为可配置，截图改写忽略目录；历史测试仅作溯源。
- 本次实际测试结果和未执行范围以`qa/BASELINE_TEST_REPORT.md`为准，不抄历史计数冒充新证据。

## 既有功能基线

0.7.2：可逆内容筛选，可选本地主题判断。0.7.1：紧凑界面、五种整理方式、原文/译文/人工核查。0.6.0：说话人实验模块与结果导航。0.5.x：有序缓存、翻译、配置读取、本地来源及停止链路修复。历史说明见`docs/history/`和保留的版本文档。

这些版本摘要只说明原包功能，不证明所有真实环境问题已关闭。
