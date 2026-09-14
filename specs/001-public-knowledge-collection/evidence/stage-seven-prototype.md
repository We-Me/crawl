# 阶段七原型收尾证据：P7-01—P7-03 三项代码缺口（2026-09-14）

本记录对应 [阶段七](../stage-seven.md) 的本轮收尾：附件与正文恢复隔离（P7-01）、
人工处置与执行状态一致（P7-02）、空身份可选中（P7-03）。它不把 T019/T026/T027 的
全业务验收、18 来源窗口数据完整性或 Q11/Q12/Q13 业务决定改为通过；软件成品可交付与
特定来源窗口数据完整性分开报告，人工补齐清单见 [manual-follow-up.md](../manual-follow-up.md)。

代码基线：`97945b9`（阶段七范围收敛与外部问题转人工说明）。实现提交：`e4e5c39`
（三项修复、对应定向用例与闭环工具扩展）；本文件、证据日志与文档状态同步在紧接
`e4e5c39` 之后的文档同步提交（提交信息以“阶段七: 原型收尾证据与文档状态同步”开头，
即 `git log` 中 `e4e5c39` 之后的第一个提交）。未推送、未部署。验证环境：CPython 3.9.25 +
uv（`uv run --locked --no-python-downloads`），Linux/WSL；未重做选型、未重装
LibreOffice、未升级锁文件；验证使用隔离临时数据根，正式 `data/` 只读。

## 1. P7-01 附件与正文恢复隔离

缺陷：`_same_recovery_object` 只按母文档 doc_id 关联对象，附件补抓会把仍 partial 的
母页标成 processed 并清空 `continuation`（隔离用例先复现：附件恢复成功、母页从
pending 变 processed）。

最小修复（`src/crawler/pipeline.py`、`output/failures_writer.py`、`fetch/retry.py`）：

- 关联母页续作必须有证明：任务 URL 必须出现在该母文档待续状态记录的下一分页/接口
  位置或已取得部分 URL 中，且待处理项是该母页主目标；仅共享 doc_id 不再关联；
- 附件/无关对象按自身 URL 恢复，恢复任务只回写同身份待处理项，不动仍待续母页；
- 失败账新增可选 `discovery_method`，标注对象种类（attachment / pagination / api）；
  已知正文分页/接口任务无法证明关联时转人工（`manual_review`），不按 URL 独立取回、
  不产出片段文档、保持失败开放（`_body_part_needs_manual`）。

| 用例 | 结果 |
| --- | --- |
| `test_attachment_recovery_isolated_from_pending_mother_continuation`（母页 partial + 附件恢复成功：附件 processed，母页仍 pending、continuation 逐字节不变） | 通过 |
| `test_unprovable_body_part_goes_manual_without_fragment_document`（身份不足转人工、不产出片段文档、人工态不自动补抓） | 通过 |
| 原片段恢复用例复用：`test_part_failure_recovery_resumes_mother_document`、`test_part_reparse_failure_does_not_create_fragment_document` | 通过 |
| 真实采集路径登记对象类型：`tests/test_pipeline.py` 的附件失败行断言 `discovery_method="attachment"` | 通过 |

## 2. P7-02 人工处置与执行状态一致

缺陷：`resolve --action skip` 只关闭失败账，队列仍 failed，`crawl check` 的队列对账
从通过变失败（隔离用例先复现：`payload["queue"]` 不存在 + reconcile 不通过）。

最小修复（`src/crawler/monitor/failures.py`、`src/crawler/cli.py`）：

- `FailureLedger.resolve_with_queue`：追加处置行后按对象身份（来源 + URL + 原运行范围
  + 母文档）协调同身份待处理项；`skip → skipped`、`recovered → processed`；
- 同对象仍有其他未关闭阶段时队列保持现状并明确报告（`queue.status=blocked`，
  `kept_open` 列出阶段），不误关、不标记完成；无关对象与不同范围/母文档不匹配；
- `manual_review` 保持未关闭：队列状态不改写（备注标注人工态），`plan`/`resume` 不
  自动补抓（`plan_retry` 返回 manual）；重复处置幂等且明确报告；
- 对象仍有正文待续（`continuation`）时，`recovered` 只关闭本次失败，队列保持
  pending 继续续作，不清空续作位置；
