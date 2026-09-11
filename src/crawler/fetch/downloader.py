"""附件下载：按块写入并由调用方计算摘要（T006/T007）。"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import unquote, urlsplit

from crawler.fetch.http_client import FetchError, HttpClient, StreamHandle
from crawler.util.paths import sanitize_filename

logger = logging.getLogger(__name__)

DEFAULT_MAX_ATTACHMENT_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class DownloadedResource:
    requested_url: str
    final_url: str
    status_code: int
    content_type: str
    filename: str
    content: bytes
    sha256: str
    size: int


class Downloader:
    """下载附件；文件名优先取响应头，其次取 URL 路径。"""

    def __init__(
        self,
        http: HttpClient,
        max_bytes: int = DEFAULT_MAX_ATTACHMENT_BYTES,
    ) -> None:
        self.http = http
        self.max_bytes = max_bytes

    def open(self, url: str, *, source_id: Optional[str] = None) -> StreamHandle:
        return self.http.open(url, source_id=source_id)

    def download(self, url: str, *, source_id: Optional[str] = None) -> DownloadedResource:
        handle = self.open(url, source_id=source_id)
        digest = hashlib.sha256()
        size = 0
        chunks = []
        try:
            for chunk in handle.iter_chunks():
                size += len(chunk)
                if size > self.max_bytes:
                    raise FetchError(
                        f"附件超过 {self.max_bytes} 字节上限",
                        url=url,
                        retryable=False,
                    )
                digest.update(chunk)
                chunks.append(chunk)
        finally:
            handle.close()
        content = b"".join(chunks)
        return DownloadedResource(
            requested_url=handle.requested_url,
            final_url=handle.final_url,
            status_code=handle.status_code,
            content_type=handle.content_type,
            filename=self.filename_for(handle),
            content=content,
            sha256=digest.hexdigest(),
            size=size,
        )

    @staticmethod
    def filename_for(handle: StreamHandle) -> str:
        disposition = handle.headers.get("Content-Disposition", "")
        match = re.search(r"filename\*?=(?:UTF-8''|\")?([^\";]+)", disposition)
        candidate = unquote(match.group(1)) if match else ""
        if not candidate:
            path = urlsplit(handle.final_url).path
            candidate = unquote(os.path.basename(path)) or "attachment.bin"
        return sanitize_filename(candidate)

