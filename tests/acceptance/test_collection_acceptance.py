"""T019：acceptance.md 采集用例 AT-001—AT-024 的夹具级验收。

只在固定夹具站点与固定样本上执行；真实来源（Q12/Q13）与质量/近似阈值（Q11）未决的
部分不判通过：AT-014、AT-024 在登记表中为 blocked，测试报告强制它们不得显示 passed。
"""

import hashlib
import json
import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

import pytest
import requests
import yaml

from crawler.config.registry import SourceRegistry
from crawler.config.settings import ConfigurationError
from crawler.fetch.http_client import FetchError, FetchLimits, HttpClient
from crawler.monitor.logger import close_run_logging, log_path
from crawler.monitor.metrics import read_metrics
from crawler.normalize.metadata_normalizer import normalize_page
from crawler.output.delivery import inspect_delivery
from crawler.output.jsonl import append_jsonl, read_jsonl
from crawler.output.layout import DeliveryLayout
from crawler.parser.dispatcher import parse_attachment
from crawler.parser.html_parser import parse_html
from crawler.parser.ocr_parser import parse_image, parse_scanned_pdf
from crawler.parser.pdf_parser import parse_pdf
from crawler.pipeline import CrawlPipeline
from crawler.validate.acceptance import ACCEPTANCE_CASES, build_acceptance_report
from crawler.validate.schema import load_contract, validate_delivery, validate_instance, validate_jsonl_file
from crawler.validate.traceability import trace_delivery
from crawler.versioning import VersionStore, document_identity, plan_version

NOW = datetime(2026, 9, 11, 10, 0, 0, tzinfo=timezone(timedelta(hours=8)))
ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures"
RESULTS = {}


def record(case_id: str, status: str = "passed") -> None:
    RESULTS[case_id] = status


def _write_registry(root: Path, base_url: str, *, source_id: str = "DEMO", **overrides):
    host = urlsplit(base_url).hostname
    entry = {
        "source_id": source_id,
        "source_name": "夹具来源",
        "base_domain": host,
        "allowed_domains": [host],
        "enabled": True,
        "language": "zh",
        "seed_terms": ["边界"],
        "search_url_template": f"{base_url}/search?q={{query}}",
        "request_rate_per_second": 1000,
        "max_retries": 2,
        "connect_timeout_seconds": 5,
        "read_timeout_seconds": 5,
    }
    entry.update(overrides)
    path = root / "sources.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump({"version": "acceptance", "sources": [entry]}, allow_unicode=True),
        encoding="utf-8",
    )
    return SourceRegistry.load(path)


def _pipeline(registry, data_dir: Path) -> CrawlPipeline:
    return CrawlPipeline(
        registry,
        data_dir,
        http=HttpClient(registry, limits=FetchLimits(request_rate_per_second=1000, max_retries=2)),
        now=lambda: NOW,
    )


def _write_sources(root: Path, base_url: str, rows):
    """多来源注册表：为每个资料类型登记独立 source_id。"""
    host = urlsplit(base_url).hostname
    sources = []
    for row in rows:
        entry = {
            "source_name": f"夹具来源 {row['source_id']}",
            "base_domain": host,
            "allowed_domains": [host],
            "enabled": True,
            "language": "zh",
            "request_rate_per_second": 1000,
            "max_retries": 2,
            "connect_timeout_seconds": 5,
            "read_timeout_seconds": 5,
        }
        entry.update(row)
        sources.append(entry)
    path = root / "sources.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump({"version": "acceptance", "sources": sources}, allow_unicode=True),
        encoding="utf-8",
    )
    return SourceRegistry.load(path)


def _site_page(title: str, body: str) -> str:
    return (
        '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
        f"<title>{title}</title></head><body><main><h1>{title}</h1>{body}</main></body></html>"
    )


def _collect(registry, data_dir: Path, **kwargs):
    pipeline = _pipeline(registry, data_dir)
    try:
        return pipeline.collect("DEMO", **kwargs)
    finally:
        close_run_logging(data_dir)


@pytest.fixture(scope="session")
def collected(tmp_path_factory, site_server):
    root = tmp_path_factory.mktemp("acceptance")
    registry = _write_registry(root, site_server)
    data = root / "data"
    report = _collect(registry, data, entry_urls=[f"{site_server}/index.html"])
    yield {"root": root, "data": data, "report": report, "registry": registry, "site": site_server}
    close_run_logging(data)


# ---------- AT-001—AT-005 ----------


