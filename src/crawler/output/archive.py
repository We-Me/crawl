"""业务响应统一归档（S5-01）：成功响应先落原件、再写账本，之后才允许解析。

发现响应（列表页、搜索页、sitemap、发现接口）、详情/正文分页、正文接口与附件
共用同一归档实现，避免每处各写一遍原件与账本逻辑。归档只负责“原件 + 账本 +
请求身份”，不生成 normalized 文档，也不改动解析结果。

约定：

- 每个成功业务响应恰好归档一次：同一个响应对象重复交给归档器时返回既有记录，
  不追加第二行账本（避免双重写账）；不同请求即使字节相同也各自保留身份；
- crawl_id 序号由账本推导（同来源同一天跨进程不重复），补抓可按 crawl_id 定位原件；
- raw_path 相对数据根，字节哈希与原件在写账本前校验（ManifestWriter 负责）；
- 304/控制请求（robots.txt 等）不经过这里，不伪造新原件。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlsplit

from crawler.fetch.http_client import FetchResponse
from crawler.output.jsonl import read_jsonl
from crawler.output.layout import DeliveryLayout
from crawler.output.manifest_writer import ManifestWriter
from crawler.output.raw_store import RawRecord, RawStore

logger = logging.getLogger(__name__)

CRAWL_ID_WIDTH = 4


def max_crawl_sequence(manifest_path: Path, prefix: str) -> int:
    """账本中同前缀 crawl_id 的最大序号；没有记录时从 0 开始。"""
    maximum = 0
    for row in read_jsonl(manifest_path):
        crawl_id = str(row.get("crawl_id") or "")
        tail = crawl_id[len(prefix):] if crawl_id.startswith(prefix) else ""
        if tail.isdigit():
            maximum = max(maximum, int(tail))
    return maximum


def basename(url: str) -> str:
    return urlsplit(url).path.rsplit("/", 1)[-1] or "index.html"


def filename_for(url: str, kind: str) -> str:
    """归档文件名：默认取 URL 末段；正文 HTML 响应补上 .html 后缀。"""
    name = basename(url)
    if kind == "html" and not name.lower().endswith((".html", ".htm")):
        name = f"{name}.html"
    return name


@dataclass(frozen=True)
class ArchivedResponse:
    """一次成功业务响应的归档结果：账本行、原件与请求身份。"""

    crawl_id: str
    raw: RawRecord
    manifest_row: dict
    reused: bool = False


class ResponseArchiver:
    """业务响应归档器：原件 + 账本 + crawl_id 序号。"""

    def __init__(
        self,
        data_dir: Path,
        *,
        now: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self.layout = DeliveryLayout(data_dir)
        self.store = RawStore(data_dir)
        self.manifest = ManifestWriter(data_dir)
        self._now = now or (lambda: datetime.now(timezone.utc).astimezone())
        self._sequences: dict = {}
        self._archived: dict = {}

    # ---- 对外入口 ----
    def archive(
        self,
        response: FetchResponse,
        *,
        source_id: str,
        kind: str,
        discovery_method: str,
        keyword: Optional[str] = None,
        referrer_url: Optional[str] = None,
        crawl_time: Optional[str] = None,
    ) -> ArchivedResponse:
        """归档一个 FetchResponse；同一响应对象重复调用不重复写账。"""
        existing = self._archived.get(id(response))
        if existing is not None and existing[0] is response:
            return ArchivedResponse(
                crawl_id=existing[1].crawl_id,
                raw=existing[1].raw,
                manifest_row=existing[1].manifest_row,
                reused=True,
            )
        record = self.archive_bytes(
            response.content,
            source_id=source_id,
            kind=kind,
            filename=filename_for(response.final_url, kind),
            discovery_method=discovery_method,
            requested_url=response.requested_url,
            final_url=response.final_url,
            status_code=response.status_code,
            content_type=response.headers.get("Content-Type", ""),
            keyword=keyword,
            referrer_url=referrer_url,
            etag=response.headers.get("ETag"),
            last_modified=response.headers.get("Last-Modified"),
            crawl_time=crawl_time,
        )
        self._archived[id(response)] = (response, record)
        return record

    def archive_bytes(
        self,
        content: bytes,
        *,
        source_id: str,
        kind: str,
        filename: str,
        discovery_method: str,
        requested_url: str,
        final_url: str,
        status_code: int,
        content_type: str = "",
        keyword: Optional[str] = None,
        referrer_url: Optional[str] = None,
        etag: Optional[str] = None,
        last_modified: Optional[str] = None,
        crawl_time: Optional[str] = None,
    ) -> ArchivedResponse:
        """按内容归档（附件下载等流式结果也走这里，保持同一顺序与账本口径）。"""
        moment = self._now()
        crawl_date = moment.date().isoformat()
        crawl_time = crawl_time or moment.isoformat()
        raw = self.store.write_bytes(
            source_id=source_id,
            crawl_date=crawl_date,
            kind=kind,
            filename=filename,
            content=content,
        )
        crawl_id = self.next_crawl_id(source_id, crawl_date)
        row = self.manifest.record(
            crawl_id=crawl_id,
            source_id=source_id,
            requested_url=requested_url,
            final_url=final_url,
            crawl_time=crawl_time,
            http_status=status_code,
            content_type=content_type,
            raw=raw,
            discovery_method=discovery_method,
            keyword=keyword,
            referrer_url=referrer_url,
            etag=etag,
            last_modified=last_modified,
        )
        return ArchivedResponse(crawl_id=crawl_id, raw=raw, manifest_row=row)

    def next_crawl_id(self, source_id: str, crawl_date: str) -> str:
        """按账本已落盘序号继续编号：同一来源同一天多次运行不复用 crawl_id。"""
        prefix = f"{source_id}_{crawl_date.replace('-', '')}_"
        if prefix not in self._sequences:
            self._sequences[prefix] = max_crawl_sequence(self.layout.manifest_path, prefix)
        self._sequences[prefix] += 1
        return f"{prefix}{self._sequences[prefix]:0{CRAWL_ID_WIDTH}d}"
