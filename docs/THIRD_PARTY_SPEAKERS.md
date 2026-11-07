# 可选说话人模块：官方依据

核对日期：2026-11-06。以下为第三方工具说明，不是本软件准确率证明。

- sherpa-onnx 本地说话人分离官方说明：https://k2-fsa.github.io/sherpa/onnx/speaker-diarization/index.html
- 官方模型与用法：https://k2-fsa.github.io/sherpa/onnx/speaker-diarization/models.html
- 对应固定运行库版本示例：https://github.com/k2-fsa/sherpa-onnx/blob/v1.12.34/python-api-examples/offline-speaker-diarization.py
- 固定安装版本与发布包：https://pypi.org/project/sherpa-onnx/1.12.34/
- 分段模型：sherpa-onnx-pyannote-segmentation-3-0，运行时使用 model.onnx。
- 声音特征模型：3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx，官方示例选择；对其他语言未完成准确度验证。

安装器仅下载公开官方资源，保留分段模型的LICENSE/README，并记录实际下载SHA256（此记录不等于发布者签名校验）。本包不包含或重新分发模型权重。依赖软件与模型的许可证/使用条件以官方发布为准。

语音特征相似度不是身份匹配概率。工程阈值(.55/.40/.08)未经过目标节目校准。没有自动人名识别，也没有以音色推断敏感属性。
