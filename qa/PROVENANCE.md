# 源码交接溯源 · git-r2 / 0.8.0

本版从 `VideoKnowledge_Git_Project_v0.7.2_git-r1.zip` 继续修改。扩展与服务均为0.8.0，协议保持5。

`baseline-source-sha256.json` 和 `BASELINE_TEST_REPORT.md` **仅是上一版历史证据**。本版有意修改业务代码，不能再使用 `--baseline` 要求与0.7.2完全一致，不要改写那份历史哈希。

当前新增/修改：自动说话人默认与只读角色卡、移除网页字幕入口和采集路径、72小时受控视频缓存、整理前上下文同音词校验、WebSocket/工作任务恢复、服务启动日志/退出码与诊断、对应测试、文档与任务。具体范围和未完成项见 `V080_TEST_REPORT.md`、`docs/UPGRADE_V080.md`。

本次 `HANDOFF_MANIFEST.json` 记录新的git-r2文件SHA256和大小（自身排除以免循环），`HANDOFF_TEST_SUMMARY.json`记录实际执行范围。它们不是保证真实模型准确率的证据。

工程不包含用户完整笔记、音视频、数据库、密钥、模型权重或运行日志。不带`.git`、远程地址或提交身份。打包只用独立临时目录检验暂存内容，没有远程操作。
