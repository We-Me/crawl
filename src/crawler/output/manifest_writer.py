"""抓取账本写出：原件存在且哈希一致后，账本才可引用（T007）。"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Optional

from crawler.output.jsonl import append_jsonl
from crawler.output.layout import DeliveryLayout
from crawler.output.raw_store import RawRecord

logger = logging.getLogger(__name__)


class ManifestError(ValueError):
    """账本记录与原件不一致。"""


class ManifestWriter:
    def __init__(self, data_dir: Path) -> None:
        self.path = DeliveryLayout(data_dir).manifest_path

    def record(
        self,
        *,
        crawl_id: str,
        source_id: str,
        requested_url: str,
        final_url: str,
        crawl_time: str,
        http_status: int,
        content_type: str,
        raw: RawRecord,
        discovery_method: str,
        keyword: Optional[str] = None,
        referrer_url: Optional[str] = None,
        etag: Optional[str] = None,
        last_modified: Optional[str] = None,
    ) -> dict:
        self._verify_raw(raw)
        row = {
            "crawl_id": crawl_id,
            "source_id": source_id,
            "requested_url": requested_url,
            "final_url": final_url,
            "crawl_time": crawl_time,
            "http_status": int(http_status),
            "content_type": content_type,
            "raw_path": raw.relative_path,
            "sha256": raw.sha256,
            "discovery_method": discovery_method,
        }
        for key, value in (
            ("keyword", keyword),
            ("referrer_url", referrer_url),
            ("etag", etag),
            ("last_modified", last_modified),
        ):
            if value is not None:
                row[key] = value
        append_jsonl(self.path, [row])
        logger.info(
            "账本记录 crawl_id=%s status=%s raw_path=%s", crawl_id, http_status, raw.relative_path
        )
        return row

    @staticmethod
    def _verify_raw(raw: RawRecord) -> None:
        if not raw.absolute_path.is_file():
            raise ManifestError(f"原件不存在，不能写入账本：{raw.absolute_path}")
        digest = hashlib.sha256()
        size = 0
        with raw.absolute_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
                size += len(chunk)
        if digest.hexdigest() != raw.sha256 or size != raw.size:
            raise ManifestError(
                f"原件字节与记录不一致：{raw.absolute_path} 记录 {raw.sha256}/{raw.size}，"
                f"实际 {digest.hexdigest()}/{size}"
            )
