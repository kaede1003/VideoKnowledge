# 测试策略与证据等级

## 统一入口

| 命令 | 范围 |
|---|---|
| `python scripts/run_checks.py --suite repository` | 结构/版本/任务依赖/可提交文件检查 |
| `python scripts/run_checks.py --suite unit` | 上述检查＋全部JS语法/测试＋Python编译/全部单元测试 |
| `python scripts/run_checks.py --suite browser` | 上述检查＋当前5组真实DOM、模拟扩展/模型的浏览器测试 |
| `python scripts/run_checks.py --suite all` | unit和browser的并集 |
| `python scripts/check_repo.py --staged` | 检查实际Git index，含强行暂存的文件 |
| `python scripts/check_repo.py --baseline` | 仅交接核查：产品源码与原包SHA一致 |

Windows双击`RUN_TESTS.bat`默认跑unit。无需模型下载；缺测试依赖须显式安装`dev/requirements-test.txt`。脚本不会把没装Node当“跳过后成功”。日志和JSON结果在`artifacts/checks/`，含执行命令、退出码、耗时和环境，不自动提交Git。

## 五级证据不能混用

1. 静态/结构：只能证明语法、目录、配置引用和工程规则。
2. 单元/模拟传输：可证明构造输入的逻辑、缓存和幂等；不能证明真实模型质量。
3. 真DOM＋测试替身：可证明按钮、布局、消息编排；不是原生扩展授权和后台生命周期。
4. 真实Windows Edge＋实际模型：验证声学采集、推理、资源、CORS和长时间运行。
5. 授权音频＋人工参考稿：才可测听写字错率/词错率、数字否定错误、翻译忠实度、角色错误和误筛率。

本工程本次运行结果见`../qa/BASELINE_TEST_REPORT.md`。历史报告保持历史身份，不拿旧计数充当本次测试。

## 真实内容验收方法

保留音频版本、采样率、播放器速度、硬件和模型版本；为同一片段建立人工核对参考稿，再比较基线和候选版本。统计重复、漏句、专名、数字、否定、推测语气和说话人归属；不要只算平均分掩盖严重语义错误。没有原音时只能做文字异常检查，不能生成“正确原话”作为金标准。

语音CER/WER、翻译评审、筛选误删率分开报告。真实数据集只能放忽略目录或外部授权存储；提交Git的夹具必须可公开并标明合成/授权来源。具体性能和准确率阈值需建立基线后由项目所有者冻结，不在本次凭空承诺。

## 当前与历史浏览器脚本

统一runner选用`browser_filter_v072.py`、`browser_quality_v071.py`、`browser_writing_v070.py`、`browser_ai_v052.py`、`browser_content_v052.py`。较早脚本仍在tests中，可用来比较旧缺陷，但不在默认门禁中；未来清理见任务清单。

所有当前浏览器截图均写入忽略目录，不覆盖仓库展示图。测试使用合成内容。默认单元测试不联网下载模型，不访问用户浏览器档案，不读取用户笔记。

## CI边界

CI文件定义Linux/Windows代码测试及手动触发的Linux DOM测试。提供配置不等于已经在GitHub执行；云端流水线可能因依赖下载、浏览器或平台差异失败，需要保留失败证据再修，不得简单跳过。
