> git-r29：只保留知识文档、文字稿、自定义三种新建整理方式；自报姓名自动关联声纹，分块断句增加邻句语境和跨块句流衔接。详见 `docs/UPGRADE_GIT_R29_SENTENCE_SELF_INTRO.md`。

> **git-r28**：访谈文字稿自动识别直接被称呼的人物（如 Sergio 感谢“玛丽安”），把姓名关联至另一位声音而非当前发言人；最终标题只显示姓名，不写“根据介绍推测”。翻译模型回显内部提示词时会拒绝并重试，旧译文检查点也重新校验。见 [升级说明](docs/UPGRADE_GIT_R28_DIALOGUE_NAMES.md)。真实声纹/Windows Edge/Ollama 两小时视频仍需目标机验收。

> **git-r27**：修复长文流式 `AI_STREAM_INCOMPLETE`：SSE 最后帧/`finish_reason` 完整解析，本机 Ollama 无结束标记时最多自动非流式重取一次，拒绝发布半截稿并保留检查点；设置页验证不以兜底结果冒充流式成功。见 [r27 升级说明](docs/UPGRADE_GIT_R27_STREAM_COMPLETION_RECOVERY.md)。真实 Windows Ollama 长视频仍需实测。

> **git-r26**：处理 r25 后仍出现的外语未译片段、单独的“我们”及访谈介绍中的姓名未映射。加入长句自动按短语段翻译、无法翻译时明确标注而不伪装成功、极短断句合并；在姓名＋多项履历介绍后，为紧接的不同说话人使用 `Sergio Marina（根据介绍推测）`。详见 [r26 升级说明](docs/UPGRADE_GIT_R26_TRANSLATION_SENTENCE_SPEAKER_BIO.md)。真实本地模型和视频效果待实机验收。

> **git-r25**：修复 r24 文字稿中“西班牙语大段残留 + 中文结尾”的错误拼接：译文语言完整性校验、ASR不完整`done`回原文自动补译、旧翻译与断句检查点重校验。源文、旧笔记不删除；真实 Windows Ollama 需复验。见 [升级说明](docs/UPGRADE_GIT_R25_TRANSLATION_INTEGRITY.md)。

> **git-r24**：修复长视频文字稿 `AI_TRANSLATION_INVALID` 反复中止：漏译逐行自动补译，复杂 JSON 连续失败时对单条发言改用纯中文翻译；旧版耗尽的重试次数迁移、合格译文复用。无可用译文的局部自动保留原文并在详情标记，不要求人工审核，也不冒充中文已译完。见 [r24 升级说明](docs/UPGRADE_GIT_R24_AUTO_TRANSLATION_RECOVERY.md)；真实 Windows/Ollama 两小时视频尚待现场验收。

> **git-r23**：长视频整理现在显示稳定的分阶段进度条和 Edge 工具栏 AI 状态；外语文字稿发生 `AI_TRANSLATION_INVALID` 时仅重新翻译缺失/不合格的发言，不重复已验证条目，长文可按检查点续跑。参阅 [r23 升级说明](docs/UPGRADE_GIT_R23_TASK_PROGRESS.md)。真实两小时 Edge/Ollama 验收仍待完成。

---

> **git-r23（长文整理进度 UI）**：已修正两小时视频整理“汇总全局主题，第 1…55/148 批”不停跳变：进度只在真正开始新模型请求时更新，不重新播放缓存批次；新增固定高度的阶段进度条、合并轮次、视频标题和 Edge 工具栏 `AI` 角标。进度条为**当前阶段批次进度**，不是全部任务完成率；不能凭它推算剩余时间。无需 Windows 常驻程序；关闭视频标签可能中断任务，旧检查点仍可续跑。详见 [r23 升级说明](docs/UPGRADE_GIT_R23_TASK_PROGRESS.md)。

---

