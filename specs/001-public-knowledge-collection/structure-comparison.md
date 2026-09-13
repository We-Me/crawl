# 当前结构与原文结构对照

日期：2026-09-13。检查基线：e2b16c8。依据：S1《一般爬虫采集与标准化数据交付需求规范》§4.2、§5—7、§12—13，data-model.md，以及源码 DeliveryLayout / RawStore / document_schema / block_schema。下列是源码定义的布局，不表示当前 Windows 工作副本已有实际采集数据。

## 数据目录：四个主要子目录本来就在原文中

```text
data/                              # 开发默认；CRAWL_DATA_DIR 可更换数据根
├── raw/<source_id>/<抓取日期>/<格式>/原件
├── manifests/
│   ├── crawl_manifest.jsonl
│   ├── failed_records.jsonl
│   └── incremental_state.json     # 实现新增：增量/恢复运行状态
├── normalized/
│   ├── documents.jsonl
│   └── blocks.jsonl
└── logs/
    ├── crawler.log
    ├── metrics.json
    └── metrics_history.jsonl      # 实现新增：指标历史
```

| 项目 | S1 原文 | 当前实现 | 结论 |
| --- | --- | --- | --- |
| 四个子目录 | §4.2 明列 raw、manifests、normalized、logs | 同名组织 | 没有额外包一层；manifests/normalized 不是后加需求 |
| raw 层级 | 来源/日期/格式，来源示例 CN_MFA、IN_MEA | source_id/抓取日期/kind，日期不是内容发布日期 | 层级一致；具体来源 ID 是登记值，不要求照抄示例 |
| 六项成果 | raw、抓取账本、文档、块、失败记录、日志/质量统计 | 对应四目录内原件与文件 | 原有成果没有被额外运行状态文件替代 |
| 增量状态 | 未指定 incremental_state.json 文件名 | manifests/incremental_state.json | 工程辅助文件；不是新的业务文档类型 |
| 指标历史 | 示例包含 metrics.json | 另有 logs/metrics_history.jsonl | 工程辅助文件；保留单次统计并记录历史 |
| 路径根 | 原文示例 data/，raw_path 示例为 raw/... | 开发与 src 同级 data/；环境变量配置；raw_path 相对数据根 | 来自用户此前补充，迁移时不写死绝对路径 |

源码依据：[layout.py](../../src/crawler/output/layout.py)、[raw_store.py](../../src/crawler/output/raw_store.py)。

## 数据字段：基础字段与实现扩展分开冻结

