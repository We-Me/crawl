"""R1：已知 URL 不等于内容未变或窗口没有新增（发现覆盖与更新复查分开）。

覆盖：入口页全为已登记目标但后续页有新增；同 URL 内容变化按复查更新；置顶/中插/
后部补录不丢；跨请求预算分轮推进覆盖整入口；本轮范围与停止原因入报告；队列为空
不足以使 discovery_complete 为真；历史 incremental_head_checked 标记失效并留来源。
"""

from datetime import datetime, timedelta, timezone

from crawler.fetch.budget import RunBudget
from crawler.fetch.http_client import FetchLimits, HttpClient
from crawler.output.jsonl import read_jsonl
from crawler.pipeline import CrawlPipeline
from crawler.schedule.cursor import CURSOR_COMPLETED, DiscoveryCursor, DiscoveryCursorStore

FIXED_NOW = datetime(2026, 9, 14, 10, 0, 0, tzinfo=timezone(timedelta(hours=8)))
LIMITS = FetchLimits(request_rate_per_second=1000, max_retries=0)


def _listing(title, items, next_href=None):
    links = "".join(f'<li><a href="{href}">{text}</a></li>' for href, text in items)
    nxt = f'<a rel="next" href="{next_href}">下一页</a>' if next_href else ""
    return (
        '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
        f"<title>{title}</title></head><body><main><h1>{title}</h1>"
        f"<ul>{links}</ul>{nxt}</main></body></html>"
    )


def _write_list_site(root):
    (root / "lp1.html").write_text(
        _listing("虚构栏目第 1 页", [("detail_1.html", "公告一")], "lp2.html"),
        encoding="utf-8",
    )
    (root / "lp2.html").write_text(
        _listing("虚构栏目第 2 页", [("detail_2.html", "公告二")], "lp3.html"),
        encoding="utf-8",
    )
    (root / "lp3.html").write_text(
        _listing("虚构栏目第 3 页", [("detail_adapter.html", "公告三")]),
        encoding="utf-8",
    )


def make_pipeline(registry, tmp_path, budget=None):
    http = HttpClient(registry, limits=LIMITS, robots=False, budget=budget)
    return CrawlPipeline(registry, tmp_path / "data", http=http, now=lambda: FIXED_NOW)


def list_stop(report):
    return next(row for row in report.coverage["discovery"]["stops"] if row["stage"] == "list")


def test_first_page_all_known_but_second_page_has_new_target(
    mutable_site, registry_factory, tmp_path
):
    """缺陷复现：入口页 URL 全未变时仍必须向后核对，发现后部新增。"""
    base_url, root = mutable_site
    _write_list_site(root)
    registry = registry_factory(base_url)
    entry = f"{base_url}/lp1.html"
    data = tmp_path / "data"

    first = make_pipeline(registry, tmp_path).collect(
        "TESTSRC", entry_urls=[entry], include_attachments=False, max_pages=5
    )
    assert first.counters.documents == 3
    assert list_stop(first)["complete"] is True

    # 第 1 页原样（全为已登记目标），第 2 页中插一条新公告
    (root / "lp2.html").write_text(
        _listing(
            "虚构栏目第 2 页",
            [("detail_2.html", "公告二"), ("detail_paged_2.html", "公告二·补录（新）")],
            "lp3.html",
        ),
        encoding="utf-8",
    )
    second = make_pipeline(registry, tmp_path).collect(
        "TESTSRC", entry_urls=[entry], include_attachments=False, max_pages=5
    )
    stop = list_stop(second)
    assert stop["stop"] == "end_of_pages" and stop["complete"] is True
    assert stop["pages"] == 3, "第 1 页无新链接也要核对到第 2 页及之后"
    assert second.coverage["queue"]["added"] == 1
    documents = read_jsonl(data / "normalized" / "documents.jsonl")
    assert f"{base_url}/detail_paged_2.html" in {row["source_url"] for row in documents}
    assert trace_refs(data)


def test_same_url_content_change_is_rechecked_and_versioned(
    mutable_site, registry_factory, tmp_path
):
    """同 URL 正文变化：已登记目标按复查更新，旧文档保留、不重复提交未变内容。"""
    base_url, root = mutable_site
    _write_list_site(root)
    registry = registry_factory(base_url)
    entry = f"{base_url}/lp1.html"
    data = tmp_path / "data"

    make_pipeline(registry, tmp_path).collect(
        "TESTSRC", entry_urls=[entry], include_attachments=False, max_pages=5
    )
    first_doc = next(
        row
        for row in read_jsonl(data / "normalized" / "documents.jsonl")
        if row["source_url"].endswith("detail_1.html")
    )
    assert "更新后的补充段落" not in first_doc["full_text"]

    changed = (
        '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
        "<title>虚构公告：试验合作安排</title></head><body><main>"
        "<h1>虚构公告：试验合作安排</h1><p>第一版正文。</p>"
        "<p>更新后的补充段落：合作范围扩大。</p></main></body></html>"
    )
    (root / "detail_1.html").write_text(changed, encoding="utf-8")

    second = make_pipeline(registry, tmp_path).collect(
        "TESTSRC", entry_urls=[entry], include_attachments=False, max_pages=5
    )
    stop = list_stop(second)
    assert stop["stop"] == "end_of_pages" and stop["complete"] is True
    assert second.coverage["queue"]["refreshed"] >= 1, "已登记目标进入更新复查"
    documents = read_jsonl(data / "normalized" / "documents.jsonl")
    latest = next(row for row in reversed(documents) if row["source_url"].endswith("detail_1.html"))
    assert "更新后的补充段落" in latest["full_text"]
    assert latest["doc_id"] != first_doc["doc_id"], "复查更新是追加新版本，不覆盖旧文档"
    assert sum(1 for row in documents if row["source_url"].endswith("detail_1.html")) == 2
    assert trace_refs(data)


