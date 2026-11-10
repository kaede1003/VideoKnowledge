# git-r24 自动翻译恢复 · 验证记录（2026-11-09）

## 复现来源与修改范围

现场报错：`AI_TRANSLATION_INVALID: 8条发言中仍有7条未获得可靠中文译文`。源代码 `extension/core.js:translateTranscriptBatch()` 原策略上限4次，某条输入连续缺失就抛异常；r23 分片检查点会保留耗尽次数。

本轮修改：`extension/core.js` 自适应有界补译及单条纯文本中文模式、旧检查点版本迁移、有限次数后自动保留原文；`extension/background.js` 和 `extension/longform-background.js` 两条文字稿入口启用自动回退、记录真实译文数量与未译数量。保留原始 ASR、音频、数据库、笔记、已生成旧结果和原来的模型服务配置。

不改系统模型，不更改访问授权，不把生成失败的外文伪装为已译中文；HTTP 401/403/429/5xx 仍按真实请求错误处理。

## 实际执行结果

- `node --test tests/transcript_translation_v0123.test.js`：18/18 通过。涵盖部分 ID、失败后补译、旧状态迁移、无 JSON 的单条直接翻译、短文/长文自动完成、数值冲突保护与 HTTP500 检查点恢复。
- `python scripts/run_checks.py --suite unit --timeout 70`：**整体退出码0**，repository / JS语法 / JS单元 / Python编译 / Python单元五项均 PASS。报告：`artifacts/checks/20261109T084438187951Z/report.json`（本地测试环境的临时报告，未打包进源码包）。
- JS 单元：327/327 通过；Python 单元：379/379 通过。代码库检查：291个源码文件检查、0问题；JavaScript语法：55个文件、0失败。
- `python tests/browser_writing_v070.py`：退出0，正常保存、取消、文字稿阅读与来源保护等用例通过。
- `python tests/browser_ai_v052.py`：退出0，普通/流式服务设置、模型验证及 UI 布局用例通过。
- `python tests/browser_task_progress_v0124.py`：退出0，进度条/缓存重播/取消用例通过。
- `python tests/browser_content_v052.py`：退出0，停止与实时摘录基础用例通过。
- `python scripts/check_repo.py` 和 `python scripts/render_planning.py --check`：退出码0。

注：最初构造长文极限案例时，个别模拟发言填充过长使并发全量测试超过工具的执行窗口；测试夹具精简为“少量待译外文 + 大段已为中文的来源”后，保留长文分支的激活条件，再运行最终全量单元套件 **PASS**。早期超时不是已通过记录。

## 尚未执行（不得按通过宣传）

- 真实 Windows 11 / Edge 插件环境，RTX 5080、Ollama 实际模型推理结果。
- 用户原两小时西班牙语视频的语义忠实度、翻译质量、时间开销、数字以外的事实保持情况。
- 真实模型出现连续身份错配/语音原文错误时的声纹/人物语义准确率。
- 全套浏览器测试在本轮仅完成四组与此改动相关的专项，不报告全套浏览器通过。

## 验收边界

由于用户选择不参与人工逐条确认，流程将自动尝试翻译，不要求人工批准。**若本地模型持续返回无效翻译，成品会保留该句原文并在生成详情说明，避免整篇失败；这不代表该句已翻译或 AI 已证明内容无误。** 用户可在实际环境中复测同视频同模型，r23 成功检查点会继续使用。
