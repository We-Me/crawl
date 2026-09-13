"""T017：运行日志、计数、重复与异常统计，按不同口径对账（FR-018）。"""

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from crawler.fetch.http_client import FetchLimits, HttpClient
from crawler.monitor.failures import FailureLedger
from crawler.monitor.logger import (
    LOG_FILENAME,
    close_run_logging,
    configure_run_logging,
    log_path,
    log_run_context,
)
from crawler.monitor.metrics import (
    COUNTING_RULES as RULES,
    MetricsConfigError,
    build_metrics,
    count_rows,
    deltas_between,
    duplicate_stats,
    duplicate_stats_from_files,
    output_stats,
    read_metrics,
    reconcile,
    write_metrics,
)
from crawler.output.jsonl import write_jsonl
from crawler.pipeline import CrawlPipeline

NOW = datetime(2026, 9, 11, 10, 0, 0, tzinfo=timezone(timedelta(hours=8)))


@pytest.fixture()
def pipeline_factory(tmp_path, site_server):
    def make(registry, **kwargs):
        http = HttpClient(
            registry, limits=FetchLimits(request_rate_per_second=1000, max_retries=2)
        )
        return CrawlPipeline(
            registry,
            tmp_path / "data",
            http=http,
            now=lambda: NOW,
            **kwargs,
        )

    return make


def _document(doc_id, sha, text="正文", source_id="src", url=None):
    return {
        "doc_id": doc_id,
        "source_id": source_id,
        "source_url": url or f"https://example.invalid/{doc_id}",
        "title": "标题",
        "full_text": text,
        "sha256": sha,
    }


# ---------- 日志 ----------


def test_run_logging_is_idempotent_and_writes_to_data_root(tmp_path):
    close_run_logging()
    logger = logging.getLogger("crawler")
    path = configure_run_logging(tmp_path)
    assert path == tmp_path / "logs" / LOG_FILENAME
    first_handlers = [h for h in logger.handlers if getattr(h, "_crawler_run_handler", False)]
    configure_run_logging(tmp_path)
    second_handlers = [h for h in logger.handlers if getattr(h, "_crawler_run_handler", False)]
    assert len(first_handlers) == 1 and len(second_handlers) == 1

    logger.info("运行测试消息 key=值")
    for handler in second_handlers:
        handler.flush()
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if "运行测试消息" in line]
    assert len(lines) == 1
    close_run_logging()


