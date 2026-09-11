# 证据：T016 分阶段失败账、补抓与运行恢复

日期：2026-09-11。目标平台：当前 Linux。对应需求：FR-017；完成标准“四阶段失败均可复现，对账可解释”。

## 实现

- `src/crawler/fetch/retry.py`：`RetryPolicy`（默认最多 3 次、指数退避 60s→上限 3600s）与
  `plan_retry`。阶段分流：discover/fetch 属网络阶段→`refetch`；parse/normalize/validate 属本地阶段
  →`reparse`（原件已保留，不需要重新下载）；永久 4xx（408/429 除外）→`manual`，只记录不重试；
  次数用尽或缺少原件→`manual` 并给出原因；未知阶段不静默忽略。`build_recovery_plan` 用账本
  `crawl_id` 在 manifest 中定位 `raw_path`；`summarize_plan`/`plan_is_ready` 提供对账与退避判断。
- `src/crawler/monitor/failures.py`：`FailureLedger` 保持只追加——`open_failures` 取同一
  (url, stage) 的最后一条记录，`record_resolution` 追加处置行（`recovered` / `manual_review`），
  带 `previous_time` 与 `attempts_before` 关联原失败，历史失败行不被改写；`pending_documents`
  找出“已成功下载但还没有文档”的账本条目，供中断恢复重解析。
- `src/crawler/output/failures_writer.py`：`final_action` 扩展 `recovered`、`manual_review`（候选扩展，
  failure 契约允许附加字段）。
- `src/crawler/pipeline.py`：`recovery_plan()`（不产生副作用）与 `resume_failures()`。网络阶段重取走
  正常采集路径（含边界、限速、账本、增量状态）；本地阶段按原件重解析：HTML 走 `parse_html`，
  其他格式走 T012 的 `parse_attachment` 分派，重新生成文档与块并复用同一 `crawl_id`；失败则保留原件
  与失败记录，追加新的失败行而不是覆盖历史。
- 失败账仍是四阶段（discover/fetch/parse/normalize，另含 validate）记录；异常与错误类型沿用 T004—T009
  的写入路径，补抓只增行。

## 验收命令与结果

```bash
UV_CACHE_DIR=/tmp/crawl-uv-cache uv run --locked --no-python-downloads pytest -q
# 210 passed（其中 tests/test_recovery.py 11 项）
python3 tools/verify_sdd_documents.py
# PASS
```

关键用例：

| 用例 | 结果 |
| --- | --- |
| 四阶段分流 | discover/fetch→refetch；parse/normalize/validate→reparse；未知阶段→manual |
| 永久 4xx | HTTP 404→manual（不重试）；429/503/连接超时→可重试；退避 60→120→上限 |
| 失败账 | 同一 (url, stage) 以最后一条为准；处置行关闭失败并保留原行与时间 |
| 网络补抓 | 记录 fetch 失败后 `resume_failures` 重新获取成功：生成 1 份文档、处置行 `recovered`、原失败行逐字节保留 |
| 本地补抓 | parse 失败 + 原件在账本中：`reparse` 不联网生成 PDF 文档与块，原件字节不变 |
| 退避与人工 | `respect_backoff=True` 时未到期任务进入 pending；永久 4xx 进入 manual |
| 中断恢复 | manifest 中已下载但无文档的条目进入 `pending_documents`，可本地重解析补齐 |

## 限制与待办

- 补抓不自动定期运行；触发时机与重试预算属 Q15/Q13，仍由运行方按配置调用 `resume_failures`。
- 重解析生成的文档沿用原 `crawl_id`；若源码来源变更导致同一 crawl_id 重复提交，DocumentsWriter 的
  doc_id 校验会拒绝并保留失败记录（当前实现按“一次抓取一份文档”处理）。
- 真实站点失败样本：2026-09-11 第四轮核验中 CN-04 触发真实 `normalize` 失败，已按原件重解析闭环（见下节）；
  其余真实来源失败样本仍待 Q12/Q13。

## 真实站点失败样本（2026-09-11 增补）

第四轮核验中 CN-04 的页面在 `normalize` 阶段真实失败（空标题块，见
[logs/t008-cn04-defect-fix.txt](logs/t008-cn04-defect-fix.txt)）：原件与账本已落盘、失败账记录原因，
修复后以 `reparse` 从已归档原件补全文档（`requests=0`、1 文档/145 块），历史失败行逐字节保留、
处置行 `final_action=recovered`，原件 sha256 不变。

同时修正一处补抓范围缺陷：`resume_failures(source_id)` 原先会处理全部未关闭失败（可能按错误来源的配置重取/重解析），
现按 `task.source_id` 过滤；新增 `tests/test_recovery.py::test_resume_failures_only_handles_requested_source`
（两来源各一条失败，断言只处理所请求来源，另一条仍在补抓计划中）。
