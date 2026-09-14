"""R3：归档事务的跨进程唯一性（两个真实进程，非多线程）。

同来源同一天、两个长期存活的归档实例交错运行：同名不同内容、相同字节与不同 URL
的文件名冲突都在同一归档锁内解决。验收 crawl_id 唯一、JSONL 可读、每条账本引用的
原件存在且哈希一致。
"""

import hashlib
import multiprocessing
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from crawler.output.archive import ARCHIVE_LOCK_NAME, ResponseArchiver
from crawler.output.jsonl import read_jsonl

FIXED = datetime(2026, 9, 14, 10, 0, 0, tzinfo=timezone.utc)
ROUNDS = 8


def _archive_worker(data_dir: str, worker: str, barrier) -> None:
    """真实子进程：一个长期实例多轮归档，与另一进程交错。"""
    archiver = ResponseArchiver(Path(data_dir), now=lambda: FIXED)
    barrier.wait(timeout=60)
    for index in range(ROUNDS):
        url = f"https://example.invalid/{worker}/{index}.html"
        archiver.archive_bytes(
            f"unique-{worker}-{index}".encode("utf-8"),
            source_id="TESTSRC",
            kind="html",
            filename="same-name.html",
            discovery_method="list",
            requested_url=url,
            final_url=url,
            status_code=200,
            content_type="text/html",
        )
        shared_url = f"https://example.invalid/{worker}/shared-{index}.html"
        archiver.archive_bytes(
            b"shared-bytes",
            source_id="TESTSRC",
            kind="html",
            filename="shared.html",
            discovery_method="list",
            requested_url=shared_url,
            final_url=shared_url,
            status_code=200,
            content_type="text/html",
        )


@pytest.mark.skipif(not hasattr(os, "fork"), reason="跨进程 flock 验证需要 POSIX fork")
def test_two_processes_archive_without_id_or_raw_collisions(tmp_path):
    data_dir = tmp_path / "data"
    ResponseArchiver(data_dir, now=lambda: FIXED)  # 建好目录与锁路径
    context = multiprocessing.get_context("fork")
    barrier = context.Barrier(2)
    processes = [
        context.Process(target=_archive_worker, args=(str(data_dir), worker, barrier))
        for worker in ("A", "B")
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=120)
        assert process.exitcode == 0, f"归档子进程失败 exitcode={process.exitcode}"

    layout_rows = read_jsonl(data_dir / "manifests" / "crawl_manifest.jsonl")
    assert len(layout_rows) == 2 * ROUNDS * 2
    crawl_ids = [row["crawl_id"] for row in layout_rows]
    assert len(set(crawl_ids)) == len(crawl_ids), "跨进程归档复用了 crawl_id"

    for row in layout_rows:
        raw_path = data_dir / row["raw_path"]
        assert raw_path.is_file(), f"账本引用的原件不存在：{row['raw_path']}"
        content = raw_path.read_bytes()
        assert hashlib.sha256(content).hexdigest() == row["sha256"], (
            f"同名原件被并发覆盖：{row['raw_path']}"
        )

    # 相同字节复用同一原件；不同字节不得覆盖同名文件。
    shared_paths = {row["raw_path"] for row in layout_rows if row["final_url"].endswith(".html") and "shared" in row["final_url"]}
    assert shared_paths == {"raw/TESTSRC/2026-09-14/html/shared.html"}
    assert (data_dir / "raw/TESTSRC/2026-09-14/html/shared.html").read_bytes() == b"shared-bytes"

    # 同名不同内容：每个 URL 的记录都指向内容与其哈希一致的原件，文件名互不覆盖。
    by_url = {}
    for row in layout_rows:
        if "same-name" in row["raw_path"]:
            by_url[row["final_url"]] = row
    assert len(by_url) == 2 * ROUNDS
    contents = {
        url: (data_dir / row["raw_path"]).read_bytes() for url, row in by_url.items()
    }
    assert len(set(contents.values())) == 2 * ROUNDS, "不同内容必须各自留存"
    assert (data_dir / "manifests" / f"{ARCHIVE_LOCK_NAME}.lock").exists()