def test_run_context_logs_mode_and_data_root_without_env(tmp_path):
    from crawler.config.settings import Settings

    close_run_logging()
    configure_run_logging(tmp_path)
    records = []

    class Capture(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    capture = Capture()
    logger = logging.getLogger("crawler")
    logger.addHandler(capture)
    settings = Settings(
        mode="development",
        data_dir=tmp_path,
        project_root=tmp_path,
        data_dir_from_default=True,
    )
    try:
        log_run_context(logger, settings)
    finally:
        logger.removeHandler(capture)
        close_run_logging(tmp_path)
    assert any("mode=development" in message and str(tmp_path) in message for message in records)
    assert all("CRAWL_DATA_DIR=" not in message for message in records)


# ---------- 计数口径与对账 ----------


def test_counting_rules_distinguish_requests_resources_documents_blocks():
    assert set(RULES) >= {"requests", "resources", "documents", "blocks", "failures", "skipped"}
    assert "不等于文档数" in RULES["requests"]
    assert "manifest" in RULES["resources"]
    assert "documents.jsonl" in RULES["documents"]


def test_output_stats_and_deltas(tmp_path):
    write_jsonl(tmp_path / "manifests" / "crawl_manifest.jsonl", [{"a": 1}, {"a": 2}])
    write_jsonl(tmp_path / "normalized" / "documents.jsonl", [{"d": 1}])
    write_jsonl(tmp_path / "normalized" / "blocks.jsonl", [{"b": 1}, {"b": 2}, {"b": 3}])
    (tmp_path / "raw" / "DEMO").mkdir(parents=True)
    (tmp_path / "raw" / "DEMO" / "page.html").write_text("<html></html>", encoding="utf-8")
    before = output_stats(tmp_path)
    assert before == {
        "crawl_manifest_rows": 2,
        "documents_rows": 1,
        "blocks_rows": 3,
        "failed_rows": 0,
        "raw_files": 1,
    }
    write_jsonl(tmp_path / "manifests" / "failed_records.jsonl", [{"f": 1}])
    after = output_stats(tmp_path)
    deltas = deltas_between(before, after)
    assert deltas["failed_rows"] == 1 and deltas["documents_rows"] == 0
    assert count_rows(tmp_path / "manifests" / "crawl_manifest.jsonl") == 2


def test_output_stats_attributes_rows_per_source_for_parallel_runs(tmp_path):
    # 两个来源并行共用数据根：未给 source_id 时数全量，给出时只数本来源的行。
    write_jsonl(
        tmp_path / "manifests" / "crawl_manifest.jsonl",
        [
            {"crawl_id": "SRCA_20260913_0001", "source_id": "SRCA"},
            {"crawl_id": "SRCB_20260913_0001", "source_id": "SRCB"},
        ],
    )
    write_jsonl(
        tmp_path / "normalized" / "documents.jsonl",
        [{"doc_id": "SRCB_20260913_0001", "source_id": "SRCB"}],
    )
    write_jsonl(
        tmp_path / "normalized" / "blocks.jsonl",
        [{"doc_id": "SRCA_20260913_0001"}, {"doc_id": "SRCB_20260913_0001"}],
    )
    write_jsonl(tmp_path / "manifests" / "failed_records.jsonl", [{"source_id": "SRCB"}])
    for source in ("SRCA", "SRCB"):
        (tmp_path / "raw" / source).mkdir(parents=True)
        (tmp_path / "raw" / source / "page.html").write_text("<html></html>", encoding="utf-8")

    everything = output_stats(tmp_path)
    assert everything["crawl_manifest_rows"] == 2 and everything["raw_files"] == 2
    assert output_stats(tmp_path, source_id="SRCA") == {
        "crawl_manifest_rows": 1,
        "documents_rows": 0,
        "blocks_rows": 1,
        "failed_rows": 0,
        "raw_files": 1,
    }
    assert count_rows(tmp_path / "manifests" / "crawl_manifest.jsonl", source_id="SRCB") == 1


def test_duplicate_stats_require_explicit_near_threshold():
    documents = [
        _document("d1", "a" * 64, "同一段虚构正文。", source_id="src_a"),
        _document("d2", "b" * 64, "同一段虚构正文。", source_id="src_b"),
    ]
    stats = duplicate_stats(documents)
    assert stats["policy"] == "keep_all_sources"
    assert stats["exact_text"]["groups"] == 1
    assert stats["duplicate_documents"] == 2
    assert stats["near_text"]["status"] == "not_computed"
    assert "Q11" in stats["near_text"]["reason"]
    with pytest.raises(MetricsConfigError):
        duplicate_stats(documents, threshold=1.5)
    with_threshold = duplicate_stats(documents, threshold=0.99)
    assert with_threshold["near_text"]["status"] == "computed"
    assert with_threshold["near_text"]["threshold"] == 0.99


def test_reconcile_detects_injected_discrepancy(tmp_path):
    before = output_stats(tmp_path)
    write_jsonl(tmp_path / "manifests" / "crawl_manifest.jsonl", [{"a": 1}])
    after = output_stats(tmp_path)
    metrics = build_metrics(
        source_id="TESTSRC",
        kind="collect",
        started_at=NOW.isoformat(),
        finished_at=NOW.isoformat(),
        counters={
            "requests": 7,
            "resources": 2,  # 账本只有 1 行 → 必须报差异
            "documents": 1,
            "blocks": 3,
            "failures": 0,
            "skipped": 0,
            "not_modified": 0,
        },
        before=before,
        after=after,
        duplicates=duplicate_stats([]),
    )
    result = reconcile(metrics)
    assert result["ok"] is False
    assert "资源数与账本追加行数一致" in result["discrepancies"]
    assert metrics.status == "ok"  # 状态与对账结论分开：有成果但有计数差异


def test_metrics_status_and_notes_follow_coverage(tmp_path):
    """S5-03/S5-06：发现截断或仍有待处理时不报 ok，覆盖口径进入说明。"""
    counts = {
        "requests": 2,
        "resources": 1,
        "documents": 1,
        "blocks": 3,
        "failures": 0,
        "skipped": 0,
        "not_modified": 0,
    }

    def build(coverage):
        return build_metrics(
            source_id="TESTSRC",
            kind="collect",
            started_at=NOW.isoformat(),
            finished_at=NOW.isoformat(),
            counters=counts,
            before=output_stats(tmp_path),
            after=output_stats(tmp_path),
            duplicates=duplicate_stats([]),
            coverage=coverage,
        )

    truncated = build(
        {
            "targets": {"discovered": 3, "attempted": 1, "processed": 1},
            "attachments": {"discovered": 0, "downloaded": 0, "pending": 2},
            "discovery": {
                "complete": False,
                "incomplete_runs": 1,
                "stops": [
                    {
                        "stage": "list",
                        "entry": "http://example.invalid/list",
                        "stop": "max_items_reached",
                        "complete": False,
                    }
                ],
            },
            "pending_total": 2,
        }
    )
    assert truncated.status == "partial"
    assert any("发现遍历未完成" in note for note in truncated.notes)
    assert any("待处理项未清空" in note for note in truncated.notes)
    assert any("覆盖口径" in note for note in truncated.notes)

    complete = build(
        {
            "targets": {"discovered": 1, "attempted": 1, "processed": 1},
            "attachments": {"discovered": 1, "downloaded": 1, "pending": 0},
            "discovery": {"complete": True, "incomplete_runs": 0, "stops": []},
            "pending_total": 0,
        }
    )
    assert complete.status == "ok"
    assert not any("发现遍历未完成" in note for note in complete.notes)


def test_metrics_written_atomically_and_history_appended(tmp_path):
    before = output_stats(tmp_path)
    write_jsonl(tmp_path / "normalized" / "documents.jsonl", [{"doc_id": "d1"}])
    write_jsonl(tmp_path / "normalized" / "blocks.jsonl", [{"doc_id": "d1"}])
    metrics = build_metrics(
        source_id="TESTSRC",
        kind="collect",
        started_at=NOW.isoformat(),
        finished_at=NOW.isoformat(),
        counters={
            "requests": 3,
            "resources": 0,
            "documents": 1,
            "blocks": 1,
            "failures": 0,
            "skipped": 0,
            "not_modified": 0,
        },
        before=before,
        after=output_stats(tmp_path),
        duplicates=duplicate_stats([]),
    )
    path = write_metrics(tmp_path, metrics)
    assert path.is_file() and path.name == "metrics.json"
    stored = read_metrics(tmp_path)
    assert stored["counters"]["documents"] == 1
    assert stored["counting_rules"]["requests"] == RULES["requests"]
    assert stored["duplicates"]["policy"] == "keep_all_sources"
    history = tmp_path / "logs" / "metrics_history.jsonl"
    assert len(history.read_text(encoding="utf-8").splitlines()) == 1
    assert not list((tmp_path / "logs").glob("*.tmp"))


def test_duplicate_stats_from_files_reads_delivery(tmp_path):
    write_jsonl(
        tmp_path / "normalized" / "documents.jsonl",
        [_document("d1", "a" * 64), _document("d2", "a" * 64, source_id="other")],
    )
    stats = duplicate_stats_from_files(tmp_path)
    assert stats["exact_bytes"]["groups"] == 1


# ---------- 端到端 ----------


def test_pipeline_writes_logs_and_metrics_after_mixed_run(
    site_server, registry_factory, pipeline_factory, tmp_path
):
    registry = registry_factory(site_server)
    pipeline = pipeline_factory(registry)
    report = pipeline.collect("TESTSRC", entry_urls=[f"{site_server}/index.html"])
    data = tmp_path / "data"
    assert report.metrics is not None
    assert report.metrics["status"] == "partial"  # 一个附件失败

    stored = read_metrics(data)
    assert stored is not None
    assert stored["run_id"] == report.metrics["run_id"]
    assert stored["counters"]["requests"] != stored["counters"]["documents"]
    # 资源 = 两个发现页（S5-01 也归档）+ 两份文档 + 一个成功附件
    assert stored["counters"]["resources"] == stored["counters"]["documents"] + 3
    assert stored["failures_by_stage"] == {"fetch": 1}
    assert stored["reconciliation"]["ok"] is True, stored["reconciliation"]["discrepancies"]
    assert stored["skipped_by_reason"] == {"domain_not_allowed:outside.invalid": 1}

    log_file = log_path(data)
    assert log_file.is_file() and log_file.name == LOG_FILENAME
    log_text = log_file.read_text(encoding="utf-8")
    assert "运行汇总" in log_text and "reconciliation_ok=True" in log_text
    assert "失败记录" in log_text  # 异常信息同时进日志
    close_run_logging(data)


def test_pipeline_metrics_flag_not_modified_without_false_documents(
    site_server, registry_factory, pipeline_factory, tmp_path
):
    registry = registry_factory(site_server)
    pipeline = pipeline_factory(registry)
    url = f"{site_server}/_etag/index.html"
    first = pipeline.collect("TESTSRC", entry_urls=[url])
    second = pipeline.collect("TESTSRC", entry_urls=[url])
    data = tmp_path / "data"
    assert second.counters.documents == 0
    stored = read_metrics(data)
    assert stored["run_id"] == second.metrics["run_id"]
    assert stored["counters"]["not_modified"] == 2  # detail_1 与 detail_2 均返回 304
    assert stored["counters"]["documents"] == 0
    assert stored["skipped_by_reason"]["not_modified"] == 2
    assert stored["counters"]["requests"] >= 1
    assert stored["reconciliation"]["ok"] is True
    assert "本次无新增成果" in ";".join(stored["notes"])
    assert first.counters.documents >= 1
    close_run_logging(data)


def test_pipeline_logs_exception_and_reconciles_failures(
    site_server, registry_factory, pipeline_factory, tmp_path
):
    registry = registry_factory(site_server)
    pipeline = pipeline_factory(registry)
    report = pipeline.collect("TESTSRC", entry_urls=[f"{site_server}/index.html"])
    data = tmp_path / "data"
    stored = read_metrics(data)
    assert stored["failures_by_type"] == {"http_error": 1}
    rows = FailureLedger(data).load()
    assert len(rows) == report.counters.failures
    assert stored["status_counts"]["failed"] == 1
    assert stored["status_counts"]["success"] == report.counters.resources
    close_run_logging(data)
