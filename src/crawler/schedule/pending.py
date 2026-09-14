"""待处理项存储（S5-06）：有限预算多轮运行继续推进未完成部分。

一次运行受请求预算、截止时间与 --max-items 限制时，尚未尝试的目标与附件不能只靠
日志记录：重新 collect 若每次从入口重新从头选择，前面的目标会反复消耗预算，后面的
目标永远到不了。这里按来源保存待处理项状态，使多轮有限运行真正向前推进：

- 目标在发现后入队（state=pending），处理后按结果标记 processed/failed/skipped；
- 已成功处理的目标在后续运行再次被发现时标记为 refresh：重新检查（条件请求可得 304），
  排在新待处理项之后，不阻塞推进；
- 预算停止时未尝试的附件以 kind=attachment 入队，保留母文档与页面关联；
- 失败任务仍按失败账（failed_records.jsonl）记录，不在这里混写为“待处理”；
- 状态文件是抓取行为索引，不属于六项交付成果；格式变化在结构对照中登记。

排队顺序：pending（按入队序号）→ refresh（按上次尝试时间），先补齐从未尝试的目标，
再复查旧目标。已成功留存的原件、账本与文档不因排队状态变化而被覆盖或删除。
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from crawler.discover.discoverer import DiscoveredTarget
from crawler.output.atomic import atomic_write_json, file_lock
from crawler.output.layout import DeliveryLayout

logger = logging.getLogger(__name__)

STATE_PENDING = "pending"
STATE_PROCESSED = "processed"
STATE_FAILED = "failed"
STATE_SKIPPED = "skipped"
STATE_REFRESH = "refresh"

KIND_TARGET = "target"
KIND_ATTACHMENT = "attachment"

OPEN_STATES = (STATE_PENDING, STATE_REFRESH)


@dataclass(frozen=True)
class PendingItem:
    """一个持久化的待处理项；key 同时编码来源、范围与对象身份。"""

    key: str
    source_id: str
    kind: str
    url: str
    state: str
    scope_start_date: Optional[str] = None
    discovery_method: Optional[str] = None
    referrer_url: Optional[str] = None
    keyword: Optional[str] = None
    title_hint: Optional[str] = None
    doc_id: Optional[str] = None
    parent_url: Optional[str] = None
    filename: Optional[str] = None
    file_type: Optional[str] = None
    attempts: int = 0
    sequence: int = 0
    enqueued_at: Optional[str] = None
    last_attempt_at: Optional[str] = None
    note: Optional[str] = None
    crawl_id: Optional[str] = None
    raw_path: Optional[str] = None
    sha256: Optional[str] = None
    previous_state: Optional[str] = None


class PendingStoreError(ValueError):
    """待处理状态文件损坏或参数非法。"""


def item_key(
    *,
    kind: str,
    source_id: str,
    scope_start_date: Optional[str],
    url: str,
    doc_id: Optional[str] = None,
) -> str:
    """待处理项身份：同一对象在同一来源同一运行范围内只保留一行。"""
    scope = scope_start_date or "-"
    if kind == KIND_ATTACHMENT:
        return f"{kind}|{source_id}|{scope}|{doc_id or '-'}|{url}"
    return f"{kind}|{source_id}|{scope}|{url}"


class PendingStore:
    """按数据根保存待处理项；JSON 原子写入，读取按 key 稳定排序。"""

    def __init__(self, data_dir: Path) -> None:
        self.path = DeliveryLayout(data_dir).pending_path

    def load(self) -> Dict[str, PendingItem]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise PendingStoreError(f"待处理状态文件损坏：{self.path}") from exc
        rows = payload.get("items") or {}
        return {key: PendingItem(**row) for key, row in rows.items()}

    def get(self, key: str) -> Optional[PendingItem]:
        return self.load().get(key)

    def all_items(self) -> List[PendingItem]:
        items = self.load()
        return [items[key] for key in sorted(items)]

    def target_urls(self, source_id: str, scope_start_date: Optional[str] = None) -> set:
        """已登记的主目标 URL 集合（含待处理、已处理、失败与跳过），供发现增量核对。"""
        return {
            item.url
            for item in self.load().values()
            if item.kind == KIND_TARGET
            and item.source_id == source_id
            and (scope_start_date is None or item.scope_start_date == scope_start_date)
        }

    def enqueue_targets(
        self,
        *,
        source_id: str,
        targets: Sequence[DiscoveredTarget],
        scope_start_date: Optional[str],
        enqueued_at: str,
        replay: bool = False,
    ) -> Dict[str, int]:
        """把本轮发现的目标并入队列；返回新增/复查/不变的计数。

        已成功处理、失败或跳过的目标再次被发现时标记 refresh（重新检查），不删除既有
        记录，也不把失败静默转成“待处理”。

        ``replay=True``（R4）表示这是崩溃后对同一发现页的幂等重放：只补齐缺失目标，
        既有记录保持原状态——重放不能把已经 processed 的目标整体转成 refresh。

        并发运行经 file_lock 串行化整段读-改-写，其他进程的新增项不会被本次写入覆盖。
        """
        with file_lock(self.path):
            items = self.load()
            result = {"added": 0, "refreshed": 0, "unchanged": 0}
            sequence = max((item.sequence for item in items.values()), default=0)
            for target in targets:
                key = item_key(
                    kind=KIND_TARGET,
                    source_id=source_id,
                    scope_start_date=scope_start_date,
                    url=target.url,
                )
                current = items.get(key)
                if current is None:
                    sequence += 1
                    items[key] = PendingItem(
                        key=key,
                        source_id=source_id,
                        kind=KIND_TARGET,
                        url=target.url,
                        state=STATE_PENDING,
                        scope_start_date=scope_start_date,
                        discovery_method=target.discovery_method,
                        referrer_url=target.referrer_url,
                        keyword=target.keyword,
                        title_hint=target.title_hint,
                        sequence=sequence,
                        enqueued_at=enqueued_at,
                    )
                    result["added"] += 1
                    continue
                if replay:
                    result["unchanged"] += 1
                    continue
                if current.state in (STATE_PROCESSED, STATE_FAILED, STATE_SKIPPED):
                    items[key] = replace(
                        current,
                        state=STATE_REFRESH,
                        previous_state=current.state,
                        discovery_method=target.discovery_method or current.discovery_method,
                        referrer_url=target.referrer_url or current.referrer_url,
                        keyword=target.keyword or current.keyword,
                        title_hint=target.title_hint or current.title_hint,
                    )
                    result["refreshed"] += 1
                    continue
                result["unchanged"] += 1
            self._write(items)
            return result

    def enqueue_attachments(
        self,
        *,
        source_id: str,
        scope_start_date: Optional[str],
        doc_id: str,
        parent_url: str,
        records: Sequence[dict],
        enqueued_at: str,
    ) -> int:
        """把预算停止时未尝试的附件登记为待处理；返回新增条数（并发运行同样串行化）。"""
        with file_lock(self.path):
            items = self.load()
            sequence = max((item.sequence for item in items.values()), default=0)
            added = 0
            for record in records:
                key = item_key(
                    kind=KIND_ATTACHMENT,
                    source_id=source_id,
                    scope_start_date=scope_start_date,
                    url=record["url"],
                    doc_id=doc_id,
                )
                if key in items:
                    continue
                sequence += 1
                items[key] = PendingItem(
                    key=key,
                    source_id=source_id,
                    kind=KIND_ATTACHMENT,
                    url=record["url"],
                    state=STATE_PENDING,
                    scope_start_date=scope_start_date,
                    discovery_method="attachment",
                    referrer_url=record.get("referrer_url") or parent_url,
                    doc_id=doc_id,
                    parent_url=parent_url,
                    filename=record.get("filename"),
                    file_type=record.get("file_type"),
                    sequence=sequence,
                    enqueued_at=enqueued_at,
                )
                added += 1
            self._write(items)
            return added

    def candidates(self, source_id: str, *, limit: Optional[int] = None) -> List[PendingItem]:
        """本次运行可处理的项：先从未尝试的 pending，再复查 refresh。"""
        items = [item for item in self.load().values() if item.source_id == source_id]
        pending = sorted(
            (item for item in items if item.state == STATE_PENDING),
            key=lambda item: (item.sequence, item.url),
        )
        refresh = sorted(
            (item for item in items if item.state == STATE_REFRESH),
            key=lambda item: (item.last_attempt_at or "", item.sequence, item.url),
        )
        ordered = pending + refresh
        return ordered[:limit] if limit is not None else ordered

    def open_items(self, source_id: Optional[str] = None) -> List[PendingItem]:
        return [
            item
            for item in self.load().values()
            if item.state in OPEN_STATES and (source_id is None or item.source_id == source_id)
        ]

    def counts(self, source_id: str) -> dict:
        items = [item for item in self.load().values() if item.source_id == source_id]
        targets = [item for item in items if item.kind == KIND_TARGET]
        attachments = [item for item in items if item.kind == KIND_ATTACHMENT]
        return {
            "targets": {
                "total": len(targets),
                "pending": sum(1 for item in targets if item.state == STATE_PENDING),
                "refresh": sum(1 for item in targets if item.state == STATE_REFRESH),
                "processed": sum(1 for item in targets if item.state == STATE_PROCESSED),
                "failed": sum(1 for item in targets if item.state == STATE_FAILED),
                "skipped": sum(1 for item in targets if item.state == STATE_SKIPPED),
            },
            "attachments": {
                "total": len(attachments),
                "pending": sum(1 for item in attachments if item.state == STATE_PENDING),
                "processed": sum(1 for item in attachments if item.state == STATE_PROCESSED),
                "failed": sum(1 for item in attachments if item.state == STATE_FAILED),
                "skipped": sum(1 for item in attachments if item.state == STATE_SKIPPED),
            },
        }

    def mark(
        self,
        key: str,
        *,
        state: str,
        attempted_at: Optional[str] = None,
        note: Optional[str] = None,
        crawl_id: Optional[str] = None,
        raw_path: Optional[str] = None,
        sha256: Optional[str] = None,
    ) -> PendingItem:
        """更新一项的处置结果；历史通过 previous_state 保留，不删除记录。

        整段读-改-写在 file_lock 内完成：并发运行时其他进程的标记不丢失。
        """
        with file_lock(self.path):
            items = self.load()
            current = items.get(key)
            if current is None:
                raise PendingStoreError(f"待处理项不存在：{key}")
            updated = replace(
                current,
                state=state,
                attempts=current.attempts + (1 if attempted_at else 0),
                last_attempt_at=attempted_at or current.last_attempt_at,
                previous_state=current.state if current.state != state else current.previous_state,
                note=note if note is not None else current.note,
            )
            if crawl_id is not None:
                updated = replace(updated, crawl_id=crawl_id)
            if raw_path is not None:
                updated = replace(updated, raw_path=raw_path)
            if sha256 is not None:
                updated = replace(updated, sha256=sha256)
            items[key] = updated
            self._write(items)
            return updated

    def _write(self, items: Dict[str, PendingItem]) -> None:
        """整文件原子写入；调用方须先持有 self.path 的 file_lock。"""
        rows = {key: asdict(value) for key, value in sorted(items.items())}
        payload = {"version": "0.1.0", "items": rows}
        atomic_write_json(self.path, payload)
        logger.debug("待处理状态更新 items=%d", len(rows))
