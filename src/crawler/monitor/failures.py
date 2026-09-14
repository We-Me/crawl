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

from crawler.output.atomic import LockUnavailable
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


class FailureQueueSyncError(RuntimeError):
    """处置行已写入失败账，但队列回写失败（P7-02）。

    必须显式报告：调用方不得在队列未同步时声称处置成功；按同一身份重复处置是幂等的，
    修复队列问题（锁/权限/磁盘）后可直接重跑同一命令重试。
    """

    def __init__(self, message: str, row: Mapping) -> None:
        super().__init__(message)
        self.row = dict(row)


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

        区分“未指定”与“显式空值”（P7-03）：参数缺省 None 表示未指定；显式传空字符串
        表示要选中该字段为空的记录（同 URL 同时有带日期/不带日期、带 doc_id/不带
        doc_id 的记录时，操作者据此准确选中空值身份，不必手改 JSONL）。
        """
        candidates = [row for row in self.load() if row.get("url") == url]
        for field, value in (
            ("source_id", source_id),
            ("scope_start_date", scope_start_date),
            ("doc_id", doc_id),
        ):
            if value is None:
                if any((row.get(field) or None) is not None for row in candidates):
                    return None
                continue
            wanted = value or None
            candidates = [
                row for row in candidates if (row.get(field) or None) == wanted
            ]
        if stage is not None:
            candidates = [
                row
                for row in candidates
                if (row.get("stage") or None) == (stage or None)
            ]
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

    def raw_path_map(self) -> Dict[str, str]:
        """一次读出账本里的 crawl_id -> raw_path（错误查询/摘要批量解析用，只读）。"""
        mapping: Dict[str, str] = {}
        for row in read_jsonl(self.layout.manifest_path):
            crawl_id = row.get("crawl_id")
            raw_path = row.get("raw_path")
            if crawl_id and raw_path:
                mapping[crawl_id] = raw_path
        return mapping

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

    def resolve_with_queue(
        self,
        failure: Mapping,
        *,
        now: datetime,
        note: str,
        crawl_id: Optional[str] = None,
        action: str = "recovered",
    ) -> dict:
        """人工处置：追加处置行并按完整身份协调同对象的待处理项（P7-02）。

        - 追加写口径不变：历史失败行不改写，只追加一条处置行；
        - 队列协调按对象身份（来源 + URL + 原运行范围 + 母文档）：同 URL 的其他范围、
          别的母文档或无关对象都不受影响；
        - 同对象仍有其他未关闭阶段时不标记完成：队列保持 failed，账本仍有开放行，
          对账保持一致，并明确报告未越权关闭哪些阶段；
        - manual_review 保持未关闭：队列状态不改写（保持可见），也不自动补抓；
        - 对象仍有正文待续（continuation）时，recovered 只关闭本次失败，对象保持
          pending 继续续作，不清空续作位置；
        - 队列回写失败抛 :class:`FailureQueueSyncError`：处置行已记录，按同一身份
          重复处置幂等，可修复后重试。
        """
        row = self.record_resolution(
            failure, now=now, note=note, crawl_id=crawl_id, action=action
        )
        queue = self._sync_queue_after_resolution(
            row, action=action, note=note, crawl_id=crawl_id
        )
        return {"resolution": row, "queue": queue}

    def _sync_queue_after_resolution(
        self,
        row: Mapping,
        *,
        action: str,
        note: str,
        crawl_id: Optional[str],
    ) -> dict:
        from crawler.schedule.pending import (
            STATE_PENDING,
            STATE_PROCESSED,
            STATE_SKIPPED,
            PendingStore,
            PendingStoreError,
        )

        identity = _object_identity(row)
        queue = {
            "identity": {
                "source_id": identity[0],
                "url": identity[1],
                "scope_start_date": identity[2],
                "doc_id": identity[3],
            },
            "matched": [],
            "updated": {},
            "unchanged": [],
            "kept_open": [],
            "status": "no_item",
        }
        try:
            matched = [
                item
                for item in PendingStore(self.data_dir).all_items()
                if _same_queue_object(item, identity)
            ]
        except (OSError, PendingStoreError, LockUnavailable) as exc:
            raise FailureQueueSyncError(f"队列读取失败：{exc}", row) from exc
        queue["matched"] = [item.key for item in matched]

        if action == MANUAL_ACTION:
            # 人工态保持未关闭：不改状态、不清续作位置，只让操作者在队列上看到处置。
            queue["status"] = "manual_review"
            queue["message"] = "manual_review 保持未关闭：队列状态不变，不自动补抓"
            for item in matched:
                new_note = f"人工处置 manual_review：{note}（保持未关闭，不自动补抓）"
                if item.note == new_note:
                    queue["unchanged"].append(item.key)
                    continue
                self._mark_queue_item(item, item.state, new_note, crawl_id)
                queue["updated"][item.key] = item.state
            return queue

        open_rows = [
            open_row
            for open_row in self.open_failures()
            if _object_identity(open_row) == identity
        ]
        if open_rows:
            # 同对象还有别的未关闭阶段：不能一条处置把整个对象标成完成。
            queue["status"] = "blocked"
            queue["kept_open"] = sorted(
                {str(open_row.get("stage") or "unknown") for open_row in open_rows}
            )
            queue["message"] = "同对象仍有未关闭阶段：队列保持现状，未标记完成"
            return queue

        target_state = STATE_SKIPPED if action == "skip" else STATE_PROCESSED
        for item in matched:
            new_state = target_state
            new_note = f"人工处置 {action}：{note}"
            if action == "recovered" and item.continuation is not None:
                # 对象仍有正文待续：不得标完成、不得清空续作位置，保持 pending 续作。
                new_state = STATE_PENDING
                new_note = f"{new_note}；对象仍有正文待续，队列保持 pending 续作"
            if item.state == new_state and item.note == new_note:
                queue["unchanged"].append(item.key)
                continue
            self._mark_queue_item(item, new_state, new_note, crawl_id)
            queue["updated"][item.key] = new_state
        if matched:
            queue["status"] = "synced"
            queue["message"] = "队列已按同一身份协调"
        else:
            queue["message"] = "未找到同身份待处理项：账本处置已记录，队列无需协调"
        return queue

    def _mark_queue_item(
        self,
        item,
        state: str,
        note: str,
        crawl_id: Optional[str],
    ) -> None:
        from crawler.schedule.pending import PendingStore, PendingStoreError

        try:
            PendingStore(self.data_dir).mark(
                item.key, state=state, note=note, crawl_id=crawl_id
            )
        except (OSError, PendingStoreError, LockUnavailable) as exc:
            raise FailureQueueSyncError(
                f"队列回写失败 key={item.key}：{exc}（处置行已记录，可重复处置重试）",
                {"url": item.url, "key": item.key, "state": state},
            ) from exc

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


def _object_identity(row: Mapping) -> tuple:
    """对象身份（不含阶段）：来源 + URL + 原运行范围 + 母文档（缺失按 None）。"""
    return (
        row.get("source_id") or None,
        row.get("url") or None,
        row.get("scope_start_date") or None,
        row.get("doc_id") or None,
    )


def _same_queue_object(item, identity: tuple) -> bool:
    """待处理项与处置行是否同一对象；缺失值按缺失值比较，不推断（P7-02）。"""
    source_id, url, scope_start_date, doc_id = identity
    return (
        (item.source_id or None) == source_id
        and (item.url or None) == url
        and (item.scope_start_date or None) == scope_start_date
        and (item.doc_id or None) == doc_id
    )
