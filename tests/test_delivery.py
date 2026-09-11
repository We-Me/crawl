"""T018：交付目录布局、六项成果完整性与采集阶段边界（FR-019/FR-020）。"""

from datetime import datetime, timedelta, timezone

import pytest

from crawler.fetch.http_client import FetchLimits, HttpClient
from crawler.monitor.failures import FailureLedger
from crawler.monitor.logger import close_run_logging, log_path
from crawler.monitor.metrics import read_metrics
from crawler.output.delivery import REQUIRED_DELIVERABLES, inspect_delivery
from crawler.output.documents_writer import DocumentsWriter
from crawler.output.failures_writer import FailureWriter
from crawler.output.jsonl import read_jsonl, write_jsonl
from crawler.output.layout import DeliveryLayout
from crawler.output.manifest_writer import ManifestWriter
from crawler.pipeline import CrawlPipeline
from crawler.util.paths import PathSafetyError

NOW = datetime(2026, 9, 11, 10, 0, 0, tzinfo=timezone(timedelta(hours=8)))


@pytest.fixture()
def pipeline_factory(tmp_path, site_server):
    def make(registry, **kwargs):
        http = HttpClient(
            registry, limits=FetchLimits(request_rate_per_second=1000, max_retries=2)
        )
        return CrawlPipeline(registry, tmp_path / "data", http=http, now=lambda: NOW, **kwargs)

    return make


# ---------- 布局 ----------


def test_layout_creates_four_dirs_and_keeps_paths_under_root(tmp_path):
    layout = DeliveryLayout(tmp_path / "data")
    assert layout.ensure().data_dir == (tmp_path / "data").resolve()
    assert sorted(child.name for child in layout.data_dir.iterdir()) == [
        "logs",
        "manifests",
        "normalized",
        "raw",
    ]
    for path in (
        layout.manifest_path,
        layout.failures_path,
        layout.documents_path,
        layout.blocks_path,
        layout.crawler_log_path,
        layout.metrics_path,
        layout.metrics_history_path,
        layout.incremental_state_path,
    ):
        assert layout.data_dir in path.parents


def test_writers_share_the_layout_paths(tmp_path):
    layout = DeliveryLayout(tmp_path)
    assert ManifestWriter(tmp_path).path == layout.manifest_path
    assert FailureWriter(tmp_path).path == layout.failures_path
    assert DocumentsWriter(tmp_path).path == layout.documents_path
    from crawler.output.blocks_writer import blocks_path

    assert blocks_path(tmp_path) == layout.blocks_path
    assert FailureLedger(tmp_path).path == layout.failures_path
    assert log_path(tmp_path) == layout.crawler_log_path


def test_resolve_raw_path_rejects_escape(tmp_path):
    layout = DeliveryLayout(tmp_path / "data").ensure()
    target = layout.raw_dir / "DEMO" / "2026-09-11" / "html"
    target.mkdir(parents=True)
    (target / "page.html").write_text("<html></html>", encoding="utf-8")

    ok = layout.resolve_raw_path("raw/DEMO/2026-09-11/html/page.html")
    assert ok.is_file() and ok.is_relative_to(layout.data_dir)
    with pytest.raises(PathSafetyError):
        layout.resolve_raw_path(str(ok))
    with pytest.raises(PathSafetyError):
        layout.resolve_raw_path("raw/../../outside.html")
    with pytest.raises(PathSafetyError):
        layout.resolve_raw_path("")

    outside = tmp_path / "outside"
    outside.mkdir()
    (layout.raw_dir / "LINK").symlink_to(outside)
    with pytest.raises(PathSafetyError):
        layout.resolve_raw_path("raw/LINK/leak.html")


# ---------- 交付包检查 ----------


def test_inspect_delivery_accepts_complete_package(
    site_server, registry_factory, pipeline_factory, tmp_path
):
    registry = registry_factory(site_server)
    pipeline = pipeline_factory(registry)
    report = pipeline.collect("TESTSRC", entry_urls=[f"{site_server}/index.html"])
    data = tmp_path / "data"
    try:
        result = inspect_delivery(data)
        assert result.ok is True, result.as_row()
        assert result.missing == [] and result.forbidden == [] and result.path_issues == []
        names = [item["name"] for item in result.present]
        assert names == [name for name, _, _ in REQUIRED_DELIVERABLES]
        stored = read_metrics(data)
        assert result.counts["manifest_rows"] == stored["counters"]["resources"]
        assert result.counts["document_rows"] == stored["counters"]["documents"]
        assert result.counts["block_rows"] == stored["counters"]["blocks"]
        assert result.counts["failure_rows"] == stored["counters"]["failures"]
        assert result.counts["raw_files"] == report.counters.resources
    finally:
        close_run_logging(data)


