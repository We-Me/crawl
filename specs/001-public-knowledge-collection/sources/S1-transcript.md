# S1 原文结构转录

原件：[ 一般爬虫采集与标准化数据交付需求规范_V1.1_仅采集整理.docx ](../../../docs/一般爬虫采集与标准化数据交付需求规范_V1.1_仅采集整理.docx)

此文件按 Word 主文档 XML 顺序转录段落和表格，供定位原文使用；不代替原件的排版、图像或批注。B 编号表示主文档直接子元素的序号，空段落计入编号但不显示。表格中的换行以 HTML 换行标记表示。

## B001

一般爬虫采集与标准化数据交付需求规范

## B002

V1.1——仅负责“把内容爬全并整理好”，暂不进行 RAG 切片与索引

## B004

| 任务边界 | 网站内容采集、原始文件归档、正文解析、结构保留、元数据整理、去重与版本管理 |
| --- | --- |
| 本阶段不做 | 语义切片、token 切片、Embedding、向量库、BM25 索引、Reranker、RAG Prompt 组织 |
| 强制交付 | raw/ + crawl_manifest.jsonl + documents.jsonl + blocks.jsonl + failed_records.jsonl |
| 目标 | 保证数据完整、可追溯、可重解析，并方便后续独立开展 RAG 切片与索引 |
| 推荐编码 | UTF-8 |

## B006

核心原则：本阶段不“切知识”，只“保结构”。后续 RAG 可以基于保留下来的标题、段落、页码、条款、表格、列表等原始结构再决定如何切片。

## B008

一、任务目标与边界

## B009

本阶段任务的目标是将目标网站、数据库和附件中的相关公开内容尽可能完整地采集下来，并整理为统一、可追溯、便于后续再加工的数据格式。当前阶段不要求生成可以直接进入 RAG 检索的“知识片段”，也不要求进行向量化或索引建设。

## B010

但为了避免后续切片时重新解析原始网页，本阶段必须在正文清洗的同时保留文档结构信息，例如标题层级、自然段、列表、表格、页码、条款号、附件关系和原始顺序。也就是说，当前交付的是“结构化的文档数据”，不是“RAG Chunk”。

## B011

1.1 本阶段必须做

## B012

发现并抓取相关网页、附件、结构化下载文件和公开 API 数据。

## B013

保留 HTML、PDF、DOCX、XLSX、JSON、XML、图片等原始文件。

## B014

抽取正文和关键元数据，统一编码、日期、URL、来源字段。

## B015

按原文结构拆成 block（标题/段落/列表项/表格/页块等），但不进行语义合并或 token 切分。

## B016

建立文档与原始文件、URL、抓取记录之间的可追溯关系。

## B017

完成 URL 去重、内容去重、版本识别、失败记录和增量更新。

## B018

1.2 本阶段明确不做

## B019

不生成 chunks.jsonl，不定义最终 RAG chunk 大小。

## B020

不按 256/512/1024 token 等阈值切分。

## B021

不做 Embedding，不生成向量。

## B022

不建立向量数据库、BM25 或混合检索索引。

## B023

不做 Reranker、Prompt 拼接、证据组织和答案生成。

## B024

不根据模型上下文窗口裁剪正文。

## B025

二、最终交付物

## B026

| 序号 | 交付物 | 是否强制 | 内容 | 主要用途 |
| --- | --- | --- | --- | --- |
| 1 | raw/ | 是 | 原始 HTML、PDF、Word、Excel、JSON/XML、图片等 | 保真归档、审计、重新解析 |
| 2 | crawl_manifest.jsonl | 是 | 每次抓取的 URL、时间、状态码、原始文件位置、哈希等 | 爬虫总账和追溯 |
| 3 | documents.jsonl | 是 | 一行一份逻辑文档；保存文档级元数据和清洗后全文 | 统一文档接口 |
| 4 | blocks.jsonl | 是 | 一行一个原始结构块；标题、段落、列表、表格、页块等 | 为后续切片保留结构 |
| 5 | failed_records.jsonl | 是 | 抓取/下载/解析/标准化失败记录 | 补抓和人工处理 |
| 6 | logs/ | 是 | 运行日志、数量统计、重复统计、异常信息 | 运维和验收 |

## B028

三、爬虫怎么爬

## B029

3.1 页面发现顺序

## B030

