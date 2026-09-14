"""队列与失败账对账校验（S5-06）：待处理项状态必须与失败账处置一致。

补抓由失败账驱动、队列状态驱动多轮续接；两者不同步就会出现同一对象“队列 failed、
账本 recovered”的矛盾（第 85 轮修复写入路径，这里把不变量变成可复跑的检查）。
当前只把无歧义的一条不变量判为失败：待处理项为 failed 时，该 URL 的账本最新处置
不得是 recovered/skip。其余组合（例如既有成功记录之后又出现 404）有合法解释，
只如实计数，不判失败。失败账仍有未关闭记录属于正常待补抓状态，不判失败。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

from crawler.output.layout import DeliveryLayout
from crawler.validate.schema import load_jsonl_rows

CLOSED_ACTIONS = ("recovered", "skip")


@dataclass
class ReconcileReport:
    items_total: int = 0
    items_by_state: Dict[str, int] = field(default_factory=dict)
    open_failures: int = 0
    problems: List[dict] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems

    def as_row(self) -> dict:
        return {
            "ok": self.ok,
            "items_total": self.items_total,
            "items_by_state": dict(self.items_by_state),
            "open_failures": self.open_failures,
            "problems": list(self.problems),
        }


def reconcile_queue_and_failures(data_dir: Path) -> ReconcileReport:
    layout = DeliveryLayout(data_dir)
    report = ReconcileReport()
    items, _ = _pending_items(layout.pending_path)
    failures, _ = load_jsonl_rows(layout.failures_path, "manifests/failed_records.jsonl")
    latest: Dict[str, dict] = {}
    for _, row in failures:
        url = row.get("url")
        if url:
            # 文件为追加式：同一 URL 的最后一行即最新处置。
            latest[url] = row
    report.open_failures = sum(
        1 for row in latest.values() if row.get("final_action") not in CLOSED_ACTIONS
    )
    report.items_total = len(items)
    for item in items:
        state = item.get("state") or "unknown"
        report.items_by_state[state] = report.items_by_state.get(state, 0) + 1
    for item in items:
        if (item.get("state") or "") != "failed":
            continue
        row = latest.get(item.get("url"))
        if row is not None and row.get("final_action") in CLOSED_ACTIONS:
            report.problems.append(
                {
                    "key": item.get("key"),
                    "url": item.get("url"),
                    "item_state": "failed",
                    "ledger_action": row.get("final_action"),
                    "message": "待处理项为 failed，但失败账该 URL 已按 recovered/skip 关闭",
                }
            )
    return report


def _pending_items(path: Path):
    """读取待处理状态文件；缺失或损坏按空集/错误返回，不猜测内容。"""
    path = Path(path)
    if not path.is_file():
        return [], []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [], [{"file": "manifests/pending_items.json", "line": 0, "message": str(exc)}]
    rows = payload.get("items") or {}
    return [rows[key] for key in sorted(rows)], []
