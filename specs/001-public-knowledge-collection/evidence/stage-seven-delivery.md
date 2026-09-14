# 阶段七交付证据：错误可处置性与有界闭环（2026-09-14）

本记录对应 [阶段七](../stage-seven.md) 的 S7-01（四项审查问题的最小修复）、S7-02（错误处置能力补齐）
与 S7-03（有界代表性闭环与候选回归）。它不把 T019/T026/T027 的正式验收、18 来源窗口的数据完整性
或 Q11/Q12/Q13 的业务决定改为通过；软件可交付结论与来源窗口数据完整性分开报告。

代码基线：文档基线 `0cd04e0`（阶段六收尾，任务书引用的 `1714184` 在本仓库不可解析，见阶段七说明）。
实现提交：`b779562`（S7-01）、`62d3648`（S7-02）；本文件与 `tools/closed_loop_fixture.py` 随
文档/证据提交交付（提交号以 `git log -1` 为准）。验证环境：CPython 3.9.25 + uv（`uv run`），
Linux/WSL；未重做环境选型、未重装 LibreOffice、未升级锁文件、未推送。

## 1. 复现依据（先复现，再修复）

按阶段六代码（`0cd04e0` 的 `src/`，经 `PYTHONPATH` 指向 `git archive` 副本）运行本轮新增用例：
13 项 S7-01 用例按预期失败，3 项 S7-02 CLI 用例因尚无 `failures`/`resolve` 子命令失败，合计 16 项。
其中 `test_damaged_continuation_without_state_record_is_refetched_fully` 取代阶段六用例
`test_damaged_continuation_is_refetched_fully_and_recorded`（状态语义改变后旧断言不再成立），
即本轮新增 16 项、移除 1 项；全量因此为 492 + 16 − 1 = 507。

- 原始输出（含命令与判读说明）：[stage-seven-baseline-repro.txt](logs/stage-seven-baseline-repro.txt)
  （`16 failed`；失败信息逐项对应 A/B/C/D 与 CLI 缺口，未做“测试数量”式扩充）。

## 2. S7-01：四项审查问题的修复

| 项 | 原缺陷（复现要点） | 最小修复 | 主要位置 | 提交 |
| --- | --- | --- | --- | --- |
| A | 待续进度写入队列与增量状态之间存在窗口：中断后重启，母页 304 把未完成正文当完整实体关闭目标 | 待续位置放进 `ResourceState.continuation`，与 ETag/哈希在同一次原子写入中落盘；队列无待续时按状态续作，状态损坏/不可用则完整重取并记 `continuation_state_damaged` 失败 | `pipeline.py`、`schedule/state.py` | `b779562` |
| B | 续抓母页返回成功但非 HTML 时，响应字节在归档前被丢弃 | 非 HTML 成功响应先按原件归档并写账本，再记 `continuation_not_html` 失败、保持待续；304/200-同版分支与普通路径共用同一套选择器/解析失败判定 | `pipeline.py` | `b779562` |
| C | 失败账/恢复/对账身份不一致：同 URL 跨来源、跨运行范围、跨母文档互相覆盖或误关闭；片段可独立成文 | 身份统一为（来源 + URL + stage + 原运行范围 + 母文档）；处理待处理项时失败记录取该对象入队范围；恢复/对账按同一身份匹配；片段任务回落到母文档续作 | `pipeline.py`、`monitor/failures.py`、`validate/reconcile.py` | `b779562` |
| D | 分页失败后经接口恢复时，正文/块顺序与一次成功抓取不同（接口正文被提前拼接） | 组装顺序固定为“母页 → 分页各部分 → 接口正文”，`part_refs` 重新编号；接口部分在仍有待处理接口 URL 时不重复追加 | `pipeline.py` | `b779562` |

用例（[定向输出](logs/stage-seven-targeted-pytest.txt)）：

| 项 | 用例 | 结果 |
| --- | --- | --- |
| A | `test_interrupted_progress_without_queue_continuation_resumes_not_complete`、`test_damaged_queue_continuation_resumes_from_incremental_state`、`test_damaged_continuation_without_state_record_is_refetched_fully` | 通过 |
| B | `test_continuation_mother_non_html_success_is_archived_before_failing` | 通过 |
| C | `test_open_failures_are_kept_per_source`、`test_pending_documents_ignores_other_source_open_failure`、`test_failure_records_pending_item_scope_not_run_scope`、`test_part_failure_recovery_resumes_mother_document`、`test_part_reparse_failure_does_not_create_fragment_document`、`test_cross_source_closed_row_does_not_close_other_source_item`、`test_cross_source_open_failures_are_counted_separately`、`test_cross_source_doc_id_identity_does_not_close_item` | 通过 |
| D | `test_pagination_failure_then_api_recovery_matches_single_successful_crawl`（与一次成功抓取逐块比较页码与正文） | 通过 |