> **git-r21（长文 AI_HTTP_403 诊断修复）**：r20 的长文流式请求返回 403 时只会报告笼统错误，设置页也仅检验非流式短文本。r21 共用 401/403/413/429/5xx 分类，分别给出本机 Ollama 来源限制和自定义服务访问拒绝的排查路径；“保存并验证”现依次执行非流式聊天和与长文一致的 `stream:true` 请求（只发固定测试文本）。继续保留 r20 分片检查点、音频和旧文稿。**此修复不会突破服务端鉴权；真实 403 的最终解除仍需核验模型服务/配置。** 见 [r21 升级说明](docs/UPGRADE_GIT_R21_LONGFORM_403.md)。

---

> **git-r20（两小时视频优化）**：实时摘录使用增量/窗口渲染，长文整理分多轮自动续跑并保存可迁移的分块检查点；自动显示有证据的说话人内容身份，减少不必要的审核提示。扩展 `0.12.1`、服务 `0.12.1`、安装器 `0.8.4` 未改变。请见 [r20 升级与回退](docs/UPGRADE_GIT_R20_LONG_VIDEO_AUTOMATION.md) 和 [测试范围](qa/GIT_R20_LONG_VIDEO_TEST_REPORT.md)。目标 Windows/真实两小时视频尚待现场验收。

---

# VideoKnowledge V0.12.1 · 旁白 / 系统播报 / 剧情角色自动分类

> **git-r17 修复包**：在 git-r16 子进程隔离基础上，将 Sherpa-ONNX 从 1.12.34 升级并固定到 1.13.8。上游 1.13.1 起已加入 speaker diarization 边界检查，防止 SIGSEGV。旧版本会被运行时门禁拦截，安装自检也在隔离进程运行。Ollama HTTP 500 仍需独立诊断。详见 [git-r17 升级说明](docs/UPGRADE_GIT_R17_SPEAKER_BOUNDS_FIX.md)。

在原有 **音频声纹分组** 的基础上，新增独立的**声音角色类型推测**：本地 Ollama 文字模型综合不同声音的多条台词、可验证的字幕以及发言顺序，给出 `剧情旁白（推测）`、`系统播报（推测）`、`剧情角色（推测）` 等标签。没有足够证据仍保留 `说话人N`，不会从高低音或片中提到的人名直接推定身份。**角色类型不等于真实姓名，声纹聚类仍由本地 sherpa-onnx 完成。**

新转写累计后自动、有限频率地触发角色分类；展开“自动识别声音与剧情角色”也会检查。不需要人工填写名字。姓名仍只使用直接自报与稳定同步字幕的证据；旁白介绍人物仅作为线索。保留原笔记、ASR 模型选择、音频缓存、说话人编号与已有生成文档。

**版本：扩展 0.12.1 / 本地服务 0.12.1 / 安装器 0.8.4 / VKN5 协议 5。** git-r17 只更新本地 Sherpa 运行库与安装自检：请停止服务、覆盖源码后运行 `INSTALL_SPEAKER_MODEL.bat`，再用 `CHECK_SPEAKER_RUNTIME.bat` 确认 1.13.8；不需要重新安装/重载 Edge 扩展，也不需要删除或重装已有说话人模型。详见 [角色分类说明](docs/UPGRADE_V0121_ROLES.md)、[git-r17 升级说明](docs/UPGRADE_GIT_R17_SPEAKER_BOUNDS_FIX.md) 和 [测试报告](qa/GIT_R17_SPEAKER_BOUNDS_TEST_REPORT.md)。

---

# VideoKnowledge V0.12.0 · 可恢复长视频整理与证据式姓名推理

当选中视频文字超过安全阈值时，自动使用**分块取证 → 全局主题索引 → 分章节写作 → 截断续写 → 来源覆盖验证**；成功的块和章节保存在原扩展本地检查点。同视频、同模型、同范围及原文不变时可直接重新点击“生成整理”续跑。可新建知识文档/文字稿/自定义三类结果；之前生成的剧本/小说成品仍可查看与导出，原文、笔记和历史结果不删除。

