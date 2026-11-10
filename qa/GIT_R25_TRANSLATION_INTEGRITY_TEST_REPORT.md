# git-r25 · 外语文字稿完整性修复测试记录

## 问题重现与修复范围

- 现场问题：Sergio Marina 的西班牙语介绍保留了大段原语言，却在末尾接上中文。r24 `isChineseTranslation` 只有最低汉字比例门槛，未检查译文内仍有完整外语语句，部分模型结果因此可能被判成功并缓存。
- 此版本修复内容：外语残留和明显漏译检测；ASR `translationStatus=done` 混合译文在保留源文时重新翻译；r24 成功误判/保底/尝试次数检查点升级；翻译修正后使失效的断句分片重新计算；保底分片与中文分片分行。
- 修复只影响文字稿翻译/排版与本地检查点，不删除已有 ASR 源文、用户音频、旧文稿。

## 本轮实际测试

| 项目 | 命令/场景 | 结果 |
|---|---|---|
| 截图相同语言模式的专项回归 | `node --test tests/transcript_translation_v0123.test.js` | **24/24通过**；其中6项为r25新增加的真实问题回归（包含长文旧缓存） |
| JS全部测试 | `python scripts/run_checks.py --suite unit --timeout 120` → javascript | **333/333通过** |
| Python全部测试 | 同上 → python | **379/379通过** |
| 仓库文件核验 | `python scripts/check_repo.py` | **294源码文件，0问题** |
| JS语法 | `node scripts/check_js.cjs` | **55文件，0失败** |
| Python语法 | 上述统一检查 → python-compile | **通过** |
| 浏览器测试 | `python scripts/run_checks.py --suite browser` | 全套入口受运行窗口限制，前5组已通过；不将整套入口记作完成 |
| 浏览器独立测试 | 余下7组分别调用 `python tests/browser_*.py` | **7/7组通过**，与前5组合计12组单独/部分通过 |

新增专项覆盖：含完整西语正文加少量中文后缀时拒绝通过；完整中文译文可以保留 `Sergio Marina` 人名；ASR将混合文本标为done时自动回到原文；r24原缓存含混排成功行、保底原文与耗尽次数时重新校验；翻译失败和中文相邻时不会黏连；短视频拒绝混排模型结果后自动补译；长视频旧断句分片在重译后自动重算。

**重要范围边界**：使用 Linux Node/Python 3.13 与模拟 Ollama HTTP 返回值、模拟扩展 DOM。没有访问用户 Windows Edge、真实 Ollama 模型、真实音频或Google翻译；因此不宣称真实模型已稳定翻译全部语义内容或两小时视频现场完成。保守词长/字符启发式不能保证所有语言和专名不出现误判；当模型始终不能翻译时，仍会保留原文并在生成详情中注明，用户无需人工审批。
