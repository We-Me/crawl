# 阶段六 R1—R6 一致性修复与候选回归（2026-09-14）

本记录对应 [阶段六](../stage-six.md) 的六项审查缺陷修复（R1—R6），关联 T005/T006/T007/T015/T016/T019
的工程部分。它不把 T019/T026/T027 的正式验收、18 来源状态、S5-02 受限结论或发布/后处理范围改为通过。

代码基线：`df1811d`（阶段六方案提交，接在阶段五 `b6041ea` 之后）。验证环境：Python 3.9.25（uv，
`requires-python >=3.9,<3.10`），Linux + POSIX fork。六项修复全部用离线夹具（进程内或本地回环）验证，
本轮未新增真实站点请求（阶段六要求“先离线重现”）；DEV-012 的线上授权未被使用。

测试证据：[定向用例](logs/stage-six-targeted-pytest.txt)（103 passed）、
[完整回归](logs/stage-six-full-pytest.txt)（492 passed）；历史数据只读评估见
[历史数据影响评估](stage-six-historical-impact.md) 与 [只读校验日志](logs/stage-six-readonly-check.txt)。

## 修复与实现对应

| 修复 | 原缺陷 | 实现要点 | 主要位置 | 提交 |
| --- | --- | --- | --- | --- |
| R6 | 损坏状态被当空集，对账误报通过 | 状态文件与失败账的读取、JSON 解析、结构错误进入 `ReconcileReport.problems`；合法缺失/合法空状态仍按零记录；`crawl check` 非零退出并给出文件与原因；检查只读，不重建损坏文件 | `validate/reconcile.py`、`cli.py` | `2155422` |
| R5 | 补抓按资源计数误判成功 | 以 `TargetOutcome` 与恢复任务阶段判定结果；失败账恢复身份为 `(url, stage, scope_start_date, doc_id)`，恢复任务携带 `doc_id`；显式分支处理 完整 / 合法 304 / partial / 续作 / 失败 / 跳过；同 URL 不同 scope 或母文档不互相关闭 | `pipeline.py`、`monitor/failures.py`、`fetch/retry.py`、`output/failures_writer.py` | `2155422` |
| R3 | 并发归档 ID 冲突 | 归档全流程（锁内重读已落盘编号、写原件并校验、分配 ID、追加并刷盘账本）在同一跨进程 `file_lock(manifests/crawl_archive)` 内；编号不再用实例缓存；所有归档入口共用该服务 | `output/archive.py` | `aad3a63` |
| R4 | 游标先提交、目标后入队 | 发现目标先经 `commit_targets` 幂等入队，再推进游标；游标记录 `last_commit_page`/`last_commit_digest`，崩溃重放按页摘要识别；入口级运行锁与 `entry_busy`/`commit_failed`/`cursor_save_failed` 终止原因；重放不把已处理目标整体转 refresh | `discover/discoverer.py`、`schedule/cursor.py`、`schedule/pending.py`、`output/atomic.py`、`pipeline.py` | `9d8b237` |
| R2 | 正文分页中断后主目标完成 | `PendingItem.continuation`（`kind=body_pagination`）持久化母身份、已取得部分的 crawl_id/raw 引用与顺序、下一正文 URL 或接口、停止原因；预算停止与可重试正文失败保持待续（不写失败账、不写完成）；母页 304 不取消未完成正文；续作完成文档用 `<母doc_id>-R<n>`，旧 partial 与 raw 保留；损坏待续显式转 `continuation_state_damaged` 失败并按整取处理 | `pipeline.py`、`schedule/pending.py` | `b37fc1c` |
| R1 | 已知 URL 页过早停止 | 删除“整页已知即完成”推断与 `target_urls` 早停；已知目标按更新策略进入 refresh（条件请求），新链接照常登记；游标新增 `pass_pages`/`coverage_rounds`/`last_round_completed_at`，终止报告带 `round_pages`/`coverage_rounds`，累计 `pages_fetched` 不再当覆盖页数；`incremental_head_checked` 仅作历史标记，下次运行在 note 前缀注明已失效并重新遍历 | `discover/discoverer.py`、`schedule/cursor.py`、`schedule/pending.py`、`pipeline.py` | `2ff6ef8` |

## 逐项验收对照

| 修复 | 阶段六验收要求 | 用例 | 结果 |
| --- | --- | --- | --- |
| R6 | 截断 JSON、`items` 类型错误、非法条目、损坏失败账均报错；合法空状态按约定处理；检查前后原文件字节不变；给出文件与原因 | `tests/test_validate_reconcile.py`（10 项，含 6 项本轮新增） | 通过 |
| R5 | HTTP 200 且 raw 留存后解析失败、规范化失败、partial、合法 304、robots 拒绝各有不同结果；同 URL 不同 scope/母文档不会互相关闭 | `tests/test_recovery.py`（32 项，含 9 项本轮新增） | 通过 |
| R3 | 两个真实进程交错归档：`crawl_id` 唯一、账本引用的原件存在且哈希一致、同名不同内容不覆盖 | `tests/test_archive_processes.py`（1 项，POSIX fork 真实子进程，8 轮交错） | 通过 |
| R4 | 故障不漏目标：提交失败不推进游标、游标保存失败可重放且幂等、崩溃恢复从下一页继续、入口并发被显式拒绝 | `tests/test_discovery_commit_order.py`（8 项：7 项故障注入 + 1 项同页 URL 换序重放幂等） | 通过 |
| R2 | 三页正文在第二页前耗尽预算、母页 304 仍能完成第二/三页与正文 API；块顺序正确无重复；待续最终关闭 | `tests/test_body_continuation.py`（5 项） | 通过 |
| R1 | 第一页均已知但第二页新增、相同 URL 正文变化、置顶与后部补录、无变化来源跨预算推进；同页 URL 换序重放幂等；不因整页已知报完成 | `tests/test_incremental_coverage.py`（5 项）、`tests/test_pagination_coverage.py`（12 项，其中 3 项按 R1 重写）、`tests/test_discovery_commit_order.py` 换序重放 1 项 | 通过 |
| 回归 | CLI 与 robots 相关既有行为不被六项修复破坏 | `tests/test_cli.py`（18 项）、`tests/test_robots.py`（12 项） | 通过 |