- 队列回写失败抛 `FailureQueueSyncError`：处置行保留、CLI 以退出码 2 报告并给出可
  重复执行的同一命令，不声称处置已成功。

| 用例 | 结果 |
| --- | --- |
| `test_cli_resolve_skip_syncs_failed_queue_item`（真实 failed 队列对象 skip 后 reconcile ok） | 通过 |
| `test_cli_resolve_skip_respects_other_open_stage_and_other_objects`（其他开放阶段 blocked；无关对象不动） | 通过 |
| `test_cli_resolve_manual_review_keeps_failed_item_and_blocks_auto_retry`（保持可见、不自动补抓、重复一致） | 通过 |
| `test_cli_resolve_recovered_keeps_pending_continuation`（不得把仍待续对象标完成/清延续作） | 通过 |
| `test_cli_resolve_reports_queue_write_failure_recoverably`（写入失败明确、可重复恢复） | 通过 |

## 3. P7-03 空身份可选中

缺陷：`find_latest` 无法区分“未指定归属”与“显式空值”，同 URL 存在带日期/不带日期或
带 doc_id/不带 doc_id 的记录时，操作者无法选中空值身份（隔离用例先复现）。

最小修复（`src/crawler/monitor/failures.py`、`src/crawler/cli.py`）：参数缺省 `None`
表示未指定（行为不变）；显式空字符串表示选中该字段为空的记录。`failures` 查询的
`--source/--stage/--scope-start-date/--doc-id` 同口径；`resolve` 报错时列出每个身份的
可复制命令（`--doc-id ''` 形式），操作者无需手改 JSONL。

| 用例 | 结果 |
| --- | --- |
| `test_find_latest_selects_explicit_empty_identity`（未指定多项身份返回 None；显式空值/具名各自命中） | 通过 |
| `test_cli_resolve_selects_explicit_empty_identity`（只关闭指定空值身份，其他身份保持未关闭，可按显式空值查询） | 通过 |

## 4. 验证命令与结果

```bash
# 定向（P7-01 4 项、P7-02 8 项、P7-03 2 项）
uv run --locked --no-python-downloads pytest tests/test_recovery.py -q \
  -k "attachment_recovery_isolated or unprovable_body_part or part_failure_recovery_resumes_mother_document or part_reparse_failure_does_not_create_fragment_document"
uv run --locked --no-python-downloads pytest tests/test_cli.py -q -k "resolve"
uv run --locked --no-python-downloads pytest tests/test_recovery.py tests/test_cli.py -q -k "explicit_empty_identity"

# 受影响闭环（本机回环夹具站点；只写 /tmp）
uv run --locked --no-python-downloads python tools/closed_loop_fixture.py \
  --workdir /tmp/crawl-s7-prototype-loop --json /tmp/s7-prototype-loop.json --clean

# 候选回归（一次全量）
uv run --locked --no-python-downloads pytest -q
```

结果：定向 `4 passed` / `8 passed` / `2 passed`；闭环 9+ 步全部通过（含新增
3e 真实 failed 队列对象处置、3f—3i 多身份显式空值与隔离），最终 `check` 为
`ok=True`、`reconcile ok`；全量 `523 passed`。原始输出见
[定向与全量测试](logs/stage-seven-prototype-tests.txt)、
[闭环逐步记录](logs/stage-seven-prototype-loop.txt)（逐步 JSON 同时在 `/tmp/s7-prototype-loop.json`）。
文档同步后另跑 SDD 结构检查：`verify_sdd_documents.py` 输出
`status=PASS`（37 需求、27 任务、968 条本地链接、四份输入指纹一致），见
[文档检查日志](logs/stage-seven-prototype-docs-check.txt)；该检查不访问业务站点，
不替代软件或数据验收。

## 5. 与来源数据完整性的边界

- 未主动联网；受限来源、缺失原件、历史 partial 与失败账开放项按
  [manual-follow-up.md](../manual-follow-up.md) 交人工补齐，原型不等待其解决；
- `failures --summary --source` 的队列/partial 仍为全数据根口径，作为非阻断局限保留
  （同上清单“可接受的报告局限”）；
- T019/T026/T027 仍为部分完成，本轮不勾选；18 来源的窗口完整性不因本证据改变。