def test_at_001_public_access_and_domain_boundary(tmp_path, collected, site_server, mutable_site):
    report = collected["report"]
    layout = DeliveryLayout(collected["data"])
    assert [item.url for item in report.skipped] == ["https://outside.invalid/secret"]
    rows = read_jsonl(layout.manifest_path)
    assert rows and all("outside.invalid" not in row["final_url"] for row in rows)
    http = HttpClient(collected["registry"], limits=FetchLimits(request_rate_per_second=1000))
    with pytest.raises(FetchError, match="边界"):
        http.get(
            f"{collected['site']}/_redirect?to=https://outside.invalid/secret",
            source_id="DEMO",
        )
    # 受限目标（robots 拒绝）：不请求、逐项记录原因；Allow 最长匹配的路径照常获取
    registry = _write_registry(tmp_path, site_server)
    data = tmp_path / "restricted"
    robots_report = _collect(registry, data, entry_urls=[f"{site_server}/robots_linked.html"])
    skipped = {item.url: item.reason for item in robots_report.skipped}
    blocked_url = f"{site_server}/private/secret.html"
    assert blocked_url in skipped and skipped[blocked_url].startswith("robots_disallowed"), skipped
    fetched = [row["final_url"] for row in read_jsonl(DeliveryLayout(data).manifest_path)]
    assert blocked_url not in fetched
    assert f"{site_server}/private/public-note.html" in fetched
    # 受限目标（登录页、验证码页）：按来源规则声明为不可访问，不请求、逐项记录原因
    site, root = mutable_site
    (root / "gateway.html").write_text(
        _site_page(
            "虚构入口",
            '<ul><li><a href="login.html">登录页</a></li>'
            '<li><a href="captcha.html">验证码页</a></li></ul>',
        ),
        encoding="utf-8",
    )
    (root / "login.html").write_text(_site_page("虚构登录页", "<p>需要登录后查看。</p>"), encoding="utf-8")
    (root / "captcha.html").write_text(_site_page("虚构验证码页", "<p>请输入验证码。</p>"), encoding="utf-8")
    guard_registry = _write_sources(
        tmp_path / "guard",
        site,
        [{"source_id": "DEMO", "blocked_paths": ["/login.html", "/captcha.html"]}],
    )
    guard_data = tmp_path / "guard-data"
    guard_report = _collect(guard_registry, guard_data, entry_urls=[f"{site}/gateway.html"])
    guard_skipped = {item.url: item.reason for item in guard_report.skipped}
    assert guard_skipped.get(f"{site}/login.html", "").startswith("path_blocked"), guard_skipped
    assert guard_skipped.get(f"{site}/captcha.html", "").startswith("path_blocked"), guard_skipped
    guard_urls = [row["final_url"] for row in read_jsonl(DeliveryLayout(guard_data).manifest_path)]
    assert all("login.html" not in url and "captcha.html" not in url for url in guard_urls)
    record("AT-001")


def test_at_002_source_config_isolation_and_validation(tmp_path, site_server):
    host = urlsplit(site_server).hostname
    path = tmp_path / "sources.yaml"
    payload = {
        "version": "acceptance",
        "sources": [
            {
                "source_id": "A",
                "source_name": "来源甲",
                "base_domain": host,
                "allowed_domains": [host],
                "enabled": True,
            },
            {
                "source_id": "B",
                "source_name": "来源乙",
                "base_domain": host,
                "allowed_domains": [host],
                "enabled": True,
            },
        ],
    }
    path.write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")
    registry = SourceRegistry.load(path)
    assert registry.get("A").source_name == "来源甲"
    payload["sources"][1]["source_name"] = "来源乙（改）"
    payload["sources"].append({"source_id": "C", "enabled": True})  # 缺 base_domain
    path.write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ConfigurationError):
        SourceRegistry.load(path)
    # 移除非法来源并重载：只应用改动的那一项，另一来源保持原值
    payload["sources"] = payload["sources"][:2]
    path.write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")
    reloaded = SourceRegistry.load(path)
    assert reloaded.get("A").source_name == "来源甲"
    assert reloaded.get("B").source_name == "来源乙（改）"
    record("AT-002")


def test_at_003_discovery_strategies(tmp_path, site_server, collected):
    registry = _write_registry(tmp_path, site_server)
    methods = {
        row["discovery_method"]
        for row in read_jsonl(DeliveryLayout(collected["data"]).manifest_path)
    }  # 会话运行覆盖 list 与 attachment
    for index, kwargs in enumerate(
        (
            {"entry_urls": [], "search_keywords": ["边界"]},
            {"entry_urls": [], "sitemap_urls": [f"{site_server}/sitemap.xml"]},
            {"entry_urls": [], "api_urls": [f"{site_server}/api.json"]},
        ),
        1,
    ):
        data = tmp_path / f"run{index}"
        _collect(registry, data, **kwargs)
        methods |= {row["discovery_method"] for row in read_jsonl(DeliveryLayout(data).manifest_path)}
    assert {"list", "search", "sitemap", "api", "attachment"} <= methods, methods
    record("AT-003")


def test_at_004_keyword_only_affects_discovery(tmp_path, site_server):
    registry = _write_registry(tmp_path, site_server)
    report = _collect(registry, tmp_path / "data", entry_urls=[], search_keywords=["边界"])
    layout = DeliveryLayout(tmp_path / "data")
    rows = read_jsonl(layout.manifest_path)
    # 宽泛触发词：用途可追踪（keyword 与发现方式逐条落在账本）
    assert rows and all(
        row["keyword"] == "边界" and row["discovery_method"] == "search" for row in rows
    )
    documents = read_jsonl(layout.documents_path)
    assert documents and all("category_hint" not in row for row in documents)
    assert all("category" not in row for row in documents)
    assert report.counters.documents == len(documents)
    # 补漏词（正式名称/机制名）：能找到已知材料，并与触发词一样在账本留痕
    supplement = _write_registry(
        tmp_path / "supplement", site_server, supplement_terms=["虚构机制名"]
    )
    supplement_data = tmp_path / "supplement-data"
    _collect(supplement, supplement_data, entry_urls=[], search_keywords=["虚构机制名"])
    supplement_rows = read_jsonl(DeliveryLayout(supplement_data).manifest_path)
    assert supplement_rows and all(row["keyword"] == "虚构机制名" for row in supplement_rows)
    assert any(row["final_url"].endswith("/detail_2.html") for row in supplement_rows)
    # 仅含标签的样本：命中标签词不生成已确认分类
    labels = _write_registry(tmp_path / "labels", site_server)
    labels_data = tmp_path / "labels-data"
    _collect(labels, labels_data, entry_urls=[], search_keywords=["公告"])
    labels_documents = read_jsonl(DeliveryLayout(labels_data).documents_path)
    assert labels_documents
    assert all("category_hint" not in row and "category" not in row for row in labels_documents)
    record("AT-004")


