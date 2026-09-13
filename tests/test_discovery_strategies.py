"""按站发现策略抽象测试：状态区分与来源声明（T005/T026 新增）。"""

import yaml

from crawler.config.registry import SourceRegistry
from crawler.discover.discoverer import Discoverer
from crawler.discover.strategies import (
    STATUS_NOT_IMPLEMENTED,
    STATUS_OK,
    STATUS_SELECTOR_MISS,
    STATUS_ZERO_RESULTS,
    DiscoveryContext,
    DiscoveryRequest,
    ListDiscovery,
    SearchDiscovery,
    declared_stages,
    render_search_url,
    resolve_strategy,
)
from crawler.fetch.http_client import FetchLimits, HttpClient
from crawler.schedule.scope import RunScope

from datetime import date


def make_context(registry, source_id="TESTSRC", **kwargs):
    client = HttpClient(registry, limits=FetchLimits(request_rate_per_second=1000, max_retries=1))
    source = registry.get(source_id)
    discoverer = Discoverer(client, registry, source, max_items=50)
    return DiscoveryContext(
        source=source,
        registry=registry,
        http=client,
        discoverer=discoverer,
        max_items=50,
        **kwargs,
    )


def registry_with(tmp_path, base_url, **overrides) -> SourceRegistry:
    from urllib.parse import urlsplit

    host = urlsplit(base_url).hostname
    entry = {
        "source_id": "TESTSRC",
        "source_name": "本地夹具来源",
        "base_domain": host,
        "allowed_domains": [host],
        "enabled": True,
        "allowed_paths": [],
        "blocked_paths": [],
        "language": "zh",
        "search_url_template": f"{base_url}/search?q={{query}}",
        "request_rate_per_second": 1000,
        "max_retries": 1,
        "connect_timeout_seconds": 5,
        "read_timeout_seconds": 5,
    }
    entry.update(overrides)
    path = tmp_path / "sources.yaml"
    path.write_text(
        yaml.safe_dump({"version": "tests", "sources": [entry]}, allow_unicode=True),
        encoding="utf-8",
    )
    return SourceRegistry.load(path)


def test_declared_stages_follow_configuration(tmp_path, site_server):
    inferred = registry_with(tmp_path, site_server)
    assert declared_stages(inferred.get("TESTSRC")) == ("list", "search")
    explicit = registry_with(
        tmp_path, site_server, adapter={"discovery": ["list"]}
    )
    assert declared_stages(explicit.get("TESTSRC")) == ("list",)
    disabled = registry_with(tmp_path, site_server, adapter={"discovery": []})
    assert declared_stages(disabled.get("TESTSRC")) == ()


def test_undeclared_stage_is_not_implemented_without_requests(tmp_path, site_server):
    registry = registry_with(tmp_path, site_server, adapter={"discovery": ["list"]})
    context = make_context(registry)
    strategy = resolve_strategy(context.source, "sitemap")
    assert strategy.name == "unimplemented"
    result = strategy.discover(
        DiscoveryRequest(stage="sitemap", sitemap_url=f"{site_server}/sitemap.xml"),
        context,
    )
    assert result.status == STATUS_NOT_IMPLEMENTED
    assert result.targets == []
    assert context.http.request_attempts == 0


def test_explicit_cli_entry_runs_generic_strategy(tmp_path, site_server):
    registry = registry_with(tmp_path, site_server, adapter={"discovery": ["list"]})
    context = make_context(registry)
    strategy = resolve_strategy(context.source, "sitemap", explicit_entry=True)
    assert strategy.name == "sitemap"
    result = strategy.discover(
        DiscoveryRequest(stage="sitemap", sitemap_url=f"{site_server}/sitemap.xml"), context
    )
    assert result.status == STATUS_OK
    assert [target.url for target in result.targets] == [f"{site_server}/detail_2.html"]


def test_selector_miss_is_recorded_separately_from_zero_results(tmp_path, site_server):
    missed = registry_with(
        tmp_path, site_server, adapter={"list_link_selector": "div.absent"}
    )
    context = make_context(missed)
    result = ListDiscovery().discover(
        DiscoveryRequest(stage="list", entries=(f"{site_server}/adapter_index.html",)), context
    )
    assert result.status == STATUS_SELECTOR_MISS
    assert result.targets == []
    assert any("adapter_list_selector_miss" in item.reason for item in result.skipped)
    assert context.discoverer.selector_misses

    filtered = registry_with(
        tmp_path, site_server, adapter={"list_link_pattern": "^/never/"}
    )
    context = make_context(filtered, source_id="TESTSRC")
    result = ListDiscovery().discover(
        DiscoveryRequest(stage="list", entries=(f"{site_server}/index.html",)), context
    )
    assert result.status == STATUS_ZERO_RESULTS
    assert result.targets == []
    assert "真实零结果" in result.note


