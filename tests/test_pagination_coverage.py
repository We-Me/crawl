"""S5-03：列表/查询分页的终止原因、失败留痕与跨轮续接。

覆盖：后续页请求失败→partial（不冒充零结果）且失败入失败账；循环分页；页数上限截断；
搜索日期查询边界；接口声明的下一页。发现游标记录未翻到的页，下一轮从该页继续。
"""

from datetime import date, datetime, timedelta, timezone

from crawler.fetch.http_client import FetchLimits, HttpClient
from crawler.output.jsonl import read_jsonl
from crawler.pipeline import CrawlPipeline
from crawler.schedule.cursor import DiscoveryCursorStore
from crawler.schedule.scope import RunScope

FIXED_NOW = datetime(2026, 9, 13, 10, 0, 0, tzinfo=timezone(timedelta(hours=8)))


def make_pipeline(registry, tmp_path):
    http = HttpClient(
        registry, limits=FetchLimits(request_rate_per_second=1000, max_retries=0)
    )
    return CrawlPipeline(registry, tmp_path / "data", http=http, now=lambda: FIXED_NOW)


def list_stop(report):
    return next(row for row in report.coverage["discovery"]["stops"] if row["stage"] == "list")


def test_pagination_failure_is_partial_and_resumes_from_failed_page(
    mutable_site, registry_factory, tmp_path
):
    # 用函数级夹具站点：瞬时失败端点的计数不与其他会用到 /_flaky/1 的用例共享。
    site_server, _root = mutable_site
    registry = registry_factory(site_server)
    pipeline = make_pipeline(registry, tmp_path)
    entry = f"{site_server}/flaky_paged.html"
    first = pipeline.collect("TESTSRC", entry_urls=[entry], include_attachments=False)

    result = next(item for item in first.discovery if item.stage == "list")
    assert result.status == "partial", "后续页失败不能当作正常结束或零结果"
    assert result.complete is False
    stop = list_stop(first)
    assert stop["stop"] == "request_failed" and stop["complete"] is False
    assert stop["reason"] == "后续页请求失败"
    assert stop["next_url"] == f"{site_server}/_flaky/1"
    assert first.counters.documents == 1, "失败前已发现的目标照常采集"
    assert first.counters.failures == 1
    failures = read_jsonl(tmp_path / "data" / "manifests" / "failed_records.jsonl")
    assert failures[0]["url"] == f"{site_server}/_flaky/1"
    assert failures[0]["stage"] == "fetch"

    cursors = DiscoveryCursorStore(tmp_path / "data").load()
    cursor = next(iter(cursors.values()))
    assert cursor.state == "active" and cursor.next_url == f"{site_server}/_flaky/1"

    rows_before = read_jsonl(tmp_path / "data" / "manifests" / "crawl_manifest.jsonl")
    second = pipeline.collect("TESTSRC", entry_urls=[entry], include_attachments=False)
    assert list_stop(second)["stop"] == "end_of_pages"
    assert list_stop(second)["complete"] is True
    rows_after = read_jsonl(tmp_path / "data" / "manifests" / "crawl_manifest.jsonl")
    new_rows = rows_after[len(rows_before):]
    assert any(row["final_url"] == f"{site_server}/_flaky/1" for row in new_rows)
    assert not any(row["final_url"] == entry for row in new_rows), "第二轮不再从入口重来"
    assert DiscoveryCursorStore(tmp_path / "data").load()[cursor.key].state == "completed"


def test_pagination_loop_is_detected_and_stops(site_server, registry_factory, tmp_path):
    registry = registry_factory(site_server)
    pipeline = make_pipeline(registry, tmp_path)
    report = pipeline.collect(
        "TESTSRC", entry_urls=[f"{site_server}/loop_a.html"], include_attachments=False
    )
    stop = list_stop(report)
    assert stop["stop"] == "loop_detected" and stop["complete"] is False
    assert stop["pages"] == 2
    rows = [
        row
        for row in read_jsonl(tmp_path / "data" / "manifests" / "crawl_manifest.jsonl")
        if "/discovery/" in row["raw_path"]
    ]
    assert {row["final_url"].rsplit("/", 1)[-1] for row in rows} == {
        "loop_a.html",
        "loop_b.html",
    }
    cursors = DiscoveryCursorStore(tmp_path / "data").load()
    assert all(cursor.state == "completed" for cursor in cursors.values())


