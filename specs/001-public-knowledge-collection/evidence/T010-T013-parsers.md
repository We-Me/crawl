# 证据：T010—T013 多格式结构与统一清洗

日期：2026-09-11。目标平台：当前 Linux（x86_64）。解释器：uv 管理的 CPython 3.9.25。
对应需求：FR-010、FR-011、FR-012、FR-013；US2 的验收方式是“直接输入固定原件及账本夹具”，
因此本轮以固定样本解析与结构复核为证据，不依赖实时站点，仍未接入真实来源（T026 保持未选）。

## T010 跨格式原始结构块模型

- `src/crawler/parser/parsed_page.py`：`ParsedBlock`/`ParsedPage`/`PageStatus` 共用模型；块新增可选
  `page_no`、`confidence`、`section_path`、`article_no`，缺省不补造。
- `src/crawler/normalize/block_schema.py`：构造时按存在性保留定位字段；校验 `page_no` 为 ≥1 整数、
  `confidence` 在 0—1、`section_path` 为非空字符串数组、`article_no` 非空字符串，并要求同文档块顺序
  的 `page_no` 不递减（回页定位与顺序一致）。
- `src/crawler/parser/html_parser.py` 改为复用共享模型并保持 `ParsedBlock`/`ParsedPage` 名称兼容。
- 测试：`tests/test_pdf_ocr_parser.py` 的 T010 段（定位字段保留/省略/非法值/页码乱序）。
  原 HTML 长段落、列表、表格与标题顺序用例在 `tests/test_html_parser.py`、`tests/test_normalize.py` 继续通过。

## T011 文本 PDF 与 OCR

- `src/crawler/parser/pdf_parser.py`（`pypdf_text`）：逐页抽取（layout 模式保留列间距，失败时退化），
  页码从 1 开始；空行分段、连续同列数（≥2 列）行成表格并同时给出 `structured_data`（headers/rows/
  column_count）与制表符文本视图；页码行保留为 `page_note`；单页失败记 `failed` 页状态。
- `src/crawler/parser/ocr_parser.py`（`rapidocr_onnxruntime`）：图片与扫描 PDF 逐页 OCR；块携带
  `page_no`、`confidence` 与 `source_anchor.bbox`；页状态区分 `ok`/`empty`/`failed`，非 ok 页写入
  `metadata_missing`（如 `ocr_page_2_failed`、`ocr_page_1_empty`）；只有全部页失败才抛 `OcrError`。
- 扫描 PDF 栅格化使用 `pypdfium2`，逐页 `render(scale=2)` 后交给 RapidOCR；不依赖系统 OCR 组件。

固定样本与实测（`uv run --locked python`）：

| 样本 | 结果 |
| --- | --- |
| `tests/fixtures/attachments/notice.pdf`（两页文本层，第二页表格） | 2 页均 ok；首页标题与段落页码=1；表格页码=2，headers `Item/Quantity/Amount`，rows 两行 |
| `tests/fixtures/ocr/scanned_notice.png` | `OCR SAMPLE 123`（0.994）、`NOT1CE-2026-09-10`（0.989）、`FIXTURE`/`EONLY`，页状态 ok |
| `tests/fixtures/ocr/scanned_notice.pdf`（无文本层） | `pdf_has_text_layer` 为 False；OCR 后全部块 page_no=1、置信度 0—1 |

OCR 识别错误（如 `NOT1CE`）按原样保留，不做词典纠正——属于“不翻译、不改写”。
完整测试：`tests/test_pdf_ocr_parser.py`（19 项，含 partial failure、全失败、空页与非法 PDF）。

## T012 Office、CSV、JSON/XML/API 与旧式格式路线

- `docx_parser.py`（`python_docx`）：按 body 顺序保留 Heading N 标题层级、段落、List 列表、表格。
- `xlsx_parser.py`（`openpyxl_read_only`）：sheet 顺序映射 `page_no`；保留表头、数据行与原始行号，
  表头中的（单位：X）按原文提取到 `units`；空 sheet 记 `empty` 页状态与 `sheet_N_empty`。
- `tabular_parser.py`（`csv_stdlib`）：BOM 显式识别，依次尝试 utf-8/gbk/gb18030（失败才用替换解码并记录），
  分隔符经 `csv.Sniffer` 限定集合判定，记录实际 encoding/delimiter，不猜不改内容。
