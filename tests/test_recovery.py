"""T016：分阶段失败账、补抓与运行恢复。"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from crawler.fetch.http_client import FetchLimits, HttpClient
from crawler.fetch.retry import (
    MANUAL,
    REFETCH,
    REPARSE,
    RetryConfigError,
    RetryPolicy,
    backoff_delay,
    build_recovery_plan,
    http_status_of,
    is_permanent,
    plan_is_ready,
    plan_retry,
    summarize_plan,
)
from crawler.monitor.failures import FailureLedger, FailureLedgerError
from crawler.output.jsonl import read_jsonl
from crawler.pipeline import CrawlPipeline

NOW = datetime(2026, 9, 11, 10, 0, 0, tzinfo=timezone(timedelta(hours=8)))
FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


def _failure(stage="fetch", retry_count=0, message="HTTP 500", **extra):
    row = {
        "source_id": "TESTSRC",
        "url": "https://example.invalid/a",
        "time": NOW.isoformat(),
        "stage": stage,
        "error_type": "http_error" if stage == "fetch" else "parse_error",
        "message": message,
        "retry_count": retry_count,
        "final_action": "retry_later",
    }
    row.update(extra)
    return row


def _pipeline(registry, data_dir):
    return CrawlPipeline(
        registry,
        data_dir,
        http=HttpClient(registry, limits=FetchLimits(request_rate_per_second=1000)),
        now=lambda: NOW,
    )


# ---------- 补抓策略 ----------


def test_retry_policy_backoff_and_limits():
    policy = RetryPolicy(max_attempts=3, base_delay_seconds=60, max_delay_seconds=120)
    assert backoff_delay(1, policy) == 60
    assert backoff_delay(2, policy) == 120
    assert backoff_delay(5, policy) == 120
    with pytest.raises(RetryConfigError):
        RetryPolicy(max_attempts=0)
    with pytest.raises(RetryConfigError):
        RetryPolicy(base_delay_seconds=0)


def test_plan_retry_routes_stages():
    policy = RetryPolicy(max_attempts=2)
    fetch_task = plan_retry(_failure(), policy=policy, now=NOW)
    assert fetch_task.action == REFETCH and fetch_task.attempt == 1
    assert fetch_task.not_before > NOW

    parse_task = plan_retry(
        _failure(stage="parse"), policy=policy, now=NOW, raw_path="raw/a.html"
    )
    assert parse_task.action == REPARSE and parse_task.raw_path == "raw/a.html"

    no_raw = plan_retry(_failure(stage="parse"), policy=policy, now=NOW)
    assert no_raw.action == MANUAL and "原件" in no_raw.reason

    exhausted = plan_retry(_failure(retry_count=2), policy=policy, now=NOW)
    assert exhausted.action == MANUAL and "用尽" in exhausted.reason

    unknown = plan_retry(_failure(stage="unknown"), policy=policy, now=NOW)
    assert unknown.action == MANUAL


def test_permanent_4xx_is_not_retried():
    assert is_permanent(_failure(message="HTTP 404")) is True
    assert is_permanent(_failure(message="HTTP 429")) is False
    assert is_permanent(_failure(message="HTTP 503")) is False
    assert is_permanent(_failure(message="连接超时")) is False
    task = plan_retry(_failure(message="HTTP 404"), policy=RetryPolicy(), now=NOW)
    assert task.action == MANUAL and "永久" in task.reason
    assert http_status_of({"message": "HTTP 404"}) == 404
    assert http_status_of({"http_status": 500}) == 500
    assert http_status_of({"message": "no status"}) is None


def test_build_recovery_plan_uses_manifest_raw_path():
    tasks = build_recovery_plan(
        [_failure(stage="normalize", crawl_id="C1")],
        now=NOW,
        manifest_by_crawl_id={"C1": {"raw_path": "raw/src/2026-09-11/html/a.html"}},
    )
    assert tasks[0].action == REPARSE and tasks[0].raw_path.endswith("a.html")
    assert summarize_plan(tasks) == {"reparse": 1}
    assert plan_is_ready(tasks[0], now=NOW) is False


@pytest.mark.parametrize(
    "stage,expected",
    [
        ("discover", REFETCH),
        ("fetch", REFETCH),
        ("parse", REPARSE),
        ("normalize", REPARSE),
        ("validate", REPARSE),
    ],
)
def test_four_stages_route_to_recovery(stage, expected):
    task = plan_retry(_failure(stage=stage), policy=RetryPolicy(), now=NOW, raw_path="raw/x.html")
    assert task.action == expected


# ---------- 失败账 ----------


def test_ledger_keeps_history_and_closes_open_failure(tmp_path):
    ledger = FailureLedger(tmp_path)
    original = ledger.writer.record(
        source_id="TESTSRC",
        url="https://example.invalid/a",
        time=NOW.isoformat(),
        stage="fetch",
        error_type="http_error",
        message="HTTP 500",
        retry_count=0,
        final_action="retry_later",
    )
    assert [row["url"] for row in ledger.open_failures()] == ["https://example.invalid/a"]
    resolution = ledger.record_resolution(
        original, now=NOW + timedelta(minutes=5), note="补抓成功", crawl_id="C2"
    )
    assert resolution["final_action"] == "recovered"
    assert resolution["previous_time"] == original["time"]
    assert ledger.open_failures() == []
    history = ledger.history_of("https://example.invalid/a")
    assert len(history) == 2 and history[0]["final_action"] == "retry_later"

    with pytest.raises(FailureLedgerError):
        ledger.record_resolution(original, now=NOW, note="x", action="unknown")


def test_ledger_latest_row_per_url_and_stage_wins(tmp_path):
    ledger = FailureLedger(tmp_path)
    for action in ("retry_later", "skip"):
        ledger.writer.record(
            source_id="TESTSRC",
            url="https://example.invalid/a",
            time=NOW.isoformat(),
            stage="fetch",
            error_type="http_error",
            message="HTTP 500",
            retry_count=0,
            final_action=action,
        )
    ledger.writer.record(
        source_id="TESTSRC",
        url="https://example.invalid/a",
        time=NOW.isoformat(),
        stage="parse",
        error_type="parse_error",
        message="坏结构",
        retry_count=0,
        final_action="retry_later",
    )
    assert [row["stage"] for row in ledger.open_failures()] == ["parse"]


def test_pending_documents_lists_downloaded_without_document(tmp_path):
    from crawler.output.jsonl import write_jsonl

    ledger = FailureLedger(tmp_path)
    (tmp_path / "manifests").mkdir(parents=True, exist_ok=True)
    write_jsonl(
        ledger.data_dir / "manifests" / "crawl_manifest.jsonl",
        [
            {"crawl_id": "C1", "final_url": "https://example.invalid/a", "raw_path": "raw/a.html"},
            {"crawl_id": "C2", "final_url": "https://example.invalid/b", "raw_path": "raw/b.html"},
        ],
    )
    write_jsonl(
        ledger.data_dir / "normalized" / "documents.jsonl",
        [{"doc_id": "C1", "crawl_ids": ["C1"]}],
    )
    pending = ledger.pending_documents()
    assert [row["crawl_id"] for row in pending] == ["C2"]


# ---------- 端到端补抓 ----------


def test_resume_refetch_recovers_network_failure(site_server, registry_factory, tmp_path):
    registry = registry_factory(site_server)
    pipeline = _pipeline(registry, tmp_path / "data")
    url = f"{site_server}/_etag/detail_1.html"
    failure = pipeline.failures.record(
        source_id="TESTSRC",
        url=url,
        time=NOW.isoformat(),
        stage="fetch",
        error_type="http_error",
        message="HTTP 500",
        retry_count=0,
        final_action="retry_later",
    )
    plan = pipeline.recovery_plan()
    assert [task.action for task in plan] == [REFETCH]

    report = pipeline.resume_failures("TESTSRC")
    assert report.counters.documents == 1
    assert len(report.recovered) == 1 and report.failures == [] and report.manual == []
    documents = read_jsonl(tmp_path / "data" / "normalized" / "documents.jsonl")
    assert len(documents) == 1
    history = pipeline.failures_ledger.history_of(url)
    assert [row["final_action"] for row in history] == ["retry_later", "recovered"]
    assert history[0] == failure  # 历史失败未被改写


def test_resume_reparse_recovers_local_failure_without_network(
    site_server, registry_factory, tmp_path
):
    registry = registry_factory(site_server)
    pipeline = _pipeline(registry, tmp_path / "data")
    pdf_bytes = (FIXTURES / "attachments" / "notice.pdf").read_bytes()
    url = f"{site_server}/attachments/notice.pdf"
    raw = pipeline.store.write_bytes(
        source_id="TESTSRC",
        crawl_date="2026-09-11",
        kind="attachment",
        filename="notice.pdf",
        content=pdf_bytes,
    )
    crawl_id = "TESTSRC_20260911_0009"
    pipeline.manifest.record(
        crawl_id=crawl_id,
        source_id="TESTSRC",
        requested_url=url,
        final_url=url,
        crawl_time=NOW.isoformat(),
        http_status=200,
        content_type="application/pdf",
        raw=raw,
        discovery_method="attachment",
    )
    pipeline.failures.record(
        source_id="TESTSRC",
        url=url,
        time=NOW.isoformat(),
        stage="parse",
        error_type="parse_error",
        message="解析失败",
        retry_count=0,
        final_action="retry_later",
        crawl_id=crawl_id,
    )
    assert pipeline.recovery_plan()[0].action == REPARSE

    report = pipeline.resume_failures("TESTSRC")
    assert report.counters.documents == 1 and report.counters.blocks > 0
    documents = read_jsonl(tmp_path / "data" / "normalized" / "documents.jsonl")
    assert documents[0]["doc_id"] == crawl_id
    assert documents[0]["extraction_method"] == "pypdf_text"
    assert (tmp_path / "data" / raw.relative_path).read_bytes() == pdf_bytes  # 原件未变


def test_resume_failures_only_handles_requested_source(
    site_server, registry_factory, tmp_path
):
    registry = registry_factory(site_server)
    pipeline = _pipeline(registry, tmp_path / "data")
    other_url = f"{site_server}/other-source-500"
    pipeline.failures.record(
        source_id="OTHER",
        url=other_url,
        time=NOW.isoformat(),
        stage="fetch",
        error_type="http_error",
        message="HTTP 500",
        retry_count=0,
        final_action="retry_later",
    )
    pipeline.failures.record(
        source_id="TESTSRC",
        url=f"{site_server}/_etag/detail_1.html",
        time=NOW.isoformat(),
        stage="fetch",
        error_type="http_error",
        message="HTTP 500",
        retry_count=0,
        final_action="retry_later",
    )

    report = pipeline.resume_failures("TESTSRC")

    assert len(report.recovered) == 1 and report.failures == []
    remaining = pipeline.recovery_plan()
    assert [(task.source_id, task.url) for task in remaining] == [("OTHER", other_url)]


def test_resume_reports_manual_and_pending(site_server, registry_factory, tmp_path):
    registry = registry_factory(site_server)
    pipeline = _pipeline(registry, tmp_path / "data")
    pipeline.failures.record(
        source_id="TESTSRC",
        url=f"{site_server}/gone",
        time=NOW.isoformat(),
        stage="fetch",
        error_type="http_error",
        message="HTTP 404",
        retry_count=0,
        final_action="record_only",
    )
    report = pipeline.resume_failures("TESTSRC")
    assert len(report.manual) == 1 and "永久" in report.manual[0]["reason"]
    assert report.recovered == []

    pipeline2 = _pipeline(registry, tmp_path / "data2")
    pipeline2.failures.record(
        source_id="TESTSRC",
        url=f"{site_server}/later",
        time=NOW.isoformat(),
        stage="fetch",
        error_type="http_error",
        message="HTTP 500",
        retry_count=0,
        final_action="retry_later",
    )
    waited = pipeline2.resume_failures("TESTSRC", respect_backoff=True)
    assert len(waited.pending) == 1 and waited.recovered == []
