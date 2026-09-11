# T004—T009 采集闭环实现记录

日期：2026-09-11｜执行：Codex｜状态：T004—T009 的实现与离线验证完成；真实站点接入仍待 Q12/Q13（T026），
数据契约冻结仍待 T001。

## 交付模块

| 任务 | 路径 | 说明 |
| --- | --- | --- |
| T004 | `src/crawler/config/registry.py`、`config/sources.yaml` | 来源配置校验（必填、域名、路径、频率、超时）、注册表、访问边界判定、配置摘要留痕 |
| T005 | `src/crawler/discover/discoverer.py` | 栏目分页、搜索、sitemap、API、附件发现；越界链接记录跳过原因；关键词只用于检索与账本 |
| T006 | `src/crawler/fetch/http_client.py`、`fetch/downloader.py`、`pipeline.py` | 手动逐跳重定向边界检查、限速、退避重试、429 Retry-After、流式下载与大小上限；来源级速率/超时/重试上限生效（见下节）；正文分页与接口正文还原（见下节） |
| T007 | `src/crawler/output/raw_store.py`、`output/manifest_writer.py` | 临时文件加原子改名、字节哈希、相同字节复用、路径越界拒绝；账本校验原件存在且哈希一致 |
| T008 | `src/crawler/parser/html_parser.py` | DOM 顺序块抽取（标题、段落、列表、表格）、锚点、元数据与发布日期、编码识别；不翻译不改写 |
| T009 | `src/crawler/normalize/`、`output/documents_writer.py`、`pipeline.py` | 文档契约字段与状态、块契约、跨文件校验后成组提交、单页到附件的最小闭环编排、失败账 |

## 设计补充（评审候选，未改变 Q 项状态）

- `document.metadata_missing`：记录缺失元数据字段名（Q06 候选实现）；`parse_status` 原记 `complete`/`partial`，
  T019 契约复核后改为 `ok`/`partial`/`failed`（与 `contracts/document.schema.json` 一致）。
- `source.entry_urls`、`source.search_url_template`：入口与搜索模板写入来源配置；已同步到
  `contracts/source-registry.schema.json` 的可选字段，真实取值待 Q12/Q13 逐站核验。
- 块 `order` 从 0 连续递增、`block_id` 形如 `<doc_id>_B0000`（Q09 候选）。
- `document_type` 暂取来源 `parser_type` 或 `html_page`；`crawl_ids` 记录本次抓取（Q03 候选）。
- 采集阶段只写 `raw/`、`manifests/`、`normalized/`；无 RAG 派生目录（S1 采集阶段边界）。

## 来源级请求参数（NFR-003 增补，2026-09-11）

原实现把来源配置里的 `request_rate_per_second`、`connect_timeout_seconds`、
`read_timeout_seconds`、`max_retries` 只做解析校验，实际请求一律使用调用方传入的
`FetchLimits`，与 NFR-003“按站点调整”不符。现改为：

- `FetchLimits.from_source(source)`：按来源配置生成限速与超时，未登记项沿用 base；
- `HttpClient.limits_for(url, source_id)`：调用方未显式传入 `FetchLimits` 时按来源解析
  （生产路径 `CrawlPipeline(registry, data_dir)` 即此行为）；显式传入时以显式值为准，
  离线用例因此不受来源配置影响；
- 重定向逐跳、robots.txt 获取同样走对应来源的限速与超时；`max_redirects` 与退避基数
  仍取客户端级配置（来源契约未登记这两项）。

验证：`tests/test_fetch.py` 新增 4 项（来源限速 0.5 req/s → 间隔 2.0s、显式 limits 覆盖来源配置、
连接/读取超时 (3.0, 7.0) 进入请求、来源 max_retries=0 时 attempts=1 不重试），
`tests/test_pipeline.py` 新增 1 项（未注入 http 的生产路径按来源解析限速与超时）；
另按 AT-023 记录 `request_controls`（来源速率、来源声明的 `max_concurrency`、生效并发 1 与说明，速率与并发分别建模、不互相换算），`tests/test_pipeline.py` 再加 1 项；全量 310 passed（真实页面缺陷修复后新增 2 项、T026 适配规则 15 项及配置/契约漂移 1 项，见下节与 [logs/t008-cn04-defect-fix.txt](logs/t008-cn04-defect-fix.txt)、[logs/t026-adapter-mechanism.txt](logs/t026-adapter-mechanism.txt)）。