自动角色姓名采用声纹编号与直接自报姓名、同步字幕标签的可验证证据，不对旁白提及人物强行绑定声纹；视觉字幕 JSON Grammar 故障改为严格校验非约束回答。**尚未在目标 Windows 真实长视频与新版最新 Ollama 日志上验收。**

[升级与回退说明](docs/UPGRADE_V0120_LONGFORM_IDENTITY_500.md) · [测试报告](qa/V0120_LONGFORM_IDENTITY_500_TEST_REPORT.md) · [当前状态](docs/STATUS.md)

当前版本：扩展 `0.12.0`、本地服务 `0.12.0`、安装器 `0.8.4`、VKN5音频协议 `5`。已有模型无需重装。请以 `VERSION.json` 为准；以下为历史版本记录。

---

# 服务端0.11.4 · Ollama ASR自动说话人分段（扩展仍0.11.3）

修复 Ollama Qwen3-ASR 无词级时间戳时无法分配说话人编号：**先做本地声学说话人分段，再按发言片段分别转写**；若可靠检测到整窗只有一个说话人则继续一次性转写并附保守的编号。重叠/短音频/模型缺失均不猜身份、不删除文本。详情：[升级说明](docs/UPGRADE_V0114_SPEAKER_OLLAMA.md) · [测试范围](qa/V0114_SPEAKER_TEST_REPORT.md)。

已安装 speaker 声学模型时，停止本地服务、覆盖本轮补丁并重启即可；缺少模型则先运行 `INSTALL_ALL.bat -Profile speaker`（仅可选分组组件，不会重新下载 Qwen3-ASR）。只有**新录制/仍有PCM缓存可重转写**的内容能够利用声纹，旧文字稿不能仅凭文字恢复不同人的声音。

---

# 安装器 0.8.4 · Ollama Qwen3-ASR 自动补装（业务版本仍 0.11.3）

`INSTALL_ALL.bat` 的默认全量安装现会检查 `frozenlab/qwen3-asr:1.7b`（或已保存的 `ollama17` 模型标签），存在则跳过，缺少时用本地 Ollama `/api/pull` 下载，并验证 `/api/tags` 与 `/api/show`；不会因此擅自切换用户已有的识别引擎。

```powershell
.\INSTALL_ALL.bat                                      # 全量组件，含 Qwen3-ASR
.\INSTALL_ALL.bat -Profile models                       # 本地文字 / 视觉 / Qwen3-ASR 三模型
.\INSTALL_ALL.bat -Profile asr -AsrProfile ollama17     # 补装 Qwen3-ASR、音频自检成功后才切换
.\INSTALL_ALL.bat -Profile asr -AsrProfile ollama17 -OllamaAsrModel frozenlab/qwen3-asr:0.6b
```

下载只走现有回环 Ollama 服务，沿用有界重试/流式进度/校验，不安装 PyTorch；不删除缓存、笔记、私有配置。完整操作与边界见 [安装器升级说明](docs/UPGRADE_INSTALLER_084.md)。上一版 ASR 业务代码与 Ollama HTTP 500 问题处理不变。

---

# V0.11.3 · Ollama ASR HTTP 500 diagnosis and retry protection (git-r11)

The service can accept Edge audio but Ollama can return HTTP 500 when its model runner fails. This update preserves the VKN5 audio cursor and retries with a 15-minute cooldown after two consecutive 5xx errors; the explicit in-page retry resets the delay after the underlying Ollama problem is fixed. It categorizes a safe subset of Ollama errors and adds `CHECK_OLLAMA_ASR.bat` (optional 16-kHz WAV argument). **It does not repair an upstream Ollama runner crash or automatically switch engines.**

