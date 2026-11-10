# 制度扫描件 OCR 中间产物

使用 Windows 自带 `Windows.Media.Ocr` 与 `zh-Hans-CN` 语言离线识别。PDF 页面在内存中渲染，未另存图片。产物是待审阅的中间文本，不代表已完成制度核验或知识库导入。

| 产物 | 来源 | 页数 |
| --- | --- | --- |
| assessment_rules_2022.jsonl | 关于印发《北京邮电大学本科生课程考核与成绩管理实施细则》的通知.pdf | 17 |
| degree_rules_2025.jsonl | 学位授予规定.pdf | 7 |

每行对应一页，包含一基页码 `page`、总页数、源文件名、源文件 SHA256、`raw_text`、`text`、OCR 引擎/语言/渲染宽度，以及始终为真的 `ocr` 和 `needs_review`。`raw_text` 从引擎 `OcrResult.Lines` 的各行 `Text` 按换行拼接，保留引擎识别的行结构和单词空格；`text` 只删除相邻汉字之间的空格或制表符，不修正数字、不改写条款，并保留换行。

在仓库根目录运行（须使用 Windows PowerShell 5 的 `powershell.exe`，且已安装 Windows 简体中文 OCR 语言）：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File backend/scripts/ocr_windows.ps1 -InputPdf 'data/raw/关于印发《北京邮电大学本科生课程考核与成绩管理实施细则》的通知.pdf' -OutputJsonl 'data/processed/ocr/assessment_rules_2022.jsonl'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File backend/scripts/ocr_windows.ps1 -InputPdf 'data/raw/学位授予规定.pdf' -OutputJsonl 'data/processed/ocr/degree_rules_2025.jsonl'
```

脚本拒绝覆盖已有输出；复跑请使用新文件名。所有页面识别成功后才创建输出文件；输出为无 BOM 的 UTF-8 JSONL。

## 已知质量问题

- 书法/艺术字体标题存在拆字和错字；通知正文可用于交叉核验标题。
- 考核细则第4页“迟到……分钟”的数字发生误识别，必须核对扫描页。
- 考核细则第14–15页公式符号不可靠，第16–17页表格存在明显行列乱序及数字错识别，不能直接作结构化数据。
- 汉字清洗不合并分散数字，因此年份等数字仍可能含空格；禁止据此自动修正阈值。
- 学位文件通知日期为2025年1月18日，末页印发日期为1月20日；生效条款为“自发布之日起施行”，不得未经核验强行合并为一个日期。
- 两份文档均未据此推断适用于某一入学年级。正式入库前应核对页码、标题、文号、关键数字、否定词、适用范围和生效条款。

生成后已核验：共24页且每页非空；页码连续；JSONL可解析；OCR与待审阅标记完整；各页源文件哈希与原PDF一致。这些检查不代表文字准确性已经人工审核。