def test_list_without_entries_is_not_implemented(tmp_path, site_server):
    registry = registry_with(tmp_path, site_server, entry_urls=[])
    context = make_context(registry)
    result = ListDiscovery().discover(DiscoveryRequest(stage="list"), context)
    assert result.status == STATUS_NOT_IMPLEMENTED
    assert context.http.request_attempts == 0


def test_search_date_template_requires_scope_and_renders_range(tmp_path, site_server):
    registry = registry_with(
        tmp_path,
        site_server,
        search_url_template=f"{site_server}/search?q={{query}}&y={{year}}&m={{month}}&s={{start_date}}",
    )
    context = make_context(registry)
    request = DiscoveryRequest(stage="search", keyword="边界")
    result = SearchDiscovery().discover(request, context)
    assert result.status == STATUS_NOT_IMPLEMENTED
    assert "start-date" in result.note
    assert context.http.request_attempts == 0

    scoped = make_context(registry, scope=RunScope(start_date=date(2026, 9, 7)))
    result = SearchDiscovery().discover(request, scoped)
    assert result.status == STATUS_OK

    rendered = render_search_url(
        "https://x/search?q={query}&start={start_date}&y={year}&m={month}",
        "边界 合作",
        RunScope(start_date=date(2026, 9, 7)),
    )
    assert rendered == "https://x/search?q=%E8%BE%B9%E7%95%8C+%E5%90%88%E4%BD%9C&start=2026-09-07&y=2026&m=09"


def test_collect_records_discovery_statuses_in_metrics(tmp_path, site_server):
    from crawler.pipeline import CrawlPipeline

    registry = registry_with(tmp_path, site_server)
    client = HttpClient(registry, limits=FetchLimits(request_rate_per_second=1000, max_retries=1))
    pipeline = CrawlPipeline(registry, tmp_path / "data", http=client)
    report = pipeline.collect("TESTSRC", entry_urls=[f"{site_server}/index.html"])
    assert [row.status for row in report.discovery] == [STATUS_OK]
    assert report.metrics["discovery"][0]["status"] == STATUS_OK
    assert report.metrics["discovery"][0]["strategy"] == "list_pagination"

    empty = registry_with(tmp_path, site_server, adapter={"discovery": []})
    client = HttpClient(empty, limits=FetchLimits(request_rate_per_second=1000, max_retries=1))
    pipeline = CrawlPipeline(empty, tmp_path / "data-empty", http=client)
    report = pipeline.collect("TESTSRC")
    assert [row.status for row in report.discovery] == [STATUS_NOT_IMPLEMENTED]
    assert report.counters.documents == 0
    assert report.metrics["status"] == "empty"
    assert any("发现方式未实现" in note for note in report.metrics["notes"])


def test_explicit_entry_runs_generic_list_for_undeclared_source(tmp_path, site_server):
    """未声明 list 的来源在显式 --entry-url 下运行通用实现，并标明尚未计入已实现。"""
    registry = registry_with(tmp_path, site_server, adapter={"discovery": []})
    context = make_context(registry)
    strategy = resolve_strategy(context.source, "list", explicit_entry=True)
    assert strategy.name == "list_pagination"
    result = strategy.discover(
        DiscoveryRequest(stage="list", entries=(f"{site_server}/index.html",)), context
    )
    assert result.status == STATUS_OK
    assert result.targets
    assert context.http.request_attempts >= 1  # robots + 入口页（夹具另含分页请求）


def test_undeclared_list_without_explicit_entry_sends_no_requests(tmp_path, site_server):
    registry = registry_with(tmp_path, site_server, adapter={"discovery": []})
    context = make_context(registry)
    strategy = resolve_strategy(context.source, "list")
    assert strategy.name == "unimplemented"
    result = strategy.discover(DiscoveryRequest(stage="list"), context)
    assert result.status == STATUS_NOT_IMPLEMENTED
    assert context.http.request_attempts == 0