def test_at_005_detail_body_completeness(tmp_path, site_server):
    parsed = parse_html(
        (FIXTURES / "html" / "expandable_page.html").read_bytes(),
        f"{site_server}/expandable_page.html",
    )
    text = parsed.full_text
    assert "正文第一部分" in text and "展开后的正文第二部分" in text
    assert text.index("正文第一部分") < text.index("展开后的正文第二部分")
    assert "无脚本提示" not in text  # noscript 不是正文
    normalized = normalize_page(parsed, base_url=f"{site_server}/expandable_page.html")
    assert normalized.full_text.strip() == text.strip()
    registry = _write_registry(tmp_path, site_server)
    http = HttpClient(registry, limits=FetchLimits(request_rate_per_second=1000))
    response = http.get(f"{site_server}/_redirect?to=/expandable_page.html", source_id="DEMO")
    assert response.requested_url != response.final_url
    assert response.final_url.endswith("/expandable_page.html")
    assert b"\xe5\xb1\x95\xe5\xbc\x80\xe5\x90\x8e\xe7\x9a\x84\xe6\xad\xa3\xe6\x96\x87" in response.content
    record("AT-005")


def test_at_005_paginated_and_api_body(tmp_path, site_server):
    """AT-005：三页正文与接口正文的固定样本，抓取后按原顺序合并为同一文档。"""
    import hashlib

    registry = _write_registry(tmp_path, site_server)
    data = tmp_path / "data"
    report = _collect(registry, data, entry_urls=[f"{site_server}/body_modes_index.html"])
    layout = DeliveryLayout(data)
    documents = read_jsonl(layout.documents_path)
    manifest = read_jsonl(layout.manifest_path)

    paged = next(row for row in documents if "正文第一部分" in row["full_text"])
    text = paged["full_text"]
    assert text.index("正文第一部分") < text.index("正文第二部分") < text.index("正文第三部分")
    assert "下一页" not in text  # 翻页控件不是正文
    assert paged["parse_status"] == "ok"
    paged_blocks = [row for row in read_jsonl(layout.blocks_path) if row["doc_id"] == paged["doc_id"]]
    assert [row["page_no"] for row in paged_blocks] == [1, 1, 2, 2, 3, 3]
    pagination_rows = [row for row in manifest if row["discovery_method"] == "pagination"]
    assert len(pagination_rows) == 2
    assert {row["crawl_id"] for row in pagination_rows} <= set(paged["crawl_ids"])
    assert all(row["referrer_url"] for row in pagination_rows)

    api_doc = next(row for row in documents if "接口正文" in row["full_text"])
    api_text = api_doc["full_text"]
    assert api_text.index("摘要") < api_text.index("接口正文第一部分") < api_text.index("接口正文第二部分")
    assert api_doc["parse_status"] == "ok"
    api_rows = [row for row in manifest if row["discovery_method"] == "api"]
    assert len(api_rows) == 1 and api_rows[0]["crawl_id"] in api_doc["crawl_ids"]
    api_raw = layout.resolve_raw_path(api_rows[0]["raw_path"])
    assert hashlib.sha256(api_raw.read_bytes()).hexdigest() == api_rows[0]["sha256"]

    assert report.metrics["reconciliation"]["ok"] is True
    assert trace_delivery(data).ok is True
    record("AT-005")


def test_at_005_pagination_failure_marks_partial(tmp_path, mutable_site):
    """AT-005：后续正文页获取失败时不静默，保留已获取部分并标 partial。"""
    base_url, root = mutable_site
    (root / "detail_paged_3.html").unlink()
    registry = _write_registry(tmp_path, base_url)
    data = tmp_path / "data"
    _collect(registry, data, entry_urls=[f"{base_url}/body_modes_index.html"])
    layout = DeliveryLayout(data)
    documents = read_jsonl(layout.documents_path)
    paged = next(row for row in documents if "正文第一部分" in row["full_text"])
    assert paged["parse_status"] == "partial"
    assert "正文第二部分" in paged["full_text"] and "正文第三部分" not in paged["full_text"]
    assert any("pagination_" in item for item in paged.get("metadata_missing", []))
    failures = read_jsonl(layout.failures_path)
    assert any(row["url"].endswith("detail_paged_3.html") and row["stage"] == "fetch" for row in failures)
    record("AT-005")


# ---------- AT-006—AT-010 ----------


def test_at_006_attachment_download_and_relations(collected):
    layout = DeliveryLayout(collected["data"])
    documents = read_jsonl(layout.documents_path)
    document = next(row for row in documents if row.get("attachments"))
    attachments = {item["filename"]: item for item in document["attachments"]}
    assert set(attachments) == {"notice.csv", "unavailable.pdf"}
    assert attachments["notice.csv"]["status"] == "downloaded"
    assert (collected["data"] / attachments["notice.csv"]["raw_path"]).is_file()
    assert attachments["unavailable.pdf"]["status"] == "failed"
    assert "raw_path" not in attachments["unavailable.pdf"]
    failures = read_jsonl(layout.failures_path)
    assert any(row["url"].endswith("unavailable.pdf") and row["stage"] == "fetch" for row in failures)
    record("AT-006")


def test_at_006_duplicate_body_attachment_keeps_identity(tmp_path, mutable_site):
    """AT-006：正文与附件内容重复时仍保留附件资源身份与母页关系。"""
    base_url, root = mutable_site
    body_text = "虚构要点：正文与附件内容相同，仍需各自保留资源身份。"
    page = _site_page(
        "虚构公告：正文与附件重复样本",
        f'<p>{body_text}</p><p><a href="attachments/dup_note.txt">附件：dup_note.txt</a></p>',
    )
    (root / "dup_page.html").write_text(page, encoding="utf-8")
    (root / "attachments" / "dup_note.txt").write_text(body_text, encoding="utf-8")
    (root / "dup_index.html").write_text(
        _site_page("虚构栏目：重复内容样本", '<ul><li><a href="dup_page.html">重复样本</a></li></ul>'),
        encoding="utf-8",
    )

    registry = _write_registry(tmp_path, base_url)
    data = tmp_path / "data"
    _collect(registry, data, entry_urls=[f"{base_url}/dup_index.html"])
    layout = DeliveryLayout(data)
    document = read_jsonl(layout.documents_path)[0]
    attachment = document["attachments"][0]
    assert attachment["status"] == "downloaded"
    assert attachment["url"].endswith("/attachments/dup_note.txt")
    assert (data / attachment["raw_path"]).read_text(encoding="utf-8") == body_text
    assert body_text in document["full_text"]
    manifest = {row["crawl_id"]: row for row in read_jsonl(layout.manifest_path)}
    attachment_row = manifest[attachment["crawl_id"]]
    assert attachment_row["discovery_method"] == "attachment"
    assert attachment_row["sha256"] == attachment["sha256"]
    assert document["doc_id"] in manifest and document["doc_id"] != attachment["crawl_id"]
    record("AT-006")


