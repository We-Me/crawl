"""S5-04：正文附件的成功/失败/边界拒绝/规则排除/待处理闭环。

覆盖：规则排除可解释（扩展名与适配规则）、同页重复附件只下载一次、robots 边界拒绝
不写成网站失败、预算停止的附件登记待处理并在下一轮续传（原件 + 账本 + 母页关联）。
"""

import hashlib
import json
from datetime import datetime, timedelta, timezone

from crawler.fetch.budget import RunBudget
from crawler.fetch.downloader import Downloader
from crawler.fetch.http_client import FetchLimits, HttpClient
from crawler.output.jsonl import read_jsonl
from crawler.output.layout import DeliveryLayout
from crawler.pipeline import CrawlPipeline

FIXED_NOW = datetime(2026, 9, 13, 10, 0, 0, tzinfo=timezone(timedelta(hours=8)))


def make_pipeline(registry, tmp_path, **kwargs):
    http = HttpClient(
        registry, limits=FetchLimits(request_rate_per_second=1000, max_retries=0)
    )
    return CrawlPipeline(registry, tmp_path / "data", http=http, now=lambda: FIXED_NOW, **kwargs)


def pending_items(data):
    path = DeliveryLayout(data).pending_path
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))["items"]


def test_rule_exclusions_and_duplicates_are_counted(
    site_server, registry_factory, tmp_path
):
    registry = registry_factory(site_server, adapter={"attachment_pattern": "notice"})
    pipeline = make_pipeline(registry, tmp_path)
    report = pipeline.collect(
        "TESTSRC", manual_urls=[f"{site_server}/attachment_rules.html"]
    )
    data = tmp_path / "data"
    coverage = report.coverage["attachments"]
    assert coverage["discovered"] == 1, "只有声明范围内的附件进入下载候选"
    assert coverage["downloaded"] == 1
    assert coverage["duplicates"] == 1, "同页重复附件只下载一次并单独计数"
    assert coverage["rule_excluded"] == 2
    exclusions = {(row["reason"], row["count"]) for row in coverage["exclusions"]}
    assert ("extension_not_declared:.mp4", 1) in exclusions  # .mp4 不在正文附件声明内
    assert ("adapter_pattern:.zip", 1) in exclusions  # .zip 被适配附件规则排除

    rows = read_jsonl(data / "manifests" / "crawl_manifest.jsonl")
    assert sum(1 for row in rows if row["discovery_method"] == "attachment") == 1
    document = read_jsonl(data / "normalized" / "documents.jsonl")[0]
    assert [item["status"] for item in document["attachments"]] == ["downloaded"]


def test_attachment_boundary_rejection_is_not_website_failure(
    site_server, registry_factory, tmp_path
):
    registry = registry_factory(site_server)
    pipeline = make_pipeline(registry, tmp_path)
    report = pipeline.collect(
        "TESTSRC", manual_urls=[f"{site_server}/robots_detail.html"]
    )
    data = tmp_path / "data"
    assert report.coverage["attachments"]["boundary_rejected"] == 1
    assert any(
        item.url.endswith("/private/secret.csv") and "robots_disallowed" in item.reason
        for item in report.skipped
    )
    failures = read_jsonl(data / "manifests" / "failed_records.jsonl")
    assert all(row["error_type"] != "robots_disallowed" for row in failures)
    document = read_jsonl(data / "normalized" / "documents.jsonl")[0]
    assert [item["status"] for item in document["attachments"]] == ["boundary_rejected"]