| 优先级 | 发现方式 | 适用场景 | 要求 |
| --- | --- | --- | --- |
| 1 | 固定栏目/列表页 | 新闻、文件、政策、法规目录 | 优先使用；完整、稳定、易增量 |
| 2 | 站内搜索/高级搜索 | 条约库、法规库、档案库 | 按宽泛关键词批量召回详情页 |
| 3 | sitemap.xml / RSS | 提供站点地图或订阅源的网站 | 作为补充发现入口 |
| 4 | 公开 API/JSON 接口 | 前端页面由接口加载 | 优先抓接口原始 JSON |
| 5 | 附件链接 | PDF、Word、Excel 等 | 详情页发现后必须继续下载 |
| 6 | 浏览器自动化 | 纯 JS 且无可用接口 | 仅兜底，不作为默认方案 |

## B032

3.2 关键词爬取要求

## B033

站内搜索关键词以高召回为目标。宽泛主题词用于发现候选页面；具体文件名、年份、人物和机制名用于补漏。关键词命中只决定“是否抓取候选页”，不直接决定最终知识分类。

## B034

| 词层级 | 作用 | 例子 |
| --- | --- | --- |
| 宽泛主题词 | 主召回 | 印度、中印、边境、边界、关系、法律、文化、协议、声明、会谈 |
| 领域扩展词 | 扩大同义表达 | 国界、口岸、条约、协定、机制、宗教、民族、地名、政策 |
| 精确补漏词 | 找重点已知资料 | 年份、正式文件名、机构名、事件名、具体地名 |

## B036

3.3 详情页与附件抓取

## B037

详情页必须保存最终 URL、标题、发布日期、发布机构、栏目路径、正文和附件链接。

## B038

附件必须单独下载；不能只保存附件 URL。

## B039

同一页面含多个附件时，逐个记录 attachment_id、文件名、类型、URL、本地路径和哈希。

## B040

如果正文和附件内容重复，两者仍保留原始文件，但标准化文档层可建立 duplicate_of / related_doc_ids 关系。

## B041

对分页正文、点击展开正文、前端接口加载正文，必须还原完整内容。

## B042

3.4 请求控制

## B043

| 项目 | 建议要求 |
| --- | --- |
| 访问边界 | 仅访问公开页面；遵守 robots.txt、站点条款和适用法律；不绕过登录/验证码/访问控制。 |
| 并发 | 单域名低并发，通常 1-3 req/s，站点慢时进一步降低。 |
| 超时 | 连接约 10 秒，读取约 30 秒，可按站点调整。 |
| 重试 | 网络错误、429、5xx 指数退避 2-3 次；永久性 4xx 不盲目重试。 |
| 重定向 | 允许正常 301/302，并记录 requested_url 与 final_url。 |
| 域名白名单 | 只递归 allowed_domains；外部链接可以记录但不自动深爬。 |

## B045

四、原始数据必须怎么保存

## B046

4.1 原始层必须保真

## B047

爬到什么就保存什么。不能为了“统一格式”而只留下纯文本。原始层是后续重新解析、审计和版本比对的唯一依据。

## B048

| 来源 | 原始保存格式 | 是否保留 |
| --- | --- | --- |
| 普通网页 | .html | 必须 |
| PDF | .pdf | 必须 |
| Word | .doc/.docx | 必须 |
| Excel/CSV | .xls/.xlsx/.csv | 必须 |
| API | .json | 必须 |
| XML/RSS | .xml | 必须 |
| 图片/扫描件 | .jpg/.png/.tif 等 | 必须 |

## B050

4.2 目录结构

## B051

| data/├── raw/│   ├── CN_MFA/│   │   └── 2026-09-07/│   │       ├── html/│   │       ├── pdf/│   │       ├── docx/│   │       ├── xlsx/│   │       ├── json/│   │       └── image/│   └── IN_MEA/├── manifests/│   ├── crawl_manifest.jsonl│   └── failed_records.jsonl├── normalized/│   ├── documents.jsonl│   └── blocks.jsonl└── logs/    ├── crawler.log    └── metrics.json |
| --- |

## B053

五、crawl_manifest.jsonl：爬虫总账

## B054

每一个成功取得的网页、附件或 API 响应必须对应一条 manifest 记录。manifest 不承担正文存储，只负责记录抓取行为和原始文件位置。