- `api_parser.py`（`json_stdlib`/`defusedxml_etree`）：JSON 列表逐项、对象逐顶层字段生成 record 块并保留
  `json_path`；XML 逐子元素保留 `xml_path`、属性与子字段文本，文本视图在子字段间保留分隔；
  `defusedxml` 拒绝实体展开。请求参数由 `canonical_url`（含查询串）与账本保留，分页字段按原样留在字段块。
- `dispatcher.py`：内容特征优先（OLE2 魔数、`%PDF-`）再按扩展名分派；不支持格式抛
  `UnsupportedFormatError`，不静默返回空文档。扫描件 OCR 需显式调用 `parse_scan`，不在分派中隐式触发。
- `legacy_parser.py`：`.doc/.xls` 按 OLE2 魔数识别，路线为系统 LibreOffice headless 转换后复用
  docx/xlsx 解析器；转换器可注入。本机核查 `which soffice libreoffice`、`/usr/lib/libreoffice/program/soffice`
  均不存在，故未安装系统组件时抛 `LegacyFormatError` 并给出安装提示，不静默降级。

固定样本与实测：

| 样本 | 结果 |
| --- | --- |
| `tests/fixtures/office/notice.docx` | 标题层级 1/2、段落、列表、表格顺序与内容一致；标题取自 Heading 1 |
| `tests/fixtures/office/notice.xlsx` | Summary/Notes 两个 ok sheet + Empty 空 sheet 状态；行号 [2,3]；units `{Quantity…: 件, Amount…: 元}` |
| `tests/fixtures/attachments/notice.csv` | encoding utf-8、delimiter `,`、headers `年份/数值`、row_numbers [2]；GBK 与 BOM 样本另行验证 |
| JSON/XML 内联样本 | 路径 `$[i]`/`$.key`、`/notice/item[i]`、属性与子字段保留；非法 JSON/XML 与实体炸弹明确报错 |

完整测试：`tests/test_format_parsers.py`（24 项）。

## T013 统一清洗与元数据规范化

- `src/crawler/normalize/text_utils.py`（叶子模块，避免 parser/normalize 循环导入）：NFC、去控制字符与
  零宽字符、NBSP 归一、按行去尾空白；不做长度裁剪。
- `src/crawler/normalize/date_utils.py`：支持 `YYYY-MM-DD`、`YYYY/M/D`、`YYYY年M月D日`、ISO 时间戳与
  英文月名；非法日期（如 2026-02-30）与仅年月（2026年9月）返回 None，调用方保留 `raw_date`，不补造。
- `src/crawler/normalize/metadata_normalizer.py`：`normalize_url`（解析相对地址、去默认端口与片段、
  小写 scheme/host，保留路径与查询）、`detect_language`（先显式标记，再按文字系统判定：汉字/假名/谚文/
  西里尔/阿拉伯/泰文/希伯来/天城文；拉丁文返回 und，不猜英语）、`normalize_page`（统一清洗块文本、
  回填可证实的日期、规范语言与 URL）、
  `check_text_integrity`（复核块清洗、full_text 与块一致、页码顺序、置信度范围与块契约）。
- 2026-09-11 补强：AT-013 场景含 zh/en/hi 三种语言与超长段落，而文字系统表原缺天城文。现按既有
  “脚本到主语言”约定加入 `devanagari → hi`（范围 U+0900—U+097F、U+A8E0—U+A8FF）；显式语言标记
  仍优先（如 `mr` 不被改成 `hi`），其他印度文字系统在来源需要前保持 und，不擅自扩展。
  同时补齐 AT-013 用例：三语原文逐字保留（不翻译/不转写）、800 段超长段落不截断不摘要、无标记天城文
  识别为 hi。
- `src/crawler/parser/html_parser.py` 复用 `collapse_whitespace` 与 `normalize_date`；`pipeline.py` 对 HTML
  解析结果调用 `normalize_page`（语言提示取来源配置），语言与日期规则不再逐格式重复。
- 全解析器一致性用例 `test_all_parsers_keep_full_text_consistent` 覆盖 HTML、PDF、CSV、DOCX、XLSX、JSON、OCR，
  均 `check_text_integrity == []`。

