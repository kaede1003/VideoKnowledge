# 开发依赖

`requirements-test.txt` 只支持模拟回归测试，不安装 faster-whisper、说话人模型和 Ollama；不构成实际运行服务的完整环境。
`requirements-browser.txt` 在此基础上增加 Playwright。浏览器二进制需另行安装，或设置 `VKN_CHROMIUM`。
正式运行仍使用 `server/requirements.txt`，可选说话人使用 `server/requirements-speaker.txt`。

这里保留基线包的依赖范围，未伪造全平台锁文件。下一个开发阶段应在目标 Windows/Python 环境实测后建立锁定依赖与升级流程（见任务 VK-019）。
