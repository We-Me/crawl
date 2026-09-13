"""按来源汇总当前数据根的覆盖状态（只读；S5-03/S5-04/S5-06 逐来源报告口径）。

用法：
    UV_CACHE_DIR=/tmp/uv-cache uv run --locked --no-python-downloads python tools/coverage_table.py \
        --data-dir data --config src/crawler/config/sources.yaml > 覆盖表.md

字段来源：sources.yaml（来源与发现方式）、manifests/discovery_cursors.json（遍历范围/终止原因）、
manifests/pending_items.json（主目标与附件状态）、manifests/crawl_manifest.jsonl（raw 留存）、
normalized/documents.jsonl 与 blocks.jsonl（已产出与近端追溯）、failed_records.jsonl（失败历史）。

只读、不联网；原件字节哈希级校验仍由 `crawl check` 完成（表内只统计原件可回指与账本哈希存在）。
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional


def load_rows(path: Path) -> List[dict]:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="按来源汇总数据根覆盖状态（只读）")
    parser.add_argument("--data-dir", default="data", help="数据根（默认 data）")
    parser.add_argument(
        "--config", default="src/crawler/config/sources.yaml", help="来源注册表 YAML"
    )
    args = parser.parse_args(argv)

    data_dir = Path(args.data_dir)
    layout_manifests = data_dir / "manifests"
    layout_normalized = data_dir / "normalized"

    registry_rows = read_json_config(Path(args.config))
    cursors = read_json(layout_manifests / "discovery_cursors.json").get("cursors", {})
    pending = read_json(layout_manifests / "pending_items.json").get("items", {})
    manifest = load_rows(layout_manifests / "crawl_manifest.jsonl")
    documents = load_rows(layout_normalized / "documents.jsonl")
    blocks = load_rows(layout_normalized / "blocks.jsonl")
    failures = load_rows(layout_manifests / "failed_records.jsonl")

    doc_source = {row.get("doc_id"): row.get("source_id") for row in documents if row.get("doc_id")}
    docs_with_blocks = Counter()
    for block in blocks:
        docs_with_blocks[block.get("doc_id")] += 1

    per_source = defaultdict(Counter)
    for row in pending.values():
        sid = row.get("source_id")
        kind = row.get("kind") or "target"
        per_source[sid][f"{kind}:{row.get('state')}"] += 1
    manifest_rows = Counter()
    manifest_hashed = Counter()
    manifest_raw_ok = Counter()
    for row in manifest:
        sid = row.get("source_id")
        manifest_rows[sid] += 1
        if row.get("sha256"):
            manifest_hashed[sid] += 1
        raw_path = row.get("raw_path")
        if raw_path and (data_dir / raw_path).is_file():
            manifest_raw_ok[sid] += 1
    doc_counts = Counter(row.get("source_id") for row in documents)
    block_counts = Counter()
    for block in blocks:
        block_counts[doc_source.get(block.get("doc_id"), "?")] += 1
    doc_raw_ok = Counter()
    for row in documents:
        raw_path = row.get("raw_path")
        if raw_path and (data_dir / raw_path).is_file():
            doc_raw_ok[row.get("source_id")] += 1
    failure_counts = Counter(row.get("source_id") for row in failures)

    cursor_rows = defaultdict(list)
    for row in cursors.values():
        cursor_rows[row.get("source_id")].append(row)

    print("| 来源 | 发现方式（主游标入口） | 遍历（游标） | 终止/续接原因 | 主目标 处理/待处理/复查/失败/跳过 | 附件 处理/待处理/失败 | raw 行（哈希/可回指） | 文档 | 块 | 失败账 |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    totals = Counter()
    for source in registry_rows:
        if not source.get("enabled", True):
            continue
        sid = source["source_id"]
        discovery = ",".join(source.get("discovery") or [])
        entry = None
        rows = sorted(
            cursor_rows.get(sid, []),
            key=lambda r: (-(r.get("pages_fetched") or 0), -(r.get("targets_found") or 0)),
        )
        if rows:
            main = rows[0]
            entry = re.sub(r"^https?://", "", str(main.get("entry") or ""))
            if len(entry) > 52:
                entry = entry[:51] + "…"
            extra = f"（+{len(rows) - 1} 其它入口）" if len(rows) > 1 else ""
            resume = ""
            if main.get("state") == "active" and main.get("next_url"):
                resume = f" → 续接 {str(main['next_url']).split('?')[-1]}"
            traversal = (
                f"{main.get('stage')} {main.get('state')} pages={main.get('pages_fetched')} "
                f"targets={main.get('targets_found')}{resume}{extra}"
            )
            reason = (main.get("note") or "").split("：")[0] or "-"
        else:
            traversal, reason = "无游标", "-"
        if entry:
            discovery = f"{discovery} `{entry}`"
        counts = per_source[sid]
        targets = [counts[f"target:{state}"] for state in ("processed", "pending", "refresh", "failed", "skipped")]
        attachments = [counts[f"attachment:{state}"] for state in ("processed", "pending", "failed")]
        total_row = (
            f"| {sid} | {discovery} | {traversal} | {reason} | "
            f"{targets[0]}/{targets[1]}/{targets[2]}/{targets[3]}/{targets[4]} | "
            f"{attachments[0]}/{attachments[1]}/{attachments[2]} | "
            f"{manifest_rows[sid]}（{manifest_hashed[sid]}/{manifest_raw_ok[sid]}） | "
            f"{doc_counts[sid]}（原件可回指 {doc_raw_ok[sid]}） | {block_counts[sid]} | {failure_counts[sid]} |"
        )
        print(total_row)
        totals["targets_processed"] += targets[0]
        totals["targets_pending"] += targets[1]
        totals["att_pending"] += attachments[1]
        totals["documents"] += doc_counts[sid]
        totals["blocks"] += block_counts[sid]
        totals["manifest"] += manifest_rows[sid]
    print(
        f"| **合计** | | | | 处理 {totals['targets_processed']} / 待处理 {totals['targets_pending']} | "
        f"附件待处理 {totals['att_pending']} | {totals['manifest']} | {totals['documents']} | "
        f"{totals['blocks']} | {sum(failure_counts.values())} |"
    )
    return 0


def read_json_config(path: Path) -> List[dict]:
    import yaml

    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    rows = []
    for entry in payload.get("sources") or []:
        adapter = entry.get("adapter") or {}
        rows.append(
            {
                "source_id": entry.get("source_id"),
                "discovery": adapter.get("discovery") or [],
                "enabled": entry.get("enabled", True),
            }
        )
    return rows


if __name__ == "__main__":
    raise SystemExit(main())
