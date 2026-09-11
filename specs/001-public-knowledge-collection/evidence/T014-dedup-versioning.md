# 证据：T014 去重、来源关系与版本保留

日期：2026-09-11。目标平台：当前 Linux。对应需求：FR-014、FR-015；完成标准“转载不丢来源；
修改条款生成新版本；旧版和下线不会删除历史”。

## 实现

- `src/crawler/dedup/fingerprint.py`：`text_hash` 按统一清洗后的折叠文本计算 content_hash，
  `text_similarity` 用标准库 difflib（确定性），`document_fingerprint` 只取身份字段，不改写文档。
- `src/crawler/dedup/duplicates.py`：按原件 sha256（exact_bytes）与规范化全文哈希（exact_text）
  分组，只返回成员 ≥2 的组；近似重复必须显式传入阈值（Q11 未决，模块不提供默认值，缺阈值抛
  `DuplicateConfigError`）。分组结果只是候选与证据，不删除、不合并、不改写任何文档。
- `src/crawler/dedup/relations.py`：`reprint_of`、`revision_of`、`mirror_of`、`duplicate_of` 关系
  必须带证据（basis/matched_url 等）；自指或未知类型报错；`attach_relations` 把关系写回文档，
  同源身份不被合并。
- `src/crawler/versioning/identity.py`：文档身份按 source_id + 规范化 URL 计算，不同来源同 URL
  不是同一身份。
- `src/crawler/versioning/versions.py`：`plan_version` 区分 NEW/UNCHANGED/REVISION；修订生成新版本号、
  `supersedes` 指向旧版、标记 `requires_review`，不改写旧文档；精确重复只记 `duplicate_of` 关系。
- `src/crawler/versioning/store.py`：`normalized/documents.jsonl` 上的 `retire`（旧版 in-place 保留全文，
  置 `is_current=false`、`source_status=superseded`）与 `record_offline`（下线状态 + `status_history`
  证据，历史全文保留）；文件缺失时明确报 `VersionStoreError`。

## 验收命令与结果

```bash
UV_CACHE_DIR=/tmp/crawl-uv-cache uv run --locked --no-python-downloads pytest -q
# 210 passed（其中 tests/test_dedup_versioning.py 13 项）
python3 tools/verify_sdd_documents.py
# PASS
```

关键用例：

| 用例 | 结果 |
| --- | --- |
| 同一字节不同来源 | exact_bytes 组保留 d1/d2 两条来源，不合并 |
| 不同字节相同全文 | exact_text 组按 content_hash 命中 |
| 近似阈值未给出 | `DuplicateConfigError`，提示 Q11 未决 |
| 近似阈值显式给出 | 分组保留两篇文档自身内容，相似度回填 |
| 转载关系 | 带证据的关系写回 `related_doc_ids`；无证据/未知类型/自指报错 |
| 版本判定 | 首次 NEW；相同内容 UNCHANGED；改动生成 REVISION v2 且 supersedes v1 |
| 精确重复跨身份 | 记为 `duplicate_of`，来源 URL 不被覆盖 |
| 现行状态与下线 | retire 后旧版全文与版本历史仍在；下线记录带证据且不删除历史 |

## 限制与待办

- 近似重复阈值、重复来源处置策略（Q05）与版本生效规则（Q04/Q09）仍待 T001 决策；当前实现只提供
  显式配置接口与保留策略，不自动合并或删除。
- VersionStore 只操作交付文件 `normalized/documents.jsonl`；采集管线批量写入时尚未逐条调用
  `plan_version`（T018 交付整理与 T019 验收时按 Q 项决定是否接入）。
