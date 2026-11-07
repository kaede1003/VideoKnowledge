# 来源与整理边界

## 本次直接依据

1. 对话交付的`VideoKnowledge_Edge_v0.7.2_FULL.zip`：现有扩展、后端、测试、脚本和历史文档。
2. `VideoKnowledge_AI_Timeout_Diagnostics.zip`：既有独立诊断脚本、9项测试及超时源码核查报告。
3. 已确认的用户需求与故障反馈：简洁界面、缓存听写、翻译、角色、五种整理、可逆筛选、100秒超时。

原包SHA256见根`VERSION.json`，产品源码逐文件SHA256见`qa/baseline-source-sha256.json`。本次没有重新进行外部框架选型，也没有将一般经验冒充现场测量。

## 没有纳入Git的数据

用户上传的完整笔记、节目视频/音频、错误截图中的个人浏览内容、现场诊断和浏览器档案不放入本项目包。与重复、翻译、筛选有关的构造测试保留为合成用例；不将用户机器输出当真实参考稿。

## 继承的官方参考链接

这些链接来自既有项目说明，仅为维护者后续核对接口/许可提供入口；本次工程归档没有重新验证其最新内容：

- Ollama聊天/分项计时：https://docs.ollama.com/api/chat
- Ollama本机来源和资源说明：https://docs.ollama.com/faq
- Ollama鉴权：https://docs.ollama.com/api/authentication
- Chromium扩展后台生命周期：https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle
- faster-whisper实现：https://github.com/SYSTRAN/faster-whisper
- sherpa-onnx说话人说明：https://k2-fsa.github.io/sherpa/onnx/speaker-diarization/index.html

后续升级依赖、浏览器API或模型时需重新核对官方资料并实际测试，不能只引用这些链接表示兼容或准确率已验收。