def test_at_007_raw_archive_fidelity(collected):
    import hashlib

    layout = DeliveryLayout(collected["data"])
    rows = read_jsonl(layout.manifest_path)
    assert rows
    for row in rows:
        raw = layout.resolve_raw_path(row["raw_path"])
        assert raw.is_file()
        assert hashlib.sha256(raw.read_bytes()).hexdigest() == row["sha256"]
    record("AT-007")


def test_at_007_all_supported_types_archived_byte_identical(tmp_path, mutable_site):
    """AT-007：各已启用类型逐字节归档；不支持的二进制不伪装成已解析文档。"""
    import hashlib

    base_url, root = mutable_site
    sources = {
        "notice.pdf": FIXTURES / "attachments" / "notice.pdf",
        "notice.docx": FIXTURES / "office" / "notice.docx",
        "notice.xlsx": FIXTURES / "office" / "notice.xlsx",
        "notice.csv": FIXTURES / "attachments" / "notice.csv",
    }
    links = []
    for name, source in sources.items():
        shutil.copy(source, root / "attachments" / name)
        links.append(f'<a href="attachments/{name}">附件：{name}</a>')
    page = _site_page("虚构公告：多类型归档样本", "<p>正文</p>" + "".join(links))
    (root / "types_page.html").write_text(page, encoding="utf-8")
    (root / "types_index.html").write_text(
        _site_page("虚构栏目：多类型样本", '<ul><li><a href="types_page.html">多类型样本</a></li></ul>'),
        encoding="utf-8",
    )

    registry = _write_registry(tmp_path, base_url)
    data = tmp_path / "data"
    _collect(registry, data, entry_urls=[f"{base_url}/types_index.html"])
    layout = DeliveryLayout(data)
    rows = read_jsonl(layout.manifest_path)
    archived = {row["final_url"].rsplit("/", 1)[-1]: row for row in rows}
    for name in sources:
        row = archived[name]
        raw = layout.resolve_raw_path(row["raw_path"])
        assert hashlib.sha256(raw.read_bytes()).hexdigest() == row["sha256"], name
    assert set(sources) <= set(archived)
    documents = read_jsonl(layout.documents_path)
    assert [row["source_url"].rsplit("/", 1)[-1] for row in documents] == ["types_page.html"]
    record("AT-007")


def test_at_008_manifest_fields_and_redirect(tmp_path, site_server, collected):
    layout = DeliveryLayout(collected["data"])
    schema = load_contract("manifest")
    errors = validate_jsonl_file(layout.manifest_path, schema, label="crawl_manifest.jsonl")
    assert errors == [], errors
    rows = read_jsonl(layout.manifest_path)
    assert all(row["crawl_id"] and row["http_status"] == 200 for row in rows)
    assert any(row["discovery_method"] == "attachment" for row in rows)
    http = HttpClient(collected["registry"], limits=FetchLimits(request_rate_per_second=1000))
    response = http.get(f"{site_server}/_redirect?to=/index.html", source_id="DEMO")
    assert response.requested_url != response.final_url
    assert response.final_url.endswith("/index.html")

    # 带关键词的站内搜索发现：搜索记录必须保留 keyword
    data = tmp_path / "search-data"
    _collect(collected["registry"], data, entry_urls=[], search_keywords=["边界"])
    search_rows = read_jsonl(DeliveryLayout(data).manifest_path)
    assert search_rows and all(
        row["discovery_method"] == "search" and row["keyword"] == "边界" for row in search_rows
    )
    record("AT-008")


def test_at_009_document_contract(tmp_path, collected):
    layout = DeliveryLayout(collected["data"])
    report = validate_delivery(collected["data"])
    assert report.ok is True, report.errors[:5]
    documents = read_jsonl(layout.documents_path)
    assert documents
    for document in documents:
        assert document["parse_status"] in ("ok", "partial", "failed")
        assert document["full_text"] and document["raw_path"] and document["sha256"]
        assert document["source_url"].startswith("http")
        # 元数据来源与未知值可区分：规范化日期必须留有原文日期，
        # 缺少日期时登记 metadata_missing，不用空串或猜测值冒充
        if document.get("publication_date"):
            assert document.get("raw_date"), document["doc_id"]
        else:
            assert "publication_date" in document.get("metadata_missing", []), document["doc_id"]

    # PDF 转换成 document：已下载的原件经补抓重解析产出契约文档（附件→独立文档的常规路径待 Q07）
    data = tmp_path / "pdf"
    pdf_bytes = (FIXTURES / "attachments" / "notice.pdf").read_bytes()
    pipeline = _pipeline(collected["registry"], data)
    url = f"{collected['site']}/attachments/notice.pdf"
    raw = pipeline.store.write_bytes(
        source_id="DEMO", crawl_date="2026-09-11", kind="attachment",
        filename="notice.pdf", content=pdf_bytes,
    )
    crawl_id = "DEMO_20260911_0900"
    pipeline.manifest.record(
        crawl_id=crawl_id, source_id="DEMO", requested_url=url, final_url=url,
        crawl_time=NOW.isoformat(), http_status=200, content_type="application/pdf",
        raw=raw, discovery_method="attachment",
    )
    pipeline.failures.record(
        source_id="DEMO", url=url, time=NOW.isoformat(), stage="parse",
        error_type="parse_error", message="夹具注入的解析失败", retry_count=0,
        final_action="retry_later", crawl_id=crawl_id,
    )
    try:
        recovered = pipeline.resume_failures("DEMO")
    finally:
        close_run_logging(data)
    assert recovered.counters.documents == 1
    pdf_document = read_jsonl(DeliveryLayout(data).documents_path)[0]
    assert pdf_document["extraction_method"] == "pypdf_text"
    assert validate_instance(pdf_document, load_contract("document")) == []
    assert trace_delivery(data).ok is True
    record("AT-009")


