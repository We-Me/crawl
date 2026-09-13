# 阶段五 raw 完整性：统一归档、分页覆盖、附件闭环与多轮续接（2026-09-13）

本记录对应 [阶段五](../stage-five.md) 的 S5-01、S5-03、S5-04 与 S5-06 工程实施，
关联 T005/T006/T007/T015/T016/T026/T027。它不把任何 AT 用例或 T019/T026/T027 总体验收
改为通过，也不代表来源启用范围、发布或后处理范围发生变化。

代码基线：`de5d532`（本轮改动未提交前的阶段五入口提交）。验证环境：Python 3.9.25（uv），
本地回环夹具站点（离线、固定响应），未新增真实站点请求。

## 缺口与实施对应

| 编号 | 原缺口 | 本轮实现 |
| --- | --- | --- |
| S5-01 | 发现页（列表/搜索/sitemap/发现接口）成功响应只被解析，没有统一的原件与账本留存 | `ResponseArchiver` 统一归档：发现响应先落原件、写账本，再解析；解析失败保留原件并写失败账 |
| S5-03 | 分页第二页失败仅 warning 后 break，截断/失败与“真实无下一页”混同 | 每个入口记录确切终止原因与 `complete` 标志；未翻到的页写入发现游标供下一轮续接 |
| S5-04 | 附件只区分下载成功/失败，规则排除、边界拒绝与预算中断没有闭环 | 附件分成功/失败/边界拒绝/规则排除/重复/待处理；预算中断的附件进入待处理存储并在下一轮续传 |
| S5-06 | 预算停止后重跑从入口重新开始，未处理计数不代表真实待处理量 | 待处理项存储 + 发现游标；发现到的目标全部入队，多轮有限预算向前推进；覆盖口径随报告输出 |
| S5-02 | 受限来源（robots 拒绝、508、TLS 失败、域名别名） | 本轮不新发请求：沿用第 37 轮复核与历史记录，见下方“受限来源”一节 |

## 受限来源（S5-02）：本轮结论

本轮没有新的外部线索，按“没有条件变化不反复探测”处理，只复用已有证据，不重跑受限来源请求：

| 类别 | 来源 | 已有证据结论 | 需要的下一步 |
| --- | --- | --- | --- |
| 站点规则明确拒绝 | CN-03（robots `Disallow /`） | 只取 robots.txt 后停采并登记 | 站点许可或公开允许通道（外部决定，Q12） |
| HTTP 508 稳定复现 | CN-05/06/07 | 第 37 轮三轮复核均 508，按不可用保守拒绝 | 可达性确认或允许方式（外部决定，Q12） |
| TLS/信任链失败 | IN-04/07/08/09 | robots 获取失败，curl `verify=1`/`verify=20` 复现 | 目标环境信任链/代理核对或站点侧确认；不关闭证书校验 |
| 域名别名 | IN-03、CN-01 旧域 | 站内链接指向别名域，按来源边界跳过、只登记 | 归属与对应规则的精确配置决定（Q12） |

工程侧可继续的部分（别名归属明确后的精确域名配置、CN-04 允许接口的调查与适配）不需要新增决定；
在归属或许可明确前保持对应路径暂停，不构造未公开接口、不使用通配域名。

## 变更的可观察行为

- **统一归档（S5-01）**：列表/搜索页、sitemap、发现接口、详情正文分页、正文接口与附件
  成功响应共用同一归档路径，先写原件与账本、后解析；`raw/<source>/<date>/discovery/` 保存发现响应，
  `counters.resources` 与账本追加行同口径。发现页不生成 normalized 文档，也不伪造成详情页。
- **终止原因（S5-03）**：每个入口的遍历结束都记录 `stop` 与 `complete`：
  `end_of_pages`（站点/规则终点）、`pagination_control_missing`、`max_pages_reached`、
  `max_items_reached`、`request_failed`、`budget_stop`、`loop_detected`、`access_denied`、
  `selector_miss`、`sitemap_index_not_expanded`、`date_scoped_query`、`parse_error`。
  截断或失败时发现策略状态为 `partial`/`parse_error`，不冒充 `ok`/`zero_results`。
- **发现游标（S5-03/S5-06）**：`manifests/discovery_cursors.json` 按“来源 + 方式 + 入口 + 运行范围”
  保存下一页位置；站点末页/规则终点置 `completed`，上限、预算、请求失败与循环保持 `active`
  并指向尚未取得的页。游标只决定从哪一页继续，不放宽 robots、边界、限速与预算。
- **附件闭环（S5-04）**：附件状态为 `downloaded`/`failed`/`boundary_rejected`/`pending`；
  规则排除按 `extension_not_declared:<ext>` 与 `adapter_pattern:<ext>` 聚合计数（不下载、不扩范围）；
  robots 拒绝记 `boundary_rejected` 并进 skipped，不写失败账；同页重复候选只下载一次并单独计数。
- **多轮续接（S5-06）**：`manifests/pending_items.json` 保存目标与附件的待处理状态
  （pending → processed/failed/skipped；已成功项重新发现时标记 refresh 复查）。
  处理顺序为先 pending（按入队序号）、后 refresh（按上次尝试时间），受 `--max-items` 限制。
  预算停止的目标保持 pending，未尝试的附件连同母文档 `doc_id`/`referrer_url` 入队，下一轮续传。
