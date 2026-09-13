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


def test_adapter_attachment_pattern_narrows_attachments(site_server, registry_factory):
    """T026：附件规则按来源登记（如 IN-02 只取条约 PDF，不取页面站点级 footer PDF）。"""
    registry = registry_factory(site_server, adapter={"attachment_pattern": r"notice\.csv$"})
    discoverer = make_discoverer(registry)
    content = Path("tests/fixtures/site/detail_1.html").read_bytes()
    targets = discoverer.attachments_from_html(content, f"{site_server}/detail_1.html")
    assert [target.url for target in targets] == [f"{site_server}/attachments/notice.csv"]


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


def test_adapter_list_link_rewrite_maps_to_equivalent_form(site_server, registry_factory):
    """T026：来源登记的等价形态改写（如 IN-06 详情壳页 → 站点自身 reader 页）。"""
    registry = registry_factory(
        site_server,
        adapter={
            "list_link_pattern": r"detail_1\.html$",
            "list_link_rewrite": [[r"detail_1\.html$", "reader_1.html"]],
        },
    )
    discoverer = make_discoverer(registry)
    targets = discoverer.discover_list([f"{site_server}/index.html"])
    assert [target.url for target in targets] == [f"{site_server}/reader_1.html"]


def test_adapter_list_link_rewrite_still_subject_to_boundary(site_server, registry_factory):
    registry = registry_factory(
        site_server,
        adapter={
            "list_link_pattern": r"detail_1\.html$",
            # 跨域等价形态：正则需匹配完整 URL（含来源），替换结果再进入边界判定
            "list_link_rewrite": [[r"^https?://[^/]+/detail_1\.html$", "https://outside.invalid/reader.html"]],
        },
    )
    discoverer = make_discoverer(registry)
    targets = discoverer.discover_list([f"{site_server}/index.html"])
    assert targets == []
    skipped = {item.url: item.reason for item in discoverer.skipped}
    assert skipped["https://outside.invalid/reader.html"] == "domain_not_allowed:outside.invalid"


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


def test_adapter_pagination_selector_avoids_ellipsis_rel_next_trap(site_server, registry_factory):
    """S5-03：省略号（…）也带 rel=next 时，只跟随适配选择器指定的“›”下一页（IN-02 真实形态）。"""
    registry = registry_factory(
        site_server,
        adapter={
            "list_link_selector": "ul.doc-list a",
            "pagination_selector": "ul.pagination li.PagedList-skipToNext.page-item a.page-link",
        },
    )
    discoverer = make_discoverer(registry)
    targets = discoverer.discover_list([f"{site_server}/adapter_paged_1.html"])
    assert [target.url for target in targets] == [
        f"{site_server}/detail_1.html",
        f"{site_server}/detail_2.html",
        f"{site_server}/detail_3.html",
    ]
    stop = discoverer.stops[-1]
    assert stop.stop == "pagination_control_missing" and stop.complete is True
    assert stop.pages == 2


def test_adapter_positional_pagination_selector_and_self_pointer_end(site_server, registry_factory):
    """S5-03：CN-02 形态 `.page` 第 3 项为“下一页”；末页自指链接按终点处理。"""
    registry = registry_factory(
        site_server,
        adapter={
            "list_link_selector": "ul.doc-list a",
            "pagination_selector": ".page li:nth-child(3) a",
        },
    )
    discoverer = make_discoverer(registry)
    targets = discoverer.discover_list([f"{site_server}/paged_positional_1.html"])
    assert [target.url for target in targets] == [
        f"{site_server}/detail_1.html",
        f"{site_server}/detail_2.html",
    ]
    stop = discoverer.stops[-1]
    assert stop.stop == "pagination_control_missing" and stop.complete is True
    assert stop.pages == 2


def test_adapter_pagination_merge_entry_params(site_server, registry_factory):
    """S5-03：控件省略入口参数（IN-02 形态）时按入口 URL 派生下一页；未开启则跟随空壳链接。"""
    entry = f"{site_server}/merge_paged?page=1&size=10"
    adapter = {
        "list_link_selector": "ul.doc-list a",
        "pagination_selector": "ul.pagination li.PagedList-skipToNext.page-item a.page-link",
        "max_pages": 2,
    }
    merged_registry = registry_factory(
        site_server, adapter={**adapter, "pagination_merge_entry_params": True}
    )
    discoverer = make_discoverer(merged_registry)
    targets = discoverer.discover_list([entry])
    assert [target.url for target in targets] == [
        f"{site_server}/detail_1.html",
        f"{site_server}/detail_2.html",
    ]
    stop = discoverer.stops[-1]
    assert stop.stop == "max_pages_reached" and stop.complete is False
    assert stop.next_url == f"{site_server}/merge_paged?page=3&size=10", "路径与入口参数沿用入口"

    plain_registry = registry_factory(site_server, adapter=dict(adapter))
    plain_targets = make_discoverer(plain_registry).discover_list([entry])
    assert [target.url for target in plain_targets] == [f"{site_server}/detail_1.html"]


def test_generic_scope_falls_back_to_whole_document(site_server, registry_factory):
    """S5-03：通用范围取不到目标而文档整体有链接（结构不完整）时按整文档兜底，不冒充零结果。"""
    registry = registry_factory(site_server, adapter={"discovery": ["list"]})
    discoverer = make_discoverer(registry)
    targets = discoverer.discover_list([f"{site_server}/double_html_list.html"])
    assert [target.url for target in targets] == [f"{site_server}/detail_1.html"]
    assert discoverer.scope_fallbacks == [
        {
            "url": f"{site_server}/double_html_list.html",
            "method": "list",
            "scope": "main",
        }
    ]