## B055

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| crawl_id | 是 | 抓取记录唯一 ID |
| source_id | 是 | 来源 ID |
| requested_url | 是 | 原始请求 URL |
| final_url | 是 | 重定向后的最终 URL |
| crawl_time | 是 | ISO 8601 抓取时间 |
| http_status | 是 | HTTP 状态码 |
| content_type | 是 | MIME 类型 |
| raw_path | 是 | 原始文件相对路径 |
| sha256 | 是 | 原始文件哈希 |
| referrer_url | 建议 | 从哪个列表页/详情页发现 |
| discovery_method | 是 | list/search/sitemap/api/attachment/manual |
| keyword | 条件必填 | 若由站内搜索发现，保存触发关键词 |
| etag / last_modified | 可选 | 用于增量更新 |

## B057

六、documents.jsonl：统一文档级数据

## B058

documents.jsonl 是本阶段最核心的统一数据文件。一行表示一份“逻辑文档”。逻辑文档可以来自网页正文、PDF、Word、API 返回的一篇文章或一份法规。这里保留完整清洗后正文，但不进行 RAG 切片。

## B059

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| doc_id | string | 是 | 文档唯一 ID |
| source_id | string | 是 | 来源 ID |
| source_name | string | 是 | 来源名称 |
| source_url | string | 是 | 原始页面/附件 URL |
| canonical_url | string | 建议 | 规范化 URL |
| title | string | 是 | 标题 |
| full_text | string | 是 | 清洗后的完整正文；不按 token 切片 |
| language | string | 是 | zh/en/hi/mixed 等 |
| document_type | string | 是 | html_page/pdf/law/agreement/news/report 等 |
| publication_date | date | 建议 | 发布日期 |
| effective_from / effective_to | date/null | 按需 | 法规、条约有效期 |
| issuer | string | 建议 | 发布机构 |
| category_hint | array | 建议 | 七类知识库的初步候选标签，不做最终语义分类 |
| section_path | array | 建议 | 网站栏目路径或文档章节路径 |
| attachments | array<object> | 可选 | 附件清单及其 URL/路径/哈希 |
| raw_path | string | 是 | 对应原始文件 |
| sha256 | string | 是 | 正文或原文件哈希 |
| crawl_time | datetime | 是 | 抓取时间 |
| version | string | 建议 | 版本编号 |
| is_current | boolean | 建议 | 是否当前版本 |
| extraction_method | string | 是 | html_parser/pdf_text/ocr/docx/xlsx/api 等 |
| parse_status | string | 是 | ok/partial/failed |

## B061

| {"doc_id":"CN_MFA_000001","source_id":"CN_MFA","source_name":"中华人民共和国外交部","source_url":"https://...","title":"某文件","full_text":"完整正文……","language":"zh","document_type":"html_page","publication_date":"2026-08-26","issuer":"中华人民共和国外交部","category_hint":["双边协定与机制库","政策立场库"],"section_path":["国家和组织","亚洲","印度"],"raw_path":"raw/CN_MFA/2026-09-07/html/xxx.html","sha256":"...","crawl_time":"2026-09-07T11:00:00+08:00","version":"1","is_current":true,"extraction_method":"html_parser","parse_status":"ok"} |
| --- |

## B063

七、blocks.jsonl：保留原文结构，不是 RAG Chunk

## B064

为了方便后续切片，本阶段额外输出 blocks.jsonl。block 是从原文直接抽取出的“原始结构单元”，例如一个标题、一个自然段、一个列表项、一张表格、一页 PDF 的文本块。它不做语义重组，不按 token 长度合并或拆分，因此不能等同于后续的 RAG chunk。

## B065

后续 RAG 切片程序可以根据 block_type、heading_level、page_no、article_no、order 等字段，决定哪些 block 合并成一个 chunk、哪些需要继续细分。这样无需重新打开 HTML/PDF 做结构恢复。