See [step-by-step diagnosis](docs/UPGRADE_V0113_OLLAMA_500.md). Existing `.venv`, local notes, cached audio, model files and private settings are not deleted. Both extension and local server use version **0.11.3**; the installer remains 0.8.3.

---

# V0.11.2 · Windows停止脚本与本地ASR设置修复（git-r10）

修复STOP_LOCAL_ASR.bat因Windows路径引号解析报“GetFullPath非法字符”，及Edge设置“检查识别引擎”收到HTTP 403。只需合并覆盖升级包的代码，不删除模型/笔记/SQLite/.venv/私有配置；扩展和服务均升级至0.11.2。安装器仍是0.8.3、协议5。

先停止旧服务，再合并覆盖补丁；运行`START_LOCAL_ASR.bat`后在`edge://extensions/`重新加载原扩展。设置页“检查识别引擎”应该显示当前与下次启动引擎状态；此检查不加载或下载模型。真实Windows端尚待用户复核。详情见[本版升级说明](docs/UPGRADE_V0112_CONFIG_STOP.md)。

---

# V0.11.1 · Ollama ASR 适配（git-r9）

**新增可选的本机 Ollama Qwen3-ASR-1.7B 语音识别。** 已经通过 `ollama pull frozenlab/qwen3-asr:1.7b` 安装模型时，不必下载 PyTorch CUDA 或独立 `.venv-qwen`。原 Whisper 与原生 Transformers Qwen 回退保留。**真实 Windows Edge/Ollama 模型准确率未在当前环境实测。**

```powershell
.\STOP_LOCAL_ASR.bat
.\INSTALL_ALL.bat -Profile asr -AsrProfile ollama17
.\START_LOCAL_ASR.bat
```

打开 `http://127.0.0.1:8765/health`，检查 `asr_backend.backend` 是否为 `ollama-qwen3-asr`。在扩展设置“本地听写 → 识别引擎”也可以选择本机已安装的模型并保存为下次启动；不会中断当前录音。回退：`INSTALL_ALL.bat -Profile asr -AsrProfile legacy`。完整说明见 [Ollama ASR升级/回退说明](docs/UPGRADE_V0111_OLLAMA_ASR.md)。

**本方案没有逐词时间戳，因此不会虚构说话人归属或置信度；外语原文进入既有翻译队列，音频失败不会推进持久游标。** 长文整理100秒超时仍是独立待办。下面内容包含历史版本说明，具体版本以 `VERSION.json` 为准。

---

# V0.11.0 · ASR引擎接入预览

**本轮已接入代码，真实模型质量待验收；不会自动替换已有设置。** 选择新模型只用一个安装入口：

```powershell
.\INSTALL_ALL.bat -Profile asr -AsrProfile qwen17
```

停服务后运行；成功加载检查才切换，再启动`START_LOCAL_ASR.bat`。失败保留旧选择；回退参数`-AsrProfile legacy`。Qwen使用独立`.venv-qwen`，并非Ollama模型。

[升级/边界/评测说明](docs/UPGRADE_V0110_ASR.md) · [当前状态](docs/STATUS.md) · [实际测试报告](qa/V0110_ASR_TEST_REPORT.md)

版本：扩展/服务0.11.0、安装器0.8.2、协议5、git-r8。以下原操作说明继续适用；历史版本号不代表当前发布。

---

# 视频知识笔记 · Video Knowledge Notebook

**Edge扩展0.10.2 / 本地服务0.10.2 / 一键安装器0.8.1 / git-r7。** 原型源码；尚未在目标Windows Edge及真实模型上完成端到端验收。

本次修复视频切换期间旧笔记/旧成稿残留、异步加载竞争和完整阅读来源错配；生成结果绑定视频与文稿ID。视频下载移除会把首项完成当失败的数量限制，细分失败原因，并新增默认匿名重试与**单次明确授权**的YouTube会话重试。未在用户Windows或真实YouTube账号上验证，不能保证所有视频下载成功。

