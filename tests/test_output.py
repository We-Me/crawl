"""T007 原件归档、账本与失败账测试。"""

import hashlib
import json
from pathlib import Path

import pytest

from crawler.output.failures_writer import FailureWriter
from crawler.output.jsonl import read_jsonl
from crawler.output.manifest_writer import ManifestError, ManifestWriter
from crawler.output.raw_store import RawRecord, RawStore, RawStoreError
from crawler.util.paths import PathSafetyError

CRAWL_TIME = "2026-09-11T10:00:00+08:00"


@pytest.fixture()
def store(tmp_path):
    return RawStore(tmp_path / "data")


def test_raw_store_writes_relative_path_and_hash(store):
    content = "<html><body>虚构</body></html>".encode("utf-8")
    record = store.write_stream(
        source_id="DEMO",
        crawl_date="2026-09-11",
        kind="html",
        filename="detail.html",
        chunks=(content[:5], content[5:]),
    )
    assert record.relative_path == "raw/DEMO/2026-09-11/html/detail.html"
    assert record.absolute_path.read_bytes() == content
    assert record.sha256 == hashlib.sha256(content).hexdigest()
    assert record.size == len(content)
    assert record.reused is False


def test_raw_store_reuses_identical_bytes(store):
    content = b"same-bytes"
    first = store.write_bytes(
        source_id="DEMO", crawl_date="2026-09-11", kind="attachment", filename="a.csv", content=content
    )
    second = store.write_bytes(
        source_id="DEMO", crawl_date="2026-09-11", kind="attachment", filename="a.csv", content=content
    )
    assert second.reused is True
    assert second.relative_path == first.relative_path
    files = list((store.data_dir / "raw/DEMO/2026-09-11/attachment").iterdir())
    assert len(files) == 1
    assert not any(item.name.startswith(".tmp-") for item in files)


def test_raw_store_keeps_distinct_bytes_under_new_name(store):
    path_a = store.write_bytes(
        source_id="DEMO", crawl_date="2026-09-11", kind="html", filename="page.html", content=b"v1"
    )
    path_b = store.write_bytes(
        source_id="DEMO", crawl_date="2026-09-11", kind="html", filename="page.html", content=b"v2"
    )
    assert path_a.relative_path != path_b.relative_path
    assert path_b.relative_path.startswith("raw/DEMO/2026-09-11/html/page-")
    assert path_a.absolute_path.read_bytes() == b"v1"
    assert path_b.absolute_path.read_bytes() == b"v2"


def test_raw_store_rejects_invalid_date_and_segments(store):
    with pytest.raises(RawStoreError):
        store.write_bytes(
            source_id="DEMO", crawl_date="2026/09/11", kind="html", filename="a.html", content=b"x"
        )
    with pytest.raises(PathSafetyError):
        store.write_bytes(
            source_id="../etc", crawl_date="2026-09-11", kind="html", filename="a.html", content=b"x"
        )
    with pytest.raises(PathSafetyError):
        store.write_bytes(
            source_id="DEMO", crawl_date="2026-09-11", kind="../x", filename="a.html", content=b"x"
        )


def test_raw_store_sanitizes_traversal_filename(store):
    record = store.write_bytes(
        source_id="DEMO",
        crawl_date="2026-09-11",
        kind="attachment",
        filename="../../evil.txt",
        content=b"x",
    )
    assert record.relative_path == "raw/DEMO/2026-09-11/attachment/evil.txt"
    assert record.absolute_path.parent == store.data_dir / "raw/DEMO/2026-09-11/attachment"


