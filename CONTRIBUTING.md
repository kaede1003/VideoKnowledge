# 协作约定

阅读`AGENTS.md`和`docs/DEVELOPMENT.md`。任务列表以`planning/backlog.json`为源，更新后运行`python scripts/render_planning.py`生成Markdown。每次变更关联VK任务与AC验收场景。

开发分支采用`fix/VK-xxx-name`或`feat/VK-xxx-name`。PR需要说明复现、修改、数据影响、测试命令和未测试部分。默认先修核心可靠性，不增加新的复杂面板。

提交前跑`python scripts/run_checks.py --suite unit`，界面变更再跑`--suite browser`；`git add`后执行`python scripts/check_repo.py --staged`。检查发现问题不要通过删测试/伪造通过绕过。初次交接可用`--baseline`核对来源，今后有意开发不要求维持旧源码哈希。

不提交运行缓存、真实录音、私人笔记、模型权重和密钥。默认测试使用明确标识的合成夹具。真实模型/浏览器验收要单列，mock输出不作为准确率或性能证明。

`.bat`必须ASCII＋CRLF；`.gitattributes`确保Git检出换行。保留已知未修问题及回滚说明。项目许可尚待选择，不默认替所有者对外授权。
