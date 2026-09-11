"""T009 最小采集闭环测试：HTML 加附件的原件、账本、文档与块可追溯。"""

import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from crawler.fetch.http_client import FetchLimits, HttpClient
from crawler.output.jsonl import read_jsonl
from crawler.pipeline import CrawlPipeline


@pytest.fixture()
def pipeline_factory(tmp_path, site_server):
    def make(registry):
        http = HttpClient(
            registry, limits=FetchLimits(request_rate_per_second=1000, max_retries=2)
        )
        fixed_now = lambda: datetime(  # noqa: E731 - 固定时间保证 crawl_id 可预期
            2026, 9, 11, 10, 0, 0, tzinfo=timezone(timedelta(hours=8))
        )
        return CrawlPipeline(registry, tmp_path / "data", http=http, now=fixed_now)

    return make


def test_minimal_html_attachment_closure(site_server, registry_factory, pipeline_factory, tmp_path):
    registry = registry_factory(site_server)
    pipeline = pipeline_factory(registry)
    report = pipeline.collect("TESTSRC", entry_urls=[f"{site_server}/index.html"])
    data = tmp_path / "data"

    assert report.counters.documents == 2
    assert report.counters.resources == 3  # 两个 HTML 页 + 一个成功附件
    assert report.counters.failures == 1
    assert report.counters.blocks > 0
    assert report.documents == ["TESTSRC_20260911_0001", "TESTSRC_20260911_0003"]

    # 账本：原件存在、字节哈希一致
    manifest_rows = read_jsonl(data / "manifests" / "crawl_manifest.jsonl")
    assert len(manifest_rows) == 3
    for row in manifest_rows:
        raw_path = data / row["raw_path"]
        assert raw_path.is_file(), row["raw_path"]
        assert hashlib.sha256(raw_path.read_bytes()).hexdigest() == row["sha256"]
        assert row["http_status"] == 200
    attachment_row = next(row for row in manifest_rows if row["raw_path"].endswith(".csv"))
    assert attachment_row["discovery_method"] == "attachment"
    assert attachment_row["referrer_url"] == f"{site_server}/detail_1.html"

    # 文档：必填字段、元数据与附件关系
    documents = read_jsonl(data / "normalized" / "documents.jsonl")
    assert len(documents) == 2
    main_document = next(doc for doc in documents if doc["title"] == "虚构公告：试验合作安排")
    assert main_document["parse_status"] == "ok"
    assert main_document["publication_date"] == "2026-09-10"
    assert main_document["language"] == "zh"
    assert main_document["crawl_ids"] == [main_document["doc_id"]]
    assert (data / main_document["raw_path"]).is_file()
    assert "category_hint" not in main_document
    attachments = {item["filename"]: item for item in main_document["attachments"]}
    assert attachments["notice.csv"]["status"] == "downloaded"
    assert (data / attachments["notice.csv"]["raw_path"]).is_file()
    assert attachments["notice.csv"]["sha256"] == hashlib.sha256(
        (data / attachments["notice.csv"]["raw_path"]).read_bytes()
    ).hexdigest()
    assert attachments["unavailable.pdf"]["status"] == "failed"
    assert "raw_path" not in attachments["unavailable.pdf"]

    # 块：顺序连续、引用有效、结构保留
    blocks = read_jsonl(data / "normalized" / "blocks.jsonl")
    main_blocks = [block for block in blocks if block["doc_id"] == main_document["doc_id"]]
    assert [block["order"] for block in main_blocks] == list(range(len(main_blocks)))
    assert main_blocks[0]["block_type"] == "heading"
    assert main_blocks[0]["heading_level"] == 1
    table = next(block for block in main_blocks if block["block_type"] == "table")
    assert table["structured_data"]["rows"] == [["2025", "12"]]

    # 失败与越界记录
    failures = read_jsonl(data / "manifests" / "failed_records.jsonl")
    assert len(failures) == 1
    assert failures[0]["url"] == f"{site_server}/attachments/unavailable.pdf"
    assert failures[0]["stage"] == "fetch"
    assert failures[0]["error_type"] == "http_error"
    assert failures[0]["retry_count"] == 0
    assert [item.url for item in report.skipped] == ["https://outside.invalid/secret"]

    # 采集阶段边界：数据根下只有原件、账本、规范化目录与运行日志（T017）
    assert {child.name for child in data.iterdir()} == {"raw", "manifests", "normalized", "logs"}


def test_search_keyword_only_affects_discovery_and_ledger(
    site_server, registry_factory, pipeline_factory, tmp_path
):
    registry = registry_factory(site_server)
    pipeline = pipeline_factory(registry)
    report = pipeline.collect("TESTSRC", entry_urls=[], search_keywords=["边界"])
    data = tmp_path / "data"
    assert report.counters.documents == 1
    rows = read_jsonl(data / "manifests" / "crawl_manifest.jsonl")
    assert len(rows) == 1
    assert rows[0]["discovery_method"] == "search"
    assert rows[0]["keyword"] == "边界"
    document = read_jsonl(data / "normalized" / "documents.jsonl")[0]
    assert "category_hint" not in document
    assert document["title"] == "虚构统计表"


def test_disabled_source_is_rejected(site_server, registry_factory, pipeline_factory):
    registry = registry_factory(site_server, enabled=False)
    pipeline = pipeline_factory(registry)
    with pytest.raises(ValueError, match="未启用"):
        pipeline.collect("TESTSRC", entry_urls=[f"{site_server}/index.html"])