## B066

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| block_id | string | 是 | 结构块唯一 ID |
| doc_id | string | 是 | 所属文档 ID |
| order | integer | 是 | 原文顺序，从 0 或 1 递增 |
| block_type | string | 是 | title/heading/paragraph/list_item/table/table_row/page_note/image_caption 等 |
| text | string | 条件必填 | 文本内容；表格可另存 structured_data |
| heading_level | integer/null | 建议 | 标题层级 1/2/3… |
| section_path | array | 建议 | 当前结构块所属章节路径 |
| page_no | integer/null | PDF/扫描件建议 | 原文件页码 |
| article_no | string/null | 法规/条约建议 | 条/款/项编号 |
| structured_data | object/null | 表格等建议 | 表格行列、键值、JSON 结构 |
| source_anchor | string/object | 建议 | DOM selector、页码、段落序号、条款号等定位信息 |
| extraction_method | string | 是 | 抽取方式 |
| confidence | number/null | OCR/自动抽取可选 | 0-1 置信度 |

## B068

| {"block_id":"CN_MFA_000001_B0007","doc_id":"CN_MFA_000001","order":7,"block_type":"heading","text":"边界问题","heading_level":2,"section_path":["正文","边界问题"],"page_no":null,"article_no":null,"source_anchor":{"dom_path":"main > h2:nth-of-type(2)"},"extraction_method":"html_parser"}{"block_id":"CN_MFA_000001_B0008","doc_id":"CN_MFA_000001","order":8,"block_type":"paragraph","text":"该段完整原文……","heading_level":null,"section_path":["正文","边界问题"],"page_no":null,"article_no":null,"source_anchor":{"paragraph_index":8},"extraction_method":"html_parser"} |
| --- |

## B070

7.1 block 与后续 chunk 的区别

## B071

| 对比项 | 本阶段 block | 后续 RAG chunk |
| --- | --- | --- |
| 形成依据 | 原始文档结构 | 语义、token 数、检索效果、模型上下文 |
| 是否允许合并多个段落 | 否，尽量保持原始单元 | 允许 |
| 是否允许把长段落再拆开 | 原则上不做语义拆分 | 允许 |
| 是否依赖 Embedding/LLM | 不依赖 | 可能依赖 |
| 本阶段是否交付 | 是 | 否 |

## B073

八、不同文件类型的解析要求

## B074

| 文件类型 | 本阶段必须产出 | 结构保留重点 |
| --- | --- | --- |
| HTML | 原 HTML + document + blocks | 标题层级、段落、列表、表格、附件、DOM/段落位置 |
| 文本型 PDF | 原 PDF + document + blocks | 页码、段落、标题、表格、脚注/页眉页脚识别 |
| 扫描 PDF/图片 | 原文件 + OCR/视觉解析后的 document + blocks | 页码、OCR 文本、置信度；必须标 extraction_method |
| DOC/DOCX | 原文件 + document + blocks | 标题样式、段落、表格、列表、脚注（按需） |
| XLS/XLSX/CSV | 原文件 + document/records + blocks | sheet 名、表头、行号、单元格结构、单位 |
| JSON/XML/API | 原响应 + document/records | 字段结构、分页、请求参数、原始 JSON/XML |

## B076

九、正文清洗要求

## B077

清洗只去除与正文无关的噪声，不得为了“让文本更像知识”而改写、总结或重排事实内容。

## B078

| 处理项 | 要求 |
| --- | --- |
| 导航/广告/推荐 | 删除网站导航、版权栏、相关推荐、广告、评论等非正文噪声。 |
| 标题与正文 | 主标题必须单独保留；小标题保留为 heading block。 |
| 段落顺序 | 严格保持原文顺序。 |
| 列表 | 保留列表项顺序，不全部拼成一个段落。 |
| 表格 | 优先保留行列结构；不得只丢成无结构长文本。 |
| 页码 | PDF/扫描件应尽量保留页码映射。 |
| 法规条款 | 保留章/节/条/款/项编号。 |
| 日期 | 标准字段统一 YYYY-MM-DD；无法确定时保留 raw_date。 |
| URL | 保存 source_url 和 canonical_url；移除明显追踪参数。 |
| 语言 | 识别 zh/en/hi/mixed 等，但不翻译原文。 |
| 改写/摘要 | 禁止；本阶段只做抽取与规范化。 |

## B080

十、表格和结构化数据

## B081

Excel、网页表格、API 记录等不应简单拼成纯文本。后续 RAG 可能需要按行、按实体、按统计项切片，因此应尽量保留原始结构。

## B082

| {  "block_id":"IN_CENSUS_DOC001_B0012",  "doc_id":"IN_CENSUS_DOC001",  "order":12,  "block_type":"table",  "text":"District \| Language \| Population ...",  "structured_data":{    "columns":["District","Language","Population"],    "rows":[      ["A","Hindi",1234],      ["A","English",456]    ]  },  "source_anchor":{"sheet":"Table C-16","range":"A1:C3"},  "extraction_method":"xlsx"} |
| --- |