def test_max_pages_marks_truncation_and_next_run_continues(
    site_server, registry_factory, tmp_path
):
    registry = registry_factory(
        site_server, adapter={"max_pages": 1, "discovery": ["list"]}
    )
    pipeline = make_pipeline(registry, tmp_path)
    entry = f"{site_server}/index.html"
    first = pipeline.collect("TESTSRC", entry_urls=[entry], include_attachments=False)
    stop = list_stop(first)
    assert stop["stop"] == "max_pages_reached" and stop["complete"] is False
    assert stop["next_url"] == f"{site_server}/page2.html"
    assert first.counters.documents == 1

    second = pipeline.collect("TESTSRC", entry_urls=[entry], include_attachments=False)
    assert list_stop(second)["complete"] is True
    assert second.counters.documents == 1
    documents = read_jsonl(tmp_path / "data" / "normalized" / "documents.jsonl")
    assert documents[-1]["source_url"] == f"{site_server}/detail_2.html"
    # 截断轮的运行状态与说明不冒充完成（S5-06 覆盖口径）
    assert first.metrics["status"] == "partial"
    assert any("发现遍历未完成" in note for note in first.metrics["notes"])
    assert second.metrics["status"] == "ok"


def test_discover_only_traverses_pages_and_enqueues_without_processing(
    site_server, registry_factory, tmp_path
):
    """S5-03：只遍历发现入口（翻页覆盖）时不消耗正文预算，目标入队待后续处理。"""
    registry = registry_factory(site_server, adapter={"max_pages": 1, "discovery": ["list"]})
    pipeline = make_pipeline(registry, tmp_path)
    entry = f"{site_server}/index.html"
    report = pipeline.collect(
        "TESTSRC",
        entry_urls=[entry],
        include_attachments=False,
        discover_only=True,
        max_pages=2,
    )

    assert report.coverage["processing"]["mode"] == "discovery_only"
    assert report.counters.documents == 0 and report.counters.blocks == 0
    stop = list_stop(report)
    assert stop["complete"] is True, "覆盖为 2 页时应遍历到站点末页"
    from crawler.schedule.pending import PendingStore

    items = PendingStore(tmp_path / "data").candidates("TESTSRC")
    assert {item.url for item in items} == {
        f"{site_server}/detail_1.html",
        f"{site_server}/detail_2.html",
    }
    raw_kinds = {
        path.parent.name
        for path in (tmp_path / "data" / "raw" / "TESTSRC").rglob("*")
        if path.is_file()
    }
    assert raw_kinds == {"discovery"}, "只遍历发现时不请求详情页"

    # 续接：下一轮普通运行按队列处理，遍历与处理分离
    second = pipeline.collect("TESTSRC", entry_urls=[entry], include_attachments=False)
    assert second.counters.documents == 2


def test_search_date_scoped_query_is_recorded(site_server, registry_factory, tmp_path):
    registry = registry_factory(
        site_server,
        search_url_template=f"{site_server}/search?q={{query}}&from={{start_date}}&to={{end_date}}",
    )
    pipeline = make_pipeline(registry, tmp_path)
    report = pipeline.collect(
        "TESTSRC",
        entry_urls=[],
        search_keywords=["边界"],
        include_attachments=False,
        scope=RunScope(start_date=date(2026, 9, 11)),
    )
    stop = next(
        row for row in report.coverage["discovery"]["stops"] if row["stage"] == "search"
    )
    assert stop["stop"] == "date_scoped_query"
    assert stop["complete"] is True
    assert "日期限定" in (stop["detail"] or "")
    assert report.coverage["discovery"]["complete"] is True


def test_api_follows_declared_next_page(site_server, registry_factory, tmp_path):
    registry = registry_factory(site_server, adapter={"discovery": ["api"]})
    pipeline = make_pipeline(registry, tmp_path)
    report = pipeline.collect(
        "TESTSRC",
        api_urls=[f"{site_server}/api_paged_1.json"],
        include_attachments=False,
    )
    stop = next(
        row for row in report.coverage["discovery"]["stops"] if row["stage"] == "api"
    )
    assert stop["stop"] == "end_of_pages" and stop["complete"] is True
    assert stop["pages"] == 2
    rows = [
        row
        for row in read_jsonl(tmp_path / "data" / "manifests" / "crawl_manifest.jsonl")
        if "/discovery/" in row["raw_path"]
    ]
    assert {row["final_url"].rsplit("/", 1)[-1] for row in rows} == {
        "api_paged_1.json",
        "api_paged_2.json",
    }
    assert report.counters.documents == 2