def test_discovery_failure_is_recorded(site_server, registry_factory, pipeline_factory, tmp_path):
    registry = registry_factory(site_server)
    pipeline = pipeline_factory(registry)
    report = pipeline.collect("TESTSRC", entry_urls=[f"{site_server}/missing-list.html"])
    assert report.counters.documents == 0
    assert len(report.failures) == 1
    failure = read_jsonl(tmp_path / "data" / "manifests" / "failed_records.jsonl")[0]
    assert failure["stage"] == "discover"
    assert failure["final_action"] == "record_only"


def test_pipeline_uses_source_limits(site_server, registry_factory, tmp_path):
    """生产路径（不注入 http）下，客户端按来源配置解析限速与超时。"""
    registry = registry_factory(
        site_server, request_rate_per_second=2, read_timeout_seconds=7
    )
    pipeline = CrawlPipeline(registry, tmp_path / "data")
    limits = pipeline.http.limits_for(f"{site_server}/index.html", "TESTSRC")
    assert limits.request_rate_per_second == 2
    assert limits.read_timeout_seconds == 7


def test_pipeline_reports_rate_and_concurrency_separately(
    site_server, registry_factory, tmp_path
):
    """AT-023：速率与并发分别建模；来源声明的并发上限不换算成速率、不冒充实际并发。"""
    registry = registry_factory(
        site_server, request_rate_per_second=2, max_concurrency=3
    )
    pipeline = CrawlPipeline(registry, tmp_path / "data")
    pipeline.collect("TESTSRC", entry_urls=[f"{site_server}/index.html"])
    rows = read_jsonl(tmp_path / "data" / "logs" / "metrics_history.jsonl")
    controls = rows[-1]["request_controls"]
    assert controls["request_rate_per_second"] == 2
    assert controls["max_concurrency_declared"] == 3
    assert controls["effective_concurrency"] == 1
    assert "分别建模" in controls["note"]


def test_adapter_content_selector_miss_is_failure_and_recoverable(
    site_server, registry_factory, pipeline_factory, tmp_path
):
    """T026：正文选择器未命中 → 原件保留 + 失败账，修正规则后可本地重解析。"""
    registry = registry_factory(
        site_server,
        adapter={
            "list_link_selector": "ul li a",
            "content_selector": "div.not-here",
        },
    )
    pipeline = pipeline_factory(registry)
    report = pipeline.collect(
        "TESTSRC", entry_urls=[f"{site_server}/adapter_index.html"], include_attachments=False
    )
    assert report.counters.documents == 0 and report.counters.failures == 1
    data = tmp_path / "data"
    manifest = read_jsonl(data / "manifests" / "crawl_manifest.jsonl")
    assert len(manifest) == 1  # 原件与账本已落盘
    raw = data / manifest[0]["raw_path"]
    assert hashlib.sha256(raw.read_bytes()).hexdigest() == manifest[0]["sha256"]
    failure = read_jsonl(data / "manifests" / "failed_records.jsonl")[0]
    assert failure["stage"] == "parse" and failure["error_type"] == "adapter_selector_miss"

    fixed_registry = registry_factory(
        site_server,
        adapter={
            "list_link_selector": "ul li a",
            "content_selector": "div.article-body",
        },
    )
    fixed = pipeline_factory(fixed_registry)
    recovered = fixed.resume_failures("TESTSRC")
    assert recovered.counters.documents == 1 and recovered.counters.requests == 0
    documents = read_jsonl(data / "normalized" / "documents.jsonl")
    assert documents[0]["extraction_method"] == "bs4_lxml_selector"
    assert "相关阅读" not in documents[0]["full_text"]
    # 失败账与补全后的交付仍满足契约校验
    from crawler.validate.schema import validate_delivery

    validation = validate_delivery(data)
    assert validation.ok is True, validation.errors


def test_crawl_ids_continue_across_runs(
    site_server, registry_factory, pipeline_factory, tmp_path
):
    """同日同来源的多次运行不复用 crawl_id；否则补抓会指向错误原件。"""
    first_registry = registry_factory(site_server)
    first = pipeline_factory(first_registry)
    first.collect(
        "TESTSRC",
        entry_urls=[f"{site_server}/index.html"],
        include_attachments=False,
        max_items=1,
    )

    broken = registry_factory(
        site_server,
        adapter={"list_link_selector": "ul li a", "content_selector": "div.not-here"},
    )
    second = pipeline_factory(broken)
    second.collect(
        "TESTSRC",
        entry_urls=[f"{site_server}/adapter_index.html"],
        include_attachments=False,
        max_items=1,
    )

    data = tmp_path / "data"
    rows = read_jsonl(data / "manifests" / "crawl_manifest.jsonl")
    crawl_ids = [row["crawl_id"] for row in rows]
    assert len(crawl_ids) == len(set(crawl_ids))
    assert crawl_ids[0] == "TESTSRC_20260911_0001"
    assert crawl_ids[-1] == "TESTSRC_20260911_0002"

    tasks = second.recovery_plan()
    assert [task.action for task in tasks] == ["reparse"]
    # 失败记录的 raw_path 必须指向本次运行的原件，而不是同名序号的上一次运行
    assert tasks[0].url == f"{site_server}/detail_adapter.html"
    assert tasks[0].raw_path == "raw/TESTSRC/2026-09-11/html/detail_adapter.html"
