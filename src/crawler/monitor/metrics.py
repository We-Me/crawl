"""运行计数、重复与异常统计、交付对账（T017，FR-018）。

四类成果分别计数，不把请求次数当文档数：
- requests：HTTP 请求尝试次数（含重试与条件请求），按网络操作计数；
- resources：成功归档的原件资源数，等于本次运行的 manifest 追加行数；
- documents：本次新写入的逻辑文档数，等于 documents.jsonl 追加行数；
- blocks：本次新写入的结构块数，等于 blocks.jsonl 追加行数。

成功、失败、跳过按不同口径分开记录：成功按资源数，失败按失败操作数，跳过按目标数。
重复统计只报候选分组，保留全部来源（Q05）；近似重复阈值属 Q11 待决项，未显式传入时
报告 not_computed，不用未决策阈值冒充结果。对账结果写入 logs/metrics.json，并在
logs/metrics_history.jsonl 追加同一行，供跨运行核对。
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Mapping, Optional, Sequence

from crawler.dedup.duplicates import EXACT_BYTES, EXACT_TEXT, NEAR_TEXT, group_row_counts
from crawler.dedup.duplicates import find_exact_duplicates, find_near_duplicates
from crawler.output.jsonl import append_jsonl, read_jsonl
from crawler.output.layout import (
    CRAWLER_LOG_FILENAME,
    DeliveryLayout,
    METRICS_FILENAME,
    METRICS_HISTORY_FILENAME,
)

logger = logging.getLogger(__name__)

NEAR_NOT_COMPUTED_REASON = "Q11 未决：近似重复阈值必须显式提供，不自动判定"

COUNTING_RULES = {
    "requests": "HTTP 请求尝试次数（含重试与条件请求），不等于文档数",
    "resources": "成功归档的原件资源数，等于本次 manifest 追加行数",
    "documents": "本次新写入的逻辑文档数，等于 documents.jsonl 追加行数",
    "blocks": "本次新写入的结构块数，等于 blocks.jsonl 追加行数",
    "failures": "按操作记录的失败条数，等于本次 failed_records.jsonl 追加行数",
    "skipped": "未产生新成果的跳过目标数（含 304 未变化与边界跳过）",
    "success": "成功口径按资源数（resources），不按请求数",
    "budget": "一次运行共享的请求数/截止时间预算；请求在发送前扣减，max-items 不计入",
}

OUTPUT_FILES = (
    ("crawl_manifest_rows", "manifest_path"),
    ("documents_rows", "documents_path"),
    ("blocks_rows", "blocks_path"),
    ("failed_rows", "failures_path"),
)


class MetricsConfigError(ValueError):
    """指标参数非法（例如阈值越界）。"""


@dataclass
class RunMetrics:
    run_id: str
    source_id: str
    kind: str
    started_at: str
    finished_at: str
    status: str
    counters: Mapping = field(default_factory=dict)
    status_counts: Mapping = field(default_factory=dict)
    failures_by_stage: Mapping = field(default_factory=dict)
    failures_by_type: Mapping = field(default_factory=dict)
    skipped_by_reason: Mapping = field(default_factory=dict)
    duplicates: Mapping = field(default_factory=dict)
    request_controls: Mapping = field(default_factory=dict)
    budget: Mapping = field(default_factory=dict)
    stop_reason: Optional[str] = None
    stop_message: str = ""
    unprocessed: Optional[int] = None
    outputs: Mapping = field(default_factory=dict)
    deltas: Mapping = field(default_factory=dict)
    expected_deltas: Mapping = field(default_factory=dict)
    reconciliation: Mapping = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)

    def as_row(self) -> dict:
        row = {
            "run_id": self.run_id,
            "source_id": self.source_id,
            "kind": self.kind,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "status": self.status,
            "counting_rules": dict(COUNTING_RULES),
            "counters": dict(self.counters),
            "status_counts": dict(self.status_counts),
            "failures_by_stage": dict(self.failures_by_stage),
            "failures_by_type": dict(self.failures_by_type),
            "skipped_by_reason": dict(self.skipped_by_reason),
            "duplicates": dict(self.duplicates),
            "request_controls": dict(self.request_controls),
            "budget": dict(self.budget),
            "stop": {
                "reason": self.stop_reason,
                "message": self.stop_message,
                "unprocessed": self.unprocessed,
            },
            "outputs": dict(self.outputs),
            "deltas": dict(self.deltas),
            "expected_deltas": dict(self.expected_deltas),
            "reconciliation": dict(self.reconciliation),
            "notes": list(self.notes),
        }
        return row


def run_id_for(source_id: str, finished_at: str) -> str:
    """运行标识：来源 + 完成时间（ISO 8601），同一来源同一秒的重复运行需自行区分。"""
    stamp = finished_at.replace("-", "").replace(":", "").split("+")[0].split(".")[0]
    return f"{source_id}_{stamp}"


def count_rows(path: Path) -> int:
    """统计 JSONL 非空行数；文件不存在按 0 计（零失败可为空文件或不存在）。"""
    path = Path(path)
    if not path.is_file():
        return 0
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def output_stats(data_dir: Path) -> dict:
    """交付文件当前行数与原件文件数快照，用于计算本次运行增量。"""
    layout = DeliveryLayout(data_dir)
    stats = {name: count_rows(getattr(layout, attribute)) for name, attribute in OUTPUT_FILES}
    raw_root = layout.raw_dir
    stats["raw_files"] = (
        sum(1 for item in raw_root.rglob("*") if item.is_file()) if raw_root.is_dir() else 0
    )
    return stats


def deltas_between(before: Mapping, after: Mapping) -> dict:
    """本次运行的追加量；键保持与 output_stats 一致。"""
    keys = sorted(set(before) | set(after))
    return {key: int(after.get(key, 0)) - int(before.get(key, 0)) for key in keys}


def duplicate_stats(
    documents: Sequence[Mapping],
    *,
    threshold: Optional[float] = None,
    similarity=None,
) -> dict:
    """重复候选统计；分组只报告，不删除、不合并任何文档。"""
    if threshold is not None and not 0 < threshold <= 1:
        raise MetricsConfigError(f"近似重复阈值必须在 (0, 1]：{threshold!r}")
    exact_groups = find_exact_duplicates(documents)
    exact_counts = group_row_counts(exact_groups)
    row = {
        "policy": "keep_all_sources",
        "scope_documents": len(documents),
        EXACT_BYTES: {"groups": exact_counts.get(EXACT_BYTES, 0)},
        EXACT_TEXT: {"groups": exact_counts.get(EXACT_TEXT, 0)},
        "exact_groups": len(exact_groups),
        "duplicate_documents": sum(group.as_row()["member_count"] for group in exact_groups),
    }
    if threshold is None:
        row[NEAR_TEXT] = {"status": "not_computed", "reason": NEAR_NOT_COMPUTED_REASON}
    else:
        near_groups = find_near_duplicates(documents, threshold=threshold, similarity=similarity)
        row[NEAR_TEXT] = {
            "status": "computed",
            "threshold": threshold,
            "groups": len(near_groups),
            "candidates": [group.as_row() for group in near_groups],
        }
    return row


def duplicate_stats_from_files(
    data_dir: Path, *, threshold: Optional[float] = None, similarity=None
) -> dict:
    """对交付文件 normalized/documents.jsonl 计算重复候选统计。"""
    documents: Iterable[dict] = read_jsonl(DeliveryLayout(data_dir).documents_path)
    return duplicate_stats(list(documents), threshold=threshold, similarity=similarity)


def build_metrics(
    *,
    source_id: str,
    kind: str,
    started_at: str,
    finished_at: str,
    counters: Mapping,
    before: Mapping,
    after: Mapping,
    failures: Iterable[Mapping] = (),
    skipped: Iterable = (),
    duplicates: Optional[Mapping] = None,
    request_controls: Optional[Mapping] = None,
    expected_deltas: Optional[Mapping] = None,
    stop_reason: Optional[str] = None,
    stop_message: str = "",
    unprocessed: Optional[int] = None,
    budget: Optional[Mapping] = None,
) -> RunMetrics:
    """汇总一次运行：计数、状态分布、异常分类、重复候选与对账。"""
    counters = {key: int(value) for key, value in dict(counters).items()}
    failures = [dict(row) for row in failures]
    failures_by_stage = _count_by(failures, "stage")
    failures_by_type = _count_by(failures, "error_type")
    skipped_by_reason = _count_skipped(skipped)
    deltas = deltas_between(before, after)
    status = _status_of(counters, stop_reason=stop_reason)
    notes = _notes_of(
        counters,
        failures_by_stage,
        skipped_by_reason,
        stop_reason=stop_reason,
        stop_message=stop_message,
        unprocessed=unprocessed,
    )
    metrics = RunMetrics(
        run_id=run_id_for(source_id, finished_at),
        source_id=source_id,
        kind=kind,
        started_at=started_at,
        finished_at=finished_at,
        status=status,
        counters=counters,
        status_counts={
            "success": counters.get("resources", 0),
            "failed": counters.get("failures", 0),
            "skipped": counters.get("skipped", 0),
            "not_modified": counters.get("not_modified", 0),
        },
        failures_by_stage=failures_by_stage,
        failures_by_type=failures_by_type,
        skipped_by_reason=skipped_by_reason,
        duplicates=dict(duplicates or {}),
        request_controls=dict(request_controls or {}),
        budget=dict(budget or {}),
        stop_reason=stop_reason,
        stop_message=stop_message,
        unprocessed=unprocessed,
        outputs=dict(after),
        deltas=deltas,
        expected_deltas={key: int(value) for key, value in dict(expected_deltas or {}).items()},
        notes=notes,
    )
    metrics.reconciliation = reconcile(metrics)
    return metrics


def reconcile(metrics: RunMetrics) -> dict:
    """按已定口径核对计数与交付文件增量；差异逐条列出，不静默容忍。"""
    checks: List[dict] = []

    def check(name: str, expected, actual, detail: str) -> None:
        checks.append(
            {
                "name": name,
                "expected": expected,
                "actual": actual,
                "ok": expected == actual,
                "detail": detail,
            }
        )

    deltas = dict(metrics.deltas)
    counters = dict(metrics.counters)

    def expected(key: str) -> int:
        if key in metrics.expected_deltas:
            return int(metrics.expected_deltas[key])
        return int(counters.get(key, 0))

    check(
        "资源数与账本追加行数一致",
        expected("resources"),
        deltas.get("crawl_manifest_rows", 0),
        "resources 按成功归档资源计数，等于 crawl_manifest.jsonl 追加行数",
    )
    check(
        "文档数与 documents 追加行数一致",
        expected("documents"),
        deltas.get("documents_rows", 0),
        "documents 按 logical document 计数",
    )
    check(
        "块数与 blocks 追加行数一致",
        expected("blocks"),
        deltas.get("blocks_rows", 0),
        "blocks 按结构块计数",
    )
    check(
        "失败数与失败账追加行数一致",
        expected("failures"),
        deltas.get("failed_rows", 0),
        "failures 按失败操作计数，不按文档计数",
    )
    check(
        "失败阶段分布合计等于失败数",
        counters.get("failures", 0),
        sum(int(value) for value in metrics.failures_by_stage.values()),
        "按 discover/fetch/parse/normalize/validate 阶段分类",
    )
    check(
        "异常类型分布合计等于失败数",
        counters.get("failures", 0),
        sum(int(value) for value in metrics.failures_by_type.values()),
        "按 error_type 分类",
    )
    check(
        "跳过原因分布合计等于跳过数",
        counters.get("skipped", 0),
        sum(int(value) for value in metrics.skipped_by_reason.values()),
        "跳过按原因分类，304 单列",
    )
    duplicates = dict(metrics.duplicates)
    if duplicates:
        policy = duplicates.get("policy")
        check(
            "重复候选保留全部来源",
            "keep_all_sources",
            policy,
            "去重只报候选，不删除、不合并文档（Q05 候选）",
        )
        near = dict(duplicates.get(NEAR_TEXT, {}))
        check(
            "近似重复状态明确",
            True,
            near.get("status") in ("computed", "not_computed"),
            "未显式给出 Q11 阈值时必须报 not_computed",
        )
    discrepancies = [item["name"] for item in checks if not item["ok"]]
    return {"ok": not discrepancies, "checks": checks, "discrepancies": discrepancies}


def write_metrics(data_dir: Path, metrics: RunMetrics) -> Path:
    """原子写出 logs/metrics.json（最近一次运行），并追加 logs/metrics_history.jsonl。"""
    layout = DeliveryLayout(data_dir)
    logs = layout.logs_dir
    logs.mkdir(parents=True, exist_ok=True)
    path = layout.metrics_path
    row = metrics.as_row()
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(row, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)
    append_jsonl(layout.metrics_history_path, [row])
    logger.info(
        "运行指标 run_id=%s status=%s metrics=%s reconciliation_ok=%s",
        metrics.run_id,
        metrics.status,
        path,
        metrics.reconciliation.get("ok"),
    )
    return path


def read_metrics(data_dir: Path) -> Optional[dict]:
    """读取最近一次运行指标；不存在时返回 None。"""
    path = DeliveryLayout(data_dir).metrics_path
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _count_by(rows: Sequence[Mapping], key: str) -> dict:
    counts: dict = {}
    for row in rows:
        value = str(row.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _count_skipped(skipped: Iterable) -> dict:
    counts: dict = {}
    for item in skipped:
        reason = getattr(item, "reason", None)
        if reason is None and isinstance(item, Mapping):
            reason = item.get("reason")
        label = "not_modified" if reason and "304" in str(reason) else str(reason or "unknown")
        counts[label] = counts.get(label, 0) + 1
    return dict(sorted(counts.items()))


def _status_of(counters: Mapping, *, stop_reason: Optional[str] = None) -> str:
    if stop_reason:
        obtained = int(counters.get("resources", 0)) + int(counters.get("documents", 0))
        return "partial" if obtained else "stopped"
    failures = int(counters.get("failures", 0))
    obtained = int(counters.get("resources", 0)) + int(counters.get("documents", 0))
    if failures and obtained:
        return "partial"
    if failures:
        return "failed"
    if not any(int(counters.get(key, 0)) for key in counters):
        return "empty"
    return "ok"


def _notes_of(
    counters: Mapping,
    failures_by_stage: Mapping,
    skipped_by_reason: Mapping,
    *,
    stop_reason: Optional[str] = None,
    stop_message: str = "",
    unprocessed: Optional[int] = None,
) -> List[str]:
    notes: List[str] = []
    if stop_reason:
        detail = f"停止原因 {stop_reason}"
        if stop_message:
            detail += f"：{stop_message}"
        if unprocessed is not None:
            detail += f"；未处理 {unprocessed} 项，已完成成果保留"
        notes.append(detail)
    if int(counters.get("not_modified", 0)) and not int(counters.get("resources", 0)):
        notes.append("本次无新增成果：目标未变化（304），复用此前原件与账本")
    if int(counters.get("skipped", 0)):
        notes.append(
            "跳过 " + "、".join(f"{key}={value}" for key, value in skipped_by_reason.items())
        )
    if failures_by_stage:
        notes.append("失败阶段 " + "、".join(f"{key}={value}" for key, value in failures_by_stage.items()))
    return notes
