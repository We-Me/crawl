"""版本库读写与现行状态维护（T014）。

documents.jsonl 仍是一行一版本（每个版本有自己的 doc_id）；同一身份出现新版本时，
旧版行保留全部内容，只把 is_current 置为 false 并记录 source_status=superseded，
通过原子重写完成，不删除历史。页面下线另用 record_offline 记录 source_status，
不因此删除历史版本，也不据此推断法律有效性。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, List, Mapping, Optional, Sequence

from crawler.output.jsonl import read_jsonl, write_jsonl
from crawler.output.layout import DOCUMENTS_FILENAME, DeliveryLayout
from crawler.versioning.identity import document_identity
from crawler.versioning.versions import version_number

logger = logging.getLogger(__name__)

SUPERSEDED_STATUS = "superseded"
OFFLINE_STATUSES = ("removed", "offline", "gone")


class VersionStoreError(ValueError):
    """版本库无法读取或更新。"""


class VersionStore:
    def __init__(self, data_dir: Path) -> None:
        self.path = DeliveryLayout(data_dir).documents_path

    def load(self) -> List[dict]:
        return read_jsonl(self.path)

    def current_documents(self) -> List[dict]:
        latest: dict = {}
        for row in self.load():
            identity = document_identity(row) or f"doc:{row.get('doc_id')}"
            if row.get("is_current") is False:
                continue
            if identity not in latest or version_number(row) >= version_number(latest[identity]):
                latest[identity] = row
        return list(latest.values())

    def retire(self, doc_ids: Iterable[str], *, source_status: str = SUPERSEDED_STATUS) -> int:
        """把被取代的旧版本标记为历史版；内容与 doc_id 不变。"""
        targets = {doc_id for doc_id in doc_ids}
        if not targets:
            return 0

        def _update(row: Mapping) -> Mapping:
            if row.get("doc_id") in targets:
                updated = dict(row)
                updated["is_current"] = False
                updated["source_status"] = source_status
                return updated
            return row

        return self._rewrite(_update)

    def record_offline(
        self,
        doc_id: str,
        *,
        source_status: str,
        evidence: Optional[Mapping] = None,
    ) -> int:
        """记录页面下线：保留历史与现行版本标记，只更新来源状态并留存证据。"""
        if source_status not in OFFLINE_STATUSES:
            raise VersionStoreError(f"下线状态不在允许集合：{source_status!r}")

        def _update(row: Mapping) -> Mapping:
            if row.get("doc_id") != doc_id:
                return row
            updated = dict(row)
            updated["source_status"] = source_status
            if evidence:
                history = list(updated.get("status_history") or [])
                history.append({"source_status": source_status, "evidence": dict(evidence)})
                updated["status_history"] = history
            return updated

        return self._rewrite(_update)

    def _rewrite(self, update) -> int:
        rows = self.load()
        if not rows:
            raise VersionStoreError(f"版本库不存在或为空：{self.path}")
        updated_rows = [update(row) for row in rows]
        changed = sum(1 for old, new in zip(rows, updated_rows) if old != new)
        if changed:
            write_jsonl(self.path, updated_rows)
            logger.info("版本库更新 path=%s rows=%d", self.path, changed)
        return changed

    def versions_of(self, identity: str) -> List[dict]:
        rows = [row for row in self.load() if document_identity(row) == identity]
        return sorted(rows, key=version_number)


def superseded_doc_ids(decisions: Sequence[Mapping]) -> List[str]:
    result = []
    for decision in decisions:
        result.extend(decision.get("supersedes", ()))
    return result