def test_body_pagination_follows_adapter_selector(site_server, registry_factory, tmp_path):
    """S5-03：正文分页按适配选择器跟随（省略号 rel=next 误报不生效），后续页正常归档合并。"""
    from crawler.output.layout import DeliveryLayout

    registry = registry_factory(
        site_server,
        adapter={
            "pagination_selector": "ul.pagination li.PagedList-skipToNext.page-item a.page-link"
        },
    )
    pipeline = make_pipeline(registry, tmp_path)
    report = pipeline.collect(
        "TESTSRC", entry_urls=[f"{site_server}/body_adapter_index.html"], include_attachments=False
    )
    layout = DeliveryLayout(tmp_path / "data")
    documents = read_jsonl(layout.documents_path)
    document = next(row for row in documents if "适配规则正文第一部分" in row["full_text"])
    text = document["full_text"]
    assert text.index("适配规则正文第一部分") < text.index("适配规则正文第二部分")
    assert document["parse_status"] == "ok"
    pagination_rows = [
        row
        for row in read_jsonl(layout.manifest_path)
        if row["discovery_method"] == "pagination"
    ]
    assert [row["final_url"] for row in pagination_rows] == [
        f"{site_server}/body_adapter_paged_2.html"
    ]
    assert report.counters.failures == 0


def test_search_cursor_is_per_keyword(site_server, registry_factory, tmp_path):
    """S5-06：搜索游标按渲染后的检索 URL 归属；一个关键词截断不把另一关键词从半途开始。"""
    registry = registry_factory(
        site_server,
        search_url_template=f"{site_server}/search_paged?q={{query}}",
        adapter={"max_pages": 1, "discovery": ["search"]},
    )
    pipeline = make_pipeline(registry, tmp_path)
    first = pipeline.collect(
        "TESTSRC", entry_urls=[], search_keywords=["边界"], include_attachments=False
    )
    stop = next(
        row for row in first.coverage["discovery"]["stops"] if row["stage"] == "search"
    )
    assert stop["stop"] == "max_pages_reached" and stop["complete"] is False
    assert "q=%E8%BE%B9%E7%95%8C" in stop["next_url"]

    layout = tmp_path / "data" / "manifests" / "crawl_manifest.jsonl"
    before = len(read_jsonl(layout))
    second = pipeline.collect(
        "TESTSRC", entry_urls=[], search_keywords=["口岸"], include_attachments=False
    )
    stop2 = next(
        row for row in second.coverage["discovery"]["stops"] if row["stage"] == "search"
    )
    assert "q=%E5%8F%A3%E5%B2%B8" in stop2["next_url"], "第二个关键词必须从自己的第 1 页开始"
    assert "page=2" in stop2["next_url"]
    rows = read_jsonl(layout)[before:]
    discovery_rows = [row for row in rows if "/discovery/" in row["raw_path"]]
    assert {row["final_url"] for row in discovery_rows} == {
        f"{site_server}/search_paged?q=%E5%8F%A3%E5%B2%B8"
    }


def test_scope_fallback_is_reported_in_discovery_note(site_server, registry_factory, tmp_path):
    """S5-03：整文档兜底在发现结果 note 中显式记录（CN-04 双 <html> 形态），不是静默回退。"""
    registry = registry_factory(site_server, adapter={"discovery": ["list"]})
    pipeline = make_pipeline(registry, tmp_path)
    report = pipeline.collect(
        "TESTSRC", entry_urls=[f"{site_server}/double_html_list.html"], include_attachments=False
    )
    result = next(row for row in report.discovery if row.stage == "list")
    assert result.status == "ok"
    assert "整文档兜底" in (result.note or "")
    rows = [
        row
        for row in read_jsonl(tmp_path / "data" / "manifests" / "crawl_manifest.jsonl")
        if "/discovery/" in row["raw_path"]
    ]
    assert any(row["final_url"].endswith("double_html_list.html") for row in rows)


