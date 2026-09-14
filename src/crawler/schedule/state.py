"""增量状态存储（T015）。

按 URL 保存此前成功抓取的校验信息（ETag/Last-Modified/哈希/crawl_id）与最近一次
304 关联，供条件请求与增量判断使用。JSON 文件原子写入；刷新失败不影响历史状态。
状态文件只记录抓取行为，不复制文档内容，也不作为交付内容。

R2/A（阶段七）：正文分页/接口正文未完成时的待续状态也在这里登记，与 ETag/哈希在
同一次原子写入中落盘。这样“正文续抓进度”和“增量状态”不会出现一个已写、另一个未写的
窗口：重启后即使待处理项尚未回写，母页 304 也不会把未完成正文当作完整实体复用。
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Mapping, Optional

from crawler.output.atomic import atomic_write_json, file_lock
from crawler.output.layout import DeliveryLayout

logger = logging.getLogger(__name__)

# 与账本同目录：它是抓取行为的状态索引，不属于六项交付成果的独立类别。
STATE_FILENAME = "incremental_state.json"
NOT_MODIFIED = "not_modified"
UPDATED = "updated"


class _Unset:
    """record_success() 的缺省标记：区分“清空待续”和“不改变待续”。"""

    def __repr__(self) -> str:  # pragma: no cover - 仅用于调试输出
        return "UNSET"


UNSET = _Unset()


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
    # 未完成正文位置的待续状态（BodyContinuation.as_dict()）；None 表示该 URL 当前无待续。
    continuation: Optional[dict] = None


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
        continuation: object = UNSET,
    ) -> ResourceState:
        """记录一次成功获取；continuation 显式传 None 表示待续关闭，缺省保持原值。"""
        existing_continuation: Optional[dict]
        if continuation is UNSET:
            previous = self.get(url)
            existing_continuation = previous.continuation if previous else None
        else:
            existing_continuation = continuation
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
            continuation=existing_continuation,
        )
        return self._update(url, lambda existing: state)

    def record_not_modified(
        self, url: str, *, now: datetime, previous_crawl_id: Optional[str]
    ) -> ResourceState:
        return self._update(
            url,
            lambda existing: replace(
                existing,
                last_checked_at=now.isoformat(),
                last_result=NOT_MODIFIED,
                not_modified_crawl_id=previous_crawl_id,
            ),
        )

    def _update(self, url: str, make_state) -> ResourceState:
        """读-改-写在 file_lock 内完成：并发运行时其他进程的记录不丢失。"""
        with file_lock(self.path):
            states = self.load()
            state = make_state(states.get(url) or ResourceState(url=url))
            states[url] = state
            rows = {key: asdict(value) for key, value in sorted(states.items())}
            payload = {"version": "0.1.0", "resources": rows}
            atomic_write_json(self.path, payload, indent=1)
        logger.debug("增量状态更新 url=%s result=%s", url, state.last_result)
        return state