## 正文分页与接口正文还原（FR-005 增补，2026-09-11）

原实现只还原“点击展开”的正文；FR-005 还要求还原分页与接口加载的正文。本次补齐两条确定性路径，
不引入浏览器或脚本执行（与 AT-003“不依赖浏览器作为默认”一致）：

- 正文分页：`html_parser` 在内容区（`main`/`article`/`body`）识别下一页链接——`rel=next` 或明确
  翻页文案（下一页/下一部分/下页/后一页/next），head 中的站外“下一篇”推荐不参与；纯翻页控件
  （段落只含该链接）不进入正文块。管线逐页获取，上限 5 个部分（含首页）、循环检测、越界与
  robots 拒绝即停；每部分原件独立归档、按 `discovery_method=pagination` 记账，块按部分顺序合并，
  `page_no` 取部分序号（1..n），文档 `crawl_ids` 覆盖各附加部分。
- 接口正文：页面以 `<link rel="alternate" type="application/json" href=...>` 声明正文档端点；
  管线获取该 JSON（归档、`discovery_method=api` 记账）后按候选字段取正文（body/content/body_html/
  html/full_text/text，含 data/result/article 一层嵌套）：HTML 片段走同一 HTML 解析器，纯文本保留为
  单一文本块。未声明端点或响应无候选字段时不猜测、不合成正文。
- 失败处置：任一附加部分获取或解析失败，写入失败账（stage=fetch/parse），`metadata_missing` 记录
  原因标记（`pagination_*` / `body_api_*`），文档 `parse_status=partial`；已成功部分保留，不静默丢弃。

验证（`tests/acceptance/test_collection_acceptance.py` AT-005 两项 + `tests/test_html_parser.py` 5 项）：
三页正文按 1→2→3 顺序合并、页码 1,1,2,2,3,3、翻页控件不入正文；接口正文追加在页面自身正文之后；
账本含 2 条 `pagination` 与 1 条 `api` 记录且原件哈希一致；对账与追溯校验通过；删除第三部分后
保留前两部分、标 `partial` 并写失败账。夹具：`tests/fixtures/site/detail_paged_1..3.html`、
`body_modes_index.html`、`api_body_page.html`、`api_body.json`。

站点专属的分页/接口形态（真实 DOM 选择器、接口字段名）仍属 T026 逐站核验，Q12/Q13 未决。

## robots.txt 规则执行（FR-001 / S3 C02 增补，2026-09-11）

原实现只登记 `source.robots_policy` 文本，请求前并不执行规则，与 S3 C02“遵守 robots.txt、站点条款和访问控制”
不符。本次补上通用执行层；它不依赖任何 Q 项决策，逐站规则核验与条款记录仍属 T026。

- `src/crawler/fetch/robots.py`：RFC 9309 可用子集解析——User-agent 组匹配（具体 token 优先于 `*`）、
  Allow/Disallow 最长匹配、同长度 Allow 优先、`*` 与 `$` 扩展、空 Disallow 放行；
  `rules_for_unavailable` 规定 4xx（含 404/410）视为无规则放行，5xx 与网络失败保守拒绝。
- `src/crawler/fetch/http_client.py`：`robots=True` 为默认值；按主机缓存一次；robots.txt 走同一客户端，
  因此同受限速与访问边界约束，不写账本、不计入 resources；拒绝抛 `RobotsDisallowed`（不可重试）。
- `src/crawler/pipeline.py`：被拒页面记入 `report.skipped`（原因前缀 `robots_disallowed:`）而不是失败账；
  被拒附件写失败账 `error_type=robots_disallowed`、`final_action=skip`、`retry_count=0`；跳过原因进入
  `skipped_by_reason` 并参与 metrics 对账。`resume_failures` 补抓遇到 robots 拒绝时，对该失败追加
  `skip` 处置行（保留历史失败、不再进入补抓计划），补抓报告单列 `skipped`。
