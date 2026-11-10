# git-r18 外语文字稿翻译回归测试报告

**日期：** 2026-11-09
**工程版本：** VideoKnowledge 0.12.1 / git-r18-transcript-translation
**测试环境：** Linux，Python 3.13.5，Node.js 22.16.0；模拟扩展消息、模拟模型响应。

## 覆盖范围

- 外语检测：西班牙语语言码、无语言码的拉丁文字、日语假名、中文来源。
- ASR 译文复用：可信中文译文不重复翻译；`needs_review` 回退到原文时重新翻译。
- 翻译契约：简体中文、逐条 ID/顺序、阿拉伯数字保留；拒绝无中文译文、缺失/错位 ID 和数字改动。
- 短文生成：独立翻译在标点之前运行；说话人标签保留；翻译失败不调用标点阶段，也不发布外语正文。
- 长文生成：分块翻译、长文检查点；模拟第二个翻译批次 HTTP 500 后重试，已成功批次可复用，完成后正文为中文。
- 长文指纹：源语言或翻译状态改变会生成新指纹，避免误用旧检查点。

## 自动化结果

运行命令：`python scripts/run_checks.py --suite unit`

| 检查 | 结果 |
|---|---:|
| 仓库结构与安全文件检查 | PASS，0 问题 |
| JavaScript 语法 | PASS |
| JavaScript 单元测试 | **285 / 285 PASS** |
| Python 编译 | PASS |
| Python 单元测试 | **379 / 379 PASS** |
| 总体 | **PASS** |

定向 JavaScript 命令：`node --test tests/transcript_translation_v0123.test.js tests/longform_v0120.test.js` — 11 / 11 PASS。
浏览器 DOM 定向命令：`python tests/browser_presentation_v090.py` — PASS；完整浏览器运行中 `browser_writing_v070` 的首轮检查已通过。随后单独重跑浏览器脚本时，Playwright 管道出现 `EPIPE` 并超时，因此不把完整浏览器套件标记为通过。

## 未验证事项

- 未在目标 Windows Edge 上重新加载扩展和生成用户截图对应的视频。
- 未调用用户实际 Ollama/Qwen 文字模型；模拟模型响应只验证流程、ID/结构、数字守卫和失败保护，不代表翻译质量。
- 未做西班牙语母语者/双语人工逐句核对；专名、否定、口语断句、隐喻、拼写数字的语义仍需人工抽查。
- 本次未改 ASR 服务端、Sherpa 运行库或 Ollama runner；r17 的现场验收边界仍然有效。

## 结论

**源码流程修复与构造回归通过。** 文字稿模式不再只做标点而直接发布外语原文；翻译阶段验证失败时会拒绝生成未翻译成稿，并保留原始听写和旧文稿。真实模型语义质量及目标 Windows 端到端验收仍待用户现场确认。