## 3. S7-02：六项错误处置能力

复用既有失败账、待处理队列、`plan`/`resume`/`check` 与运行日志；未新建错误管理平台、数据库、
Web 控制台或常驻监控服务。

| 能力 | 实现与命令 | 证据 |
| --- | --- | --- |
| 错误可定位 | `crawl failures [--source/--url/--stage] [--limit] [--json]`：默认只列未关闭失败，输出身份（scope/doc/crawl）、阶段、错误类型、动作与说明 | 用例 `test_cli_failures_lists_open_and_history`；[只读评估](logs/stage-seven-readonly-check.txt) 列出 4 项未关闭失败 |
| 有限重试 | `crawl plan` 给出 refetch/reparse/manual 与 `attempt`/`not_before`；`crawl resume --max-tasks/--max-attempts/--respect-backoff` 受预算与退避约束；`manual_review` 转人工不自动补抓 | `fetch/retry.py`；闭环第 3a—3c 步；用例 `test_cli_resolve_manual_review_keeps_failure_visible` |
| 预算耗尽退出 | 退出码 3 + `stop.reason`/`stop.unprocessed`；已归档原件、账本、文档与块保留，未完成目标进入待处理队列供下轮续作 | 闭环第 1→2 步（`request_budget`，unprocessed=2；下一轮完成归档与分块） |
| 离线重解析 | `crawl resume` 对本地阶段失败按 `raw_path` 重解析，不重新下载；片段/未完成正文任务改按母文档续作 | `pipeline._recover_reparse`；用例 `test_part_reparse_failure_does_not_create_fragment_document` |
| 人工处置 | `crawl resolve --url ... --action recovered\|skip\|manual_review`（按显式身份）：身份没写全即拒绝并列出该 URL 现有身份；只追加处置行，不改写历史 | 闭环第 4b 步；用例 `test_cli_resolve_closes_failure_and_queries_result` |
| 结果查询 | `crawl failures --all` 输出历史与处置行（含动作分布），`crawl check` 对账显示未关闭失败数 | 闭环第 4c 步；[只读评估](logs/stage-seven-readonly-check.txt) |

`manual_review` 不等于 recovered：它保持未关闭并在 `failures`/`plan`/`check` 与失败计数中可见，
直到按同一身份再次处置。

## 4. S7-03：有界代表性闭环与候选回归

闭环工具：[tools/closed_loop_fixture.py](../../../tools/closed_loop_fixture.py)（开发工具，只请求
`tests/fixtures/site` 的本机回环站点，不访问真实来源；数据根写在 `--workdir`，不触碰正式 `data/`）。
一次运行的逐步原始输出：[stage-seven-closed-loop.txt](logs/stage-seven-closed-loop.txt)。

| 步骤 | 命令要点 | 退出码 | 关键结果 |
| --- | --- | --- | --- |
| 1 发现 + 预算停止 | `collect --entry-url …/index.html --max-requests 3` | 3 | `stop.reason=request_budget`、`unprocessed=2`、已归档 2 个资源 |
| 2 续作：归档与最小分块 | 同命令 `--max-items 3` | 1 | 文档 2、块 16；夹具自带的 404 附件入失败账（`doc_id` 身份可见） |
| 3a 临时失败入账 | `collect --url …/_flaky/1` | 1 | 首个 500 记入失败账 |
| 3b 补抓计划 | `plan --source TESTSRC` | 0 | `refetch=1`（临时失败）+ `manual=1`（永久 404） |
| 3c 补抓恢复 | `resume --max-tasks 5` | 1 | `recovered=1`、`failed=0`、`manual=1`（永久 4xx 转人工） |
| 4a 失败定位 | `failures --source TESTSRC` | 0 | 未关闭 1，按身份列出 |
| 4b 人工处置 | `resolve … --doc-id … --scope-start-date … --action skip` | 0 | 追加 `skip` 处置行 |
| 4c 结果查询 | `failures --url … --all` | 0 | 未关闭 0，历史含处置说明 |
| 5 对账 | `check --json` | 0 | `ok=true`，`reconcile.ok=true`（items 3/3 processed，open_failures 0） |

候选回归（实现提交 `62d3648`，其后仅新增文档/证据/工具）：