def test_completed_entry_recheck_advances_across_runs(site_server, registry_factory, tmp_path):
    """R1：已完成入口不再停在入口页；复查轮按页数边界推进并跨轮覆盖整入口。"""
    registry = registry_factory(site_server, adapter={"max_pages": 1, "discovery": ["list"]})
    pipeline = make_pipeline(registry, tmp_path)
    entry = f"{site_server}/index.html"
    manifest = tmp_path / "data" / "manifests" / "crawl_manifest.jsonl"
    first = pipeline.collect(
        "TESTSRC", entry_urls=[entry], include_attachments=False, max_pages=5
    )
    assert first.counters.documents == 2
    cursor = next(iter(DiscoveryCursorStore(tmp_path / "data").load().values()))
    assert cursor.state == "completed"
    assert cursor.coverage_rounds == 1 and cursor.pass_pages == 0

    # 第二轮：从入口开始新一轮复查，页数边界内只覆盖第 1 页；未完成是显式停止原因
    before = len(read_jsonl(manifest))
    second = pipeline.collect("TESTSRC", entry_urls=[entry], include_attachments=False)
    stop = list_stop(second)
    assert stop["stop"] == "max_pages_reached" and stop["complete"] is False
    assert stop["round_pages"] == 1 and stop["coverage_rounds"] == 1
    assert stop["next_url"] == f"{site_server}/page2.html"
    assert second.coverage["queue"]["refreshed"] == 1, "已登记目标进入复查（refresh）而非跳过"
    rows = read_jsonl(manifest)[before:]
    discovery_rows = [row for row in rows if "/discovery/" in row["raw_path"]]
    assert [row["final_url"] for row in discovery_rows] == [entry]
    cursor = DiscoveryCursorStore(tmp_path / "data").load()[cursor.key]
    assert cursor.state == "active" and cursor.next_url == f"{site_server}/page2.html"
    assert cursor.pass_pages == 1 and cursor.coverage_rounds == 1

    # 第三轮：从续接页覆盖到终点，覆盖轮 +1；下一轮重新从入口开始
    third = pipeline.collect("TESTSRC", entry_urls=[entry], include_attachments=False)
    stop = list_stop(third)
    assert stop["stop"] == "end_of_pages" and stop["complete"] is True
    assert stop["pages"] == 1 and stop["coverage_rounds"] == 2
    cursor = DiscoveryCursorStore(tmp_path / "data").load()[cursor.key]
    assert cursor.state == "completed" and cursor.coverage_rounds == 2 and cursor.pass_pages == 0