| 对象 | 原文基础要求 | 当前使用情况与差异 |
| --- | --- | --- |
| manifest | crawl_id/source_id/requested_url/final_url/crawl_time/http_status/content_type/raw_path/sha256/discovery_method；搜索 keyword 条件必填 | 基础字段保留，sha256 为原件字节哈希；恢复或额外字段不是原文基础必填 |
| manifest.discovery_method | S1 列举 list/search/sitemap/api/attachment/manual | 实现另用 `pagination`（正文分页部分）与 `retry`（补抓重取）并写入账本；契约枚举收录这两个候选扩展并注明待 Q12/Q15 冻结，不改名规避 |
| document | doc_id/source_id/source_name/source_url/title/full_text/language/document_type/raw_path/sha256/crawl_time/extraction_method/parse_status | 基础字段保留；实现使用 crawl_ids、metadata_missing 等补充关系/缺失说明，content_hash 用于正文指纹；不能冒称 S1 原字段表全部规定 |
| document.sha256 | S1 允许正文或原文件哈希 | 当前选择原件哈希，并区分正文 content_hash；属于原文允许范围内的具体工程语义，应在兼容规则中明确 |
| block | block_id/doc_id/order/block_type/extraction_method，以及条件 text/结构化数据、定位等 | 实现将 order 固定从 0 连续递增、block_id 采用 doc_id 加序号；原文允许从 0 或 1 开始，当前是具体约定 |
| attachment | 原文要求身份、文件名、类型、URL、路径、哈希等信息 | 独立 attachment schema 细化 status、crawl_id/doc_id 等关系；不是新增必交 attachment.jsonl 文件 |
| failure | source_id/url/time/stage/error_type/message/retry_count/final_action | 保留核心字段，恢复关联另有工程表达；成功补抓不抹去原失败 |
| source registry | S1/S2 来源配置建议 | config/sources.yaml 与 source-registry schema 整合配置及适配规则；不是采集正文或额外知识库 |
| adapter.discovery | 原文未规定发现方式的表达 | 每个来源声明已实现的发现方式（`list`/`search`/`sitemap`/`api`）；未声明的方式显式记为未实现，不新增业务文档类型 |
| failure.scope_start_date | 原文失败账未规定起始日字段 | 恢复任务/失败行保留原运行起始日（可空）；属于运行范围追溯，不改变失败核心字段 |
| metrics.scope / discovery / date_decisions | 原文日志/质量统计未规定起始日与逐目标日期判定 | `logs/metrics.json` 记录起始日语义、各发现策略状态与逐目标日期判定；运行状态统计，不是新的交付成果 |
| counters.out_of_window | 原文未规定日期下界计数 | 运行计数单列“早于起始日、只留原件不产文档”的目标数；与 skipped/failures 分开 |
| 发现页归档位置 | 原文要求可核对原件与账本，未规定发现页目录 | 发现响应存 `raw/<source_id>/<YYYY-MM-DD>/discovery/`，账本沿用声明的 discovery_method；发现页不生成 normalized 文档 |
| attachment.status | 原文列出附件信息项，未给状态枚举 | 契约扩展为 `downloaded`/`failed`/`boundary_rejected`/`pending`；边界拒绝与预算停止分别记录，不写成网站失败，也不借限幅宣称完整 |
| metrics.coverage | 原文未规定覆盖口径 | 运行指标分开记录主目标、附件与发现完整性；发现截断时窗口总量是未知，不把当前成功数当全站分母 |
| 待处理项与发现游标文件 | 原文数据布局未规定续接状态文件 | `manifests/pending_items.json`、`manifests/discovery_cursors.json` 属抓取行为索引，不是六项交付成果；有限预算多轮运行据此推进到未完成部分 |

此表描述关键兼容差异，完整字段表见 [data-model.md](data-model.md)，机器契约见 [contracts/README.md](contracts/README.md)。本轮“按文档冻结”确认原文的基础字段、必填层级与含义；不直接提升可选字段为必填，不把全部候选扩展自动认定为原文要求。现有扩展先保留并登记，不能未经迁移方案删除；新增 dummy 与日期参数不应随意改变 JSONL 格式。

## 项目目录与数据目录不同

docs/ 存放四份需求输入，specs/ 与 .specify/ 管理 SDD；src/crawler/ 是业务代码，tests/、tools/ 为验证和辅助工具，templates/uv/ 为环境模板。这些属于工程组织，不能算成 raw 成果的额外业务目录。

src/crawler/contracts/ 是规格中六份 Schema 的随包副本，用于安装后脱离源码目录运行；通过 tools/sync_contracts.py 保持一致。它没有新增第七种业务数据契约。dist/ 是构建产物目录，.venv/ 是本地环境，均不是规范化采集成果，也不随 Git 默认提交。

以上 `scope`/`discovery`/`date_decisions`/`out_of_window` 与 `adapter.discovery` 均为 2026-09-13 新增的**运行期字段**，
只出现在运行指标、失败账与来源配置中，不修改 `documents.jsonl`/`blocks.jsonl` 的基础字段与必填层级；
`documents.jsonl`、`blocks.jsonl` 的格式未因起始日期与分块实现改变（正文块仍走原有 block 契约）。

结论：数据根的主要组织已与原文 §4.2 一致。新增主要为运行状态/指标历史文件、工程管理目录及随包契约副本；不存在因当前分块决定而必须新增 chunks/ 或 RAG 目录的要求。

## 61e34d8 契约差异补充

