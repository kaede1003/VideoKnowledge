# 一键安装与 Ollama 下载排障 · 安装器 0.8.1

本次只更新安装流程。**Edge 扩展与本地业务服务仍为 0.8.0，音频协议仍为5。** 不修改听写、翻译、长文整理或视频缓存算法；原来的100秒长文请求问题未在此修复。

## 现在只需一个安装入口

在包含 `extension`、`server` 和 `scripts` 的工程根目录双击：

```text
INSTALL_ALL.bat
```

此后日常使用仍运行 `START_LOCAL_ASR.bat`（或已有的准确模式启动器），**不需要每天安装**。旧 `INSTALL_TEXT_MODEL.bat`、`INSTALL_LORA_MODEL.bat`、`INSTALL_SPEAKER_MODEL.bat`、`INSTALL_CONTEXT_REVIEW.bat`、`INSTALL_VIDEO_CACHE.bat` 保留为兼容快捷入口，内部统一调用新安装器，用户不必逐个点击。

安装前暂停采集，等待可处理的缓存完成，再停止本项目本地服务。若8765端口还在使用，安装器会停止修改Python环境并提示，不会强杀任何进程。不要同时运行新旧多个安装脚本。

### 一键安装包含什么

| 项目 | 行为及边界 |
|---|---|
| Python 环境 | 复用本项目 `.venv`；没有时用64位Python 3.11/3.12创建。现有环境不可用时明确报错，不删掉重建。 |
| 缺少 Python | WinGet可用且得到确认后安装 Python.Python.3.11；没有WinGet则说明缺项，不远程执行来历不明脚本。 |
| 本地服务 | 安装 `server/requirements.txt` 并检查模块可导入，包括WebSocket依赖。 |
| 上下文纠词 | 安装 pypinyin；不擅自修改原文或扩大模型权限。 |
| 视频保存 | 安装 yt-dlp；检查FFmpeg/ffprobe与Deno 2。缺少时经确认使用WinGet安装。不是实际网站下载成功率验证。 |
| Ollama | 复用已有安装；缺少时经确认使用WinGet安装。已有可用版本不强制升级/降级。服务没启动时可启动本机 `ollama serve`，只绑定回环地址，不强制结束原实例。 |
| 文字模型 | 检查 `qwen2.5:3b`，已有则跳过下载；缺少才通过本机Ollama流式拉取。 |
| 视觉模型 | 检查 `qwen2.5vl:3b`，用于图片筛选；不是“训练LoRA权重”。 |
| 听写模型 | 读取原 `ASR_SETTINGS.bat` 的模型选择，未设置默认small。预下载所选Whisper；本地CPU INT8加载检查，不覆盖已有设备/模型设置。 |
| 说话人 | 安装可选sherpa-onnx依赖，复用或下载原项目模型，执行加载/静音检查；不表示真实角色识别准确。 |
| Edge 扩展 | 安装器不替你授权或修改浏览器策略。已有扩展无需卸载；首次加载需在Edge手动确认。 |

首次缺少系统软件时需要确认安装协议，Windows/WinGet可能显示额外授权窗口。**一个入口不等于无视系统授权、网络限制和许可的零交互。** WinGet来源使用明确的 `winget` 源与精确包ID，不安装未知搜索结果；源不可用时记录失败。

## 你这次截图的错误不是普通慢

关键字是：

```text
redirect target not allowed
resolves to non-public 198.18.0.253
```

截图中Ollama0.40.15的下载主机是：

```text
dd20bb891979d25aebc8bec07b2b3bbc.r2.cloudflarestorage.com
```

其版本的公开源码对下载重定向目标做公网地址检查，明确拒绝 `198.18.0.0/15`。这个网段也是常见Fake-IP配置使用的范围。**能确定是非公网解析触发拒绝；只有截图不能确定具体是哪一款代理、路由器或DNS软件造成。** 继续拉取相同错误并不会通过检查，调整插件推理超时或填写API Key也无关。

安装器会读系统DNS作辅助检查，并在真正拉取返回这种错误时输出 `DNS_NON_PUBLIC`、停止该模型的重复重试。后续缺失的Ollama模型暂缓，不把它当成随机网络抖动。原有已安装模型仍可检查；其他可完成的安装步骤继续，最后列出未完成项。系统DNS探测与守护进程网络不一定完全一致，拉取错误才是本次下载被拒绝的直接依据。