def test_at_010_block_structure(collected):
    layout = DeliveryLayout(collected["data"])
    blocks = read_jsonl(layout.blocks_path)
    assert blocks
    by_doc = {}
    for block in blocks:
        by_doc.setdefault(block["doc_id"], []).append(block)
    for doc_id, rows in by_doc.items():
        assert [row["order"] for row in rows] == list(range(len(rows))), doc_id
        assert len({row["block_id"] for row in rows}) == len(rows)
    long_text = max((block["text"] or "" for block in blocks), key=len)
    assert len(long_text) > 0
    record("AT-010")


# ---------- AT-011—AT-013 ----------


def test_at_011_pdf_and_ocr_locators():
    text_pdf = parse_pdf((FIXTURES / "attachments" / "notice.pdf").read_bytes())
    assert text_pdf.page_count == 2 and text_pdf.extraction_method == "pypdf_text"
    assert all(block.page_no in (1, 2) for block in text_pdf.blocks)
    scanned = parse_scanned_pdf((FIXTURES / "ocr" / "scanned_notice.pdf").read_bytes())
    assert scanned.extraction_method == "rapidocr_onnxruntime"
    assert all(block.page_no == 1 and 0 < (block.confidence or 0) <= 1 for block in scanned.blocks)
    image = parse_image((FIXTURES / "ocr" / "scanned_notice.png").read_bytes())
    assert image.page_status[0].mean_confidence is not None
    record("AT-011")


def test_at_012_office_and_structured_formats():
    docx = parse_attachment((FIXTURES / "office" / "notice.docx").read_bytes(), "notice.docx")
    assert any(block.block_type == "table" for block in docx.blocks)
    xlsx = parse_attachment((FIXTURES / "office" / "notice.xlsx").read_bytes(), "notice.xlsx")
    assert any(block.block_type == "table" for block in xlsx.blocks)
    csv = parse_attachment((FIXTURES / "attachments" / "notice.csv").read_bytes(), "notice.csv")
    assert any(block.structured_data for block in csv.blocks)
    payload = json.dumps([{"id": 1, "name": "甲"}, {"id": 2, "name": "乙"}]).encode("utf-8")
    parsed_json = parse_attachment(payload, "items.json")
    assert parsed_json.extraction_method == "json_stdlib"
    assert [block.block_type for block in parsed_json.blocks] == ["record", "record"]
    assert all(block.structured_data for block in parsed_json.blocks)
    assert "甲" in parsed_json.full_text and "乙" in parsed_json.full_text
    xml = b"<root><item name='a'>1</item></root>"
    parsed_xml = parse_attachment(xml, "items.xml")
    assert parsed_xml.extraction_method == "defusedxml_etree"
    assert parsed_xml.blocks and parsed_xml.blocks[0].structured_data
    # 分页 JSON：分页字段与列表项各自保留为记录块，分页信息不丢也不被推断语义
    paged_payload = json.dumps(
        {
            "page": 2,
            "page_size": 2,
            "total_pages": 3,
            "total": 5,
            "items": [{"id": 3, "name": "丙"}, {"id": 4, "name": "丁"}],
        },
        ensure_ascii=False,
    ).encode("utf-8")
    paged = parse_attachment(paged_payload, "items_page2.json")
    assert all(block.block_type == "record" and block.structured_data for block in paged.blocks)
    by_field = {block.structured_data.get("field"): block for block in paged.blocks}
    assert {"page", "page_size", "total_pages", "total", "items"} <= set(by_field), by_field
    assert by_field["page"].text == "2" and by_field["total_pages"].text == "3"
    assert by_field["page"].structured_data["json_path"] == "$.page"
    assert "丙" in by_field["items"].text and "丁" in by_field["items"].text
    record("AT-012")