## 依赖变更（DEV-007/DEV-009）

| 包 | 约束 | 锁定版本 | 用途与说明 |
| --- | --- | --- | --- |
| pypdf | `>=5,<7` | 6.18.0 | 文本层 PDF 逐页抽取；传递仅 typing-extensions |
| rapidocr-onnxruntime | `>=1.3,<2` | 1.4.4 | 图片/扫描件 OCR（自带 ONNX 模型，纯 pip） |
| pypdfium2 | `>=4.30,<5` | 4.30.0 | 扫描 PDF 逐页栅格化；无传递依赖 |
| python-docx | `>=1.1,<2` | 1.2.0 | DOCX 结构解析（复用现有 lxml） |
| openpyxl | `>=3.1,<4` | 3.1.5 | XLSX 只读解析；传递 et-xmlfile 2.0.0 |
| （已有）defusedxml | `>=0.7.1,<1` | 0.7.1 | XML 安全解析，本任务首次实际使用 |
| （传递）onnxruntime | — | 1.19.2 | 引入 coloredlogs、flatbuffers、protobuf、sympy、packaging |
| （传递）numpy / opencv-python / pillow / shapely / pyclipper / six / tqdm | — | 2.0.2 / 5.0.0.93 / 11.3.0 / 2.0.7 / 1.3.0.post6 / 1.17.0 / 4.70.0 | RapidOCR 图像处理链 |

- 全部经登记清华镜像 `uv add` 安装，`prerelease=disallow`，锁文件来源见 T002 证据与 `uv.lock`；
  未新增官方 PyPI 兜底。opencv-python 解析到 5.x 为该包的正式稳定版本，仅在 3.9 下验证通过后保留；
  若后续出现兼容问题，按 DEV-007 以最小约束回到 4.x 并重跑 OCR 样本。
- 未引入 pandas（csv/json 标准库足够）、未引入调度、数据库或 Web 框架；OCR 未使用系统 tesseract
  （本机只有 libtesseract5 无可执行文件，故选择纯 pip 路线）。

## 样本夹具

`tools/make_fixture_binaries.py` 仍与 SDD 初始文档生成脚本无关，重复运行字节一致（DOCX/XLSX 固定
zip 时间戳与 core.xml modified）。本轮固定样本 sha256：

| 路径 | sha256 |
| --- | --- |
| `tests/fixtures/attachments/notice.pdf` | `3223c9df5d05174fc45b24e0507819d97f071e8def008d086e7e1cb87bd61782` |
| `tests/fixtures/ocr/scanned_notice.png` | `99d011b6fccab27db904353dafb9b4d3f08716d873bbefcd652d635de41e4b87` |
| `tests/fixtures/ocr/scanned_notice.pdf` | `e1618689234713b9a924109a9d62432f3d36d904daf0ef33f1a5e323f1e8d6d1` |
| `tests/fixtures/office/notice.docx` | `65da833b0864734c4b4ff21422a8542ab63d986239eae1cacc5f534a4525af79` |
| `tests/fixtures/office/notice.xlsx` | `d2e61aa457ea7d4a57a5143e662e2aa76b30295deef29998b999057eeb175f92` |

## 验收命令与结果

```bash
UV_CACHE_DIR=/tmp/crawl-uv-cache uv run --locked --no-python-downloads pytest -q
# 175 passed
python3 tools/verify_sdd_documents.py
# PASS
```

## 已知限制与待办

- PDF 表格识别基于 layout 抽取的空格列间距（连续≥2 行、同列数）；行内单空格分隔的复杂表格可能不被
  识别为表格，但文本视图不丢内容。表格/API 的最终产出形态仍属 Q08 待决。
- 附件尚未在采集管线中解析为独立文档（Q07 待决；本证据按 US2 的固定样本方式验证解析器）。分派器
  `parse_attachment` 已就绪，供 T018 交付整理与 Q07 决定后的联调使用。
- OCR 置信度阈值、准确率分母与近重复阈值仍属 Q11 待决，未自动判定通过。
- 旧式 DOC/XLS 的实机转换未验证（本机无 LibreOffice）；已验证的是识别、路线选择与显式失败路径。
