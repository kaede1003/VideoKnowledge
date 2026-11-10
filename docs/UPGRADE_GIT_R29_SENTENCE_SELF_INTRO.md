# VideoKnowledge git-r29 升级说明

## 本次更新

- **断句与合并**：模型每次整理小片段时可读取同一说话人前后最多90字符的只读上下文。最终输出再次检查被错误切开的条件句，必要时只调整标点和换行，防止跨不同说话人拼接。
- **自我介绍命名**：包含“大家好，我是社长”“我叫小雨”“my name is Sergio Marina”等明确自称的发言会直接命名对应声音。仍保留说话人编号和依据供内部溯源，不要求人工审批。
- **整理模式**：仅保留知识文档、文字稿、按我的要求。历史小说/剧本文稿不被删除、仍可从结果历史中打开和导出。历史的模式偏好自动转为知识文档。
- **旧检查点**：升级后的首次重新生成会让旧版“标点排版”分块重新处理；已完成的ASR音频、外语译文、笔记不删除。

## Windows 原地升级

1. 停止当前文稿生成任务，退出 VideoKnowledge 采集服务（如正在使用），备份 `D:\VideoKnowledge_Git_Project`。
2. 解压新的ZIP，将 `VideoKnowledge_Git_Project` 内的源码文件合并覆盖到原工程同名位置。
3. **不要删除** `.venv`、`.venv-qwen`、`models`、录音缓存、SQLite、私人配置及旧笔记；不要重新导入一个全新扩展ID。
4. 打开 `edge://extensions`，找到原来“加载已解压”的 VideoKnowledge，点击“重新加载”，然后刷新视频页面。
5. 在相同视频中重新生成一份**新文字稿**。旧导出的HTML/Markdown不会自动被改写。

## Git 提交（原工程内操作）

```powershell
cd D:\VideoKnowledge_Git_Project
git status
git add -A
git diff --cached --check
git commit -m "fix: improve transcript sentence flow and self-introduced speaker labels; simplify writing modes"
git push
```

不要将虚拟环境、模型文件、API密钥、音频或数据库加入 Git。

## 已知边界

- **截图中的“再打不赢。行的话”**：新版可将误断开的句子连接，但不擅自删除音频识别出来的“行”字。词汇本身是否应为“的话”，只有回听原音或可靠字幕证据才能确定。
- 仍依赖 Sherpa 声纹分组；如果声纹归属本来就错了，姓名也可能绑定错误。自报名与视频人物真实身份并非同一层面的核验。
- 本轮没有在用户的Windows、Edge、真实Ollama或2小时视频上执行实机测试。浏览器的旧完整写作回归脚本超时，详见QA报告。

回滚：备份原目录、恢复原源码并在 `edge://extensions` 重新加载即可。新的生成结果已另外保存，不会主动覆盖旧导出文件。
