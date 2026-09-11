# NEXT-06 统一请求预算、运行截止时间与停止报告（2026-09-11）

本记录对应 [阶段三计划](../stage-three.md) NEXT-06（GAP-02），关联 T006/T016/T026/T027。
它不改变 AT 用例状态，也不代表正式来源启用或 T019/T026/T027 总体验收完成。

## 变更的可观察行为

- `crawl collect` 与 `crawl resume` 新增 `--max-requests N` 与 `--deadline-seconds S`；
  两项都省略时运行不受这两项限制（输出会提示未设置预算，参数见 `--max-requests`、`--deadline-seconds`）。
- 一次运行共享一个 `RunBudget`：robots.txt、重定向每一跳、重试尝试、发现页、正文分页、
  正文接口与附件下载**全部在发送前扣减同一请求预算**；达到上限不再发送任何请求。
- 截止时间使用单调时钟；等待限速或 Retry-After 前比较剩余时间，网站要求的等待超过剩余时间即停止，
  不缩短站点要求的等待。单次连接/读取超时被压到剩余时间内（下限 0.1s，见限制）。
- 流式下载按块检查截止时间；停止后不再读取下一块、不再解析下一批目标。
- 停止报告：`stop.reason`（`request_budget` / `deadline` / `rate_limit_wait` / `retry_wait` /
  `retry_after_wait`）、`stop.message`、`stop.unprocessed`（未处理完的目标数）与 `budget`
  （上限、已用请求数、已用时间）；`logs/metrics.json` 的 `status` 记 `partial`/`stopped`，
  不会把预算停止伪装成 `ok`。
- 退出码：预算/截止时间停止返回 `3`（未完成），与 `0` 成功、`1` 有失败或交付不通过、`2` 配置错误区分。
- 预算停止不记为网站失败：失败账不追加 `http_error`；已归档原件、账本、文档与块保持不动，
  分页/附件阶段停止时父文档先落盘（`parse_status=partial`）再停止。
- `max-items`/`max-tasks` 仍只是结果数量限制，不参与请求预算。

## 实现位置

| 文件 | 内容 |
| --- | --- |
| `src/crawler/fetch/budget.py` | `RunBudget`（请求数/截止时间/等待判定）与 `BudgetStop`（与 `FetchError` 区分） |
| `src/crawler/fetch/http_client.py` | 发送前扣减、限速与 Retry-After 等待预检、流式读取截止检查、超时压缩、未发送请求退回额度 |
| `src/crawler/pipeline.py` | collect/resume 挂预算、分页/接口/附件阶段保留已归档数据、`stop_reason`/`unprocessed`/`budget` 报告 |
| `src/crawler/monitor/metrics.py` | `metrics.json` 的 `budget`、`stop` 与停止状态/说明 |
| `src/crawler/cli.py` | 参数校验、停止输出、退出码 3 |

## 验证（最小必要集合）

用例集中在 `tests/test_budget.py`（14 项，本地回环夹具 + 可注入时钟，不依赖真实站点限流）：

- `test_request_budget_counts_robots_redirect_hops_and_retries`：robots、重定向每跳、重试尝试共用计数；
  预算用尽后不再发送（实际发送次数由记录型 Session 计数）；重试仍按既有退避等待。
- `test_request_budget_exhaustion_blocks_send`、`test_redirect_hops_share_request_budget`：上限前停止发送。
- `test_retry_after_longer_than_remaining_stops_without_waiting`：Retry-After 超剩余时间即停，不缩短等待。
- `test_rate_limit_wait_beyond_remaining_stops`：限速等待超剩余时间即停，未发送的请求退回额度。
- `test_attempt_timeouts_are_clamped_to_remaining_time`：连接/读取超时受剩余时间约束。
- `test_streaming_download_stops_when_deadline_passes`：流式读取中截止时间生效，内容不进入原件库。
- `test_collect_budget_stop_keeps_archived_data`、`test_collect_budget_stop_during_attachments_keeps_parent_document`：
  停止后已归档原件/账本/文档/块保留，不记网站失败，未处理目标与 stop 原因出现在报告与 metrics。
- `test_resume_budget_stop_reports_unprocessed_tasks`：resume 与 collect 同一语义，恢复成果保留。
- `test_cli_collect_budget_stop_exit_3`、`test_cli_resume_budget_stop_exit_3`、
  `test_cli_budget_arguments_must_be_positive`：CLI 退出码 3/2 与 JSON 报告字段。

历史结果：`tests/test_budget.py` 14 passed；阶段候选全量回归 345 passed，见
[阶段三完整回归](logs/stage-three-full-pytest.txt)。

## 限制

- 单次同步请求/读取的超时下限为 0.1s：剩余时间更短时允许本次调用略微越过截止时间，
  最长终止延迟约等于该超时加底层 socket 行为；本实现不宣称硬实时中断（与 stage-three.md 的说明一致）。
- 预算按一次 CLI 运行生效；同机多进程写同一数据根仍不受支持（见 runbook 第 9 节）。
- 真实站点限流行为不靠加压测试验证；线上运行须显式给出预算（DEV-012 试点为 10 请求/5 分钟）。
