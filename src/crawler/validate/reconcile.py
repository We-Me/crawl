"""队列与失败账对账校验（S5-06）：待处理项状态必须与失败账处置一致。

补抓由失败账驱动、队列状态驱动多轮续接；两者不同步就会出现同一对象“队列 failed、
账本 recovered”的矛盾（第 85 轮修复写入路径，这里把不变量变成可复跑的检查）。
当前只把无歧义的一条不变量判为失败：待处理项为 failed 时，该 URL 的账本最新处置
不得是 recovered/skip。其余组合（例如既有成功记录之后又出现 404）有合法解释，
只如实计数，不判失败。失败账仍有未关闭记录属于正常待补抓状态，不判失败。

R6：读取失败不再按空集吞掉。状态文件/失败账的读取、JSON 解析与结构错误都进入
problems，使 ``reconcile.ok=False``、``crawl check`` 返回非零；合法缺失（文件不存在）
与合法空状态（`items` 为空映射、JSONL 空文件）仍按零记录处理。检查只读，不覆盖或
重建损坏文件，错误信息带文件名与原因。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Mapping, Tuple

from crawler.output.layout import DeliveryLayout
from crawler.validate.schema import load_jsonl_rows

CLOSED_ACTIONS = ("recovered", "skip")

PENDING_LABEL = "manifests/pending_items.json"
FAILURES_LABEL = "manifests/failed_records.jsonl"

# 待处理项合法状态与种类；与 schedule.pending 的常量保持一致（此处重复字面量，
# 避免校验模块为常量引入发现器/解析器依赖）。
ITEM_STATES = frozenset({"pending", "processed", "failed", "skipped", "refresh"})
ITEM_KINDS = frozenset({"target", "attachment"})
ITEM_IDENTITY_FIELDS = ("key", "source_id", "kind", "url", "state")


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
    items, item_problems = _pending_items(layout.pending_path)
    report.problems.extend(item_problems)
    failures, failure_problems = load_jsonl_rows(layout.failures_path, FAILURES_LABEL)
    for problem in failure_problems:
        report.problems.append(
            {
                "file": problem.get("file", FAILURES_LABEL),
                "line": problem.get("line", 0),
                "message": f"失败账读取失败：{problem.get('message', '')}",
            }
        )
    latest: Dict[tuple, dict] = {}
    for _, row in failures:
        url = row.get("url")
        if url:
            # 文件为追加式：同一身份的最后一行即最新处置。身份与恢复关联一致
            # （来源 + URL + 原运行范围 + 母文档）：不能只按 URL 推断“全部任务已恢复”（R5/C）。
            latest[_ledger_identity(row)] = row
    report.open_failures = sum(
        1 for row in latest.values() if row.get("final_action") not in CLOSED_ACTIONS
    )
    report.items_total = len(items)
    for item in items:
        state = item.get("state") or "unknown"
        report.items_by_state[state] = report.items_by_state.get(state, 0) + 1
    if report.problems:
        # 状态不可信时不再据此推断“某任务已恢复”：只报告读取问题，不产生级联误判。
        return report
    for item in items:
        if (item.get("state") or "") != "failed":
            continue
        row = latest.get(_item_identity(item))
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


def _ledger_identity(row) -> tuple:
    """失败账行的恢复身份：来源 + URL + 原运行范围 + 母文档（缺失按 None）。"""
    return (
        row.get("source_id") or None,
        row.get("url"),
        row.get("scope_start_date") or None,
        row.get("doc_id") or None,
    )


def _item_identity(item) -> tuple:
    """待处理项的对账身份：与失败账同一口径。"""
    return (
        item.get("source_id") or None,
        item.get("url"),
        item.get("scope_start_date") or None,
        item.get("doc_id") or None,
    )


def _pending_items(path: Path) -> Tuple[List[dict], List[dict]]:
    """读取待处理状态文件；返回 (条目, 问题)。

    文件不存在是合法初始状态（空队列）；文件存在但不可读/不是合法 JSON/结构非法都
    作为问题返回，不静默降级为空队列。只读检查不写入、不重建任何文件。
    """
    path = Path(path)
    if not path.is_file():
        return [], []
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        return [], [_problem(PENDING_LABEL, 0, f"文件不是合法 UTF-8：{exc}")]
    except OSError as exc:
        return [], [_problem(PENDING_LABEL, 0, f"文件无法读取：{exc}")]
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        return [], [
            _problem(
                PENDING_LABEL,
                0,
                f"JSON 语法错误：{exc.msg}（第 {exc.lineno} 行第 {exc.colno} 列）",
            )
        ]
    if not isinstance(payload, Mapping):
        return [], [
            _problem(
                PENDING_LABEL,
                0,
                f"顶层应为 JSON 对象，实际 {type(payload).__name__}",
            )
        ]
    rows = payload.get("items", {})
    if rows is None:
        return [], [
            _problem(PENDING_LABEL, 0, "items 为 null，无法区分空队列与损坏状态；视为结构错误")
        ]
    if not isinstance(rows, Mapping):
        return [], [
            _problem(
                PENDING_LABEL,
                0,
                f"items 应为 JSON 对象，实际 {type(rows).__name__}",
            )
        ]
    items: List[dict] = []
    problems: List[dict] = []
    for key in sorted(rows):
        row = rows[key]
        if not isinstance(row, Mapping):
            problems.append(
                _problem(
                    PENDING_LABEL,
                    0,
                    f"条目 {key!r} 应为 JSON 对象，实际 {type(row).__name__}",
                )
            )
            continue
        invalid = [
            name
            for name in ITEM_IDENTITY_FIELDS
            if not isinstance(row.get(name), str) or not str(row.get(name)).strip()
        ]
        if invalid:
            problems.append(
                _problem(
                    PENDING_LABEL,
                    0,
                    f"条目 {key!r} 缺少合法身份字段（{'/'.join(invalid)} 应为非空字符串）",
                )
            )
            continue
        if row["state"] not in ITEM_STATES:
            problems.append(
                _problem(
                    PENDING_LABEL,
                    0,
                    f"条目 {key!r} 状态非法：{row['state']!r}，允许 {sorted(ITEM_STATES)}",
                )
            )
            continue
        if row["kind"] not in ITEM_KINDS:
            problems.append(
                _problem(
                    PENDING_LABEL,
                    0,
                    f"条目 {key!r} 种类非法：{row['kind']!r}，允许 {sorted(ITEM_KINDS)}",
                )
            )
            continue
        if row["key"] != key:
            problems.append(
                _problem(
                    PENDING_LABEL,
                    0,
                    f"条目身份不一致：映射键 {key!r} 与条目 key {row['key']!r} 不同",
                )
            )
            continue
        items.append(dict(row))
    return items, problems


def _problem(file: str, line: int, message: str) -> dict:
    return {"file": file, "line": int(line), "message": message}
