"""S5-01：发现响应统一归档——原件字节、账本身份、解析失败留痕（T005—T007/T016）。

发现页（列表/搜索/sitemap/发现接口）也是成功业务响应：先落原件与账本，再解析；
解析失败不丢原件，且不产出 normalized 文档。重复请求保留各自请求身份，字节相同的
原件复用同一 raw_path。
"""

import hashlib
from datetime import datetime, timedelta, timezone

from crawler.fetch.http_client import FetchLimits, FetchResponse, HttpClient
from crawler.output.archive import ResponseArchiver
from crawler.output.jsonl import read_jsonl
from crawler.output.layout import DeliveryLayout
from crawler.pipeline import CrawlPipeline

FIXED_NOW = datetime(2026, 9, 13, 10, 0, 0, tzinfo=timezone(timedelta(hours=8)))


def make_pipeline(registry, tmp_path):
    http = HttpClient(
        registry, limits=FetchLimits(request_rate_per_second=1000, max_retries=1)
    )
    return CrawlPipeline(registry, tmp_path / "data", http=http, now=lambda: FIXED_NOW)


def discovery_rows(data):
    return [
        row
        for row in read_jsonl(data / "manifests" / "crawl_manifest.jsonl")
        if "/discovery/" in row["raw_path"]
    ]


def test_each_discovery_stage_archives_response_before_parse(
    site_server, registry_factory, tmp_path
):
    registry = registry_factory(
        site_server, adapter={"discovery": ["list", "search", "sitemap", "api"]}
    )
    pipeline = make_pipeline(registry, tmp_path)
    report = pipeline.collect(
        "TESTSRC",
        entry_urls=[f"{site_server}/index.html"],
        search_keywords=["边界"],
        sitemap_urls=[f"{site_server}/sitemap.xml"],
        api_urls=[f"{site_server}/api.json"],
        include_attachments=False,
    )
    data = tmp_path / "data"
    rows = discovery_rows(data)
    assert {row["discovery_method"] for row in rows} == {"list", "search", "sitemap", "api"}
    for row in rows:
        raw = data / row["raw_path"]
        assert raw.is_file(), row["raw_path"]
        assert hashlib.sha256(raw.read_bytes()).hexdigest() == row["sha256"]
        assert row["http_status"] == 200
        assert row["requested_url"].startswith("http")

    documents = read_jsonl(data / "normalized" / "documents.jsonl")
    archived_ids = {row["crawl_id"] for row in rows}
    document_ids = {doc["doc_id"] for doc in documents}
    assert not (archived_ids & document_ids), "发现页不产出 normalized 文档"

    # 每个入口都记录终止原因与是否完整（S5-03 口径随运行留存）
    stops = report.coverage["discovery"]["stops"]
    assert stops and {row["stage"] for row in stops} == {"list", "search", "sitemap", "api"}
    assert all("stop" in row and "complete" in row for row in stops)


def test_discovery_parse_failure_keeps_original_and_records_failure(
    site_server, registry_factory, tmp_path
):
    registry = registry_factory(site_server)
    pipeline = make_pipeline(registry, tmp_path)
    report = pipeline.collect(
        "TESTSRC",
        entry_urls=[],
        sitemap_urls=[f"{site_server}/bad_sitemap.xml"],
        api_urls=[f"{site_server}/bad_api.json"],
        include_attachments=False,
    )
    data = tmp_path / "data"
    statuses = {result.stage: result.status for result in report.discovery}
    assert statuses["sitemap"] == "parse_error"
    assert statuses["api"] == "parse_error"
    assert report.counters.documents == 0

    rows = discovery_rows(data)
    assert {row["final_url"].rsplit("/", 1)[-1] for row in rows} == {
        "bad_sitemap.xml",
        "bad_api.json",
    }
    for row in rows:
        raw = data / row["raw_path"]
        assert raw.is_file()
        assert hashlib.sha256(raw.read_bytes()).hexdigest() == row["sha256"]

    failures = read_jsonl(data / "manifests" / "failed_records.jsonl")
    assert {row["error_type"] for row in failures} == {"discovery_parse_error"}
    assert {row["stage"] for row in failures} == {"parse"}
    assert {row["crawl_id"] for row in failures} == {row["crawl_id"] for row in rows}
    assert report.coverage["discovery"]["complete"] is False
    assert any(
        row["stop"] == "parse_error" and row["complete"] is False
        for row in report.coverage["discovery"]["stops"]
    )


def test_repeated_requests_keep_distinct_identity_and_reuse_bytes(
    site_server, registry_factory, tmp_path
):
    registry = registry_factory(site_server)
    pipeline = make_pipeline(registry, tmp_path)
    for _ in range(2):
        pipeline.collect(
            "TESTSRC",
            entry_urls=[f"{site_server}/index.html"],
            include_attachments=False,
            max_items=10,
        )
    data = tmp_path / "data"
    rows = read_jsonl(data / "manifests" / "crawl_manifest.jsonl")
    crawl_ids = [row["crawl_id"] for row in rows]
    assert len(crawl_ids) == len(set(crawl_ids)), "重复请求不复用 crawl_id"

    same_page = [
        row
        for row in discovery_rows(data)
        if row["final_url"] == f"{site_server}/index.html"
    ]
    assert len(same_page) == 2
    assert same_page[0]["crawl_id"] != same_page[1]["crawl_id"]
    assert same_page[0]["raw_path"] == same_page[1]["raw_path"]
    assert same_page[0]["sha256"] == same_page[1]["sha256"]
    assert (data / same_page[0]["raw_path"]).is_file()


def test_archiver_does_not_double_write_same_response(tmp_path):
    data = tmp_path / "data"
    archiver = ResponseArchiver(data, now=lambda: FIXED_NOW)
    response = FetchResponse(
        requested_url="http://example.invalid/list.html",
        final_url="http://example.invalid/list.html",
        status_code=200,
        headers={"Content-Type": "text/html; charset=utf-8"},
        content=b"<html><body><a href='a.html'>a</a></body></html>",
        redirect_chain=(),
        attempts=1,
    )
    first = archiver.archive(
        response, source_id="DEMO", kind="discovery", discovery_method="list"
    )
    second = archiver.archive(
        response, source_id="DEMO", kind="discovery", discovery_method="list"
    )
    assert second.reused is True and second.crawl_id == first.crawl_id
    rows = read_jsonl(DeliveryLayout(data).manifest_path)
    assert len(rows) == 1