### Fake-IP 的处理

使用Clash/Mihomo一类软件且确实启用了Fake-IP时，把Ollama下载域名设置为**返回真实DNS结果，不发放Fake-IP**；这不等于将所有下载强制改成直连。下载流量仍可按原有合法代理路由处理。

下面仅适用于已有 `fake-ip-filter-mode: blacklist` 的配置。合并到现有 `dns.fake-ip-filter`，不要覆盖整个代理配置、删除原条目或额外再加一份顶层 `dns`。

```yaml
dns:
  fake-ip-filter-mode: blacklist
  fake-ip-filter:
    - '+.ollama.com'
    - '+.ollama.ai'
    - 'dd20bb891979d25aebc8bec07b2b3bbc.r2.cloudflarestorage.com'
```

若你已有 `whitelist` 或 `rule` 模式，不要直接改成blacklist。按相应客户端语义，对上述主机设置 `real-ip`。rule模式可用精确的 `DOMAIN,主机名,real-ip` 条目，放在会先匹配它的泛规则之前。以后Ollama使用新的存储域名时，以新的错误域名为准。

保存并重载代理/DNS配置后，在PowerShell检查：

```powershell
Resolve-DnsName dd20bb891979d25aebc8bec07b2b3bbc.r2.cloudflarestorage.com -Type A
```

不应再得到198.18/198.19开头或其他非公网地址。必要时清理系统DNS缓存（权限由Windows决定）：

```powershell
ipconfig /flushdns
```

然后重新运行 `INSTALL_ALL.bat`。只刷新DNS而没有修复上游Fake-IP规则，不能根治问题。公司网络/受管理路由器的策略应由其管理员调整，不擅自绕过。安装器**不自动修改代理订阅、系统DNS、hosts、证书、地址校验或安全软件**，也不硬编码公网CDN地址。

### 使用显式 HTTPS 代理的用户

Ollama官方建议为**Ollama服务进程**配置 `HTTPS_PROXY`；不要为了拉模型新增 `HTTP_PROXY`，它可能影响本机服务连接。已经运行的托盘Ollama不会自动继承后来在某个终端中设置的环境变量，需完整退出后重新启动才会读取新环境。

本安装器不会自动写入代理地址或猜你的端口。确有需要时按Ollama官方FAQ设置真实HTTP CONNECT代理地址，并给本机回环连接保留NO_PROXY；不要将SOCKS端口误当HTTP代理，不公开含密码的地址。配置代理也不保证Fake-IP问题消失，仍需检查下载主机的解析。

正常下载过程中不要反复重启Ollama或删除 `.ollama/models`。本安装器不清理模型缓存；Ollama自身版本、缓存完整性及启动清理行为仍会影响续传。

## 下载优化的实际范围

- 本机模型列表＋元数据已就绪：跳过下载，不反复拉取已安装标签。
- 使用官方 `/api/pull` 流式进度，串行下载文字/视觉模型，不并发争抢带宽；完成后必须看到success且本机能列出/读取模型元数据。
- 连接断开、远端临时错误：默认最多3次尝试，有5秒、15秒退避；不重新安装Ollama，不手动清空其分片。
- 默认180秒收不到数据才触发连接空闲超时；连续600秒无状态/字节进展触发卡住判定。每次拉取还有4小时安全上限，**不是预计下载耗时**。正常有进度时不会被统一100秒截止。
- 非公网重定向、证书错误、鉴权拒绝、模型名不存在、磁盘不足及摘要校验异常：清楚分类，停止无效重试。
- 元数据验证不是实际生成测试，不代表模型显存、速度、质量或Edge访问权限已验收。
- 重试复用Ollama自己的可用分片；不是自行重写模型下载协议，不能保证缓存损坏、断电或任意Ollama版本下永远从精确字节续传。也没有承诺网络带宽变快。
- Whisper使用原Hugging Face缓存；说话人复用原模型文件。Whisper/说话人网络失败会独立记录，不影响已有可用文字模型。说话人首次下载中断仍沿用既有下载器的行为，不宣称所有第三方模型都具有精确断点续传。