## B084

十一、去重、版本与增量更新

## B085

| 能力 | 要求 |
| --- | --- |
| URL 去重 | canonical_url 去追踪参数；同一 URL 在未到更新时间时不重复抓。 |
| 原始文件去重 | SHA-256 相同则标记重复关系，不重复保存无意义副本。 |
| 正文近似去重 | 识别转载、镜像、重复栏目；保留来源关系。 |
| 版本管理 | 法规/条约/政策正文变化时不得覆盖旧数据；新旧版本均保留。 |
| 增量抓取 | 新闻按新发布日期抓；法规定期检查状态和哈希；统计资料按版本/年份更新。 |
| 删除/失效 | 若页面下线，不直接删除历史数据，记录 source_status=offline 或失效状态。 |

## B087

十二、失败数据与日志

## B088

任何失败都必须可复现、可补抓。failed_records.jsonl 至少记录 source_id、url、时间、阶段、错误类型、错误信息、重试次数和后续处理动作。

## B089

| {"source_id":"CN_MFA","url":"https://...","time":"2026-09-07T11:05:00+08:00","stage":"parse","error_type":"parse_error","message":"正文节点未识别","retry_count":0,"final_action":"manual_review"} |
| --- |

## B091

十三、质量验收要求

## B092

| 指标 | 建议验收口径 |
| --- | --- |
| 原始资源可追溯 | documents/blocks 100% 可回到 source_url、raw_path 和 crawl_manifest。 |
| 原始文件留存 | 所有成功抓取的网页/附件均保留原格式。 |
| 正文完整性 | 正文型文档抽样对比原站，标题、正文、列表、表格不能明显缺失。 |
| 结构完整性 | 长文档至少能恢复标题层级、段落顺序；PDF 能恢复页码；法规能恢复条款。 |
| JSONL 合规 | UTF-8，一行一个合法 JSON 对象；所有必填字段通过 schema 校验。 |
| 重复控制 | 相同文件/相同正文不得无控制重复入库。 |
| 版本不覆盖 | 历史版本必须保留。 |
| 失败可对账 | 失败 URL 必须进入 failed_records.jsonl。 |
| 不提前切片 | 不得出现按 token 数切分或语义合并后的 RAG chunk。 |

## B094

十四、推荐程序目录

## B095

| crawler/├── config/│   └── sources.yaml├── discover/│   ├── list_page.py│   ├── search_page.py│   ├── sitemap.py│   └── api_discovery.py├── fetch/│   ├── http_client.py│   └── downloader.py├── parser/│   ├── html_parser.py│   ├── pdf_parser.py│   ├── docx_parser.py│   ├── xlsx_parser.py│   └── api_parser.py├── normalize/│   ├── document_schema.py│   ├── block_schema.py│   └── metadata_normalizer.py├── dedup/├── output/│   ├── raw_store.py│   ├── manifest_writer.py│   ├── documents_writer.py│   └── blocks_writer.py└── monitor/    ├── logger.py    └── metrics.py |
| --- |

## B097

十五、最终格式口径

## B098

本阶段的最终结果不是 RAG chunk，而是两层数据：第一层是原始资源保真归档；第二层是统一的“文档 + 原始结构块”数据。后续 RAG 团队直接使用 documents.jsonl 和 blocks.jsonl 做自己的切片、向量化、索引和检索优化即可，无需重新爬取和重新恢复文档结构。

## B099

| 层级 | 必须格式 | 说明 |
| --- | --- | --- |
| 原始层 | HTML/PDF/DOCX/XLSX/JSON/XML/图片原格式 | 保真，不转换替代原文件 |
| 抓取账本 | crawl_manifest.jsonl | 记录 URL、抓取时间、状态、哈希、raw_path |
| 文档层 | documents.jsonl | 每行一份完整逻辑文档，保留 full_text |
| 结构层 | blocks.jsonl | 每行一个原始结构单元，方便后续任意切片 |
| 失败层 | failed_records.jsonl | 失败对账与补抓 |
| 后续 RAG 层 | 本阶段不交付 | 不生成 chunk、Embedding、向量索引 |