def test_recheck_uses_new_links_and_refresh_as_separate_states(
    mutable_site, registry_factory, tmp_path
):
    """R1：入口页 URL 未变不停止；新链接入队与已登记目标复查是两条独立状态。"""
    site_server, root = mutable_site
    registry = registry_factory(site_server, adapter={"max_pages": 2, "discovery": ["list"]})
    pipeline = make_pipeline(registry, tmp_path)
    listing = (
        '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
        "<title>虚构栏目{page}</title></head><body><main><ul>{items}</ul>"
        "{next_link}</main></body></html>"
    )
    (root / "hc_p1.html").write_text(
        listing.format(
            page="第 1 页",
            items='<li><a href="detail_1.html">公告一</a></li>',
            next_link='<a rel="next" href="hc_p2.html">下一页</a>',
        ),
        encoding="utf-8",
    )
    (root / "hc_p2.html").write_text(
        listing.format(
            page="第 2 页",
            items='<li><a href="detail_2.html">公告二</a></li>',
            next_link='<a rel="next" href="hc_p3.html">下一页</a>',
        ),
        encoding="utf-8",
    )
    (root / "hc_p3.html").write_text(
        listing.format(
            page="第 3 页",
            items='<li><a href="detail_paged_3.html">公告三</a></li>',
            next_link="",
        ),
        encoding="utf-8",
    )
    entry = f"{site_server}/hc_p1.html"
    first = pipeline.collect(
        "TESTSRC", entry_urls=[entry], include_attachments=False, max_pages=5
    )
    assert first.counters.documents == 3
    cursor = next(iter(DiscoveryCursorStore(tmp_path / "data").load().values()))
    assert cursor.state == "completed" and cursor.pages_fetched == 3

    # 站点在入口前插入新条目：第 1 页有新目标；第 2 页整体为已登记目标
    (root / "hc_p1.html").write_text(
        listing.format(
            page="第 1 页",
            items=(
                '<li><a href="detail_adapter.html">公告零（新）</a></li>'
                '<li><a href="detail_1.html">公告一</a></li>'
            ),
            next_link='<a rel="next" href="hc_p2.html">下一页</a>',
        ),
        encoding="utf-8",
    )
    (root / "hc_p2.html").write_text(
        listing.format(
            page="第 2 页",
            items=(
                '<li><a href="detail_2.html">公告二</a></li>'
                '<li><a href="detail_paged_2.html">公告二·补录（新）</a></li>'
            ),
            next_link='<a rel="next" href="hc_p3.html">下一页</a>',
        ),
        encoding="utf-8",
    )

    second = pipeline.collect("TESTSRC", entry_urls=[entry], include_attachments=False)
    stop = list_stop(second)
    assert stop["stop"] == "max_pages_reached" and stop["complete"] is False
    assert stop["pages"] == 2, "第 1 页无新链接也要继续核对第 2 页"
    assert second.coverage["queue"]["added"] == 2, "第 1、2 页的新链接都入队"
    assert second.coverage["queue"]["refreshed"] == 2, "已登记目标进入复查"
    documents = read_jsonl(tmp_path / "data" / "normalized" / "documents.jsonl")
    urls = {row["source_url"] for row in documents}
    assert f"{site_server}/detail_adapter.html" in urls
    assert f"{site_server}/detail_paged_2.html" in urls
    assert second.counters.not_modified == 2, "未变化的已登记目标按条件请求复查（304 复用原件）"
    assert second.counters.documents == 2, "复查为 304 的目标不重复产出文档；只有两个新目标落文档"

    third = pipeline.collect("TESTSRC", entry_urls=[entry], include_attachments=False)
    stop = list_stop(third)
    assert stop["stop"] == "end_of_pages" and stop["complete"] is True
    assert stop["coverage_rounds"] == 2, "续接页覆盖到终点后完成一轮复查"
    refreshed = DiscoveryCursorStore(tmp_path / "data").load()[cursor.key]
    assert refreshed.state == "completed" and refreshed.pass_pages == 0


def test_completed_search_recheck_advances_and_refreshes(
    site_server, registry_factory, tmp_path
):
    """R1：检索入口同样按覆盖轮推进；已登记结果复查而非整入口停在第一页。"""
    registry = registry_factory(
        site_server,
        search_url_template=f"{site_server}/search_paged?q={{query}}",
        adapter={"max_pages": 1, "discovery": ["search"]},
    )
    pipeline = make_pipeline(registry, tmp_path)
    first = pipeline.collect("TESTSRC", search_keywords=["边界"], include_attachments=False, max_pages=5)
    assert first.counters.documents == 2
    cursor = next(iter(DiscoveryCursorStore(tmp_path / "data").load().values()))
    assert cursor.state == "completed" and cursor.coverage_rounds == 1

    second = pipeline.collect("TESTSRC", search_keywords=["边界"], include_attachments=False)
    stop = next(
        row for row in second.coverage["discovery"]["stops"] if row["stage"] == "search"
    )
    assert stop["stop"] == "max_pages_reached" and stop["complete"] is False
    assert stop["round_pages"] == 1
    assert second.coverage["queue"] == {"added": 0, "refreshed": 1, "unchanged": 0}
    cursor = DiscoveryCursorStore(tmp_path / "data").load()[cursor.key]
    assert cursor.state == "active" and "page=2" in cursor.next_url

    third = pipeline.collect("TESTSRC", search_keywords=["边界"], include_attachments=False)
    stop = next(
        row for row in third.coverage["discovery"]["stops"] if row["stage"] == "search"
    )
    assert stop["stop"] == "end_of_pages" and stop["complete"] is True
    assert stop["coverage_rounds"] == 2
    cursor = DiscoveryCursorStore(tmp_path / "data").load()[cursor.key]
    assert cursor.state == "completed" and cursor.pass_pages == 0
