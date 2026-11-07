# V0.11.2 · 停止服务与ASR配置HTTP 403修复

基线：Edge扩展 0.11.1 / 本地服务 0.11.1 / 安装器 0.8.3 / VKN5。更新后：**扩展与服务均为0.11.2，安装器仍为0.8.3**。仅更改本项目启动停止和ASR配置访问相关代码；不更换识别引擎、音频协议或数据结构。

## 症状与已确认代码机制

1. `STOP_LOCAL_ASR.bat` 将带末尾反斜杠的`%~dp0`放进Windows命令行的引号中传给PowerShell。某些参数解析下会形成非法路径，随后`Path.GetFullPath()`报“路径中具有非法字符”。本版将参数改为带终止点的`"%~dp0."`，让它规范化为原项目目录，不改变停止范围。
2. 设置页`/asr/config`曾仅以HTTP `Origin`识别扩展。Chromium/Edge宿主权限下的部分GET/POST可能没有该头；服务会返回403，但该403发生在访问8765配置端点时，**并非11434上的Ollama没有密钥**。本版插件在请求里添加`X-VKN-Extension-ID`，服务只在没有Origin且该标识为合法扩展ID时兼容；如果带Origin却不是扩展或与声明ID不符，始终拒绝。普通网页跨域预检依旧拒绝。

上述代码机制已通过独立构造用例复现；用户现场是否还受到代理/端口被其它程序占用影响，尚未由Windows原生日志确定。403响应现在会附上有限的错误码，便于区分。

## 升级步骤：保留原目录、原笔记

1. 在视频中停止录音并等待可处理的缓存完成，导出重要笔记；不要删除`.venv`、`.venv-qwen`、用户数据库或模型。
2. 解压`VideoKnowledge_v0.11.2_ASR_CONFIG_STOP_UPGRADE.zip`，将其中同名文件和目录合并覆盖到原工程根目录，例如 `D:\VideoKnowledge_Git_Project`。不要生成第二层`VideoKnowledge_Git_Project`，不要卸载原扩展或更换扩展加载路径。
3. 在原工程下运行 **更新后的** `STOP_LOCAL_ASR.bat`，确认只停止本项目服务；如果8765属于其他程序，它会提示且不结束对方进程。
4. 运行 `START_LOCAL_ASR.bat`（或原来使用的`START_ACCURATE_ASR.bat`，只能运行一个）。访问 `http://127.0.0.1:8765/health` 检查 `version` 为`0.11.2`、`asr_backend`是你之前选择的模型；Ollama模型仍从本机11434读取。
5. Edge → `edge://extensions/` → **重新加载原插件**，确认0.11.2，刷新视频网站并重新打开设置页。在“识别引擎”点击“检查识别引擎”，应显示当前/下次启动配置。如果已选本地Ollama，不需要在本次升级里重新安装或下载模型。

**注意**：直接在普通网页地址栏输入 `http://127.0.0.1:8765/asr/config` 仍应返回403，这是正常的安全限制；必须从原扩展设置页面访问。健康接口`/health`可用于检查版本，无需调用受限配置接口。

## 仍无法停止时的检查

先不要用`taskkill /IM python.exe /F`，它会结束所有Python任务。可以在PowerShell中查明8765的PID及命令行（不会结束进程）：

```powershell
Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue |
  Select-Object LocalAddress, LocalPort, OwningProcess

Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" |
  Where-Object { $_.CommandLine -match 'uvicorn\s+server\.app:app' } |
  Select-Object ProcessId, ExecutablePath, CommandLine
```

仅在确认为本项目`D:\VideoKnowledge_Git_Project`的服务后，可按对应PID使用`Stop-Process -Id <实际PID> -Force`；不应对不认识的PID批量强制停止。不要强制退出Ollama，它是独立服务。

## 403仍出现时

1. 检查`/health`确实返回`0.11.2`，再确认扩展管理页版本0.11.2、只启用一个本插件副本。
2. 在设置页点击“检查识别引擎”。如果错误是`ASR_EXTENSION_HEADER_REQUIRED`，通常是旧版设置JS尚在缓存中；如果是`ASR_ORIGIN_ID_MISMATCH`，说明页面标识和请求来源不一致。
3. 若HTTP403没有`detail`，或健康接口返回代理/安全软件页面，可能是外部拦截；需检查8765端口的实际监听者、代理软件对127.0.0.1的处理和服务日志。**不需要修改 `OLLAMA_ORIGINS=*`、关闭安全检查或填API Key。**

## 验收范围

- 已自动验证：STOP路径参数静态检查；ASR HTTP GET/POST带Origin兼容、无Origin带扩展ID兼容、恶意Origin/不匹配拒绝、CORS预检仅放行扩展来源；设置页真实Chromium DOM＋模拟HTTP发出的请求头；既有仓库/模型/缓存/翻译回归。
- **尚未验证：用户Windows PowerShell真正停止服务、真实Edge扩展CORS/Origin表现、真实Ollama Qwen3-ASR推理。** 这次不改变先前长文整理100秒超时与失败断点续跑问题。
