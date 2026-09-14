"""T016：分阶段失败账、补抓与运行恢复。"""

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests
from crawler.discover.discoverer import DiscoveredTarget
from crawler.fetch.budget import RunBudget
from crawler.fetch.downloader import Downloader
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
from crawler.schedule.scope import RunScope

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


def _page(title, body, head=""):
    return (
        '<!DOCTYPE html>\n<html lang="zh-CN"><head><meta charset="utf-8">'
        f"<title>{title}</title>{head}</head><body><main>{body}</main></body></html>"
    )


def _write_paged_body_site(root):
    """两页正文站点：第二页可删除后再恢复，用于片段失败 → 母文档续作场景。"""
    (root / "r7_index.html").write_text(
        _page("R7 列表", '<ul><li><a href="r7_paged_1.html">两页正文</a></li></ul>'),
        encoding="utf-8",
    )
    (root / "r7_paged_1.html").write_text(
        _page(
            "两页正文（第一部分）",
            "<h1>两页正文样本（第一部分）</h1><p>正文第一部分：背景。</p>"
            '<p class="pager"><a rel="next" href="r7_paged_2.html">下一页</a></p>',
        ),
        encoding="utf-8",
    )
    (root / "r7_paged_2.html").write_text(
        _page(
            "两页正文（第二部分）",
            "<h1>两页正文样本（第二部分）</h1><p>正文第二部分：结尾。</p>",
        ),
        encoding="utf-8",
    )


def _budget_pipeline(registry, data_dir, max_requests):
    budget = RunBudget(max_requests=max_requests)
    http = HttpClient(
        registry,
        limits=FetchLimits(request_rate_per_second=1000),
        robots=False,
        budget=budget,
    )
    return CrawlPipeline(registry, data_dir, http=http, now=lambda: NOW), budget


class _FailingCallSession:
    """在第 n 次请求抛指定 requests 异常，之后委托真实 Session（确定性瞬时失败）。"""

    def __init__(self, inner, fail_calls, exc):
        self.inner = inner
        self.fail_calls = set(fail_calls)
        self.exc = exc
        self.calls = 0
        self.headers = inner.headers

    def get(self, url, **kwargs):
        self.calls += 1
        if self.calls in self.fail_calls:
            raise self.exc
        return self.inner.get(url, **kwargs)


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


def test_port_number_in_message_is_not_an_http_status():
    """回归：消息里的端口号（port=443）不得被当作永久 4xx——瞬时超时应可补抓。

    真实失败例：IN-02 条约 PDF 读取超时消息含 "port=443"，曾被误判为永久 4xx
    并转入人工，无法按补抓计划重取。
    """
    message = (
        "读取响应失败：HTTPSConnectionPool(host='www.mea.gov.in', port=443): "
        "Read timed out."
    )
    failure = _failure(message=message)
    assert http_status_of(failure) is None
    assert is_permanent(failure) is False
    task = plan_retry(failure, policy=RetryPolicy(), now=NOW)
    assert task.action == REFETCH


def test_structured_http_status_wins_over_message_text():
    failure = _failure(message="port=443 连接中断", http_status=404)
    assert http_status_of(failure) == 404
    assert is_permanent(failure) is True


def test_non_status_numbers_in_message_are_ignored():
    assert http_status_of({"message": "附件超过 67108864 字节上限"}) is None
    assert http_status_of({"message": "IncompleteRead(28583205 bytes read, 134200808 more expected)"}) is None


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