def test_at_013_cleaning_fidelity():
    html = (
        "<html lang='zh-CN'><head><title>虚构清洗样本</title>"
        "<link rel='canonical' href='/a?utm_source=x#part'></head><body>"
        "<nav>导航</nav><main><p>正文第一部分。</p>"
        "<p>发布日期：近期</p><p>English paragraph stays as is.</p></main></body></html>"
    ).encode("utf-8")
    page = normalize_page(
        parse_html(html, "https://example.invalid/a?utm_source=x#part"),
        base_url="https://example.invalid/a",
    )
    assert page.publication_date is None  # 模糊日期不编造
    assert "publication_date" in page.metadata_missing
    assert "English paragraph stays as is." in page.full_text
    assert "导航" not in page.full_text
    # 规范 URL：解析相对地址并去片段；查询参数保留（当前规则不剥离追踪参数）
    assert page.canonical_url == "https://example.invalid/a?utm_source=x"
    assert page.language_hint == "zh"
    dated = normalize_page(
        parse_html(
            html.replace("近期".encode("utf-8"), "2026年9月10日".encode("utf-8")),
            "https://example.invalid/a",
        ),
        base_url="https://example.invalid/a",
    )
    assert dated.publication_date == "2026-09-10"
    assert dated.raw_date_text and "2026" in dated.raw_date_text
    # 三种语言原文保留、超长段落不裁剪（AT-013 场景含 zh/en/hi 与超长段落）
    long_paragraph = "超长段落内容。" * 800 + "段落结束标记"
    multilingual = (
        "<html lang='zh-CN'><head><meta charset='utf-8'><title>多语样本</title></head><body><main>"
        "<p>中文段落保留。</p>"
        "<p>English paragraph stays as is.</p>"
        "<p>यह हिन्दी पाठ यथावत रहेगा।</p>"
        f"<p>{long_paragraph}</p></main></body></html>"
    ).encode("utf-8")
    multi = normalize_page(
        parse_html(multilingual, "https://example.invalid/multi"),
        base_url="https://example.invalid/multi",
    )
    assert "中文段落保留。" in multi.full_text
    assert "English paragraph stays as is." in multi.full_text
    assert "यह हिन्दी पाठ यथावत रहेगा।" in multi.full_text  # 不翻译、不转写
    assert "段落结束标记" in multi.full_text  # 超长段落不截断、不摘要
    assert multi.language_hint == "zh"
    # 无语言标记的天城文文本按文字系统识别为 hi；拉丁文仍返回 und 不猜测
    hindi = normalize_page(
        parse_html(
            "<html><head><meta charset='utf-8'></head><body><main>"
            "<p>यह हिन्दी दस्तावेज़ है।</p></main></body></html>".encode("utf-8"),
            "https://example.invalid/hi",
        ),
        base_url="https://example.invalid/hi",
    )
    assert hindi.language_hint == "hi"
    record("AT-013")


# ---------- AT-015—AT-020 ----------


def test_at_015_versions_and_offline_history(tmp_path):
    from crawler.normalize.document_schema import build_document

    pages = []
    for name, version in (("version_v1.html", "1"), ("version_v2.html", "2")):
        parsed = parse_html((FIXTURES / "html" / name).read_bytes(), "https://example.invalid/rule")
        pages.append(
            build_document(
                doc_id=f"DOC-{version}",
                source_id="DEMO",
                source_name="夹具来源",
                source_url="https://example.invalid/rule",
                title=parsed.title,
                full_text=parsed.full_text,
                language="zh",
                document_type="html_page",
                raw_path=f"raw/DEMO/2026-09-11/html/{name}",
                sha256="a" * 64,
                crawl_time=NOW.isoformat(),
                extraction_method=parsed.extraction_method,
                crawl_ids=[f"DEMO_000{version}"],
                version=version,
                is_current=True,
            )
        )
    decision = plan_version(pages[1], existing_documents=[pages[0]], similarity_threshold=0.99)
    assert decision.supersedes == ("DOC-1",)
    store = VersionStore(tmp_path)
    (tmp_path / "normalized").mkdir(parents=True, exist_ok=True)
    from crawler.output.jsonl import write_jsonl

    write_jsonl(store.path, pages)
    assert store.retire(["DOC-1"]) == 1
    assert store.record_offline("DOC-1", source_status="removed", evidence={"checked_at": NOW.isoformat()}) == 1
    rows = {row["doc_id"]: row for row in store.load()}
    assert rows["DOC-1"]["full_text"] and rows["DOC-1"]["source_status"] == "removed"
    assert rows["DOC-1"]["status_history"]
    assert [row["version"] for row in store.versions_of(document_identity(pages[0]))] == ["1", "2"]
    record("AT-015")


def test_at_016_incremental_update_without_false_documents(tmp_path, site_server):
    registry = _write_registry(tmp_path, site_server)
    data = tmp_path / "data"
    url = f"{site_server}/_etag/index.html"
    first = _collect(registry, data, entry_urls=[url])
    second = _collect(registry, data, entry_urls=[url])
    assert first.counters.documents >= 1 and second.counters.documents == 0
    assert second.counters.not_modified >= 1
    stored = read_metrics(data)
    assert stored["counters"]["documents"] == 0 and stored["reconciliation"]["ok"] is True
    record("AT-016")


