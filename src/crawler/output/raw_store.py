"""原件归档：先写临时文件、字节完整后原子改名；raw_path 相对数据根。"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, Union

from crawler.output.layout import DeliveryLayout
from crawler.util.paths import ensure_within, sanitize_filename

logger = logging.getLogger(__name__)

_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CHUNK = 64 * 1024


class RawStoreError(ValueError):
    """原件写入失败或路径越界。"""


@dataclass(frozen=True)
class RawRecord:
    relative_path: str
    absolute_path: Path
    sha256: str
    size: int
    reused: bool = False


class RawStore:
    """按 raw/<source_id>/<date>/<kind>/ 归档；相同字节复用同一原件。"""

    def __init__(self, data_dir: Path) -> None:
        self.layout = DeliveryLayout(data_dir)
        self.data_dir = self.layout.data_dir
        self.layout.ensure()

    def write_bytes(
        self,
        *,
        source_id: str,
        crawl_date: Union[date, str],
        kind: str,
        filename: str,
        content: bytes,
    ) -> RawRecord:
        return self.write_stream(
            source_id=source_id,
            crawl_date=crawl_date,
            kind=kind,
            filename=filename,
            chunks=(content,),
        )

    def write_stream(
        self,
        *,
        source_id: str,
        crawl_date: Union[date, str],
        kind: str,
        filename: str,
        chunks: Iterable[bytes],
    ) -> RawRecord:
        date_str = crawl_date.isoformat() if isinstance(crawl_date, date) else str(crawl_date)
        if not _DATE_PATTERN.match(date_str):
            raise RawStoreError(f"crawl_date 必须是 YYYY-MM-DD：{date_str!r}")
        directory = self._directory(source_id, date_str, kind)
        ensure_within(self.data_dir, directory)
        directory.mkdir(parents=True, exist_ok=True)

        safe_name = sanitize_filename(filename)
        target = ensure_within(self.data_dir, directory / safe_name)
        tmp_path = directory / f".tmp-{uuid.uuid4().hex}"

        digest = hashlib.sha256()
        size = 0
        wrote_tmp = False
        try:
            with tmp_path.open("wb") as handle:
                wrote_tmp = True
                for chunk in chunks:
                    if not chunk:
                        continue
                    digest.update(chunk)
                    size += len(chunk)
                    handle.write(chunk)
                handle.flush()
                os.fsync(handle.fileno())
            sha = digest.hexdigest()
            if target.exists():
                existing = self._existing_record(target, date_str, kind, source_id)
                if existing.sha256 == sha and existing.size == size:
                    os.unlink(tmp_path)
                    logger.debug("原件字节相同，复用 raw_path=%s", existing.relative_path)
                    return RawRecord(
                        relative_path=existing.relative_path,
                        absolute_path=existing.absolute_path,
                        sha256=existing.sha256,
                        size=existing.size,
                        reused=True,
                    )
                target = self._collision_path(directory, safe_name, sha)
            os.replace(tmp_path, target)
            wrote_tmp = False
        finally:
            if wrote_tmp and tmp_path.exists():
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
        relative = self.layout.relative_to_root(target)
        logger.debug("原件写入 raw_path=%s size=%d", relative, size)
        return RawRecord(
            relative_path=relative,
            absolute_path=target.resolve(),
            sha256=sha,
            size=size,
            reused=False,
        )

    def _directory(self, source_id: str, date_str: str, kind: str) -> Path:
        return self.layout.raw_dir_for(source_id, date_str, kind)

    def _existing_record(
        self, path: Path, date_str: str, kind: str, source_id: str
    ) -> RawRecord:
        digest = hashlib.sha256()
        size = 0
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(_CHUNK)
                if not chunk:
                    break
                digest.update(chunk)
                size += len(chunk)
        return RawRecord(
            relative_path=self.layout.relative_to_root(path),
            absolute_path=path.resolve(),
            sha256=digest.hexdigest(),
            size=size,
        )

    @staticmethod
    def _collision_path(directory: Path, filename: str, sha: str) -> Path:
        stem = Path(filename).stem
        suffix = Path(filename).suffix
        return directory / f"{stem}-{sha[:8]}{suffix}"
