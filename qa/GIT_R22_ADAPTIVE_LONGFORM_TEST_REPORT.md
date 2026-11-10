# git-r22 测试报告：长文自适应来源拆分与合并

## 环境、范围

基线：用户此前收到的 `VideoKnowledge_r21_FULL_PROJECT_HTTP403_DIAGNOSTICS.zip`（284 个文件）。变更只涉及 Edge 扩展内的文字模型整理流程、JavaScript 测试及项目说明；本地 ASR、Sherpa、Ollama 安装、认证机制和用户笔记没有修改。测试在 Linux / Node 22.16 / Python 3.13 测试运行时执行，**不是用户 Windows + Edge + Ollama 真实两小时现场验收**。

## 错误根因

`extension/longform-background.js` 的 r21 `build()` 遇到 `finish_reason=length` 时携带前文尾巴继续写同一任务，最多 32 次，随后报 `AI_DOCUMENT_TOO_LARGE：章节多轮续写仍无终点`。这不是“章节数已超过硬限制”。取材阶段提示曾允许最多 1300 汉字但输出上限仅 750 tokens，导致部分模型更容易反复触发输出长度上限。

## 修复验收

- 长文生成在首次长度截断后，将**原来源文本**二分处理，分别保存每个子片段处理状态；已完成结果合并进入后续索引/章节/主题整合。处理单个阶段的拆分递归层数有限（最多4层），不会在同一输入反复续写32次。
- 构造模型每次都返回 `finish_reason=length`：约2小时的合成记录流程能够结束；截断模型回复不作为已完成正文发布；无法完成的最小分块从原文安全保底并在整理详情留下质量声明。
- 来源切分可逐字符还原包含表情、标点、数字、空白的文本；最小分块全为原文保底时，拼合文本与原来源完全一致。
- 模拟可恢复模型（长输入截断、短输入完成）确认能逐段成功合并；模拟 HTTP413 可自动按源缩小输入而不换服务方；HTTP403 仍明确失败且旧文稿/检查点保留。
- r21 的 `attempt=32` 未完成续写分片归档为 `:r21-incomplete`，再由原来源重新整理；已完成分片和 r19 单体检查点迁移路径仍可复用。
- 上述“全来源覆盖”是**流程输入覆盖率**，不意味着语义层面绝无遗漏、翻译/实体无误或主题已完美去重。模型一直截断时，保底文档虽可生成，但该片段未经深度归纳。

## 当次自动化执行结果

| 检查 | 结果 | 执行依据 |
|---|---|---|
| repository integrity | 通过 | `python scripts/check_repo.py` |
| JS syntax | 通过 | `node scripts/check_js.cjs` |
| JavaScript 全量单元测试 | **306/306 通过** | `node scripts/run_js_tests.cjs` |
| Python 编译检查 | 通过 | `python -m compileall -q server scripts tests` |
| Python 单元测试 | **379/379 通过** | `python -m unittest discover -s tests -p 'test_*.py' -v` |
| 构造长文专项 | **14/14 通过** | `node --test tests/longform_v0120.test.js`（包含在306项中） |
| 浏览器自动化测试 | **11/11 组通过** | `python scripts/run_checks.py --suite browser`（浏览器DOM/模拟扩展测试，不是原生Edge） |

完整测试入口：`python scripts/run_checks.py --suite unit --timeout 180`（通过）和 `python scripts/run_checks.py --suite browser --timeout 120`（通过）。具体运行日志存于开发环境 `artifacts/checks/20261109T065257364866Z` 与 `artifacts/checks/20261109T064944284700Z`；本工程发行包不包含大型运行产物。

## 未经现场验证的边界

- 尚未在用户的 Windows、Edge 扩展和实际本地文字模型上测试两小时原视频；无法保证真实用时、峰值内存、自动续跑是否因浏览器生命周期中断或最终文稿语义质量。
- 如果模型一直无法按 `max_tokens` 完成，在有界重试后会保留原始来源片段，故最终文档**可能有部分未完全去重/翻译/润色**；需查看整理详情的保底说明，而非视为全部主题均深度完成。
- HTTP403 和 Ollama 500、Windows 原生 Sherpa 崩溃是其他故障；本版不更换服务、模型或绕过访问限制。
