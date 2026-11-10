# git-r21 长文 HTTP 403 修复测试报告

日期：2026-11-09（UTC）；基线：用户此前提供的 `VideoKnowledge_r20_FULL_PROJECT.zip`。环境：容器 Linux / Python 3.13.5 / Node 22.16.0 / Playwright 模拟 Chromium。**未连接用户实际 Windows、Ollama、Edge 或自定义聊天服务器。**

## 改动与复现

- r20 `extension/longform-background.js` 的非 2xx 分支无论服务端返回何种拒绝，均显示 `AI_HTTP_状态码：长文整理请求失败`；`testAiConnection` 仅调用 `stream:false`，未覆盖 `stream:true` 长文通道。
- r21 新增 `extension/ai-http.js`，普通聊天与长文共享安全的错误分类。`VKN_AI_TEST` 从单一非流式探测改为普通 + 流式双探测。固定测试提示不会上传实际视频内容，且不回显任何服务端响应体、API Key、URL 查询参数。
- r21 不重试 403、不关闭安全校验、不自动更换提供方。r20 的来源指纹、分片检查点及断点续跑没有格式变化。

## 本次执行结果

| 检查 | 实际结果 | 说明 |
|---|---|---|
| 仓库完整性 | 通过 | 283 个源文件（新增报告后为 284），0 问题；测试执行于增加本报告之前 |
| JavaScript 语法 | 通过 | 52 个 JS 文件，0 失败 |
| JavaScript 单元 | 301 / 301 通过 | 包括 403 分流、隐私不泄漏、普通聊天成功但流式拒绝、SSE、413/429/500、长文检查点续跑 |
| Python 单元 | 379 / 379 通过 | 未变更 Python 业务逻辑 |
| Python 编译 | 通过 | `server/ scripts/ tests/` |
| 浏览器集成 | 11 / 11 组执行成功 | 模拟 Chromium + Chrome API；含设置页“普通/长文双通道验证”、长文阅读与保存等 |

执行入口：`python scripts/run_checks.py --suite unit` 全部通过。整套 `--suite browser` 在顺序执行过程中达到外部运行窗口，已经完成的前五组通过；后续六组测试在独立进程中分别验证成功。该报告不将整体一次运行记作成功，也不将模拟浏览器当成原生 Edge。

## 核心回归覆盖

1. 本地 `/api/tags` 正常、`stream:false` 成功，但同一模型 `stream:true` 返回 403：识别为本地 Ollama 访问拒绝，不将测试伪报为成功。
2. 自定义 HTTPS 服务 `stream:true` 返回 403：识别为自定义服务拒绝；不回显密钥、敏感 URL 查询字段、服务响应体，保留合法的 `x-request-id`。
3. 同一通道可接受 SSE 与 JSON 响应；其它 HTTP 状态码得到对应提示；遇到 403 不无限重试。
4. 长文知识整理 POST 被拒绝时，metadata 为 `paused`、`completed=false`；服务恢复后可按相同来源指纹继续生成，不伪造已完成结果。

## 尚待用户环境确认

- Windows Edge 中本地/自定义 403 由哪个进程/服务策略导致。
- Ollama 11434 是否已设置精确扩展 ID `OLLAMA_ORIGINS`、是否完整重启；若自定义服务，是否允许同模型的流式推理及当前账号权限。
- 两小时原视频在真实 RTX 5080 环境中的连续生成与知识合并质量。仅凭这批自动化测试**不能宣布用户实际 403 已经解除**。
