"""T006/FR-001：robots.txt 解析、判定与采集管线集成测试。

夹具站点提供 tests/fixtures/site/robots.txt：`User-agent: *` 下
`Disallow: /private/`，并用更长的 `Allow: /private/public-note.html` 验证最长匹配。
"""

from datetime import datetime, timedelta, timezone

import pytest

from crawler.fetch.http_client import FetchLimits, HttpClient, RobotsDisallowed
from crawler.fetch.robots import parse_robots, rules_for_unavailable
from crawler.output.jsonl import read_jsonl
from crawler.output.failures_writer import FailureWriter
from crawler.output.layout import DeliveryLayout
from crawler.pipeline import CrawlPipeline

UA = "public-knowledge-collection/0.1 (fixture-driven development)"
FAST = FetchLimits(request_rate_per_second=1000, max_retries=2)

SAMPLE = """
# 注释行
User-agent: *
Disallow: /all/
Crawl-delay: 5

User-agent: knowledge-bot
Disallow: /

User-agent: fixture-crawler
Disallow: /mixed/
Allow: /mixed/ok/
"""


def test_wildcard_and_specific_groups():
    rules = parse_robots(SAMPLE)
    assert rules.decision("/all/x", "knowledge-bot/1.0")[0] is False  # 具体组优先
    assert rules.decision("/all/x", UA)[0] is False  # 未命名爬虫落到 *
    assert rules.decision("/mixed/no", "fixture-crawler/2")[0] is False
    assert rules.decision("/mixed/ok/page", "fixture-crawler/2")[0] is True


def test_longest_match_then_allow_wins():
    rules = parse_robots(
        "User-agent: *\n"
        "Disallow: /a/\n"
        "Allow: /a/b\n"
        "Disallow: /tie/\n"
        "Allow: /tie/\n"
    )
    assert rules.decision("/a/deep/page", UA)[0] is False
    assert rules.decision("/a/b/page", UA)[0] is True
    assert rules.decision("/tie/anything", UA)[0] is True  # 同长度 Allow 优先


def test_empty_disallow_and_missing_group_allow():
    rules = parse_robots("User-agent: *\nDisallow:\n")
    assert rules.decision("/anything", UA)[0] is True
    assert rules.decision("/anything", "other-bot")[0] is True


def test_bom_crlf_and_unknown_fields_are_tolerated():
    rules = parse_robots("\ufeffUser-agent: *\r\nSitemap: /s.xml\r\nDisallow: /x/\r\n")
    assert rules.decision("/x/1", UA)[0] is False
    assert rules.decision("/y/1", UA)[0] is True


def test_star_and_end_anchor_patterns():
    rules = parse_robots("User-agent: *\nDisallow: /*.pdf$\nDisallow: /tmp/*/draft\n")
    assert rules.decision("/docs/report.pdf", UA)[0] is False
    assert rules.decision("/docs/report.pdf.html", UA)[0] is True
    assert rules.decision("/tmp/a/draft", UA)[0] is False
    assert rules.decision("/tmp/a/b/draft", UA)[0] is False


def test_rules_for_unavailable_status():
    assert rules_for_unavailable(404).decision("/x", UA)[0] is True
    assert rules_for_unavailable(410).decision("/x", UA)[0] is True
    assert rules_for_unavailable(503).decision("/x", UA)[0] is False
    assert rules_for_unavailable(None).decision("/x", UA)[0] is False


def test_disallowed_path_is_not_requested(site_server, registry_factory):
    client = HttpClient(registry_factory(site_server), limits=FAST)
    with pytest.raises(RobotsDisallowed) as excinfo:
        client.get(f"{site_server}/private/secret.html", source_id="TESTSRC")
    assert "Disallow /private/" in str(excinfo.value)
    # 只发出 robots.txt 一次请求；受限路径本身没有被请求
    assert client.request_attempts == 1


def test_longer_allow_rule_overrides_disallow(site_server, registry_factory):
    client = HttpClient(registry_factory(site_server), limits=FAST)
    response = client.get(f"{site_server}/private/public-note.html", source_id="TESTSRC")
    assert response.status_code == 200
    assert "虚构公开说明" in response.content.decode("utf-8")
    assert client.request_attempts == 2  # robots.txt + 页面