manifest.discovery_method 的机器枚举已加入 pagination/retry，规格与随包副本均有；它们分别用于正文分页与补抓，是实现扩展，不是 S1 原枚举。因此不能笼统表述该提交“未改动数据契约”。原文基础字段含义继续保留，新增归档/进度字段如有必要须另记版本与兼容性；本轮未更改 Schema。

## 阶段五差异补充（2026-09-13）

本轮唯一改动的机器契约是 `attachment.schema.json`：`status` 枚举由 `downloaded`/`failed` 扩展为
`downloaded`/`failed`/`boundary_rejected`/`pending`，规格契约与随包副本同步（`tools/sync_contracts.py --check` 通过）。
其余变化都不改 Schema：

- `crawl_manifest.jsonl` 新增的是**行**（发现页成功响应也归档一行，`discovery_method` 沿用 list/search/sitemap/api），
  不是新字段；`counters.resources` 与账本追加行同口径，`reconciliation` 按原规则核对。
- 运行期新增 `metrics.coverage`（主目标/附件/发现完整性/待处理合计）与 `stop.unprocessed` 口径调整；
  只出现在 `logs/metrics.json` 与命令报告，不进入 `documents.jsonl`/`blocks.jsonl`。
- 新增运行状态文件 `manifests/pending_items.json`（待处理目标/附件）与 `manifests/discovery_cursors.json`
  （发现分页游标）；它们是抓取行为索引，不属于六项交付成果，`crawl check` 不要求也不把它们当成果。
- 删除与覆盖规则不变：已归档原件不被后续成功运行覆盖（同路径不同字节时另存 `-<sha8>` 后缀）；
  失败历史只追加，成功恢复保留前后关联。

## 阶段五第二轮差异补充（2026-09-13，发现分页与附件失败）

本轮改动的机器契约仍是 `source-registry.schema.json`：`adapter` 新增
`pagination_merge_entry_params`（布尔；需与 `pagination_selector` 同时配置），规格契约与随包副本同步
（`tools/sync_contracts.py --check` 通过）。它的含义是“站点分页控件省略入口参数时，下一页 URL 由入口 URL
派生（路径与入口参数沿用入口，控件显式给出的参数覆盖）”，用于 IN-02 端点（控件只带 `page=N`，缺
`PageSize/sortBy` 返回空壳）。其余变化不改 Schema：

- `adapter.pagination_selector` 的取值从“仅发现阶段”扩展到“发现阶段 + 正文分页”：`parse_html` 现在接受
  该规则并据此跟随正文下一页；未配置的来源保持原通用行为。
- 发现结果的 `note` 可能包含“通用列表范围未取到目标，已按整文档兜底（结构不完整）：<url>”：
  这是既有 text 字段的内容，不是新字段；记录 CN-04 双 `<html>` 页被范围漏采后按整文档兜底的事实。
- 流式读取中断（附件下载读取超时/连接重置）由 `FetchError` 表达，走既有失败账与附件 `failed` 状态，
  不新增字段；`documents.jsonl`/`blocks.jsonl` 基础格式未变。

## 阶段五差异补充（2026-09-13，已完成入口的增量核对）

不改 Schema：新增的发现终止原因与游标 note 变化都在既有 `text`/`note` 字段内表达。

- 新的发现终止原因 `incremental_head_checked`（`complete=true`）：入口此前已遍历完成、且历史遍历页数超过
  单轮页数上限时，本轮只从入口向后核对到首个全为已登记目标的页为止，不重取历史覆盖页；目的入口是
  IN-02（433 页 / 单轮 5 页）与 CN-02 关键词检索（13 页 / 单轮 5 页）。页数上限内可整入口复核的入口行为不变。
- `manifests/discovery_cursors.json` 的 note 在该情形下写为
  `incremental_head_checked: …；上次终点 <原终止原因>`：原遍历的页数/目标计数与终点原因保留（不累计、
  不改写成截断），`next_url=null`、`state=completed`。
- `manifests/pending_items.json` 与 `crawl_manifest.jsonl` 基础格式未变；增量核对不产出 documents/blocks，
  也不把已登记目标再标 refresh（仅当入口页出现新目标时，该页目标照常入队/复查）。
