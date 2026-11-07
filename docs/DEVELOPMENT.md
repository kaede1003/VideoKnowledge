# 开发手册

## 环境分层

产品使用：Edge、Python运行依赖、相应本地模型。开发测试额外需要Node。Node不用于普通安装后的听写服务。

开发目标为Windows 64位Python3.11/3.12，Node22；本次实际执行平台另见QA报告，不能混写成Windows已通过。模型与依赖按现有范围保留，完整依赖锁定是VK-019。

## 初始化（Windows PowerShell）

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r dev\requirements-test.txt
.\.venv\Scripts\python.exe scripts\run_checks.py --suite unit
```

不需要激活环境，也不需要修改全局执行策略。使用真实服务时安装`server/requirements.txt`，或运行根目录启动脚本；测试依赖不包括faster-whisper，所以单元测试成功不代表ASR运行依赖已安装。

```powershell
.\.venv\Scripts\python.exe -m pip install -r server\requirements.txt
.\.venv\Scripts\python.exe -m uvicorn server.app:app --host 127.0.0.1 --port 8765 --ws websockets
```

只运行一个服务实例。需要本机偏好时复制`ASR_SETTINGS.example.bat`为`ASR_SETTINGS.bat`；后者不提交。批处理自动加载它，直接运行uvicorn则需在当前终端设置相同环境变量。

## Linux/macOS开发测试

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r dev/requirements-test.txt
.venv/bin/python scripts/run_checks.py --suite unit
```

上述测试不代表这些平台已经成为最终产品支持范围。批处理仍仅面向Windows。

## 浏览器DOM回归

```powershell
.\.venv\Scripts\python.exe -m pip install -r dev\requirements-browser.txt
.\.venv\Scripts\python.exe -m playwright install chromium
$env:VKN_CHROMIUM = "playwright"
.\.venv\Scripts\python.exe scripts\run_checks.py --suite browser
```

也可以令`VKN_CHROMIUM`指向已有浏览器可执行文件。无设置时查找本机chromium，找不到则使用Playwright自己的二进制。当前默认选5组匹配现有界面的DOM测试；历史脚本保留作溯源，不全部视为当前发布门禁。

`tests/extension_runtime.py`是独立原生扩展尝试入口，可能因环境策略而不能加载。失败或退出2不计为通过，不修改系统策略绕过限制。

## 调试入口

- `CHECK_LOCAL_ASR.bat`：HTTP与WebSocket检查。
- `CHECK_OLLAMA_ORIGIN.bat`：本地来源访问诊断。
- `FIX_OLLAMA_ORIGIN.bat`：用户明确操作后追加扩展精确来源，不自动杀服务。
- `CHECK_AI_TIMEOUT.bat`：发送合成文字到本机Ollama，写`diagnostics/`计时，不读取私人笔记；运行会消耗模型资源。
- Edge扩展管理页：检查当前加载目录、版本、后台日志和是否有重复副本。

## Git协作

使用`feat/VK-xxx-description`或`fix/VK-xxx-description`分支，提交标题包含任务ID。每个PR有复现、测试范围、迁移和未测项。机器可读任务修改后运行`python scripts/render_planning.py`。

首次提交：`git init -b main`，然后`git add .`、`python scripts/check_repo.py --staged`、人工审阅`git diff --cached`、`git commit`。若Git提示缺少提交身份，仅在本仓库按用户自己的姓名和邮箱设置，不为其编造身份或改全局配置。

GitHub CI文件只随包提供，不会自动创建远程仓库或推送。先建私有仓库评审许可和数据边界更稳妥；本次未执行任何远程操作。

## 本次工程变更范围

`RUN_TESTS.bat`不再硬编码6个早期JS文件、不再在测试时自动安装依赖；统一runner自动发现所有用例，缺工具或失败返回非零。测试截图写入`artifacts/browser/`；浏览器路径不再写死`/usr/bin/chromium`。不修改产品UI或识别流程。
