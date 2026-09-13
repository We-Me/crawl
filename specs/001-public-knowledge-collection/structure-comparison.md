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
| document | doc_id/source_id/source_name/source_url/title/full_text/language/document_type/raw_path/sha256/crawl_time/extraction_method/parse_status | 基础字段保留；实现使用 crawl_ids、metadata_missing 等补充关系/缺失说明，content_hash 用于正文指纹；不能冒称 S1 原字段表全部规定 |
| document.sha256 | S1 允许正文或原文件哈希 | 当前选择原件哈希，并区分正文 content_hash；属于原文允许范围内的具体工程语义，应在兼容规则中明确 |
| block | block_id/doc_id/order/block_type/extraction_method，以及条件 text/结构化数据、定位等 | 实现将 order 固定从 0 连续递增、block_id 采用 doc_id 加序号；原文允许从 0 或 1 开始，当前是具体约定 |
| attachment | 原文要求身份、文件名、类型、URL、路径、哈希等信息 | 独立 attachment schema 细化 status、crawl_id/doc_id 等关系；不是新增必交 attachment.jsonl 文件 |
| failure | source_id/url/time/stage/error_type/message/retry_count/final_action | 保留核心字段，恢复关联另有工程表达；成功补抓不抹去原失败 |
| source registry | S1/S2 来源配置建议 | config/sources.yaml 与 source-registry schema 整合配置及适配规则；不是采集正文或额外知识库 |

此表描述关键兼容差异，完整字段表见 [data-model.md](data-model.md)，机器契约见 [contracts/README.md](contracts/README.md)。本轮“按文档冻结”确认原文的基础字段、必填层级与含义；不直接提升可选字段为必填，不把全部候选扩展自动认定为原文要求。现有扩展先保留并登记，不能未经迁移方案删除；新增 dummy 与日期参数不应随意改变 JSONL 格式。

## 项目目录与数据目录不同

docs/ 存放四份需求输入，specs/ 与 .specify/ 管理 SDD；src/crawler/ 是业务代码，tests/、tools/ 为验证和辅助工具，templates/uv/ 为环境模板。这些属于工程组织，不能算成 raw 成果的额外业务目录。

src/crawler/contracts/ 是规格中六份 Schema 的随包副本，用于安装后脱离源码目录运行；通过 tools/sync_contracts.py 保持一致。它没有新增第七种业务数据契约。dist/ 是构建产物目录，.venv/ 是本地环境，均不是规范化采集成果，也不随 Git 默认提交。

结论：数据根的主要组织已与原文 §4.2 一致。新增主要为运行状态/指标历史文件、工程管理目录及随包契约副本；不存在因当前分块决定而必须新增 chunks/ 或 RAG 目录的要求。