def test_resume_refetch_enforces_attachment_size_cap(
    site_server, registry_factory, tmp_path
):
    """S5-04 回归：补抓直达非 HTML 原件同样执行附件大小上限。

    真实例（第 83 轮）：IN-02 条约 PDF 经补抓路径归档，绕过了附件下载路径的
    64 MiB 上限与边界拒绝口径；上限是已声明边界，所有入口必须一致。
    确定性边界拒绝按 skip 关闭失败记录，不写失败账残留、不产出原件。
    """
    registry = registry_factory(site_server)
    pipeline = _pipeline(registry, tmp_path / "data")
    pipeline.downloader = Downloader(pipeline.http, max_bytes=10)  # notice.csv 为 22 字节
    url = f"{site_server}/attachments/notice.csv"
    doc_id = "TESTSRC_20260911_0002"
    pipeline.pending.enqueue_attachments(
        source_id="TESTSRC",
        scope_start_date=None,
        doc_id=doc_id,
        parent_url=f"{site_server}/detail_1.html",
        records=[
            {
                "attachment_id": f"{doc_id}_A01",
                "filename": "notice.csv",
                "file_type": "csv",
                "url": url,
                "doc_id": doc_id,
                "referrer_url": f"{site_server}/detail_1.html",
            }
        ],
        enqueued_at=NOW.isoformat(),
    )
    pipeline.failures.record(
        source_id="TESTSRC",
        url=url,
        time=NOW.isoformat(),
        stage="fetch",
        error_type="request_error",
        message="读取响应失败：连接中断",
        retry_count=0,
        final_action="retry_later",
    )
    assert [task.action for task in pipeline.recovery_plan()] == [REFETCH]

    report = pipeline.resume_failures("TESTSRC")

    assert report.recovered == [] and report.failures == []
    assert len(report.skipped) == 1
    queued = next(row for row in pipeline.pending.all_items() if row.url == url)
    assert queued.state == "skipped" and "boundary_rejected" in queued.note
    assert report.skipped[0]["note"] == (
        "边界拒绝，按 skip 关闭：boundary_rejected:size_limit_exceeded:10"
    )
    history = pipeline.failures_ledger.history_of(url)
    assert [row["final_action"] for row in history] == ["retry_later", "skip"]
    manifest_rows = read_jsonl(tmp_path / "data" / "manifests" / "crawl_manifest.jsonl")
    assert all(row.get("requested_url") != url for row in manifest_rows)
    assert pipeline.recovery_plan() == [], "按 skip 关闭后不再重复进入补抓计划"


def test_resume_refetch_closes_matching_pending_item(
    site_server, registry_factory, tmp_path
):
    """S5-06 回归：补抓成功时同步回写同对象的待处理项状态。

    真实例（IN-05）：156 MB 年报 PDF 在待处理队列里长期为 failed，而失败账已在
    补抓后按 recovered 关闭，覆盖表因此显示矛盾的“附件失败 1”；队列口径必须与
    失败账处置对账一致（已提交文档仍不回写，追加写口径不变）。
    """
    registry = registry_factory(site_server)
    pipeline = _pipeline(registry, tmp_path / "data")
    url = f"{site_server}/attachments/notice.csv"
    doc_id = "TESTSRC_20260911_0001"
    pipeline.pending.enqueue_attachments(
        source_id="TESTSRC",
        scope_start_date=None,
        doc_id=doc_id,
        parent_url=f"{site_server}/detail_1.html",
        records=[
            {
                "attachment_id": f"{doc_id}_A01",
                "filename": "notice.csv",
                "file_type": "csv",
                "url": url,
                "doc_id": doc_id,
                "referrer_url": f"{site_server}/detail_1.html",
            }
        ],
        enqueued_at=NOW.isoformat(),
    )
    item = next(row for row in pipeline.pending.all_items() if row.url == url)
    pipeline.pending.mark(
        item.key, state="failed", attempted_at=NOW.isoformat(), note="读取响应失败：连接中断"
    )
    pipeline.failures.record(
        source_id="TESTSRC",
        url=url,
        time=NOW.isoformat(),
        stage="fetch",
        error_type="request_error",
        message="读取响应失败：连接中断",
        retry_count=0,
        final_action="retry_later",
    )

    report = pipeline.resume_failures("TESTSRC")

    assert len(report.recovered) == 1 and report.failures == []
    updated = next(row for row in pipeline.pending.all_items() if row.key == item.key)
    assert updated.state == "processed"
    assert updated.crawl_id and updated.raw_path and updated.sha256
    counts = pipeline.pending.counts("TESTSRC")["attachments"]
    assert counts == {"total": 1, "pending": 0, "processed": 1, "failed": 0, "skipped": 0}
    manifest_rows = read_jsonl(tmp_path / "data" / "manifests" / "crawl_manifest.jsonl")
    row = next(row for row in manifest_rows if row["crawl_id"] == updated.crawl_id)
    assert row["requested_url"] == url and row["raw_path"] == updated.raw_path