def test_robots_is_cached_per_host(site_server, registry_factory):
    client = HttpClient(registry_factory(site_server), limits=FAST)
    client.get(f"{site_server}/detail_1.html", source_id="TESTSRC")
    client.get(f"{site_server}/page2.html", source_id="TESTSRC")
    assert client.request_attempts == 3  # 1 次 robots + 2 次页面
    assert len(client._robots) == 1


def test_robots_can_be_disabled_explicitly(site_server, registry_factory):
    client = HttpClient(registry_factory(site_server), limits=FAST, robots=False)
    response = client.get(f"{site_server}/private/secret.html", source_id="TESTSRC")
    assert response.status_code == 200
    assert client.request_attempts == 1


def test_pipeline_records_robots_skip_not_failure(site_server, registry_factory, tmp_path):
    registry = registry_factory(site_server)
    http = HttpClient(registry, limits=FAST)
    fixed_now = lambda: datetime(  # noqa: E731 - 固定时间保证 crawl_id 可预期
        2026, 9, 11, 10, 0, 0, tzinfo=timezone(timedelta(hours=8))
    )
    pipeline = CrawlPipeline(registry, tmp_path / "data", http=http, now=fixed_now)

    report = pipeline.collect(
        "TESTSRC", entry_urls=[f"{site_server}/robots_linked.html"]
    )
    layout = DeliveryLayout(tmp_path / "data")

    skipped = {item.url: item.reason for item in report.skipped}
    assert skipped[f"{site_server}/private/secret.html"].startswith("robots_disallowed:")

    rows = read_jsonl(layout.manifest_path)
    urls = {row["final_url"] for row in rows}
    assert f"{site_server}/private/secret.html" not in urls
    assert f"{site_server}/private/secret.csv" not in urls
    assert f"{site_server}/private/public-note.html" in urls  # 更长 Allow 规则放行

    failures = read_jsonl(layout.failures_path)
    robots_failures = [row for row in failures if row["error_type"] == "robots_disallowed"]
    # S5-04：附件被 robots 拒绝属边界拒绝（skipped + 覆盖计数），不写失败账
    assert robots_failures == []
    assert any(
        item.url.endswith("/private/secret.csv") and "robots_disallowed" in item.reason
        for item in report.skipped
    )
    assert report.coverage["attachments"]["boundary_rejected"] >= 1

    assert any(
        "robots_disallowed" in reason for reason in report.metrics["skipped_by_reason"]
    )
    assert report.counters.skipped == len(report.skipped)


def test_resume_failures_closes_robots_disallowed_as_skip(
    site_server, registry_factory, tmp_path
):
    """补抓遇到 robots 拒绝时按 skip 关闭失败，不再进入补抓计划。"""
    registry = registry_factory(site_server)
    data_dir = tmp_path / "data"
    http = HttpClient(registry, limits=FAST)
    fixed_now = lambda: datetime(  # noqa: E731
        2026, 9, 11, 10, 0, 0, tzinfo=timezone(timedelta(hours=8))
    )
    pipeline = CrawlPipeline(registry, data_dir, http=http, now=fixed_now)
    pipeline.layout.ensure()
    blocked_url = f"{site_server}/private/secret.html"
    FailureWriter(data_dir).record(
        source_id="TESTSRC",
        url=blocked_url,
        time=fixed_now().isoformat(),
        stage="fetch",
        error_type="request_error",
        message="模拟早先抓取失败",
        retry_count=0,
        final_action="retry_later",
    )

    report = pipeline.resume_failures("TESTSRC")

    assert [row["url"] for row in report.skipped] == [blocked_url]
    assert report.recovered == []
    # R5 身份键：URL + stage + 原运行范围 + 母文档（此处均无）。
    resolution = pipeline.failures_ledger.latest_by_key()[(blocked_url, "fetch", None, None)]
    assert resolution["final_action"] == "skip"
    assert resolution["error_type"] == "resolved"
    assert pipeline.recovery_plan() == []  # 已关闭，不再请求