def test_late_target_is_found_when_pass_reaches_last_page(
    mutable_site, registry_factory, tmp_path
):
    """后部补录：末页新目标在覆盖轮推进到该页时被发现，不因前页未变而丢失。"""
    base_url, root = mutable_site
    _write_list_site(root)
    registry = registry_factory(base_url, adapter={"max_pages": 1, "discovery": ["list"]})
    entry = f"{base_url}/lp1.html"
    data = tmp_path / "data"

    pipeline = make_pipeline(registry, tmp_path)
    first = pipeline.collect("TESTSRC", entry_urls=[entry], include_attachments=False)
    assert first.counters.documents == 1, "每轮页数上限 1：首轮只覆盖第 1 页"
    stop = list_stop(first)
    assert stop["stop"] == "max_pages_reached" and stop["complete"] is False
    assert stop["round_pages"] == 1 and stop["next_url"].endswith("lp2.html")
    assert first.unprocessed == 0, "队列可以为空"
    assert first.coverage["discovery"]["complete"] is False, "队列空不能推出遍历完成"

    pipeline.collect("TESTSRC", entry_urls=[entry], include_attachments=False)

    # 第 3 页插入新目标；前两页均未变化
    (root / "lp3.html").write_text(
        _listing(
            "虚构栏目第 3 页",
            [("detail_adapter.html", "公告三"), ("detail_paged_3.html", "公告三·补录（新）")],
        ),
        encoding="utf-8",
    )
    third = pipeline.collect("TESTSRC", entry_urls=[entry], include_attachments=False)
    stop = list_stop(third)
    assert stop["stop"] == "end_of_pages" and stop["complete"] is True
    assert stop["coverage_rounds"] == 1, "跨三轮续接完成首个覆盖轮"
    assert stop["round_pages"] == 3, "轮内覆盖页数跨预算轮次累计（1+1+1）"
    assert third.coverage["queue"]["added"] == 2, "末页原有目标首次入队 + 后部补录的新目标"
    documents = read_jsonl(data / "normalized" / "documents.jsonl")
    assert f"{base_url}/detail_paged_3.html" in {row["source_url"] for row in documents}
    assert trace_refs(data)


def test_coverage_advances_across_budget_stops(mutable_site, registry_factory, tmp_path):
    """无变化来源跨请求预算推进：预算停止保存续接位置，下一轮从该页继续。"""
    base_url, root = mutable_site
    _write_list_site(root)
    registry = registry_factory(base_url)
    entry = f"{base_url}/lp1.html"
    data = tmp_path / "data"

    pipeline = make_pipeline(registry, tmp_path)
    first = pipeline.collect(
        "TESTSRC", entry_urls=[entry], include_attachments=False, budget=RunBudget(max_requests=2)
    )
    assert first.stop_reason == "request_budget"
    stop = list_stop(first)
    assert stop["stop"] == "budget_stop" and stop["complete"] is False
    assert stop["next_url"].endswith("lp3.html"), "已覆盖页由游标记录，下一轮从这里继续"
    assert first.counters.documents == 0

    second = make_pipeline(registry, tmp_path).collect(
        "TESTSRC", entry_urls=[entry], include_attachments=False, budget=RunBudget(max_requests=20)
    )
    stop = list_stop(second)
    assert stop["stop"] == "end_of_pages" and stop["complete"] is True
    assert stop["pages"] == 1 and stop["coverage_rounds"] == 1
    assert stop["round_pages"] == 3, "预算停止前覆盖的两页计入同一覆盖轮"
    documents = read_jsonl(data / "normalized" / "documents.jsonl")
    assert second.counters.documents == 3
    assert {row["source_url"].rsplit("/", 1)[-1] for row in documents} == {
        "detail_1.html",
        "detail_2.html",
        "detail_adapter.html",
    }
    assert trace_refs(data)


def test_legacy_head_check_marker_is_invalidated_and_recorded(
    mutable_site, registry_factory, tmp_path
):
    """旧 incremental_head_checked 完成标记不再断言完成，按新语义重新遍历并记来源。"""
    base_url, root = mutable_site
    _write_list_site(root)
    registry = registry_factory(base_url, adapter={"max_pages": 1, "discovery": ["list"]})
    entry = f"{base_url}/lp1.html"
    data = tmp_path / "data"
    key = f"TESTSRC|list|-|{entry}"
    (data / "manifests").mkdir(parents=True, exist_ok=True)
    store = DiscoveryCursorStore(data)
    store.save(
        DiscoveryCursor(
            key=key,
            source_id="TESTSRC",
            stage="list",
            entry=entry,
            state=CURSOR_COMPLETED,
            pages_fetched=433,
            targets_found=433,
            note="incremental_head_checked: 已完成遍历的增量核对",
        )
    )

    pipeline = make_pipeline(registry, tmp_path)
    report = pipeline.collect("TESTSRC", entry_urls=[entry], include_attachments=False)
    stop = list_stop(report)
    assert stop["stop"] == "max_pages_reached" and stop["complete"] is False, (
        "旧标记不使本轮自动成为完成：本轮只覆盖第 1 页"
    )
    cursor = DiscoveryCursorStore(data).load()[key]
    assert "历史快检标记已按 R1 失效" in (cursor.note or "")
    assert cursor.state == "active" and cursor.next_url.endswith("lp2.html")


def trace_refs(data):
    from crawler.validate.traceability import trace_delivery

    return trace_delivery(data).ok
