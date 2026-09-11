# 证据：T017 运行日志、计数、重复与异常统计

日期：2026-09-11。目标平台：当前 Linux。对应需求：FR-018；完成标准“混合运行日志及全部成果
按已定口径可对账”。

## 实现

- `src/crawler/monitor/logger.py`：`configure_run_logging(data_dir)` 把运行日志写到
  `<数据根>/logs/crawler.log`（追加、UTF-8、ISO 时间戳）。同一数据根只挂一个处理器，重复调用不
  重复写行；切换数据根时只移除本模块挂的处理器，不动调用方自己的 handler。
  `log_run_context` 只记录运行模式、解析后的数据根与是否默认值，不打印环境变量或 .env 内容。
- `src/crawler/monitor/metrics.py`：`COUNTING_RULES` 固化四类成果口径——requests（HTTP 请求尝试
  次数，含重试与条件请求）、resources（成功归档原件数）、documents（逻辑文档数）、blocks
  （结构块数），并明确成功按资源数、失败按操作数、跳过按目标数分别计数。
  - `output_stats`/`deltas_between`：对 `crawl_manifest.jsonl`、`documents.jsonl`、
    `blocks.jsonl`、`failed_records.jsonl` 与 `raw/` 取运行前后快照，得到本次追加量。
  - `duplicate_stats`：按 exact_bytes/exact_text 统计重复候选，`policy=keep_all_sources`
    保留全部来源；近似重复必须显式给出阈值，未给出时记 `not_computed` 并写明 Q11 未决，不用
    未决策阈值冒充结果。
  - `reconcile`：逐条核对“资源数=账本追加行数、文档数=documents 行数、块数=blocks 行数、
    失败数=失败账行数、阶段/类型/跳过原因分布合计=总失败/跳过数、重复候选保留全部来源”，差异
    以 `discrepancies` 列出，不静默容忍。
  - `write_metrics`：原子写 `logs/metrics.json`（最近一次运行，含口径定义与全部核对结果），并
    追加 `logs/metrics_history.jsonl`；`read_metrics` 供验收读取。
  - `request_controls`（2026-09-11 增补）：记录来源速率、来源声明的 `max_concurrency` 与生效并发
    （单进程同步恒为 1）及说明，满足 AT-023“速率与并发分别建模”，不把声明上限冒充已实现并发。
- `src/crawler/fetch/http_client.py`：新增只读计数 `request_attempts`，在每次真正发出 HTTP 尝试
  前自增（含重试与逐跳重定向），让请求计数覆盖发现、详情与附件请求。
- `src/crawler/pipeline.py`：`collect`/`resume_failures` 开始时配置日志、记录运行前交付快照与
  请求计数起点，结束时调用 `_finish_run` 汇总计数、异常分类、重复候选与对账结果，写日志和
  metrics；补抓运行把“处置行追加”计入预期失败账增量，避免把人工/成功处置误判为对账差异。
  `RunReport.metrics`/`RecoveryReport.metrics` 暴露同一份结果；管线接受可选 `Settings`
  （记录运行模式与数据根）与可选 `duplicate_threshold`（近似统计开关，Q11 未决时保持关闭）。

## 验收命令与结果

```bash
UV_CACHE_DIR=/tmp/crawl-uv-cache uv run --locked --no-python-downloads pytest -q
# 221 passed（其中 tests/test_monitor.py 11 项）
python3 tools/verify_sdd_documents.py
# PASS
```

关键用例：

| 用例 | 结果 |
| --- | --- |
| 日志幂等 | 同一数据根重复配置后只有一个运行处理器，一条消息只写一行 |
| 运行上下文 | 记录 mode 与解析后的数据根，不含任何环境变量值 |
| 计数口径 | requests 明确“不等于文档数”；resources/documents/blocks 各自绑定交付文件 |
| 快照与增量 | 空交付为 0；写入后 failed_rows 增量 1、documents_rows 增量 0 |
| 对账检出差异 | 注入 resources=2 而账本 1 行时 `reconciliation.ok=false` 并列出差异名 |
| 重复统计 | 同字节两文档记 1 组且成员保留；未给阈值时 near_text=not_computed 且注明 Q11 |
| metrics 写出 | `logs/metrics.json` 原子落盘（无残留 .tmp），history 追加且携带口径定义 |
| 端到端混合运行 | 夹具站点一次采集 requests=6、resources=3、documents=2、blocks=16、failures=1、skipped=1，对账全部通过；失败进入 `failures_by_stage=fetch`、`failures_by_type=http_error` |
| 304 不产生虚假文档 | 第二次条件请求 documents=0、not_modified=2、skip 原因 not_modified、日志/指标注明“本次无新增成果” |
| 异常进日志 | 失败时 `logs/crawler.log` 同时有失败记录行与运行汇总行 |

真实运行样本（本地夹具站点，非真实来源）：[logs/t017-metrics-sample.txt](logs/t017-metrics-sample.txt)；
测试输出：[logs/t017-pytest.txt](logs/t017-pytest.txt)。

## 限制与待办

- Q11 未决，正文完整性/召回阈值与近似重复阈值都不给默认值；样本缺陷率、质量结论仍属 T019/AT-024。
- Q15 未决，日志保留期限与轮转策略未定；当前为追加式运行日志，不做轮转，不引入日志框架。
- 请求计数是进程内只读计数；跨进程或跨次运行的对账以 `metrics_history.jsonl` 与交付文件增量为准。
- `metrics.json` 记录的是最近一次运行；完整历史的对账读取 `metrics_history.jsonl`（T018 交付整理时
  与 logs/ 一并说明）。
