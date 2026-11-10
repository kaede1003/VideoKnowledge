# git-r28 对话姓名关联与翻译提示词泄漏修复测试报告

日期：2026-11-09
基线：VideoKnowledge_r27_FULL_PROJECT_STREAM_RECOVERY.zip
改动涉及：`extension/speaker-identity.js`、`extension/identity-background.js`、`extension/core.js`、`tests/regression_r28_speaker_address.test.js`、文档及任务记录。

## 根因

1. r26/r27 的 `labelIntroducedSpeakers()` 仅对嘉宾履历介绍建立姓名绑定，并把“（根据介绍推测）”写进可见标题；未识别主持人与嘉宾之间的直接称呼（例如“谢谢你，玛丽安”）。
2. 独立的本地姓名推断只支持自报、字幕、欢迎/介绍；对直接称呼中的被称呼者缺乏经过声纹轮次约束的自动持久化路径。
3. `inspectTranscriptTranslation()` 只查中文占比、原文数字等，模型回显内部翻译提示词时也可能被当作“合格中文译文”写入检查点。

## 修复验证

| 项目 | 结果 |
|---|---|
| 新增 r28 合成单元测试：双人访谈直接称呼、三声纹歧义、非直呼第三人称、普通致谢非姓名、中文/西班牙语姓名、短文完整生成、无模型时持久化、旧标签与旧翻译缓存复核 | 9 / 9 PASS |
| `python scripts/run_checks.py --suite unit --timeout 180`：repo、JS语法、JS全部测试、Python编译、Python全部测试 | 5 / 5 PASS |
| JavaScript（完整单元集） | 366 / 366 PASS |
| Python unittest | 379 / 379 PASS |
| Chromium DOM/扩展模拟：navigation、cache、reader、caption、quality | 5组 PASS |
| 单独运行浏览器专项：`browser_speaker_roles_v0121.py`、`browser_ai_v052.py`、`browser_writing_v070.py` | 3组 PASS |
| 全套 `--suite browser` 一次运行 | 中途超过当前执行窗口，未整体完成；不得记录为全套通过 |
| 真实 Windows Edge、Ollama、Sherpa 及原视频两小时转写 | 未运行；需目标环境验证 |

## 防误判边界

- `Sergio Marina` 的履历介绍归于介绍者的原始发言，但在紧随其后不同声音应答时，将名字标给受访者；介绍者不会因此被改成 Sergio。
- `谢谢你，玛丽安` 的姓名归属对话对象，而非致谢者；前后出现两个不同可能对象时跳过自动分配。
- `Gracias por participar` 不是人名；`谢谢，朋友` 和 `谢谢，你也辛苦了` 也不能变成姓名。
- 内部“请把下面标签内的发言准确翻译……”等已知翻译提示词回显会被拒绝，旧“成功”检查点重新验证后自动请求重译。不能依此断言任意模型幻觉已被全部识别。
- 旧的历史导出文件、原始声纹分组、音频和源文本未清理/覆盖；重新生成新文字稿才会出现新的姓名标题。新增身份 cache schema 5，不必清空存储。

**结论：** 源码与模拟输入测试支持 r28 改动按预期工作。对实际视频里哪段声音属于玛丽安，仍依赖原 ASR/声纹分组正确性；未进行目标 Windows 环境的音频对照，不宣称识别率或真实人名认证。