保留字幕校对、标点断句、五种整理文体和72小时缓存；**无关内容过滤仍已移除**。本版不重写已有文稿、不删除原文，不自动还原历史混入的资料。
[升级与使用](docs/UPGRADE_V0102.md) · [测试与限制](qa/V0102_TEST_REPORT.md) · [当前状态](docs/STATUS.md) · [已知问题](docs/KNOWN_ISSUES.md)

| 组件 | 版本 |
|---|---|
| Edge扩展 | 0.10.2 |
| 本地ASR / LoRA / 字幕校验服务 | 0.10.2 |
| 安装器 | 0.8.1 |
| 音频协议 | VKN5 / 5 |
| 工程修订 | git-r7 |

已有用户必须同时覆盖扩展与服务并重启。不要卸载原扩展或删除模型、环境和笔记。首次/补缺项只运行 INSTALL_ALL.bat，日常仍运行 START_LOCAL_ASR.bat 或 START_ACCURATE_ASR.bat（二者选一）。

**100秒长文非流式等待、后台生命周期和失败续跑仍为未完成项。** 字幕校对不是此问题的修复，新增视觉工作也可能增加本机模型负载。

## 能做什么

观看 YouTube、B站等视频时，在主动授权后采集当前标签音频；通过本地 Whisper 增量转写，保留时间戳、原文、译文候选与人工修订。实时记录默认折叠，阶段摘要定时执行，完整整理只手动触发。

完整整理支持 **知识文档 / 文字稿 / 自定义要求**，并保留结果历史。不再先按主题/置信度自动排除记录；语音质量提示只保留在来源详情。所有原始记录可导出，正文按所选文体整理。

可选功能：本地外语转中文、保守纠错建议、自动说话人分组、72小时本地视频缓存、同音短语校对、自然语言筛选 LoRA 图片候选。说话人仍待真实精度验收；采图输出不是经过连续性验收的视频 LoRA 数据集。视频网站兼容性与受保护内容可采集性仍以实际浏览器许可和测试为准。

## 最快开始使用（Windows）

准备 64 位 Python 3.11 或 3.12、Microsoft Edge。文字整理/翻译另需本地 Ollama；安装器与模型首次下载需要网络，权重不在仓库内。

1. 解压工程到固定目录，双击 `INSTALL_ALL.bat`。它创建/复用本项目 `.venv` 并按步骤补齐所选组件；缺少系统软件时经确认通过WinGet安装。已有部署先停止本地服务，不删除其缓存。
2. 安装报告无缺项后，运行 `START_LOCAL_ASR.bat`。准确模式可用 `START_ACCURATE_ASR.bat`，**两个脚本只能运行一个**。文字/视觉模型已由统一安装器检查，不必再逐个运行INSTALL脚本。默认CPU INT8，不自动改成GPU。
3. Edge 打开 `edge://extensions/`，开启开发人员模式，加载本工程 `extension` 文件夹。可在页面点“开始听写”，选择当前视频标签并勾选共享音频；或按 Alt+Shift+V 原生启动。插件中保存设置并验证实际推理；本地模式 API Key 留空。
4. 按“开始”记录，按“停止全部采集”停止新输入；停止前缓存可能继续补录。手动选择整理方式并生成，结果在面板下方可完整阅读、切换和导出。

本地偏好可将 `ASR_SETTINGS.example.bat` 复制为 `ASR_SETTINGS.bat` 后修改；副本已被 Git 忽略。识别窗口在扩展设置中选6/12/18秒，默认12秒，不在示例批处理中设置过时的窗口变量。

**已有用户：不要为了建立 Git 仓库卸载原插件或直接改加载目录。** 扩展 ID/存储和来源授权可能随迁移受影响。先看 [升级、数据与回滚](docs/MIGRATION.md)。

## 开发和测试

