# git-r27 · AI_STREAM_INCOMPLETE 模拟回归与兼容性测试

测试环境：Linux / Python 3.13.5 / Node.js v22.16.0 / Chromium（Playwright 模拟扩展和 AI 接口）。2026-11-09。

## 故障复现

- r26 `vknLongformStream` 在 SSE 传输结束时，如果没有 `[DONE]` 和 `finish_reason`，立即抛出 `AI_STREAM_INCOMPLETE`，没有重取；`finish_reason=stop` 但缺 `[DONE]` 虽可从底层函数返回，却使 `complete=false`，最终无法作为完整章节。
- r26 把 EOF 时未用空行分隔的 `data: [DONE]` 当成“不完整帧”；SSE 末尾合法单帧因此会被拒绝。
- r27 新的专门测试先在未修改实现上执行，10 个测试中有 7 项预期失败，用于验证复现；之后加入修复和安全边界用例。

## 代码及模拟测试结果

| 检查 | 实际结果 |
|---|---|
| `python scripts/run_checks.py --suite unit --timeout 180` | **通过**：仓库、JavaScript 语法、JS 单元、Python 编译、Python 单元全部通过 |
| JavaScript 自动化 | **357 / 357 通过** |
| Python 自动化 | **379 / 379 通过** |
| `python scripts/run_checks.py --suite browser --timeout 65` | **通过**：仓库检查 + 12 组 Chromium DOM / 模拟桥接测试 |
| r27 新增定向用例 | **16 项通过**：12 项流解析/恢复、2 项长文检查点、2 项设置页严格流式验证 |
| ZIP 文件校验 | 打包后验证 CRC、条目数、文件内容及核心源码差异 |

单元报告：`artifacts/checks/20261109T113536794988Z/report.json`（运行产物，未纳入项目 ZIP）；浏览器报告：`artifacts/checks/20261109T113645871802Z/report.json`。

## 新增边界测试

1. `finish_reason=stop` 无 `[DONE]` 与 EOF 最后帧缺空行仍正确识别为完整。
2. UTF-8 中文/emoji 切包、CRLF、心跳注释不会破坏 SSE 解析。
3. 无任何终止信息时仅本机 Ollama 进行一次同模型、同输入、同参数的非流式重取；此前收到的片段永远不被拼成最终正文。
4. 非流式结果若明确 `finish_reason=length`，仍交给原始来源自适应拆分；`content_filter` / `tool_calls` 不能作为完整生成。
5. 重取遇 HTTP 500、远程自定义服务、非法 JSON 帧、读取中断、服务返回空正文等均安全处理，不绕过权限、不无限调用。
6. 长文多阶段在恢复 HTTP 500 后检查点保持 paused，同一视频重新生成可以继续；成功恢复只保存可靠 JSON 内容。
7. 设置页要求流式测试本身成功，禁止非流式恢复掩盖流式接口故障。

## 未验证的事项

- **没有**调用用户本机 Windows、Edge、Ollama 及用户视频，无法证明截图对应的上游流中断原因已彻底消除。
- 浏览器测试使用模拟的模型返回及扩展桥接，不等于真实 2 小时资料生成的速度、内容质量、显存或 Windows 进程稳定性验收。
- 真正的 Ollama runner 崩溃、API 403/500 或服务与网络持续中断，客户端不能保证恢复；检查点/原文按原项目规则保留。
