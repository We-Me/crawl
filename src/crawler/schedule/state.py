"""增量状态存储（T015）。

按 URL 保存此前成功抓取的校验信息（ETag/Last-Modified/哈希/crawl_id）与最近一次
304 关联，供条件请求与增量判断使用。JSON 文件原子写入；刷新失败不影响历史状态。
状态文件只记录抓取行为，不复制文档内容，也不作为交付内容。
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Mapping, Optional

from crawler.output.layout import DeliveryLayout

logger = logging.getLogger(__name__)

# 与账本同目录：它是抓取行为的状态索引，不属于六项交付成果的独立类别。
STATE_FILENAME = "incremental_state.json"
NOT_MODIFIED = "not_modified"
UPDATED = "updated"


@dataclass(frozen=True)
class ResourceState:
    url: str
    etag: Optional[str] = None
    last_modified: Optional[str] = None
    sha256: Optional[str] = None
    content_hash: Optional[str] = None
    crawl_id: Optional[str] = None
    last_success_at: Optional[str] = None
    last_checked_at: Optional[str] = None
    last_publication_date: Optional[str] = None
    last_version: Optional[str] = None
    last_result: Optional[str] = None
    not_modified_crawl_id: Optional[str] = None


class IncrementalStateStore:
    def __init__(self, data_dir: Path) -> None:
        self.path = DeliveryLayout(data_dir).incremental_state_path

    def load(self) -> Dict[str, ResourceState]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"增量状态文件损坏：{self.path}") from exc
        resources = payload.get("resources") or {}
        return {url: ResourceState(**row) for url, row in resources.items()}

    def get(self, url: str) -> Optional[ResourceState]:
        return self.load().get(url)

    def record_success(
        self,
        url: str,
        *,
        now: datetime,
        etag: Optional[str] = None,
        last_modified: Optional[str] = None,
        sha256: Optional[str] = None,
        content_hash: Optional[str] = None,
        crawl_id: Optional[str] = None,
        publication_date: Optional[str] = None,
        version: Optional[str] = None,
    ) -> ResourceState:
        state = ResourceState(
            url=url,
            etag=etag,
            last_modified=last_modified,
            sha256=sha256,
            content_hash=content_hash,
            crawl_id=crawl_id,
            last_success_at=now.isoformat(),
            last_checked_at=now.isoformat(),
            last_publication_date=publication_date,
            last_version=version,
            last_result=UPDATED,
        )
        self._write(url, state)
        return state

    def record_not_modified(
        self, url: str, *, now: datetime, previous_crawl_id: Optional[str]
    ) -> ResourceState:
        existing = self.get(url) or ResourceState(url=url)
        state = replace(
            existing,
            last_checked_at=now.isoformat(),
            last_result=NOT_MODIFIED,
            not_modified_crawl_id=previous_crawl_id,
        )
        self._write(url, state)
        return state

    def _write(self, url: str, state: ResourceState) -> None:
        states = self.load()
        states[url] = state
        rows = {key: asdict(value) for key, value in sorted(states.items())}
        payload = {"version": "0.1.0", "resources": rows}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        with tmp.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=1, sort_keys=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, self.path)
        logger.debug("增量状态更新 url=%s result=%s", url, state.last_result)
