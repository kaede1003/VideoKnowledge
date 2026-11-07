# 统一安装器0.8.1验证报告 · git-r3

日期：2026-11-06。扩展/本地服务仍为0.8.0，VKN5协议5。

## 验证对象与环境

本轮新增统一入口、Windows启动引导、Python安装协调器、Ollama流式下载与网络诊断、Whisper预下载辅助，五个原INSTALL脚本改为兼容转发。没有修改extension/server业务源码。

实际执行环境为Linux容器、Python3.13.5、Node22.16.0；安装器的目标运行环境为Windows64位Python3.11/3.12。没有在本轮容器中安装/下载真实Ollama、Whisper、说话人模型或WinGet软件。

## 实际执行结果

| 项目 | 结果 | 限制 |
|---|---|---|
| `python scripts/run_checks.py --suite unit` | 全部通过 | 五组检查：仓库、JS语法、JS用例、Python编译、Python用例；以附带JSON为准 |
| JavaScript回归 | 194/194通过 | 原应用的模拟用例；本轮未改JS业务代码 |
| Python回归 | 199/199通过 | 原156项加43项安装器用例 |
| 新安装器专项 | 43/43通过 | 其中下载器使用真实回环HTTP socket和固定Ollama协议响应，不是真实模型下载 |
| `INSTALL_ALL.bat -Plan`的Python执行端 | 已在容器执行等效`python scripts/install_all.py --plan` | 仅构造计划，无安装副作用；不是Windows批处理实跑 |
| Windows BAT/PS文件格式 | 静态检查通过 | BAT为ASCII/CRLF，PS为UTF8 BOM/CRLF；没有PowerShell原生语法/行为执行证明 |
| 业务源码身份 | 43份extension/server文件与git-r2逐字节相同 | 见`INSTALLER_V081_RUNTIME_IDENTITY.json` |
| Git暂存及ZIP完整性 | 打包时核验 | 不创建远程仓库，不推送，不打包运行数据 |

具体测试汇总见 `INSTALLER_V081_TEST_SUMMARY.json`。运行日志产生在被Git忽略的`artifacts/checks/`；最终ZIP不夹带这些日志。

## 新覆盖路径

- 将198.18.0.253、198.19地址与IPv4-mapped IPv6识别为基准/Fake-IP范围；私网、回环与组播不误作公网。
- “redirect target not allowed / resolves to non-public”单独分类且不重复重试；磁盘、TLS、404、412、摘要不一致不盲目重试。
- 系统DNS探测超时/失败不伪造成功，签名URL与URL凭据在错误输出中脱敏。
- 本机Ollama连接不使用环境代理；拒绝远程端点、带凭据端点、任意额外URL路径。
- 已装模型跳过pull并检查元数据；成功流必须在模型列表登记；没有success、无效JSON、超长行、无效计数都不是成功。
- EOF后有限重试；状态/字节持续进展不被统一100秒中断；重复无变化进度不能无限续期；空闲和绝对期限分别验证。
- 绝对期限会对当前请求持有的原始socket执行关闭，包括HTTP/1.0把socket从HTTPConnection对象分离的情形。
- 安装锁、防止同时启动；原子报告写入；部分失败不报告全成功；只看计划不启动安装器。
- 旧安装入口转发到统一入口并传播退出码；项目venv与明确WinGet来源保留；不加入安全校验绕过、未知镜像或缓存清空代码。

## 未验证与交付边界

1. 没有在用户Windows、PowerShell5.1、WinGet或真实Ollama0.40.15网络上跑安装；缺软件安装、UAC/许可、PATH刷新仍需现场验收。
2. 没有替用户修改代理/DNS，也没有证明其Fake-IP规则已修复。截图只能证实本次重定向被非公网地址检查拒绝，不能唯一定位哪款网络软件。
3. 没有下载完整模型测速度或断点续传字节量。续传依赖Ollama实现与缓存健康；不保证任意断电/重启/版本缺陷下保留精确进度。
4. Python包依赖沿用项目范围约束，不是新建立的锁定供应链；包/模型安装仍依赖其官方源可访问。
5. 没有运行真实Whisper、声学分组或文字/视觉模型推理质量测试；元数据可读/加载静音通过不代表真实内容准确。
6. 本轮没有重新执行浏览器UI流程，因为extension/server字节未变；历史报告不冒充本次Windows端到端验证。
7. 原有长文100秒非流式请求/失败续跑等P0仍未完成。这里的下载流式与下载超时参数不改变生成流程。