def test_raw_store_rejects_symlinked_escape(store, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    raw_root = store.data_dir / "raw"
    raw_root.mkdir(parents=True, exist_ok=True)
    (raw_root / "DEMO").symlink_to(outside)
    with pytest.raises(PathSafetyError):
        store.write_bytes(
            source_id="DEMO", crawl_date="2026-09-11", kind="html", filename="a.html", content=b"x"
        )
    assert list(outside.iterdir()) == []


def test_manifest_requires_existing_matching_raw(store, tmp_path):
    raw = store.write_bytes(
        source_id="DEMO", crawl_date="2026-09-11", kind="html", filename="detail.html", content=b"<html/>"
    )
    writer = ManifestWriter(store.data_dir)
    row = writer.record(
        crawl_id="DEMO_20260911_0001",
        source_id="DEMO",
        requested_url="https://example.invalid/detail.html",
        final_url="https://example.invalid/detail.html",
        crawl_time=CRAWL_TIME,
        http_status=200,
        content_type="text/html",
        raw=raw,
        discovery_method="list",
        referrer_url="https://example.invalid/index.html",
    )
    assert row["raw_path"] == raw.relative_path
    assert row["sha256"] == raw.sha256
    stored = read_jsonl(writer.path)
    assert stored == [row]

    raw.absolute_path.unlink()
    with pytest.raises(ManifestError, match="原件不存在"):
        writer.record(
            crawl_id="DEMO_20260911_0002",
            source_id="DEMO",
            requested_url="https://example.invalid/detail.html",
            final_url="https://example.invalid/detail.html",
            crawl_time=CRAWL_TIME,
            http_status=200,
            content_type="text/html",
            raw=raw,
            discovery_method="list",
        )


def test_manifest_detects_tampered_bytes(store, tmp_path):
    raw = store.write_bytes(
        source_id="DEMO", crawl_date="2026-09-11", kind="html", filename="detail.html", content=b"original"
    )
    raw.absolute_path.write_bytes(b"tampered")
    writer = ManifestWriter(store.data_dir)
    with pytest.raises(ManifestError, match="不一致"):
        writer.record(
            crawl_id="DEMO_20260911_0001",
            source_id="DEMO",
            requested_url="https://example.invalid/detail.html",
            final_url="https://example.invalid/detail.html",
            crawl_time=CRAWL_TIME,
            http_status=200,
            content_type="text/html",
            raw=raw,
            discovery_method="list",
        )


def test_failure_writer_records_contract_fields(tmp_path):
    writer = FailureWriter(tmp_path / "data")
    row = writer.record(
        source_id="DEMO",
        url="https://example.invalid/attachments/unavailable.pdf",
        time=CRAWL_TIME,
        stage="fetch",
        error_type="http_error",
        message="HTTP 404",
        retry_count=0,
        final_action="record_only",
        referrer_url="https://example.invalid/detail.html",
    )
    required = {
        "source_id",
        "url",
        "time",
        "stage",
        "error_type",
        "message",
        "retry_count",
        "final_action",
    }
    assert required <= set(row)
    assert row["retry_count"] == 0
    assert json.loads(writer.path.read_text(encoding="utf-8").splitlines()[0]) == row
    with pytest.raises(ValueError, match="失败阶段"):
        writer.record(
            source_id="DEMO",
            url="https://example.invalid/x",
            time=CRAWL_TIME,
            stage="unknown",
            error_type="x",
            message="x",
        )
    with pytest.raises(ValueError, match="处置"):
        writer.record(
            source_id="DEMO",
            url="https://example.invalid/x",
            time=CRAWL_TIME,
            stage="fetch",
            error_type="x",
            message="x",
            final_action="unknown",
        )


def test_interrupted_write_leaves_no_partial_or_temporary_file(store):
    def interrupted_chunks():
        yield b"part-1"
        raise RuntimeError("模拟写入中断")

    with pytest.raises(RuntimeError, match="中断"):
        store.write_stream(
            source_id="DEMO",
            crawl_date="2026-09-11",
            kind="html",
            filename="interrupted.html",
            chunks=interrupted_chunks(),
        )
    directory = store.data_dir / "raw/DEMO/2026-09-11/html"
    assert list(directory.iterdir()) == []
    assert not (store.data_dir / "manifests" / "crawl_manifest.jsonl").exists()
