# 证据：T018 交付目录组织与采集范围禁令

日期：2026-09-11。目标平台：当前 Linux。对应需求：FR-019、FR-020；完成标准“完整交付包可读取，
原件可定位，采集包中没有 RAG 派生成果”。

## 实现

- `src/crawler/output/layout.py`：新增 `DeliveryLayout`，把六项成果的落盘位置收口到一处——
  `raw/`、`manifests/crawl_manifest.jsonl`、`normalized/documents.jsonl`、`normalized/blocks.jsonl`、
  `manifests/failed_records.jsonl`、`logs/`（含 `crawler.log`、`metrics.json`、`metrics_history.jsonl`）。
  同时提供 `ensure()`（建齐四个交付目录，不删除、不搬迁旧内容）、`raw_dir_for()`（统一
  raw/<source_id>/<date>/<kind>/ 结构）、`resolve_raw_path()`（拒绝绝对路径、空值、``..`` 与符号链接
  越界）和 `relative_to_root()`。raw_path 仍是相对数据根的路径，不含机器绝对路径。
  原件归档、账本、失败账、文档/块写出、日志、指标、增量状态与版本库全部改为从该布局取路径。
- `src/crawler/output/delivery.py`：新增只读交付检查 `inspect_delivery(data_dir)`：
  - 六项成果清单核对（`failed_records.jsonl` 在零失败时可为空或不存在，符合 AT-019）；
  - 行数统计（账本/文档/块/失败/原件文件数），可直接与 `logs/metrics.json` 对账；
  - 逐行核对 manifest 与 documents（含附件）的 raw_path：必须相对、位于数据根内、原件存在；
  - 扫描数据根，报告 FR-020 禁止的 RAG 派生成果（chunks、embeddings/vectors、索引 faiss/bm25/hnsw、
    rerank、prompts、answers 等）。
- `src/crawler/pipeline.py`：管线持有同一布局，运行开始 `ensure()` 四个交付目录；补抓重解析改为经
  `resolve_raw_path` 读取原件，越界路径直接拒绝并保留失败记录（CFG-08 的前置实现）。

## 验收命令与结果

```bash
UV_CACHE_DIR=/tmp/crawl-uv-cache uv run --locked --no-python-downloads pytest -q
# 229 passed（其中 tests/test_delivery.py 8 项）
python3 tools/verify_sdd_documents.py
# PASS
```

关键用例：

| 用例 | 结果 |
| --- | --- |
| 布局 | `ensure()` 后数据根下恰好 raw/manifests/normalized/logs 四个目录；各写入口径一致 |
| 相对路径 | 合法相对 raw_path 可解析；绝对路径、空值、`../`、符号链接越界均抛 `PathSafetyError` |
| 完整交付包 | 夹具运行后六项成果齐全、路径问题与禁令均为空；行数与 `metrics.json` 计数一致 |
| 零失败 | 无失败采集不产生失败账文件，检查仍判通过并注明“零失败可为空” |
| 禁令检出 | 注入 `normalized/chunks.jsonl`、`vectors/`、`vectors/index.faiss` 后 `ok=false` 并逐项列出 |
| 路径问题检出 | 绝对 raw_path、缺失 raw_path、不存在的原件、`..` 越界分别定位到文件与行 |
| 重解析越界 | 失败账指向 `../../etc/passwd` 时补抓拒绝读取，失败保持未关闭，不产生文档 |

真实检查样本：[logs/t018-delivery-sample.txt](logs/t018-delivery-sample.txt)；
测试输出：[logs/t018-pytest.txt](logs/t018-pytest.txt)。

## 限制与待办

- 本任务只做位置与禁令检查；字段级 schema、哈希与溯源链校验属 T019/AT-021/AT-022，
  已在 [T019-acceptance.md](T019-acceptance.md) 执行并通过，本记录不再重复其结论。
- 增量状态文件 `manifests/incremental_state.json` 是运行状态，不是第七项交付类别；它随账本目录存放，
  不计入六项成果（与 T015 证据一致）。
- CFG-06（工程外绝对数据根）与 CFG-07（搬迁后引用不变）已在 T019 执行并通过，见
  [logs/t019-cfg.txt](logs/t019-cfg.txt)；本任务的布局与相对路径实现是它们的前置。