def test_budget_stop_persists_pending_attachments_and_next_run_resumes(
    site_server, registry_factory, tmp_path
):
    registry = registry_factory(site_server)
    pipeline = make_pipeline(registry, tmp_path)
    data = tmp_path / "data"
    page_url = f"{site_server}/detail_1.html"
    csv_url = f"{site_server}/attachments/notice.csv"
    pdf_url = f"{site_server}/attachments/unavailable.pdf"

    budget = RunBudget(max_requests=2)  # robots(1) + 正文页(2)，附件阶段预算用尽
    first = pipeline.collect("TESTSRC", manual_urls=[page_url], budget=budget)
    assert first.stop_reason == "request_budget"
    assert first.coverage["attachments"]["pending"] == 2
    document = read_jsonl(data / "normalized" / "documents.jsonl")[0]
    assert {item["status"] for item in document["attachments"]} == {"pending"}

    items = pending_items(data)
    attachments = [row for row in items.values() if row["kind"] == "attachment"]
    assert {row["url"] for row in attachments} == {csv_url, pdf_url}
    assert all(row["state"] == "pending" for row in attachments)
    assert all(row["doc_id"] == document["doc_id"] for row in attachments)
    assert all(row["referrer_url"] == page_url for row in attachments)
    assert first.unprocessed == 2

    # 第二轮不传预算：本次运行不受上一轮已耗尽预算约束，续传待处理附件。
    second = pipeline.collect(
        "TESTSRC", manual_urls=[page_url], include_attachments=False
    )
    coverage = second.coverage["attachments"]
    assert coverage["resumed"] == 1
    assert coverage["downloaded"] == 1 and coverage["failed"] == 1
    assert second.coverage["pending_total"] == 0

    items = pending_items(data)
    states = {row["url"]: row["state"] for row in items.values() if row["kind"] == "attachment"}
    assert states[csv_url] == "processed"
    assert states[pdf_url] == "failed"
    resumed = [row for row in items.values() if row["url"] == csv_url][0]
    assert resumed["crawl_id"] and resumed["raw_path"] and resumed["sha256"]
    manifest_rows = read_jsonl(data / "manifests" / "crawl_manifest.jsonl")
    row = next(item for item in manifest_rows if item["crawl_id"] == resumed["crawl_id"])
    raw = data / row["raw_path"]
    assert raw.is_file()
    assert hashlib.sha256(raw.read_bytes()).hexdigest() == row["sha256"] == resumed["sha256"]
    assert row["referrer_url"] == page_url
    failures = read_jsonl(data / "manifests" / "failed_records.jsonl")
    assert any(item["url"] == pdf_url and item["stage"] == "fetch" for item in failures)


def test_attachment_size_cap_is_boundary_rejection_not_failure(
    site_server, registry_factory, tmp_path
):
    """S5-04：超过已声明大小上限的附件是确定性边界拒绝，不写失败账、不进重试。"""
    registry = registry_factory(site_server)
    pipeline = make_pipeline(registry, tmp_path)
    # notice.csv 为 22 字节，超过 10 字节上限 → 边界拒绝；unavailable.pdf 为 404 传输失败。
    pipeline.downloader = Downloader(pipeline.http, max_bytes=10)
    data = tmp_path / "data"
    report = pipeline.collect("TESTSRC", manual_urls=[f"{site_server}/detail_1.html"])

    coverage = report.coverage["attachments"]
    assert coverage["boundary_rejected"] == 1
    assert coverage["downloaded"] == 0 and coverage["failed"] == 1
    size_skips = [item for item in report.skipped if "size_limit_exceeded" in item.reason]
    assert len(size_skips) == 1
    assert size_skips[0].reason.startswith("boundary_rejected:size_limit_exceeded")
    failures = read_jsonl(data / "manifests" / "failed_records.jsonl")
    assert len(failures) == 1 and "size_limit_exceeded" not in failures[0]["message"]
    document = read_jsonl(data / "normalized" / "documents.jsonl")[0]
    by_file = {item["filename"]: item for item in document["attachments"]}
    assert by_file["notice.csv"]["status"] == "boundary_rejected"
    assert "size_limit_exceeded" in by_file["notice.csv"]["note"]
    assert by_file["unavailable.pdf"]["status"] == "failed"
    leftover = [
        row for row in pending_items(data).values() if row.get("state") == "pending"
    ]
    assert leftover == [], "边界拒绝不留待处理项，不反复消耗预算"


def test_pending_attachment_size_cap_marks_skipped(
    site_server, registry_factory, tmp_path
):
    """S5-04：续传时遇到大小上限，按边界拒绝记 skipped（不写失败、不留在待处理）。"""
    registry = registry_factory(site_server)
    pipeline = make_pipeline(registry, tmp_path)
    page_url = f"{site_server}/detail_1.html"
    budget = RunBudget(max_requests=2)  # robots + 正文页：附件阶段预算用尽 → 登记待处理
    pipeline.collect("TESTSRC", manual_urls=[page_url], budget=budget)
    pending = [row for row in pending_items(tmp_path / "data").values() if row["kind"] == "attachment"]
    assert len(pending) == 2

    csv_url = f"{site_server}/attachments/notice.csv"
    pdf_url = f"{site_server}/attachments/unavailable.pdf"
    pipeline.downloader = Downloader(pipeline.http, max_bytes=10)
    second = pipeline.collect("TESTSRC", manual_urls=[page_url], include_attachments=False)
    assert second.coverage["attachments"]["boundary_rejected"] == 1
    assert second.coverage["attachments"]["failed"] == 1
    assert second.coverage["pending_total"] == 0
    states = {
        row["url"]: row["state"]
        for row in pending_items(tmp_path / "data").values()
        if row["kind"] == "attachment"
    }
    assert states[csv_url] == "skipped" and states[pdf_url] == "failed"
    failures = read_jsonl(tmp_path / "data" / "manifests" / "failed_records.jsonl")
    assert all("size_limit_exceeded" not in row.get("message", "") for row in failures)
