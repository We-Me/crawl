"""失败账查询、补抓关闭与运行恢复（T016）。

失败账保持只追加：补抓成功或转为人工处理时追加一条处置行，不删除、不改写历史
失败；原件与既有成功下载不回退。`open_failures` 取同一身份的最后一条记录判断是否
仍未关闭；身份为 (source_id, url, stage, scope_start_date, doc_id)——同一 URL 在不同
来源、运行范围或不同母文档下的失败互不覆盖（R5/C）。运行恢复额外从账本中找出
“已下载但还没有文档”的条目，供重解析补全，不必重新下载。
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence

from crawler.output.failures_writer import FAILURE_STAGES, FailureWriter
from crawler.output.jsonl import append_jsonl, read_jsonl
from crawler.output.layout import DeliveryLayout

logger = logging.getLogger(__name__)

MANUAL_ACTION = "manual_review"
# 未关闭 = 仍需处置：record_only/retry_later 等待补抓，manual_review 等待人工处置。
# manual_review 不等于 recovered：它保持可见（plan/check/失败数），直到人工按同一身份关闭。
OPEN_ACTIONS = ("record_only", "retry_later", MANUAL_ACTION)
CLOSED_ACTIONS = ("recovered", "skip")


class FailureLedgerError(ValueError):
    """失败账操作非法。"""


class FailureLedger:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.layout = DeliveryLayout(self.data_dir)
        self.path = self.layout.failures_path
        self.writer = FailureWriter(self.data_dir)

    def load(self) -> List[dict]:
        return read_jsonl(self.path)

    def latest_by_key(self) -> Dict[tuple, dict]:
        latest: Dict[tuple, dict] = {}
        for row in self.load():
            latest[
                (
                    row.get("source_id") or None,
                    row.get("url"),
                    row.get("stage"),
                    row.get("scope_start_date") or None,
                    row.get("doc_id") or None,
                )
            ] = row
        return latest

    def open_failures(self) -> List[dict]:
        open_rows = [
            row for row in self.latest_by_key().values()
            if row.get("final_action") in OPEN_ACTIONS
        ]
        logger.debug("未关闭失败数=%d", len(open_rows))
        return open_rows

    def history_of(self, url: str) -> List[dict]:
        return [row for row in self.load() if row.get("url") == url]

    def latest_rows(self, rows: Optional[Sequence[dict]] = None) -> List[dict]:
        """每个身份（来源 + URL + stage + 范围 + 母文档）的最后一行，按 URL 稳定排序。"""
        latest: Dict[tuple, dict] = {}
        for index, row in enumerate(self.load() if rows is None else rows):
            key = (
                row.get("source_id") or None,
                row.get("url"),
                row.get("stage"),
                row.get("scope_start_date") or None,
                row.get("doc_id") or None,
            )
            latest[key] = (index, row)
        return [row for _, row in sorted(latest.values(), key=lambda item: item[0])]

    def find_latest(
        self,
        *,
        url: str,
        stage: Optional[str] = None,
        source_id: Optional[str] = None,
        scope_start_date: Optional[str] = None,
        doc_id: Optional[str] = None,
    ) -> Optional[dict]:
        """按显式身份取最后一行；归属没写全就不动（返回 None），宁可人工补齐后再处置。

        身份 = (source_id, url, stage, scope_start_date, doc_id)。记录里带值的归属维度
        调用方必须显式给出：否则无法确认要关闭的是哪个对象（同 URL 可能来自别的来源、
        别的运行范围或另一份母文档），交回调用方按 identities_for 列出的身份重试。
        未给 stage 时只接受该 URL 唯一的 stage。
        """
        candidates = [row for row in self.load() if row.get("url") == url]
        if source_id is not None:
            candidates = [
                row for row in candidates if (row.get("source_id") or None) == source_id
            ]
        elif any((row.get("source_id") or None) is not None for row in candidates):
            return None
        if scope_start_date is not None:
            candidates = [
                row
                for row in candidates
                if (row.get("scope_start_date") or None) == scope_start_date
            ]
        elif any((row.get("scope_start_date") or None) is not None for row in candidates):
            return None
        if doc_id is not None:
            candidates = [
                row for row in candidates if (row.get("doc_id") or None) == doc_id
            ]
        elif any((row.get("doc_id") or None) is not None for row in candidates):
            return None
        if stage is not None:
            candidates = [row for row in candidates if row.get("stage") == stage]
        else:
            stages = {row.get("stage") for row in candidates}
            if len(stages) != 1:
                return None
        if not candidates:
            return None
        return candidates[-1]

    def identities_for(self, url: str) -> List[dict]:
        """该 URL 下出现过的身份（供人工处置时选择），每个身份取最后一行。"""
        rows = [row for row in self.load() if row.get("url") == url]
        return self.latest_rows(rows)

    def default_raw_path(self, crawl_id: str) -> Optional[str]:
        for row in read_jsonl(self.layout.manifest_path):
            if row.get("crawl_id") == crawl_id:
                return row.get("raw_path")
        return None

    def record_resolution(
        self,
        failure: Mapping,
        *,
        now: datetime,
        note: str,
        crawl_id: Optional[str] = None,
        action: str = "recovered",
    ) -> dict:
        """追加处置行；保留原失败行，用同一身份关闭该失败。"""
        if action not in CLOSED_ACTIONS + (MANUAL_ACTION,):
            raise FailureLedgerError(f"未知处置动作：{action!r}")
        stage = str(failure.get("stage") or "fetch")
        if stage not in FAILURE_STAGES:
            raise FailureLedgerError(f"未知失败阶段：{stage!r}")
        row = {
            "source_id": str(failure.get("source_id") or ""),
            "url": str(failure.get("url") or ""),
            "time": now.isoformat(),
            "stage": stage,
            "error_type": "resolved" if action in CLOSED_ACTIONS else "needs_manual_review",
            "message": note,
            "retry_count": int(failure.get("retry_count") or 0) + 1,
            "final_action": action,
            "previous_time": failure.get("time"),
            "attempts_before": int(failure.get("retry_count") or 0),
        }
        recovered_crawl_id = crawl_id or failure.get("crawl_id")
        if recovered_crawl_id:
            row["crawl_id"] = recovered_crawl_id
        if failure.get("referrer_url"):
            row["referrer_url"] = failure["referrer_url"]
        if failure.get("scope_start_date"):
            # 范围与母文档身份随处置行保留：对账/补抓按身份匹配，不按 URL 全局关闭（R5）。
            row["scope_start_date"] = failure["scope_start_date"]
        if failure.get("doc_id"):
            row["doc_id"] = failure["doc_id"]
        append_jsonl(self.path, [row])
        logger.info("失败处置 url=%s stage=%s action=%s", row["url"], stage, action)
        return row

    def pending_documents(
        self,
        *,
        limit: Optional[int] = None,
    ) -> List[dict]:
        """账本中有成功下载、但规范化里还没有文档的原件：可本地重解析补全。"""
        manifest_rows = read_jsonl(self.layout.manifest_path)
        document_rows = read_jsonl(self.layout.documents_path)
        documented = {doc_id for row in document_rows for doc_id in row.get("crawl_ids") or []}
        # 身份含来源：别的来源的未关闭失败不得把本来源的原件排除在重解析候选之外。
        open_keys = {
            (row.get("source_id") or None, row.get("url"), row.get("stage"))
            for row in self.open_failures()
        }
        pending = []
        for row in manifest_rows:
            crawl_id = row.get("crawl_id")
            if not crawl_id or crawl_id in documented:
                continue
            if row.get("discovery_method") == "attachment":
                continue
            urls = {row.get("final_url"), row.get("requested_url")}
            if any(
                key[0] == (row.get("source_id") or None) and key[1] in urls
                for key in open_keys
            ):
                continue
            pending.append(row)
        if limit is not None:
            pending = pending[:limit]
        return pending
