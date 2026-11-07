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

完整整理支持 **知识文档 / 剧本 / 小说 / 文字稿 / 自定义要求**，并保留结果历史。不再先按主题/置信度自动排除记录；语音质量提示只保留在来源详情。所有原始记录可导出，正文按所选文体整理。

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