- **覆盖报告**：`collect` 输出与 `--json` 增加 `coverage`（targets/attachments/discovery/queue/
  pending_total），`logs/metrics.json` 增加同口径 `coverage` 与说明；`stop.unprocessed` 改为
  待处理项合计，不再只等于本轮已选主目标数。发现截断或仍有待处理时运行状态为 `partial`/`stopped`，
  不报 `ok`（未完成不冒充完成）。
- **预算按次运行生效**：`collect`/`resume_failures` 每次运行以本次传入的预算为准；
  未传预算的运行不受上一轮遗留的有限预算约束（这是有限预算分轮续作的前提，见限制一节）。

## 实现位置

| 文件 | 内容 |
| --- | --- |
| `src/crawler/output/archive.py` | `ResponseArchiver`、`ArchivedResponse`：原件 + 账本 + crawl_id 序号，同一响应对象不重复写账 |
| `src/crawler/discover/discoverer.py` | 发现响应先归档再解析；`DiscoveryStop` 与终止原因；发现游标续接；附件规则排除与重复计数 |
| `src/crawler/discover/strategies.py` | `partial`/`parse_error` 状态与 `complete` 传播；`summarize_discovery` 增加完整性 |
| `src/crawler/schedule/pending.py` | `PendingStore`：待处理项入队、处置、计数与候选排序（JSON 原子写入） |
| `src/crawler/schedule/cursor.py` | `DiscoveryCursorStore`：发现游标读写与累计页数/目标数 |
| `src/crawler/pipeline.py` | 统一归档装配；发现预览入队与候选处理；附件闭环；覆盖口径与报告 |
| `src/crawler/monitor/metrics.py` | `coverage` 指标与覆盖/待处理/发现未完整说明 |
| `src/crawler/cli.py` | `coverage` 进入 JSON 与文本报告 |
| `src/crawler/contracts/attachment.schema.json`、`specs/.../contracts/attachment.schema.json` | 附件状态枚举新增 `boundary_rejected`、`pending`（`tools/sync_contracts.py` 同步，`--check` 通过） |

## 验证（离线夹具，最小必要集合）

新增 13 项用例（三个专题文件 + 1 项指标状态用例；本地回环网点、固定响应，不发真实站点请求）：

| 用例文件 | 覆盖 | 结果 |
| --- | --- | --- |
| `tests/test_discovery_archive.py`（4 项） | 列表/搜索/sitemap/接口响应先归档再解析；解析失败保留原件与失败账；重复请求身份不同、`raw_path` 复用；同一响应对象不双重写账 | 通过 |
| `tests/test_pagination_coverage.py`（5 项） | 后续页失败→`partial` + 失败账 + 游标从失败页续接；循环检测；`max_pages` 截断后游标续接；日期限定查询；接口声明下一页 | 通过 |
| `tests/test_attachment_coverage.py`（3 项） | 规则排除与重复计数可解释；robots 边界拒绝不写失败账；预算停止登记待处理并在下一轮续传（原件 + 账本 + 母页关联） | 通过 |
| `tests/test_monitor.py::test_metrics_status_and_notes_follow_coverage` | 发现截断/仍有待处理时 `metrics.status` 不报 `ok`，覆盖口径进入 notes | 通过 |

相关既有用例同步到新契约（预期变化，不是放宽断言）：`test_pipeline.py`、`test_budget.py`
（预算停止后未处理目标/附件进待处理存储）、`test_schedule.py`（304 复查不产生新文档、
发现页另行归档）、`test_robots.py`（附件 robots 拒绝改记边界拒绝）、`test_start_date.py`、
`test_monitor.py`、`test_cli.py`（覆盖字段随报告输出）等。

全量回归：419 passed（历史 406 passed + 新增 13 项），见
[阶段五完整回归](logs/stage-five-full-pytest.txt)；`tools/sync_contracts.py --check` 通过。

## 限制与未完成

- 覆盖口径只在夹具与固定响应上验证；真实来源的列表分页、附件与续接仍按来源逐个推进，
  9/0/9/0 的样本状态与受限状态不因本记录改变，见 [十八来源状态](t026-eighteen-sources.md)。
- 发现提前截断时窗口总量仍是未知，报告按“已发现/已尝试/未处理”记录，不把当前成功数
  当全站分母；`unprocessed=0` 只说明待处理队列已清空，不等于来源已完整遍历。
- 待处理项与游标是抓取行为索引（`manifests/` 下的运行状态文件），不是六项交付成果，
  也不改变 `documents.jsonl`/`blocks.jsonl` 的基础字段。
- 预算按次运行生效意味着无预算运行不受限制；线上运行仍须显式给出预算（DEV-012）。
- S5-02 的受限来源仍等待用户侧工程条件或允许方式（Q12）；没有新线索不重复探测。
- 正式验收（T019/T026/T027）、来源启用范围、后处理与发布仍不在本轮范围。

## 复现

```bash
uv run --locked --no-python-downloads pytest -q tests/test_discovery_archive.py \
  tests/test_pagination_coverage.py tests/test_attachment_coverage.py
uv run --locked --no-python-downloads pytest -q          # 419 passed（见上方日志）
uv run --locked --no-python-downloads python tools/sync_contracts.py --check
```