Windows PowerShell（已安装 Git、Node.js 22 和 Python 3.11；这是开发目标版本，不是本次Windows实测证明）：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r dev\requirements-test.txt
.\.venv\Scripts\python.exe scripts\run_checks.py --suite unit
```

上面只安装模拟测试依赖，不安装/下载语音模型。实际服务依赖见 `server/requirements.txt`；Ollama 是独立程序。JavaScript 不依赖 npm 包，`npm test` 或 `node scripts/run_js_tests.cjs` 均可。

安装真实浏览器DOM测试依赖后：

```powershell
.\.venv\Scripts\python.exe -m pip install -r dev\requirements-browser.txt
.\.venv\Scripts\python.exe -m playwright install chromium
$env:VKN_CHROMIUM = "playwright"
.\.venv\Scripts\python.exe scripts\run_checks.py --suite browser
```

这些浏览器测试运行真实 DOM，但扩展接口、音频和模型有测试替身，不等同于真实 tabCapture 或模型验收。输出落入已忽略的 `artifacts/`。完整说明见 [开发手册](docs/DEVELOPMENT.md) 和 [测试说明](docs/TESTING.md)。

## 提交到新 Git 仓库

进入解压后的工程根目录执行（不要在已有仓库上重置分支）：

```powershell
git init -b main
py -3.11 scripts/check_repo.py
git add .
py -3.11 scripts/check_repo.py --staged
git status --short
git commit -m "fix: isolate video readers and cache retry 0.10.2"
```

有 `.venv` 时可将 `py -3.11` 换成 `.\.venv\Scripts\python.exe`。`--staged` 检查实际暂存内容，包含被 `git add -f` 加入的文件。它是轻量检查，不替代人工检查 `git diff --cached`。

**没有自动创建远程仓库，没有执行 push，也没有替你选择开源许可证。** 发布前检查 [授权状态](LICENSE.md) 和 [安全/隐私](SECURITY.md)。用户原始完整笔记、视频、模型、数据库、密钥、历史运行日志不在本包内。

## 给 AI 开发代理的入口

先读 `AGENTS.md` → `docs/STATUS.md` → `docs/KNOWN_ISSUES.md` → `planning/BACKLOG.md`。从 **VK-002：真实长文超时计时** 开始；后续持久任务草案在 `docs/RFC_LONG_TASKS.md`。不要先扩张界面功能，也不要把过滤异常文字当成修复语音准确率。

当前规划有43项任务和50项验收场景。新增功能已实现代码并作构造测试，真实环境验收未通过前保持in_progress；实际状态以JSON和QA报告为准。

## 目录

```text
extension/       Edge MV3 原有源码
server/          本地ASR、缓存、翻译、说话人和采图服务
scripts/         启停辅助、诊断、完整测试与Git检查
*.bat            Windows运行/安装/检查入口
ASR_SETTINGS.example.bat  可提交的配置模板
AGENTS.md        AI开发约束与开工顺序
docs/            当前规格、架构、排障、迁移和历史说明
planning/        任务JSON/Markdown、验收JSON
qa/              本次验证报告、原始基线源码SHA256
.github/         CI配置、Issue及PR模板
dev/             不下载模型的开发测试依赖
tests/           单元、模拟集成、浏览器DOM测试
```

[全部文档导航](docs/README.md) · [任务列表](planning/BACKLOG.md) · [验收标准](docs/ACCEPTANCE.md)

## V0.8.0新增入口

角色无需手填；可选组件首次用INSTALL_SPEAKER_MODEL.bat。保存视频按钮执行显式下载，INSTALL_VIDEO_CACHE.bat安装可选组件；72小时从完成算，服务运行时清理，关机后下次启动清理。INSTALL_CONTEXT_REVIEW.bat安装同音校验组件。CHECK_LOCAL_SERVICE.bat生成无笔记正文的连接诊断JSON。所有入口与升级步骤见[UPGRADE_V080.md](docs/UPGRADE_V080.md)。网页字幕入口及后台读取已移除，手动字幕文件导入保留。