R3 的并发验证是 Linux 两个真实子进程（`multiprocessing` fork + `flock`）；多线程或单进程重入不能替代
跨进程锁验证，本记录不以多线程结果外推。另有反向灵敏度核对（[脚本](logs/stage-six-r3-unlocked-sensitivity.py)、
[输出](logs/stage-six-r3-unlocked-sensitivity.txt)）：临时移除归档锁后，同名不同字节场景复现原件覆盖错误
（一个子进程以 `ManifestError` 退出）；同名相同字节场景 5 次中 4 次出现重复 `crawl_id`（每次最多 3 个重复
身份）。说明 `tests/test_archive_processes.py` 约束的是锁语义本身。

## 命令与结果

```bash
uv run pytest -q tests/test_recovery.py tests/test_validate_reconcile.py tests/test_archive_processes.py \
  tests/test_discovery_commit_order.py tests/test_body_continuation.py tests/test_incremental_coverage.py \
  tests/test_pagination_coverage.py tests/test_cli.py tests/test_robots.py
# 103 passed in 15.50s

uv run pytest -q
# 492 passed in 35.76s
```

## 分维度报告（2026-09-14，按阶段六要求分列）

| 维度 | 本轮事实 | 未知/限制 |
| --- | --- | --- |
| 发现覆盖 | 无线上运行；R1/R4 的覆盖推进、重放与旧快检失效由离线夹具验证（5 + 7 项）；历史游标只读核对：15 个中 12 个旧快检标记等待下次运行重核，1 个 `active` 游标的当页目标 10/10 已登记（未观察到漏目标） | 各来源窗口总量未知；历史游标的新 `coverage_rounds` 从 0 重新累计，不等于已覆盖 |
| 主目标 | 待处理目标 4463 条：4446 processed、17 skipped（日期窗口外等）；失败账 4 项未关闭 | 旧账身份不闭合（见只读评估第 2 节），不按 URL 推断已恢复 |
| 正文部分 | 新机制：预算停止/正文请求失败持久化 `continuation` 并续作（5 项离线场景）；历史 39 份 partial 无 continuation | 历史 partial 的未取部分不能自动补全，数量未知；需要时按来源新窗口复核 |
| 附件 | 文档附件 6749 条：downloaded 5815、pending 929、failed 3、boundary_rejected 2；929 个 pending 中 928 个实物已下载（原件 + 账本 + 待处理行一致）、1 个 robots 保守拒绝无原件 | 文档行状态滞后于实物（只读评估第 5 节）；本轮不重写文档行 |
| 恢复链 | 失败账 10 行（8 fetch、2 normalize）追加式保留；4 项未关闭（IN-05 1、IN-02 3），对应 raw 均已归档且 sha 一致 | 旧行缺 `doc_id`/`scope_start_date`，需有界 `crawl resume` 或另行迁移才能闭合 |
| raw 留存 | 账本 12164 行、raw 文件 11838 个；重复身份 6 行原件全部存在且 sha 一致（未覆盖）；4 个未关闭失败对应 PDF 全部在 raw | 哈希一致只证明已取得字节留存，不证明窗口完整 |
| 追溯 | documents 4728/4728、blocks 26774/26774（均 100%，分母非零） | 追溯率不表达来源覆盖完整性 |

“队列清空不等于窗口完整”：待处理队列状态与来源窗口覆盖分别报告，未知总量保持未知。

## 边界与限制

- 六项修复均以离线夹具验证，不依赖站点事实，因此本轮没有线上运行；如后续需要来源窗口复验，按阶段六的
  登记与有限预算要求单独进行。
- R4 的“重放”以页目标摘要（排序后 URL 的 SHA-1）识别；页面内容未变但目标集合变化时仍按新目标入队，
  不会用摘要相等掩盖新增链接。
- R2 的待续状态只在新建/续作路径写入；本轮之前的旧数据没有 `continuation`，不会被误读，也不会自动补全
  （见历史数据影响评估第 4 节）。
- R1 的覆盖轮计数从新语义开始累计；历史游标缺字段按 0 处理，旧 note 不作为新语义下的覆盖证据。
- T019/T026/T027 仍为部分完成；S5-02 复用既有受限证据，S5-05/07 保持暂缓；本记录不改变这些状态。