def test_at_016_incremental_by_resource_kind(tmp_path, mutable_site):
    """三种资料类型的增量：新增新闻、未改法规、新年份统计。"""
    site, root = mutable_site
    (root / "news.html").write_text(
        _site_page("虚构新闻列表", '<ul><li><a href="_etag/news_a.html">虚构新闻 A</a></li></ul>'),
        encoding="utf-8",
    )
    (root / "news_a.html").write_text(
        _site_page("虚构新闻 A", "<p>2026-09-01 发布的旧条目。</p>"), encoding="utf-8"
    )
    (root / "news_b.html").write_text(
        _site_page("虚构新闻 B", "<p>2026-09-11 发布的新条目。</p>"), encoding="utf-8"
    )
    (root / "law.html").write_text(
        _site_page("虚构法规栏目", '<ul><li><a href="_etag/regulation.html">虚构法规</a></li></ul>'),
        encoding="utf-8",
    )
    (root / "regulation.html").write_text(
        _site_page("虚构法规（未修订）", "<p>条款文本保持不变。</p>"), encoding="utf-8"
    )
    (root / "stats.html").write_text(
        _site_page("虚构统计栏目", '<ul><li><a href="_etag/stats_data.html">年度统计</a></li></ul>'),
        encoding="utf-8",
    )
    (root / "stats_data.html").write_text(
        _site_page("虚构统计 2025 年", "<p>2025 年数值 12。</p>"), encoding="utf-8"
    )
    registry = _write_sources(
        tmp_path,
        site,
        [
            {"source_id": "NEWS", "resource_kind": "news"},
            {"source_id": "LAW", "resource_kind": "law"},
            {"source_id": "STATS", "resource_kind": "statistics"},
        ],
    )
    data = tmp_path / "data"

    def collect(source_id, url):
        pipeline = _pipeline(registry, data)
        try:
            return pipeline.collect(source_id, entry_urls=[url])
        finally:
            close_run_logging(data)

    first = {
        "NEWS": collect("NEWS", f"{site}/news.html"),
        "LAW": collect("LAW", f"{site}/law.html"),
        "STATS": collect("STATS", f"{site}/stats.html"),
    }
    assert first["NEWS"].counters.documents == 1  # 列表已有一条新闻
    assert first["LAW"].counters.documents == 1
    assert first["STATS"].counters.documents == 1

    # 站点变化：列表新增一条新闻、统计数据出到 2026 年、法规保持不变
    (root / "news.html").write_text(
        _site_page(
            "虚构新闻列表",
            '<ul><li><a href="_etag/news_a.html">虚构新闻 A</a></li>'
            '<li><a href="_etag/news_b.html">虚构新闻 B</a></li></ul>',
        ),
        encoding="utf-8",
    )
    (root / "stats_data.html").write_text(
        _site_page("虚构统计 2026 年", "<p>2026 年数值 15。</p>"), encoding="utf-8"
    )
    second = {
        "NEWS": collect("NEWS", f"{site}/news.html"),
        "LAW": collect("LAW", f"{site}/law.html"),
        "STATS": collect("STATS", f"{site}/stats.html"),
    }
    layout = DeliveryLayout(data)
    urls = [row["source_url"] for row in read_jsonl(layout.documents_path)]
    assert sum(url.endswith("/_etag/news_a.html") for url in urls) == 1  # 未变条目只有一份
    assert sum(url.endswith("/_etag/news_b.html") for url in urls) == 1  # 新增条目才产生新文档
    assert second["NEWS"].counters.documents == 1 and second["NEWS"].counters.not_modified == 1
    assert second["LAW"].counters.documents == 0  # 未改法规不创建新数据
    assert second["LAW"].counters.not_modified == 1
    assert second["STATS"].counters.documents == 1  # 新年份统计才更新
    stats_docs = [
        row
        for row in read_jsonl(layout.documents_path)
        if row["source_url"].endswith("/_etag/stats_data.html")
    ]
    assert len(stats_docs) == 2 and "2026" in stats_docs[-1]["full_text"]
    record("AT-016")


def test_at_017_failures_and_recovery(tmp_path, collected):
    data = tmp_path / "copy"
    shutil.copytree(collected["data"], data)
    layout = DeliveryLayout(data)
    manifest_row = read_jsonl(layout.manifest_path)[0]
    failure_url = manifest_row["final_url"]
    append_jsonl(
        layout.failures_path,
        [
            {
                "source_id": "DEMO",
                "url": failure_url,
                "time": NOW.isoformat(),
                "stage": "normalize",
                "error_type": "normalization_error",
                "message": "夹具注入的本地阶段失败",
                "retry_count": 0,
                "final_action": "retry_later",
                "crawl_id": manifest_row["crawl_id"],
            }
        ],
    )
    # 成功下载但解析失败：原件与账本行都在，失败记录指向同一 crawl_id，不是只留 URL
    raw_file = layout.resolve_raw_path(manifest_row["raw_path"])
    assert raw_file.is_file()
    assert hashlib.sha256(raw_file.read_bytes()).hexdigest() == manifest_row["sha256"]
    recorded = read_jsonl(layout.failures_path)[-1]
    assert recorded["crawl_id"] == manifest_row["crawl_id"] and recorded["stage"] == "normalize"

    pipeline = _pipeline(collected["registry"], data)
    try:
        report = pipeline.resume_failures("DEMO", max_tasks=5)
    finally:
        close_run_logging(data)
    assert report.recovered and report.counters.documents >= 1
    history = [row for row in read_jsonl(layout.failures_path) if row["url"] == failure_url]
    assert len(history) == 2
    assert history[0]["final_action"] == "retry_later"  # 历史失败不删除
    assert history[1]["final_action"] == "recovered"
    record("AT-017")


def test_at_018_logs_and_reconciliation(collected):
    data = collected["data"]
    stored = read_metrics(data)
    assert stored["reconciliation"]["ok"] is True
    assert stored["counters"]["requests"] != stored["counters"]["documents"]
    assert stored["counting_rules"]["requests"]
    log_text = log_path(data).read_text(encoding="utf-8")
    assert "运行汇总" in log_text and "reconciliation_ok=True" in log_text
    assert read_jsonl(DeliveryLayout(data).metrics_history_path)
    # 交付检查直接遍历数据根（不依赖任何“首页摘要”），logs 不会被摘要遗漏而缺项
    inspection = inspect_delivery(data)
    assert inspection.ok is True
    present = {entry["name"] for entry in inspection.present}
    assert {"raw/", "manifests/crawl_manifest.jsonl", "normalized/documents.jsonl",
            "normalized/blocks.jsonl", "logs/"} <= present
    record("AT-018")


def test_at_019_delivery_files(collected, tmp_path):
    report = inspect_delivery(collected["data"])
    assert report.ok is True, report.as_row()
    names = [item["name"] for item in report.present]
    assert len(names) == 6 and "logs/" in names and "raw/" in names
    assert report.counts["manifest_rows"] == collected["report"].counters.resources
    # 零失败场景：失败账可以是合法空 JSONL（不需要占位行，也不强制“必须不存在”）
    empty_root = tmp_path / "zero_failures" / "manifests"
    empty_root.mkdir(parents=True)
    empty_failures = empty_root / "failed_records.jsonl"
    empty_failures.write_text("", encoding="utf-8")
    assert read_jsonl(empty_failures) == []
    assert (
        validate_jsonl_file(empty_failures, load_contract("failure"), label="failed_records.jsonl")
        == []
    )
    record("AT-019")


def test_at_020_collection_stage_boundary(collected):
    report = inspect_delivery(collected["data"])
    assert report.forbidden == []
    assert not (collected["data"] / "normalized" / "chunks.jsonl").exists()
    record("AT-020")


# ---------- AT-021—AT-023 ----------


