"""T005 发现策略测试（本地夹具站点）。"""

from pathlib import Path

import pytest

from crawler.discover.discoverer import Discoverer
from crawler.fetch.http_client import FetchError, FetchLimits, HttpClient


def make_discoverer(registry, source_id="TESTSRC", **kwargs):
    client = HttpClient(registry, limits=FetchLimits(request_rate_per_second=1000, max_retries=1))
    return Discoverer(client, registry, registry.get(source_id), **kwargs)


def test_list_discovery_follows_pagination(site_server, registry_factory):
    registry = registry_factory(site_server)
    discoverer = make_discoverer(registry)
    targets = discoverer.discover_list([f"{site_server}/index.html"])
    urls = [target.url for target in targets]
    assert urls == [f"{site_server}/detail_1.html", f"{site_server}/detail_2.html"]
    assert all(target.discovery_method == "list" for target in targets)
    assert targets[0].referrer_url == f"{site_server}/index.html"
    assert targets[0].title_hint == "虚构公告：试验合作安排"
    assert targets[1].referrer_url == f"{site_server}/page2.html"


def test_list_discovery_skips_out_of_boundary_links(site_server, registry_factory):
    registry = registry_factory(site_server)
    discoverer = make_discoverer(registry)
    discoverer.discover_list([f"{site_server}/index.html"])
    skipped = {item.url: item.reason for item in discoverer.skipped}
    assert "https://outside.invalid/secret" in skipped
    assert skipped["https://outside.invalid/secret"] == "domain_not_allowed:outside.invalid"


def test_attachments_are_discovered_separately(site_server, registry_factory):
    registry = registry_factory(site_server)
    discoverer = make_discoverer(registry)
    content = (Path("tests/fixtures/site/detail_1.html")).read_bytes()
    targets = discoverer.attachments_from_html(content, f"{site_server}/detail_1.html")
    assert [target.url for target in targets] == [
        f"{site_server}/attachments/notice.csv",
        f"{site_server}/attachments/unavailable.pdf",
    ]
    assert all(target.discovery_method == "attachment" for target in targets)
    assert targets[0].referrer_url == f"{site_server}/detail_1.html"
    assert targets[0].title_hint == "附件下载：notice.csv"


def test_search_discovery_records_keyword(site_server, registry_factory):
    registry = registry_factory(site_server)
    discoverer = make_discoverer(registry)
    targets = discoverer.discover_search("边界")
    assert [target.url for target in targets] == [f"{site_server}/detail_2.html"]
    assert targets[0].discovery_method == "search"
    assert targets[0].keyword == "边界"
    assert "边界" in targets[0].title_hint


def test_sitemap_and_api_discovery(site_server, registry_factory):
    registry = registry_factory(site_server)
    discoverer = make_discoverer(registry)
    sitemap = discoverer.discover_sitemap(f"{site_server}/sitemap.xml")
    assert [target.url for target in sitemap] == [f"{site_server}/detail_2.html"]
    assert sitemap[0].discovery_method == "sitemap"
    api = discoverer.discover_api(f"{site_server}/api.json")
    assert [target.url for target in api] == [f"{site_server}/detail_1.html"]
    assert api[0].discovery_method == "api"
    assert api[0].title_hint == "虚构公告：试验合作安排"


def test_entry_failure_propagates(site_server, registry_factory):
    registry = registry_factory(site_server)
    discoverer = make_discoverer(registry)
    with pytest.raises(FetchError):
        discoverer.discover_list([f"{site_server}/missing-list.html"])


def test_discovery_requires_entries(site_server, registry_factory):
    registry = registry_factory(site_server)
    discoverer = make_discoverer(registry)
    with pytest.raises(ValueError, match="entry_urls"):
        discoverer.discover_list([])
    no_search = make_discoverer(registry_factory(site_server, search_url_template=None))
    with pytest.raises(ValueError, match="search_url_template"):
        no_search.discover_search("x")


# ---------- T026 逐来源适配规则（列表选择器 / 分页终止条件） ----------


def test_adapter_list_selector_narrows_to_document_links(site_server, registry_factory):
    registry = registry_factory(
        site_server,
        adapter={"list_link_selector": "ul li a", "list_link_pattern": r"detail_\d+\.html$"},
    )
    discoverer = make_discoverer(registry)
    targets = discoverer.discover_list([f"{site_server}/index.html"])
    assert [target.url for target in targets] == [
        f"{site_server}/detail_1.html",
        f"{site_server}/detail_2.html",
    ]


def test_adapter_list_selector_miss_is_recorded_not_fallen_back(site_server, registry_factory):
    registry = registry_factory(site_server, adapter={"list_link_selector": "div.not-here a"})
    discoverer = make_discoverer(registry)
    targets = discoverer.discover_list([f"{site_server}/index.html"])
    assert targets == []
    assert discoverer.skipped[0].url == f"{site_server}/index.html"
    assert discoverer.skipped[0].reason == "adapter_list_selector_miss:div.not-here a"


def test_adapter_max_pages_is_pagination_stop_condition(site_server, registry_factory):
    registry = registry_factory(
        site_server,
        adapter={"list_link_selector": "ul li a", "max_pages": 1},
    )
    discoverer = make_discoverer(registry)
    targets = discoverer.discover_list([f"{site_server}/index.html"])
    assert [target.url for target in targets] == [f"{site_server}/detail_1.html"]


def test_adapter_pagination_selector_stops_when_absent(site_server, registry_factory):
    registry = registry_factory(
        site_server,
        adapter={"list_link_selector": "ul li a", "pagination_selector": "a.next-page"},
    )
    discoverer = make_discoverer(registry)
    targets = discoverer.discover_list([f"{site_server}/index.html"])
    assert [target.url for target in targets] == [f"{site_server}/detail_1.html"]

    explicit = registry_factory(
        site_server,
        adapter={"list_link_selector": "ul li a", "pagination_selector": "link[rel=next]"},
    )
    explicit_targets = make_discoverer(explicit).discover_list([f"{site_server}/index.html"])
    assert [target.url for target in explicit_targets] == [
        f"{site_server}/detail_1.html",
        f"{site_server}/detail_2.html",
    ]
