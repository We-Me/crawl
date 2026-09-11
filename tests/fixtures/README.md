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
| `manifests/failed_records.jsonl` | 失败样本，字段对齐 `contracts/failure.schema.json` |
| `site/` | 本地回环夹具站点（列表分页、详情、附件、重定向、临时失败与 429 端点、`robots.txt` 及 `private/` 受限样本），由 `tests/conftest.py` 提供服务 |
| `site/detail_paged_1..3.html`、`site/body_modes_index.html` | 三页正文样本：内容区 `rel=next` 翻页，供正文分页还原用例（AT-005） |
| `site/api_body_page.html`、`site/api_body.json` | 接口正文样本：页面以 `<link rel="alternate" type="application/json">` 声明正文端点（AT-005） |

二进制夹具由 `tools/make_fixture_binaries.py` 确定性生成；该脚本与 SDD 文档生成脚本无关。
夹具字节变化时需同步相关测试与证据记录。

2026-09-11 复核：重建前后五个二进制夹具 SHA-256 一致，见
[evidence/logs/t003-repro-checks.txt](../../specs/001-public-knowledge-collection/evidence/logs/t003-repro-checks.txt)。
