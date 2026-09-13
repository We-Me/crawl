# T003/T012 固定样本夹具

本目录的非真实样本用于离线开发和验收，不来自任何真实机构，也不得用于真实网络请求。
所有链接使用 `example.invalid`，只作为可预期的下载目标标识。

| 路径 | 用途 |
| --- | --- |
| `html/detail_page.html` | 详情页样本：标题、元数据、正文、列表、表格、成功附件与失败附件链接 |
| `html/table_page.html` | 表格结构样本 |
| `html/version_v1.html`、`html/version_v2.html` | 同一文档两个版本，v2 修订了条款文本 |
| `attachments/notice.csv` | 文本附件样本（成功下载目标） |
| `attachments/notice.pdf` | 两页文本层 PDF 附件样本（第二页含三列表格），由 `tools/make_fixture_binaries.py` 生成 |
| `ocr/scanned_notice.png`、`ocr/scanned_notice.pdf` | 图像式“扫描件”样本，无文本层，供 OCR 与 PDF 解析任务使用 |
| `office/notice.docx` | DOCX 样本：Heading 1/2、段落、列表、表格 |
| `office/notice.xlsx` | XLSX 样本：Summary（含单位标注与表头）、Notes 与空 sheet |
| `office/notice.doc` | 旧式 DOC 样本：与 notice.docx 同内容，真实 MS Word 97（OLE2）二进制 |
| `office/notice.xls` | 旧式 XLS 样本：与 notice.xlsx 同内容，真实 MS Excel 97-2003（OLE2）二进制 |
| `manifests/failed_records.jsonl` | 失败样本，字段对齐 `contracts/failure.schema.json` |
| `site/` | 本地回环夹具站点（列表分页、详情、附件、重定向、临时失败与 429 端点、`robots.txt` 及 `private/` 受限样本），由 `tests/conftest.py` 提供服务 |
| `site/detail_paged_1..3.html`、`site/body_modes_index.html` | 三页正文样本：内容区 `rel=next` 翻页，供正文分页还原用例（AT-005） |
| `site/api_body_page.html`、`site/api_body.json` | 接口正文样本：页面以 `<link rel="alternate" type="application/json">` 声明正文端点（AT-005） |

二进制夹具由 `tools/make_fixture_binaries.py` 确定性生成；该脚本与 SDD 文档生成脚本无关。
夹具字节变化时需同步相关测试与证据记录。

`office/notice.doc` 与 `office/notice.xls` 是真实 OLE2 复合文档，不是改扩展名的伪文件，
但仍是自产虚构夹具，只用于离线结构验证，**不代表真实站点或机构文档验收**。两者由
`tools/make_legacy_fixtures.py` 用系统 LibreOffice（24.2.7.2 下验证）从同目录 OOXML 夹具
生成，DOC 经 ODT 中转移除导出侧对 python-docx 表格的拉平影响；内容、来源、哈希与局限
记录见 [NEXT-04 证据](../../specs/001-public-knowledge-collection/evidence/next04-legacy-office.md)。
缺少 LibreOffice 的机器不能重建这两个样本，但可用已提交的固定字节运行相关用例。

两者另有不依赖 LibreOffice 的结构级校验（`tests/test_legacy_office_real.py`）：直接解析
OLE2/CFB 目录与 FAT/miniFAT 链，确认 `notice.doc` 含 `WordDocument` 流（首部 `ec a5 01 01`，
即 Word FIB wIdent=0xA5EC）与 `1Table` 流，`notice.xls` 含 `Workbook` 流（首部
`09 08 10 00`，即 BIFF8 BOF），并各含 `\x05SummaryInformation`、
`\x05DocumentSummaryInformation` 属性集流。改扩展名或只有魔数的伪文件会在这些用例上失败。

2026-09-11 复核：重建前后五个二进制夹具 SHA-256 一致，见
[evidence/logs/t003-repro-checks.txt](../../specs/001-public-knowledge-collection/evidence/logs/t003-repro-checks.txt)。