## 从现有D盘工程升级

本补丁基于上一版V0.8.0。把内容合并到原工程根目录，例如：

```text
D:\VideoKnowledge_Git_Project\INSTALL_ALL.bat
D:\VideoKnowledge_Git_Project\scripts\install_all.py
```

不卸载Edge扩展、不更换加载目录、不删除`.venv`。补丁不含`ASR_SETTINGS.bat`、模型权重、用户数据库或笔记。**此次业务组件仍为0.8.0，不必为安装器更新去重新加载扩展或重装语音服务。** 安装完成后，需要关闭旧启动窗口并重新启动服务，以读取新安装工具的PATH和依赖。

安装器会读取本地 `ASR_SETTINGS.bat`，这是你已有的可执行偏好文件，请不要替换成来源不明内容。旧环境不是64位Python3.11/3.12时会明确阻止，不偷偷删除修复。

## 可选模式（仍是同一个入口）

```powershell
.\INSTALL_ALL.bat                     # 默认全部组件
.\INSTALL_ALL.bat -Profile core       # 仅听写、文字整理与同音校验
.\INSTALL_ALL.bat -Profile models     # 仅两个Ollama模型
.\INSTALL_ALL.bat -Profile diagnose   # 只诊断，不安装/拉模型
.\INSTALL_ALL.bat -Plan               # 只显示安装计划
```

`-Yes` 明确同意缺少的WinGet软件及其协议，可用于你已审查的自动部署；不会免除Windows本身的权限检查。`-SkipSystemTools` 不安装外部软件，缺项会记录，不能把缺组件状态当成全部就绪。

只诊断/只看计划不创建venv，也不自动装Python；没有可用Python时会说明。默认全部安装会创建项目venv、安装依赖/模型，在首次缺少外部软件时请求确认。

## 报告与恢复

`diagnostics/install/install-日期时间.json` 和同名`.log` 保存每一步的状态、错误类型、时间与辅助DNS结果；日志约10MiB轮换一份。临时签名URL、URL用户名/密码和常见密钥字段作脱敏，不读取用户笔记。报告仍可能包含本机路径/IP，分享前检查。

失败步骤不会使已完成模型被删除。重新运行同一个入口，组件重新校验、已满足的包及已有模型复用，不凭一个旧的“成功标志”就盲目跳过。进程级锁阻止本工程同时运行两个新版安装器，但不能控制用户在另一终端手动运行的pip/ollama。

如果安装器启动了Ollama，它会保留该回环守护进程以供插件使用，并记录PID。它不会结束用户本来运行的Ollama或清空其模型。安装器取消只终止自身的安装子进程/请求，不承诺立刻停止Ollama服务端所有下载。

## 验证范围与未解决问题

此次测试范围在 `qa/INSTALLER_V081_TEST_REPORT.md`：构造模型响应、真实回环HTTP连接、状态/重试/拒绝分类与代码回归。**没有在你的Windows、WinGet、真实Ollama下载网络、真实Whisper/声学模型上完成安装验收。** PowerShell/BAT仅静态与格式检查。初次实际安装、真实CDN下载和DNS修复结果须在你的机器上确认。

原有长文100秒超时、真实听写/翻译准确率、角色分组准确率等仍按项目待办单独处理，本安装器不把下载优化冒充为这些问题已修好。

## 官方依据

- Ollama 0.40.15 重定向校验源码：https://github.com/ollama/ollama/blob/v0.40.15/transfer/redirect.go
- 相同Fake-IP症状的上游报告：https://github.com/ollama/ollama/issues/19086
- Mihomo DNS配置与不同filter模式：https://wiki.metacubex.one/config/dns/
- Ollama代理及Windows环境变量：https://docs.ollama.com/faq
- Ollama模型流式下载、进度与续传接口：https://github.com/ollama/ollama/blob/v0.40.15/docs/api.md#pull-a-model
- Ollama缓存恢复相关上游报告：https://github.com/ollama/ollama/issues/19337
- WinGet精确安装与安装协议：https://learn.microsoft.com/en-us/windows/package-manager/winget/install
- Deno官方Windows安装：https://docs.deno.com/runtime/getting_started/installation/

这些来源只支持接口/配置说明，不构成本工程在用户机器上已经安装成功的证据。
