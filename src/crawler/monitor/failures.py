"""失败账查询、补抓关闭与运行恢复（T016）。

失败账保持只追加：补抓成功或转为人工处理时追加一条处置行，不删除、不改写历史
失败；原件与既有成功下载不回退。`open_failures` 取同一 (url, stage) 的最后一条
记录判断是否仍未关闭。运行恢复额外从账本中找出“已下载但还没有文档”的条目，
供重解析补全，不必重新下载。
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

OPEN_ACTIONS = ("record_only", "retry_later")
CLOSED_ACTIONS = ("recovered", "skip")
MANUAL_ACTION = "manual_review"


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
            latest[(row.get("url"), row.get("stage"))] = row
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
        """追加处置行；保留原失败行，用同一 (url, stage) 关闭该失败。"""
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
        open_keys = {(row.get("url"), row.get("stage")) for row in self.open_failures()}
        pending = []
        for row in manifest_rows:
            crawl_id = row.get("crawl_id")
            if not crawl_id or crawl_id in documented:
                continue
            if row.get("discovery_method") == "attachment":
                continue
            if any(key[0] == row.get("final_url") for key in open_keys):
                continue
            pending.append(row)
        if limit is not None:
            pending = pending[:limit]
        return pending
