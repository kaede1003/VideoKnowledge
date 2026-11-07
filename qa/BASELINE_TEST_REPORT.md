# Git工程交接验证报告 · git-r1

日期：2026-11-06。验证对象：本项目实际归并源码与新工程工具，扩展0.7.2/服务0.7.1/协议5。

## 实际执行环境

Linux容器，Python 3.13.5，Node v22.16.0，本机Chromium。不是用户Windows环境。本次没有安装或运行真实faster-whisper、Ollama、说话人权重；既有服务业务测试采用测试替身。

## 最终通过结果

| 检查 | 结果 | 说明 |
|---|---|---|
| JavaScript测试 | 166/166通过 | 全部`tests/*.test.js`自动发现，无遗漏/跳过 |
| Python测试 | 110/110通过 | 87项既有＋9项超时诊断＋14项工程工具测试 |
| JavaScript语法与Python编译 | 通过 | 包含当前全部产品/脚本/测试源文件 |
| 当前浏览器DOM流程 | 5/5通过 | 筛选、核查、写作、设置、停止；接口/声音/模型模拟 |
| 基线产品源码比对 | 33/33一致 | `extension/`、`server/`与原完整包字节一致 |
| 新Git暂存区检查 | 通过 | 在独立临时仓库执行，没有远程操作 |
| 强行暂存私有文件的负例 | 按预期拒绝 | 合成`private-data/fixture.wav`和`.env`；撤回后恢复通过 |
| 任务/验收引用与JSON/Markdown一致性 | 通过 | 25项任务、32项场景，依赖无环 |
| GitHub配置YAML解析 | 通过 | 仅静态解析，不是云端实际执行 |

最终统一命令：`python scripts/run_checks.py --suite all`。每个检查的实际退出码和耗时：

| 检查 | 退出码 | 本次秒数 |
|---|---:|---:|
| repository | 0 | 0.741 |
| js-syntax | 0 | 0.668 |
| javascript | 0 | 0.581 |
| python-compile | 0 | 0.699 |
| python | 0 | 2.728 |
| browser_filter_v072 | 0 | 8.092 |
| browser_quality_v071 | 0 | 6.439 |
| browser_writing_v070 | 0 | 11.814 |
| browser_ai_v052 | 0 | 4.738 |
| browser_content_v052 | 0 | 11.355 |

这里的秒数只是当前容器执行测试的耗时，不能当作用户机器的推理速度或开发工期。原始日志在本次工作目录的`artifacts/checks/`；交接ZIP不携带运行日志，只提交无正文的结构化摘要`HANDOFF_TEST_SUMMARY.json`。用户重跑后会生成自己的日志。

## 整合过程中发现并纠正的测试工具问题

旧RUN_TESTS硬编码较早的6个JS文件，未覆盖后续新增用例；现已改为动态发现。原浏览器测试路径写死Linux位置且截图覆盖docs，现改为可配置路径和忽略输出目录。首次路径迁移时，两处测试文件的`__future__`导入顺序被打乱，编译检查捕获；调整后重新执行完整套件，以上是最终结果，未把失败轮次算通过。

## 未完成，不得据此宣传

没有用户Windows Edge原生采集、真实Whisper/Ollama/声学模型端到端测试；没有字错率、翻译忠实度、误筛率、角色错误率或实际GPU性能测量；没有真实长视频模型整理或100秒超时修复。Windows BAT/PowerShell只做格式和逻辑静态检查；GitHub Actions仅提供文件。

归档仅使已有项目便于提交Git和继续开发。长期可靠性和实际内容准确度仍按`docs/KNOWN_ISSUES.md`及`planning/backlog.json`推进。
