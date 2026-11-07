## 对应任务

VK-xxx / AC-xxx

## 复现与改动

说明证据、根因、变更范围；不要把计划写成已实现。

## 测试与限制

写出实际执行命令、退出码/计数；明确模拟输出与真实Edge/模型边界。

## 数据、迁移与回滚

原始文字、人工修订、缓存、旧成品是否保持；如何回滚。

- [ ] 更新任务JSON、CHANGELOG、已知问题及必要文档
- [ ] `python scripts/run_checks.py --suite unit`
- [ ] 涉及界面时运行browser套件；未运行说明原因
- [ ] `python scripts/check_repo.py --staged`并人工检查暂存区
- [ ] 未提交个人笔记、模型、凭据或数据库