def test_resume_refetch_html_page_ignores_attachment_size_cap(
    site_server, registry_factory, tmp_path
):
    """附件上限只约束非 HTML 原件：补抓 HTML 页面不受上限影响。"""
    registry = registry_factory(site_server)
    pipeline = _pipeline(registry, tmp_path / "data")
    pipeline.downloader = Downloader(pipeline.http, max_bytes=10)
    url = f"{site_server}/_etag/detail_1.html"
    pipeline.failures.record(
        source_id="TESTSRC",
        url=url,
        time=NOW.isoformat(),
        stage="fetch",
        error_type="http_error",
        message="HTTP 500",
        retry_count=0,
        final_action="retry_later",
    )

    report = pipeline.resume_failures("TESTSRC")

    assert report.counters.documents == 1 and report.skipped == []
    history = pipeline.failures_ledger.history_of(url)
    assert [row["final_action"] for row in history] == ["retry_later", "recovered"]


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


def test_resume_reparse_closes_matching_pending_item(
    site_server, registry_factory, tmp_path
):
    """S5-06 回归：重解析成功/范围外跳过时同样回写同对象的待处理项。"""
    registry = registry_factory(site_server)
    pipeline = _pipeline(registry, tmp_path / "data")
    url = f"{site_server}/attachments/notice.pdf"
    pdf_bytes = (FIXTURES / "attachments" / "notice.pdf").read_bytes()
    raw = pipeline.store.write_bytes(
        source_id="TESTSRC",
        crawl_date="2026-09-11",
        kind="attachment",
        filename="notice.pdf",
        content=pdf_bytes,
    )
    crawl_id = "TESTSRC_20260911_0011"
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
    pipeline.pending.enqueue_targets(
        source_id="TESTSRC",
        targets=[DiscoveredTarget(url=url, discovery_method="manual")],
        scope_start_date=None,
        enqueued_at=NOW.isoformat(),
    )
    item = next(row for row in pipeline.pending.all_items() if row.url == url)
    pipeline.pending.mark(
        item.key, state="failed", attempted_at=NOW.isoformat(), note="解析失败"
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

    assert report.counters.documents == 1 and report.failures == []
    updated = next(row for row in pipeline.pending.all_items() if row.key == item.key)
    assert updated.state == "processed"
    assert updated.crawl_id == crawl_id and updated.raw_path == raw.relative_path
    assert updated.sha256


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


# ---------- R5：恢复按显式结果与对象身份判定 ----------


def _enqueue_failed_target(pipeline, url, *, scope=None, note="HTTP 500", referrer=None, doc_id=None):
    pipeline.pending.enqueue_targets(
        source_id="TESTSRC",
        targets=[DiscoveredTarget(url=url, discovery_method="manual")],
        scope_start_date=scope,
        enqueued_at=NOW.isoformat(),
    )
    item = next(
        row
        for row in pipeline.pending.all_items()
        if row.url == url and (row.scope_start_date or None) == (scope or None)
    )
    item = pipeline.pending.mark(
        item.key, state="failed", attempted_at=NOW.isoformat(), note=note
    )
    row = pipeline.failures.record(
        source_id="TESTSRC",
        url=url,
        time=NOW.isoformat(),
        stage="fetch",
        error_type="http_error",
        message=note,
        retry_count=0,
        final_action="retry_later",
        scope_start_date=scope,
        referrer_url=referrer,
        doc_id=doc_id,
    )
    return item, row


def test_refetch_parse_failure_stays_open_despite_archived_raw(
    site_server, registry_factory, tmp_path
):
    """R5：HTTP 200 且原件已留存、正文选择器未命中时，不得按资源计数报“恢复成功”。"""
    registry = registry_factory(
        site_server,
        adapter={"list_link_selector": "ul li a", "content_selector": "div.not-here"},
    )
    pipeline = _pipeline(registry, tmp_path / "data")
    url = f"{site_server}/detail_1.html"
    item, _ = _enqueue_failed_target(pipeline, url)
    assert [task.action for task in pipeline.recovery_plan()] == [REFETCH]

    report = pipeline.resume_failures("TESTSRC")

    assert report.recovered == [] and len(report.failures) == 1
    history = pipeline.failures_ledger.history_of(url)
    assert all(row["final_action"] != "recovered" for row in history), (
        "派生 parse 失败仍开放时不得追加 recovered 行掩盖"
    )
    assert history[-1]["stage"] == "parse"
    updated = next(row for row in pipeline.pending.all_items() if row.key == item.key)
    assert updated.state == "failed" and "后续阶段失败" in updated.note
    manifest_rows = read_jsonl(tmp_path / "data" / "manifests" / "crawl_manifest.jsonl")
    assert any(row["requested_url"] == url for row in manifest_rows), "原件已留存"
    assert sorted(task.action for task in pipeline.recovery_plan()) == ["refetch", "reparse"], (
        "fetch 阶段保持开放，派生 parse 阶段另成一条补抓任务"
    )


def test_refetch_normalization_failure_stays_open(
    site_server, registry_factory, tmp_path, monkeypatch
):
    """R5：规范化失败与解析失败不同阶段，但同样不得关闭整个目标。"""
    from crawler.normalize.document_schema import NormalizationError

    registry = registry_factory(site_server)
    pipeline = _pipeline(registry, tmp_path / "data")
    url = f"{site_server}/detail_1.html"
    item, _ = _enqueue_failed_target(pipeline, url)

    def boom(**_kwargs):
        raise NormalizationError("注入的规范化失败")

    monkeypatch.setattr("crawler.pipeline.build_document", boom)
    report = pipeline.resume_failures("TESTSRC")

    assert report.recovered == [] and len(report.failures) == 1
    history = pipeline.failures_ledger.history_of(url)
    assert [row["stage"] for row in history] == ["fetch", "normalize"]
    assert all(row["final_action"] != "recovered" for row in history)
    updated = next(row for row in pipeline.pending.all_items() if row.key == item.key)
    assert updated.state == "failed" and "normalization_error" in updated.note
    assert sorted(task.action for task in pipeline.recovery_plan()) == ["refetch", "reparse"]


def test_refetch_partial_keeps_target_pending_not_complete(
    site_server, registry_factory, tmp_path
):
    """R5：正文分页仍待续时，fetch 阶段可关闭，但主目标保持待处理、不标 processed。"""
    registry = registry_factory(site_server)
    pipeline = _pipeline(registry, tmp_path / "data")
    url = f"{site_server}/loop_a.html"
    item, _ = _enqueue_failed_target(pipeline, url)

    report = pipeline.resume_failures("TESTSRC")

    assert len(report.recovered) == 1 and report.failures == []
    assert "待续" in report.recovered[0]["note"]
    updated = next(row for row in pipeline.pending.all_items() if row.key == item.key)
    assert updated.state == "pending" and "待续" in updated.note
    documents = read_jsonl(tmp_path / "data" / "normalized" / "documents.jsonl")
    assert documents and documents[0]["parse_status"] == "partial"
    history = pipeline.failures_ledger.history_of(url)
    assert history[-1]["final_action"] == "recovered", "网络阶段失败确已解决，可关闭该阶段"


def test_refetch_304_closes_only_with_complete_existing_entity(
    site_server, registry_factory, tmp_path
):
    """R5：304 只在既有实体完整时算恢复；否则保持失败开放。"""
    registry = registry_factory(site_server)
    pipeline = _pipeline(registry, tmp_path / "data")
    url = f"{site_server}/_etag/detail_1.html"
    first = pipeline.collect("TESTSRC", manual_urls=[url], include_attachments=False)
    assert first.counters.documents == 1
    item, _ = _enqueue_failed_target(pipeline, url)

    report = pipeline.resume_failures("TESTSRC")

    assert len(report.recovered) == 1 and report.failures == []
    updated = next(row for row in pipeline.pending.all_items() if row.key == item.key)
    assert updated.state == "processed"
    documents = read_jsonl(tmp_path / "data" / "normalized" / "documents.jsonl")
    assert len(documents) == 1, "304 不产生新文档"


def test_refetch_304_without_document_keeps_failure_open(
    site_server, registry_factory, tmp_path
):
    """R5：304 只说响应未变；没有既有文档时不能据此宣布目标已恢复。"""
    import hashlib
    import json as jsonlib

    registry = registry_factory(site_server)
    pipeline = _pipeline(registry, tmp_path / "data")
    url = f"{site_server}/_etag/detail_1.html"
    etag = '"' + hashlib.sha256((FIXTURES / "site" / "detail_1.html").read_bytes()).hexdigest()[:16] + '"'
    state_path = tmp_path / "data" / "manifests" / "incremental_state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        jsonlib.dumps(
            {
                "version": "0.1.0",
                "resources": {
                    url: {"url": url, "etag": etag, "crawl_id": "TESTSRC_20260910_9999"},
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    item, _ = _enqueue_failed_target(pipeline, url)

    report = pipeline.resume_failures("TESTSRC")

    assert report.recovered == [] and len(report.failures) == 1
    history = pipeline.failures_ledger.history_of(url)
    assert all(row["final_action"] != "recovered" for row in history)
    updated = next(row for row in pipeline.pending.all_items() if row.key == item.key)
    assert updated.state == "failed"


def test_refetch_robots_disallowed_closes_as_skip(site_server, registry_factory, tmp_path):
    """R5：合法访问拒绝（robots）按 skip 关闭，不冒充 recovered、不标 processed。"""
    registry = registry_factory(site_server)
    pipeline = _pipeline(registry, tmp_path / "data")
    url = f"{site_server}/private/secret.html"
    item, _ = _enqueue_failed_target(pipeline, url)

    report = pipeline.resume_failures("TESTSRC")

    assert len(report.skipped) == 1 and report.recovered == [] and report.failures == []
    history = pipeline.failures_ledger.history_of(url)
    assert history[-1]["final_action"] == "skip"
    updated = next(row for row in pipeline.pending.all_items() if row.key == item.key)
    assert updated.state == "skipped"


def test_refetch_out_of_scope_closes_as_skip(site_server, registry_factory, tmp_path):
    """R5：原运行范围外属合法跳过，保留原件但不产出文档，且按同一范围身份关闭。"""
    registry = registry_factory(site_server)
    pipeline = _pipeline(registry, tmp_path / "data")
    url = f"{site_server}/detail_1.html"
    item, _ = _enqueue_failed_target(pipeline, url, scope="2026-09-20")

    report = pipeline.resume_failures("TESTSRC")

    assert len(report.skipped) == 1 and report.recovered == []
    updated = next(row for row in pipeline.pending.all_items() if row.key == item.key)
    assert updated.state == "skipped" and "before_start_date" in updated.note
    assert read_jsonl(tmp_path / "data" / "normalized" / "documents.jsonl") == []


def test_recovery_closes_only_same_scope_identity(site_server, registry_factory, tmp_path):
    """R5：同一 URL 不同运行范围的两个任务不互相关闭。"""
    registry = registry_factory(site_server)
    pipeline = _pipeline(registry, tmp_path / "data")
    url = f"{site_server}/attachments/notice.csv"
    for scope in (None, "2026-09-01"):
        pipeline.pending.enqueue_targets(
            source_id="TESTSRC",
            targets=[DiscoveredTarget(url=url, discovery_method="manual")],
            scope_start_date=scope,
            enqueued_at=NOW.isoformat(),
        )
    for item in pipeline.pending.all_items():
        pipeline.pending.mark(item.key, state="failed", attempted_at=NOW.isoformat(), note="HTTP 500")
    pipeline.failures.record(
        source_id="TESTSRC",
        url=url,
        time=NOW.isoformat(),
        stage="fetch",
        error_type="http_error",
        message="HTTP 500",
        retry_count=0,
        final_action="retry_later",
        scope_start_date="2026-09-01",
    )

    report = pipeline.resume_failures("TESTSRC")

    assert len(report.recovered) == 1
    states = {
        (item.scope_start_date or None): item.state
        for item in pipeline.pending.all_items()
        if item.url == url
    }
    assert states == {None: "failed", "2026-09-01": "processed"}
    history = pipeline.failures_ledger.history_of(url)
    assert [row["final_action"] for row in history] == ["retry_later", "recovered"]
    assert history[-1]["scope_start_date"] == "2026-09-01"


def test_recovery_closes_only_same_parent_document(site_server, registry_factory, tmp_path):
    """R5：同一附件 URL 挂在不同母文档下（或作为主目标）时不按 URL 批量关闭。"""
    registry = registry_factory(site_server)
    pipeline = _pipeline(registry, tmp_path / "data")
    url = f"{site_server}/attachments/notice.csv"
    parents = {
        "DOC-1": f"{site_server}/detail_1.html",
        "DOC-2": f"{site_server}/detail_2.html",
    }
    for doc_id, parent in parents.items():
        pipeline.pending.enqueue_attachments(
            source_id="TESTSRC",
            scope_start_date=None,
            doc_id=doc_id,
            parent_url=parent,
            records=[{"url": url, "filename": "notice.csv", "referrer_url": parent}],
            enqueued_at=NOW.isoformat(),
        )
    pipeline.pending.enqueue_targets(
        source_id="TESTSRC",
        targets=[DiscoveredTarget(url=url, discovery_method="manual")],
        scope_start_date=None,
        enqueued_at=NOW.isoformat(),
    )
    for item in pipeline.pending.all_items():
        pipeline.pending.mark(item.key, state="failed", attempted_at=NOW.isoformat(), note="HTTP 500")
    pipeline.failures.record(
        source_id="TESTSRC",
        url=url,
        time=NOW.isoformat(),
        stage="fetch",
        error_type="http_error",
        message="HTTP 500",
        retry_count=0,
        final_action="retry_later",
        referrer_url=parents["DOC-1"],
        doc_id="DOC-1",
    )

    report = pipeline.resume_failures("TESTSRC")

    assert len(report.recovered) == 1
    states = {
        (item.doc_id or item.kind): item.state for item in pipeline.pending.all_items()
    }
    assert states == {"DOC-1": "processed", "DOC-2": "failed", "target": "failed"}


# ---------- C：身份统一（来源 + URL + 范围 + 母文档） ----------


def test_open_failures_are_kept_per_source(tmp_path):
    """C：同一 URL/stage/范围/母文档的失败行按来源分开，不互相覆盖。"""
    from crawler.monitor.failures import FailureLedger

    ledger = FailureLedger(tmp_path)
    common = {
        "url": "https://example.invalid/a.pdf",
        "time": NOW.isoformat(),
        "stage": "fetch",
        "error_type": "request_error",
        "message": "HTTP 500",
        "retry_count": 0,
    }
    ledger.writer.record(source_id="A", final_action="retry_later", **common)
    ledger.writer.record(source_id="B", final_action="retry_later", **common)

    keys = set(ledger.latest_by_key())
    assert ("A", *[common["url"], "fetch", None, None]) in keys
    assert len(ledger.open_failures()) == 2, "两个来源各自保持未关闭"


def test_pending_documents_ignores_other_source_open_failure(tmp_path):
    """C：别的来源的未关闭失败不得把本来源已下载原件排除在重解析候选之外。"""
    from crawler.monitor.failures import FailureLedger
    from crawler.output.jsonl import write_jsonl

    ledger = FailureLedger(tmp_path)
    (tmp_path / "manifests").mkdir(parents=True, exist_ok=True)
    write_jsonl(
        tmp_path / "manifests" / "crawl_manifest.jsonl",
        [
            {
                "crawl_id": "C1",
                "source_id": "A",
                "requested_url": "https://example.invalid/a.pdf",
                "final_url": "https://example.invalid/a.pdf",
                "raw_path": "raw/a.pdf",
            }
        ],
    )
    ledger.writer.record(
        source_id="B",
        url="https://example.invalid/a.pdf",
        time=NOW.isoformat(),
        stage="fetch",
        error_type="request_error",
        message="HTTP 500",
        retry_count=0,
        final_action="retry_later",
    )

    pending = ledger.pending_documents()

    assert [row["crawl_id"] for row in pending] == ["C1"]


def test_failure_records_pending_item_scope_not_run_scope(
    site_server, registry_factory, tmp_path
):
    """C：处理待处理项时，失败记录使用该对象入队范围（不是本次运行窗口）。

    否则补抓计划与对账会按不同范围找不到同一对象，队列与账本无法互相关闭。
    """
    registry = registry_factory(site_server)
    pipeline = _pipeline(registry, tmp_path / "data")
    url = f"{site_server}/missing-page.html"
    pipeline.pending.enqueue_targets(
        source_id="TESTSRC",
        targets=[DiscoveredTarget(url=url, discovery_method="manual")],
        scope_start_date="2026-09-01",
        enqueued_at=NOW.isoformat(),
    )

    report = pipeline.collect(
        "TESTSRC",
        manual_urls=[url],
        scope=RunScope(start_date=date(2026, 9, 10)),
        max_items=1,
    )

    assert report.counters.failures == 1
    row = report.failures[0]
    assert row["scope_start_date"] == "2026-09-01", "对象范围优先于本次运行窗口"
    item = next(row for row in pipeline.pending.all_items() if row.url == url)
    assert item.scope_start_date == "2026-09-01"
    tasks = pipeline.recovery_plan()
    assert [task.scope_start_date for task in tasks] == ["2026-09-01"]


def test_part_failure_recovery_resumes_mother_document(
    mutable_site, registry_factory, tmp_path
):
    """C：正文片段失败在补抓时回到母文档续作，不产出片段文档、不误关其它对象。"""
    base_url, root = mutable_site
    _write_paged_body_site(root)
    registry = registry_factory(base_url)
    data = tmp_path / "data"

    # 第二轮正文请求瞬时失败（第 3 个请求：列表、母页之后的分页部分）
    budget = RunBudget(max_requests=3)
    session = requests.Session()
    session.headers.setdefault("User-Agent", "test-agent")
    inner = _FailingCallSession(
        session, fail_calls={3}, exc=requests.exceptions.ReadTimeout("瞬时读取超时")
    )
    http = HttpClient(
        registry,
        limits=FetchLimits(request_rate_per_second=1000, max_retries=0),
        robots=False,
        session=inner,
        budget=budget,
    )
    pipeline = CrawlPipeline(registry, data, http=http, now=lambda: NOW)
    pipeline.collect("TESTSRC", entry_urls=[f"{base_url}/r7_index.html"], budget=budget)
    item = next(
        row for row in pipeline.pending.all_items() if row.url.endswith("r7_paged_1.html")
    )
    assert item.state == "pending" and item.continuation is not None
    part_failure = next(
        row
        for row in pipeline.failures_ledger.open_failures()
        if row["url"].endswith("r7_paged_2.html")
    )
    assert part_failure["doc_id"] == item.continuation["doc_id"]
    assert pipeline.recovery_plan()[0].action == REFETCH

    (root / "r7_paged_2.html").write_text(
        _page(
            "两页正文（第二部分）",
            "<h1>两页正文样本（第二部分）</h1><p>正文第二部分：结尾。</p>",
        ),
        encoding="utf-8",
    )
    report = pipeline.resume_failures("TESTSRC")

    assert [row["note"] for row in report.recovered] == ["补抓成功，账本与文档已更新"]
    documents = read_jsonl(data / "normalized" / "documents.jsonl")
    assert all(
        doc["source_url"].endswith(("r7_paged_1.html", "r7_index.html")) for doc in documents
    ), "分页片段不得独立成文"
    final_doc = documents[-1]
    assert "正文第二部分" in final_doc["full_text"]
    updated = next(row for row in pipeline.pending.all_items() if row.key == item.key)
    assert updated.state == "processed" and updated.continuation is None
    assert pipeline.failures_ledger.open_failures() == []


def test_part_reparse_failure_does_not_create_fragment_document(
    site_server, registry_factory, tmp_path
):
    """C：正文片段的本地重解析任务不得产出片段文档；对象有未完成正文时回到母页续作。"""
    registry = registry_factory(site_server)
    data = tmp_path / "data"
    pipeline = _pipeline(registry, data)
    mother_url = f"{site_server}/detail_1.html"
    part_url = f"{site_server}/detail_paged_2.html"
    mother_doc_id = "MOTHER1"

    pipeline.pending.enqueue_targets(
        source_id="TESTSRC",
        targets=[DiscoveredTarget(url=mother_url, discovery_method="manual")],
        scope_start_date=None,
        enqueued_at=NOW.isoformat(),
    )
    item = next(row for row in pipeline.pending.all_items() if row.url == mother_url)
    pipeline.pending.mark(
        item.key,
        state="pending",
        doc_id=mother_doc_id,
        continuation={
            "kind": "body_pagination",
            "doc_id": mother_doc_id,
            "mother_url": mother_url,
            "mother_final_url": mother_url,
            "mother_raw_path": "raw/TESTSRC/2026-09-11/html/detail_1.html",
            "mother_sha256": "0" * 64,
            "mother_content_type": "text/html; charset=utf-8",
            "next_url": part_url,
            "body_api_url": None,
            "parts": [],
            "stop_reason": "resume_part_failed",
            "attempts": 1,
            "updated_at": NOW.isoformat(),
        },
    )
    raw = pipeline.store.write_bytes(
        source_id="TESTSRC",
        crawl_date="2026-09-11",
        kind="html",
        filename="detail_paged_2.html",
        content=(FIXTURES / "site" / "detail_paged_2.html").read_bytes(),
    )
    pipeline.manifest.record(
        crawl_id="PART1",
        source_id="TESTSRC",
        requested_url=part_url,
        final_url=part_url,
        crawl_time=NOW.isoformat(),
        http_status=200,
        content_type="text/html; charset=utf-8",
        raw=raw,
        discovery_method="pagination",
        referrer_url=mother_url,
    )
    pipeline.failures.record(
        source_id="TESTSRC",
        url=part_url,
        time=NOW.isoformat(),
        stage="parse",
        error_type="continuation_part_unreadable",
        message="已取得正文部分无法重建",
        retry_count=0,
        final_action="record_only",
        crawl_id="PART1",
        doc_id=mother_doc_id,
        referrer_url=mother_url,
    )
    assert pipeline.recovery_plan()[0].action == REPARSE

    report = pipeline.resume_failures("TESTSRC")

    documents = read_jsonl(data / "normalized" / "documents.jsonl")
    assert all(doc["source_url"] != part_url for doc in documents), "片段不得独立成文"
    assert [doc["source_url"] for doc in documents] == [mother_url]
    assert [row["note"] for row in report.recovered] == ["补抓成功，账本与文档已更新"]
    updated = next(row for row in pipeline.pending.all_items() if row.key == item.key)
    assert updated.state == "processed" and updated.continuation is None
    assert pipeline.failures_ledger.open_failures() == []
