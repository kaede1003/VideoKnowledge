# V0.11.2 STOP_LOCAL_ASR / ASR设置403修复验证

测试环境：当前隔离Linux容器、Python3.13、Node22、Chromium；不是用户的Windows/Edge。测试源码基于V0.11.1/git-r9。未连接真实Ollama，未向Youtube/B站发送请求，也未启动用户本地服务或访问用户音频、笔记。

## 已执行

- `python scripts/run_checks.py --suite unit`：仓库检查、JS语法、JavaScript **263项通过**、Python语法、Python **330项通过**，全部检查返回0。新增测试先在V0.11.1源码上产生预期失败，修复后通过。
- Python `test_ollama_asr_v0111`：新增加3个用例覆盖无Origin但有扩展身份头的GET/POST，以及恶意Origin、无效ID和Origin-ID不匹配始终403；原版有合法Origin但无ID的兼容性保留。
- `test_windows_batch_integrity`：原版停止脚本会未通过“路径引号内以反斜杠结束”的静态测试，修复后使用`"%~dp0."`，现共5项通过。**无法在本测试环境执行Windows PowerShell命令以证明原生停止成功。**
- 实际FastAPI/Starlette CORS预检测试：仅允许合法`chrome-extension://`的预检（200），拒绝`https://evil.example`（400/没有Access-Control-Allow-Origin）；未向任意网站开放配置接口。
- `python tests/browser_asr_settings_v0112.py`：真实Chromium DOM执行生产 `options.js`，模拟HTTP和扩展存储。初次加载、手动刷新、点击“验证并保存”均携带匹配的`X-VKN-Extension-ID`；页面状态更新；通过。此测试模拟了本地服务响应，**并未执行原生Chrome扩展权限**。
- 旧DOM回归：导航、视频缓存、正文阅读、字幕、质量、五种写作共6组通过；另单独运行`browser_content_v052`、`browser_v080`、`browser_presentation_v090`三组通过。
- 旧`browser_ai_v052`：实际输出了全部内部断言通过消息，但本轮统一浏览器套件外层调用超时、未收到该脚本正常退出码，因此 **不计为通过**。这不能被解释成产品修复或该测试失败的确定根因。

## 尚未验收

- 用户本机原生Windows PowerShell路径、CIM进程检查及停止结果；尤其是实际项目路径中是否存在其他特殊字符。
- 原生Edge中有/无Origin请求的具体报头、用户是否同时启用了多个插件副本，以及本机反向代理/安全软件是否劫持了8765 HTTP请求。
- 用户已安装的Ollama模型及真实音频转写速度、准确率；识别模型、VKN5音频缓存、用户笔记均未改动。
- 100秒长文整理中断、阶段恢复和Windows环境其他原有问题，仍是独立待办。

## 现场建议

覆盖补丁并重启**同目录**服务；检查 `/health` 为0.11.2，并在原Edge扩展设置页点击“检查识别引擎”。如果403仍出现，收集HTTP响应中的`detail`和8765实际监听PID，不需要任何API Key或账号Cookie。
