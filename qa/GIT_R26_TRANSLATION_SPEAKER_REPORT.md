# git-r26 翻译残句与访谈角色命名修复 · 测试报告

日期：2026-11-09。基线：用户上传并经前序生成的 `VideoKnowledge_r25_FULL_PROJECT_TRANSLATION_INTEGRITY.zip`。

## 本次修复的可复现问题

- **用户现场截图**：`Sergio Marina, doctora y filosofía ... guiando数以千计...` 前部为西语、后部为中文；r25 虽然不再误判为合格中文，最终模型连续失败时仍原样保底显示，未完成翻译。
- **用户现场截图**：“我们”作为没有归属的极短发言独立显示，下一位说话人的完整句子另起。
- **用户现场截图**：访谈者已用西语完整介绍 Sergio Marina 履历，紧接着的应答角色仍显示为 `说话人1` 等编号。

## 修改与验收范围

1. `extension/core.js`：增加混合语言长句的有界短语段自动补译，旧 r25 失败译文检查点迁移；每个被验证的短片段持久存储，避免重复请求；无法翻译的原文显式标示 `〔未译原文：...〕`，不冒充已翻译。
2. `extension/background.js` 和 `extension/longform-background.js`：普通文字稿与两小时长视频文字稿都使用新译文及不足注释；断句阶段依据更新后的内容指纹重新计算；不删除旧音频、缓存和文稿。
3. `extension/core.js` 阅读层：对于紧邻、极短且未归属的残句，若前段明确结束且有下一位可靠说话人，可把“我们”接回下一位发言；独立应答词不强行归属。
4. `extension/speaker-identity.js` 和 `extension/identity-background.js`：识别姓名+多项履历的介绍句，仅将姓名映射给接下来马上说话的**不同声纹**，不把朗读介绍的人误当被介绍者。文字稿即时展示推测标签，异步命名元数据保存候选依据。

## 实际已运行

| 项目 | 命令 / 范围 | 结果 |
|---|---|---|
| 工程入口单元检查 | `python scripts/run_checks.py --suite unit` | PASS，全部阶段成功 |
| JavaScript 单元 | `node scripts/run_js_tests.cjs`（由统一入口启动） | **341 / 341** |
| Python 单元 | `python -m unittest discover -s tests -p 'test_*.py' -v` | **379 / 379** |
| JavaScript 语法 | `node scripts/check_js.cjs` | PASS |
| Python 编译 | `python -m compileall -q server scripts tests` | PASS |
| 仓库完整性 | `python scripts/check_repo.py` | PASS |
| r26 专项 | `node --test tests/regression_r26_transcript_identity.test.js` | **8 / 8** |
| r26 与既有翻译兼容 | `node --test tests/regression_r26_transcript_identity.test.js tests/transcript_translation_v0123.test.js` | **32 / 32** |
| 浏览器文字稿与保存模拟 | `python tests/browser_writing_v070.py` | PASS |
| 浏览器模型设置及保存模拟 | `python tests/browser_ai_v052.py` | PASS |
| 浏览器文稿展示模拟 | `python tests/browser_presentation_v090.py` | PASS |
| 浏览器实时内容基本烟测 | `python tests/browser_content_v052.py` | PASS（此前同版本源码完成，最终代码语法/单元检查重复通过） |

统一测试日志位于工作环境 `artifacts/checks/20261109T102453963678Z`，不随工程发布包复制用户环境路径。浏览器使用容器 Chromium 与模拟扩展协议，不是用户原生 Windows Edge。

## 仍未验证 / 不可宣称

- **没有运行用户真实西班牙语视频、Windows Edge、Ollama、Sherpa 声纹 DLL、RTX 5080**，因此无法断言实际录音里的每句西语都已正确翻译或说话人真实身份准确。
- 中文内容自动判定和短语段翻译不能证明语义保真；原始 ASR 如听错人名或把数值误识别为词，模型未必能自愈。
- 声纹分组错误/介绍者与被介绍者的关系如果没有相邻声纹证据，保留中性标签。`（根据介绍推测）` 是推断，不是核实名人身份。
- 若本地翻译模型始终不产出完整中文，仍会出现**明确标记**的 `〔未译原文：...〕`，不会删除或隐藏该来源。无需人工逐项审批；未译原文也不等于已解决翻译质量。

## 现场复测建议

覆盖工程源码后从 `edge://extensions` 重新加载，并重新生成（不要只打开原 r25 已导出的旧 HTML）。请对照现场的 Sergio Marina 片段、紧邻的“我们”和下一位发言人的姓名展示。如果仍有 `〔未译原文〕`，通过生成详情定位具体模型无法翻译的子句。