def test_inspect_delivery_allows_absent_failed_records_when_no_failure(
    site_server, registry_factory, pipeline_factory, tmp_path
):
    registry = registry_factory(site_server)
    pipeline = pipeline_factory(registry)
    report = pipeline.collect("TESTSRC", entry_urls=[f"{site_server}/page2.html"])
    data = tmp_path / "data"
    try:
        assert report.counters.failures == 0
        assert not (data / "manifests" / "failed_records.jsonl").exists()
        result = inspect_delivery(data)
        assert result.ok is True, result.as_row()
        failed = next(item for item in result.present if item["kind"] == "file_optional_if_empty")
        assert failed["present"] is True and failed["optional"] is True
        assert any("零失败" in note for note in result.notes)
    finally:
        close_run_logging(data)


def test_inspect_delivery_reports_forbidden_rag_artifacts(tmp_path):
    layout = DeliveryLayout(tmp_path / "data").ensure()
    write_jsonl(layout.manifest_path, [])
    write_jsonl(layout.documents_path, [])
    write_jsonl(layout.blocks_path, [])
    (layout.data_dir / "normalized" / "chunks.jsonl").write_text("{}\n", encoding="utf-8")
    (layout.data_dir / "vectors").mkdir()
    (layout.data_dir / "vectors" / "index.faiss").write_bytes(b"\x00")
    result = inspect_delivery(layout.data_dir)
    assert result.ok is False
    assert "normalized/chunks.jsonl" in result.forbidden
    assert "vectors" in result.forbidden
    assert "vectors/index.faiss" in result.forbidden


def test_inspect_delivery_reports_broken_raw_paths(tmp_path):
    layout = DeliveryLayout(tmp_path / "data").ensure()
    raw = layout.raw_dir / "DEMO" / "2026-09-11" / "html"
    raw.mkdir(parents=True)
    (raw / "ok.html").write_text("<html></html>", encoding="utf-8")
    write_jsonl(
        layout.manifest_path,
        [
            {"crawl_id": "ok", "raw_path": "raw/DEMO/2026-09-11/html/ok.html"},
            {"crawl_id": "abs", "raw_path": str(raw / "ok.html")},
            {"crawl_id": "blank"},
        ],
    )
    write_jsonl(
        layout.documents_path,
        [
            {
                "doc_id": "d1",
                "raw_path": "raw/../outside.html",
                "attachments": [
                    {"filename": "gone.csv", "status": "downloaded", "raw_path": "raw/DEMO/gone.csv"},
                    {"filename": "failed.pdf", "status": "failed"},
                ],
            }
        ],
    )
    write_jsonl(layout.blocks_path, [])
    write_jsonl(layout.failures_path, [])
    result = inspect_delivery(layout.data_dir)
    assert result.ok is False
    reasons = [issue["reason"] for issue in result.path_issues]
    assert any("必须是相对路径" in reason for reason in reasons)
    assert any("缺少 raw_path" in reason for reason in reasons)
    assert any("原件不存在" in reason for reason in reasons)
    assert any("不能包含 .." in reason for reason in reasons)
    # 失败附件没有 raw_path 不算问题
    assert all(issue.get("context") != "failed.pdf" for issue in result.path_issues)


def test_recovery_reparse_rejects_out_of_root_raw_path(
    site_server, registry_factory, pipeline_factory, tmp_path
):
    registry = registry_factory(site_server)
    pipeline = pipeline_factory(registry)
    data = tmp_path / "data"
    layout = DeliveryLayout(data).ensure()
    write_jsonl(
        layout.manifest_path,
        [{"crawl_id": "BAD_0001", "raw_path": "../../etc/passwd"}],
    )
    write_jsonl(
        layout.failures_path,
        [
            {
                "source_id": "TESTSRC",
                "url": f"{site_server}/broken.html",
                "time": NOW.isoformat(),
                "stage": "parse",
                "error_type": "parse_error",
                "message": "解析失败",
                "retry_count": 0,
                "final_action": "retry_later",
                "crawl_id": "BAD_0001",
            }
        ],
    )
    try:
        report = pipeline.resume_failures("TESTSRC", max_tasks=1)
        assert report.recovered == []
        assert len(report.failures) == 1  # 越界原件不允许重解析，失败保持未关闭
        assert len(FailureLedger(data).open_failures()) == 1
        assert read_jsonl(layout.documents_path) == []
    finally:
        close_run_logging(data)