- 定向：[80 passed](logs/stage-seven-targeted-pytest.txt)
  （`test_body_continuation.py`、`test_recovery.py`、`test_validate_reconcile.py`、`test_cli.py`）；
- 全量：[507 passed](logs/stage-seven-full-pytest.txt)（阶段六基线 492 + 新增 16 − 重写 1）。

## 5. 正式数据根只读评估（不批量改写历史数据）

`data/` 17GB 真实原件只做只读校验，原始输出见 [stage-seven-readonly-check.txt](logs/stage-seven-readonly-check.txt)。

- `check`：`ok=true`；交付项齐备；schema `error_count=0`；追溯 docs 4728/4728、blocks 26774/26774（rate 1.0）；
  对账 `ok=true`（items 5392：processed 5374、skipped 18），`open_failures=4`；
  计数：manifest 12164、documents 4728、blocks 26774、failure 行 10、raw 文件 11838。
- `failures`：未关闭 4 项，均为网络阶段 `record_only`——IN-05 `ReportOutput_Current_Year_PDF_2026`（约 162 MiB PDF
  流式读取中断）与 IN-02 三份条约 PDF；历史另有 `recovered` 5 行（含第 83 轮超大附件补抓）。
- `plan`：`refetch=4`，保留各自 `scope_start_date`（如 2026-09-06），不是按 URL 全局重抓。
- 数据完整性项（非软件缺陷）：39 篇 `parse_status=partial`（其中 3 篇正文为空，其余为分页/正文未完成），
  原件与账本均保留，属来源窗口内的数据完整性问题，不影响软件交付结论。
- 文档/契约一致性（只读）：`tools/verify_sdd_documents.py` PASS（64 个文件、832 条本地链接），
  `tools/sync_contracts.py --check` 契约一致（6 个文件），见 [stage-seven-docs-check.txt](logs/stage-seven-docs-check.txt)。

## 6. 结论一：基础软件可交付（本阶段判定）

- S7-01 四项均有复现依据、最小修复、针对用例与结果，无静默丢原件、错误成功、跨对象误关闭或追溯破坏；
- S7-02 六项能力均有实际命令或用例证据，追加历史、`manual_review` 保持可见、开放错误可查询；
- S7-03 闭环一次通过（9 步，退出码 3/1/1/0/1/0/0/0/0），候选回归 507 passed；
- 交付校验覆盖 18 来源的既有成果仍为 `ok=true`，追溯 1.0，对账通过。

## 7. 结论二：来源窗口的数据完整性（不等于采集验收通过）

18 来源逐站状态见 [T026 十八来源状态记录](t026-eighteen-sources.md)、受限分因见
[S5-02](stage-five-s5-02-restricted.md)；本轮未新增线上请求（DEV-012 授权未使用），因此下表是历史窗口的如实汇总，
不是本轮新验证：

| 分类 | 数量 | 来源 | 事实与限制 |
| --- | --- | --- | --- |
| 已实现并验证（有限窗口） | 9 | CN-01、CN-02、CN-04、CN-08、IN-01、IN-02、IN-05、IN-06、IN-10 | 有原件、账本与文档；窗口内共 4728 篇文档（IN-02 4307）。9 来源有限样本通过不等于各站分页/附件/窗口完整 |
| 访问受限 | 9 | CN-03（robots `Disallow /`）、CN-05/06/07（robots 508）、IN-03（别名/主体域 robots 502）、IN-04/07/08/09（本地代理链路 TLS 中断） | 均在访问边界前停止，未绕过；触发条件（Q12/Q13、代理豁免）见上表链接 |
| 未完成 | 0 | — | 18 来源均有记录；“有记录”不等于“验收通过” |

## 8. 确需用户处理的事项

- Q12/Q13 来源决定：受限来源的允许访问方式、窗口与验收口径；CN-03 需按其规则申请或使用公开接口。
- IN-04/IN-07/IN-08/IN-09 的本机代理链路：需要在 Windows 侧代理对该域直连/豁免后，再按 ≤2 请求复核 robots。
- IN-05 超大 PDF（约 162 MiB）与 IN-02 三份条约 PDF 的网络中断属来源/链路条件，按预算重试即可，
  不需要改软件；如需更小失败面可调整附件大小上限或重试窗口（当前无此需求）。

## 9. 未做与边界

RAG、向量化/索引/检索/问答、高级后处理质量与发布部署不在本阶段范围；未新增错误管理平台/数据库/
控制台/常驻服务；未改写历史日志或批量改写已有数据；未推送远端、未部署。
