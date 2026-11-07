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