def test_at_021_traceability_and_dangling_block(tmp_path, collected):
    trace = trace_delivery(collected["data"])
    assert trace.ok is True and trace.document_rate == 1.0 and trace.block_rate == 1.0
    data = tmp_path / "copy"
    shutil.copytree(collected["data"], data)
    layout = DeliveryLayout(data)
    append_jsonl(
        layout.blocks_path,
        [
            {
                "block_id": "DANGLING_B0001",
                "doc_id": "UNKNOWN_DOC",
                "order": 0,
                "block_type": "paragraph",
                "text": "悬挂块",
                "extraction_method": "fixture",
            }
        ],
    )
    after = trace_delivery(data)
    assert after.ok is False
    assert any("悬挂块" in problem["reason"] and problem.get("block_id") == "DANGLING_B0001" for problem in after.problems)
    empty = trace_delivery(tmp_path / "empty")
    assert empty.document_rate is None and empty.block_rate is None
    record("AT-021")


def test_at_022_jsonl_schema_and_located_errors(tmp_path, collected):
    assert validate_delivery(collected["data"]).ok is True
    data = tmp_path / "broken"
    shutil.copytree(collected["data"], data)
    layout = DeliveryLayout(data)
    with layout.documents_path.open("a", encoding="utf-8") as handle:
        handle.write("{不是 JSON}\n")
    report = validate_delivery(data)
    assert report.ok is False
    assert any(error["file"] == "documents.jsonl" and error["line"] > 0 for error in report.errors)

    schema = load_contract("manifest")
    missing = [{"crawl_id": "x"}]
    errors = validate_instance(missing[0], schema)
    assert any("缺少必填字段" in message for message in errors)
    wrong_type = dict(read_jsonl(layout.manifest_path)[0])
    wrong_type["http_status"] = "200"
    assert any("类型" in message for message in validate_instance(wrong_type, schema))
    # 编码错误同样定位到文件（非法 UTF-8 不能静默通过，也不能让校验崩溃）
    broken_encoding = tmp_path / "broken_encoding"
    shutil.copytree(collected["data"], broken_encoding)
    encoding_layout = DeliveryLayout(broken_encoding)
    with encoding_layout.documents_path.open("ab") as handle:
        handle.write(b"\xff\xfe\xfd\n")
    encoding_report = validate_delivery(broken_encoding)
    assert encoding_report.ok is False
    assert any(
        error["file"] == "documents.jsonl" and "UTF-8" in error["message"]
        for error in encoding_report.errors
    )
    record("AT-022")


def test_at_023_request_controls(tmp_path, site_server, timeout_session):
    registry = _write_registry(tmp_path, site_server)
    state = {"now": 0.0, "sleeps": []}

    def sleep(seconds):
        state["sleeps"].append(seconds)
        state["now"] += seconds

    limits = FetchLimits(request_rate_per_second=1000, max_retries=2)
    http = HttpClient(
        registry,
        limits=limits,
        sleep=sleep,
        clock=lambda: state["now"],
    )
    # 429：遵守 Retry-After 并重试到成功（夹具端点前两次返回 429 且 Retry-After: 0）
    retried = http.get(f"{site_server}/_429/2", source_id="DEMO")
    assert retried.status_code == 200 and retried.attempts == 3
    # 5xx：临时 500 按指数退避重试后成功
    before = len(state["sleeps"])
    retried_500 = http.get(f"{site_server}/_flaky/1", source_id="DEMO")
    assert retried_500.status_code == 200 and retried_500.attempts == 2
    assert 1.0 in state["sleeps"][before:]  # 第一次退避 = backoff_base_seconds
    # 超时：读取超时重试后成功（注入式，避免依赖真实慢端点）
    timeout_http = HttpClient(
        registry,
        limits=limits,
        session=timeout_session(
            requests.Session(), 1, requests.ReadTimeout("模拟读取超时")
        ),
        sleep=sleep,
        clock=lambda: state["now"],
        robots=False,  # 本用例只验证请求控制参数，robots 规则另有用例
    )
    recovered = timeout_http.get(f"{site_server}/detail_1.html", source_id="DEMO")
    assert recovered.status_code == 200 and recovered.attempts == 2
    # 永久 404：不重试、不进入退避
    before = len(state["sleeps"])
    with pytest.raises(FetchError) as excinfo:
        http.get(f"{site_server}/missing.pdf", source_id="DEMO")
    assert excinfo.value.status_code == 404 and excinfo.value.retryable is False
    assert excinfo.value.attempts == 1
    assert state["sleeps"][before:] == []
    record("AT-023")


# ---------- 登记表与报告 ----------


def test_blocked_cases_never_pass():
    report = build_acceptance_report({"AT-014": "passed", "AT-024": "passed"})
    by_id = {row["case_id"]: row for row in report["cases"]}
    assert by_id["AT-014"]["status"] == "blocked" and by_id["AT-014"]["blocked_by"]
    assert by_id["AT-024"]["status"] == "blocked" and by_id["AT-024"]["blocked_by"]
    assert by_id["AT-025"]["status"] == "not_applicable"


def test_acceptance_report_covers_all_cases():
    implemented = [case.case_id for case in ACCEPTANCE_CASES if case.status == "implemented"]
    missing = [case_id for case_id in implemented if RESULTS.get(case_id) != "passed"]
    assert missing == [], f"未执行或未通过的验收用例：{missing}"
    target = os.environ.get("T019_ACCEPTANCE_REPORT")
    # 写盘的报告是运行证据，用实际执行时间；仅在测试内断言时用固定时刻保持确定性。
    executed_at = (
        datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        if target
        else NOW.isoformat()
    )
    report = build_acceptance_report(RESULTS, executed_at=executed_at)
    assert report["summary"].get("failed", 0) == 0
    assert report["blocked_cases"] == ["AT-014", "AT-024"]
    if target:
        Path(target).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