- 夹具与用例：`tests/fixtures/site/robots.txt`（`Disallow: /private/` 加更长的 `Allow: /private/public-note.html`）、
  `robots_linked.html`、`robots_detail.html`、`private/` 样本；`tests/test_robots.py` 12 项；
  夹具运行对账 `reconciliation_ok=True`。原始输出见 [logs/t004-robots.txt](logs/t004-robots.txt)。
- 依据：[RFC 9309](https://www.rfc-editor.org/rfc/rfc9309.html)。
- 逐站 robots/使用条款核验结果仍按 T026 记录到来源注册表；本次只实现协议层执行，不代替逐站核验。

## 验证

```bash
uv run --locked pytest -q          # 118 passed（T004—T009 当时）
```

覆盖要点：

- 访问边界：未登记域、相似域、非 http(s)、禁用来源、被阻路径、逐跳重定向越界全部拒绝；
  本地夹具站点含一个越界链接，发现阶段记录跳过原因而不请求。
- 获取：302 跟随后记录最终 URL 与跳转链；500 重试后成功；重试耗尽报告可重试失败；
  429 遵守 Retry-After；读取超时退避重试成功、连接超时耗尽后按 `retryable=True` 上报且退避按指数
  增长（`tests/test_fetch.py`，AT-023 同步覆盖）；永久 404 不重试；限速按域生效；下载字节与源文件 SHA-256 一致；
  附件大小上限与 `Content-Disposition` 文件名解析。
- 归档：raw_path 形如 `raw/<source>/<date>/<kind>/<name>`；相同字节复用同一原件；
  不同字节保留副本；路径穿越、非法片段与符号链接越界被拒绝；中断写入不留半成品与临时文件。
- 账本：原件缺失或字节被改动时拒绝写入；成功记录可由 raw_path 定位且哈希一致。
- 解析与标准化：块顺序与原文一致，表格保留结构；标题或正文缺失时为 partial 并记录缺失字段；
  块 order 连续、引用有效，校验失败时成组提交不落盘。
- 闭环：两个 HTML 页加一个成功附件、一个失败附件形成原件、账本、文档、块的可追溯链；
  失败附件进入失败账且不伪造 raw_path；关键词只出现在账本与发现策略中，不生成分类结论。

## 与验收用例的关系

AT-001—AT-009 的样本范围已有对应自动化检查（本地夹具、不访问真实站点），但正式验收判定、
真实来源核验与质量阈值仍按 acceptance.md 在 T019/T026 执行；在此之前 AT 用例保持 NOT RUN。

## 未完成范围

- 真实来源接入、逐站 DOM/接口核验与 10 词验证属 T026，前置 Q12/Q13。
- PDF/OCR/Office/CSV/JSON/XML 解析属 T011/T012；去重版本、增量与日志指标属 T014—T017；
  交付口径与全量校验属 T018/T019。

## 真实页面缺陷修复：空标题块（2026-09-11 增补）

第四轮真实站点核验中，`https://www.gov.cn/` 的页面在标准化阶段失败
（`normalization_error：非表格块缺少 text`），失败账与原件均保留。离线复现确认根因：页面上存在内容为空的
装饰性 `<h2>`，`parse_html` 的标题分支没有像 `p`/`li` 那样过滤空文本，产出的空 `heading` 块违反块契约。
修复为“空标题不产出块 + 文档标题取首个非空标题”，并补回归用例
`tests/test_html_parser.py::test_empty_headings_are_skipped_and_do_not_blank_the_title`。
同一原件经 `resume_failures('CN-04')` 本地重解析补全（0 个新请求，1 文档/145 块），原件字节与 sha256 未变。
完整过程见 [logs/t008-cn04-defect-fix.txt](logs/t008-cn04-defect-fix.txt)。

残留观察（属 T026 适配器范围，不在本轮改动）：gov.cn 首页的通用抽取仍以导航项开头，
该类站点需要栏目级内容选择器。
