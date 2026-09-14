"""R4：发现目标先持久化入队，再推进游标；故障注入后重启不漏目标。"""

from datetime import datetime, timedelta, timezone

import pytest

from crawler.fetch.http_client import FetchLimits, HttpClient
from crawler.output.jsonl import read_jsonl
from crawler.pipeline import CrawlPipeline
from crawler.schedule.cursor import DiscoveryCursorStore

FIXED_NOW = datetime(2026, 9, 14, 10, 0, 0, tzinfo=timezone(timedelta(hours=8)))

LISTING = (
    "<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
    "<title>虚构列表 {page}</title></head><body><main><h1>列表 {page}</h1>"
    "<ul>{items}</ul>{next_link}</main></body></html>"
)


def _write_pages(root, pages=3, prefix="cm_p"):
    """写一个三页列表入口：每页一个不同目标，最后一页无下一页。"""
    for number in range(1, pages + 1):
        target = f"commit_target_{number}.html"
        (root / target).write_text(
            "<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
            f"<title>虚构公告 {number}</title></head><body><main><h1>公告 {number}</h1>"
            "<p>虚构正文，用于 R4 提交顺序用例。</p></main></body></html>",
            encoding="utf-8",
        )
        next_link = (
            f'<a rel="next" href="{prefix}{number + 1}.html">下一页</a>'
            if number < pages
            else ""
        )
        (root / f"{prefix}{number}.html").write_text(
            LISTING.format(
                page=f"第 {number} 页",
                items=f'<li><a href="{target}">公告 {number}</a></li>',
                next_link=next_link,
            ),
            encoding="utf-8",
        )
    return f"{prefix}1.html"


def _target_url(site_server, number):
    return f"{site_server}/commit_target_{number}.html"


def _pipeline(registry, tmp_path):
    http = HttpClient(registry, limits=FetchLimits(request_rate_per_second=1000))
    return CrawlPipeline(registry, tmp_path / "data", http=http, now=lambda: FIXED_NOW)


def _stops(report):
    return report.coverage["discovery"]["stops"]


def _pending_urls(pipeline):
    return {item.url for item in pipeline.pending.all_items()}


def test_page_targets_are_committed_before_cursor_advances(
    mutable_site, registry_factory, tmp_path
):
    """正常路径：页级提交成功后才写游标；完成后游标停在终点并带提交标记。"""
    site_server, root = mutable_site
    registry = registry_factory(site_server)
    pipeline = _pipeline(registry, tmp_path)
    entry = f"{site_server}/{_write_pages(root)}"

    report = pipeline.collect("TESTSRC", entry_urls=[entry], include_attachments=False)

    assert _stops(report)[0]["stop"] == "end_of_pages"
    cursor = next(iter(DiscoveryCursorStore(tmp_path / "data").load().values()))
    assert cursor.state == "completed" and cursor.next_url is None
    assert cursor.pages_fetched == 3
    assert cursor.last_commit_page == f"{site_server}/cm_p3.html"
    assert cursor.last_commit_digest
    urls = _pending_urls(pipeline)
    assert urls == {_target_url(site_server, number) for number in (1, 2, 3)}


def test_commit_failure_leaves_cursor_on_page_and_rerun_recovers(
    mutable_site, registry_factory, tmp_path, monkeypatch
):
    """入队前故障：游标不推进到下一页，重启后重新发现并补齐目标。"""
    site_server, root = mutable_site
    registry = registry_factory(site_server)
    pipeline = _pipeline(registry, tmp_path)
    entry = f"{site_server}/{_write_pages(root)}"

    original = pipeline.pending.enqueue_targets
    calls = {"count": 0}

    def flaky_enqueue(**kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise OSError("注入的队列写入失败")
        return original(**kwargs)

    monkeypatch.setattr(pipeline.pending, "enqueue_targets", flaky_enqueue)
    first = pipeline.collect("TESTSRC", entry_urls=[entry], include_attachments=False)

    stop = _stops(first)[0]
    assert stop["stop"] == "commit_failed" and stop["complete"] is False
    assert _pending_urls(pipeline) == set(), "失败页的目标未入队，不能假装已提交"
    cursor = next(iter(DiscoveryCursorStore(tmp_path / "data").load().values()))
    assert cursor.state == "active"
    assert cursor.next_url == f"{site_server}/cm_p1.html", "游标停在未提交的页"

    monkeypatch.setattr(pipeline.pending, "enqueue_targets", original)
    second = pipeline.collect("TESTSRC", entry_urls=[entry], include_attachments=False)

    assert _stops(second)[0]["stop"] == "end_of_pages"
    assert _pending_urls(pipeline) == {_target_url(site_server, number) for number in (1, 2, 3)}
    refreshed = DiscoveryCursorStore(tmp_path / "data").load()[cursor.key]
    assert refreshed.state == "completed" and refreshed.pages_fetched == 3


def test_targets_committed_when_cursor_save_fails_then_replay_is_idempotent(
    mutable_site, registry_factory, tmp_path, monkeypatch
):
    """入队后游标前故障：目标已在队列；重启重放本页不把 processed 转成 refresh。"""
    site_server, root = mutable_site
    registry = registry_factory(site_server)
    pipeline = _pipeline(registry, tmp_path)
    entry = f"{site_server}/{_write_pages(root)}"

    store = DiscoveryCursorStore(tmp_path / "data")
    original_save = store.save
    calls = {"count": 0}

    def flaky_save(cursor):
        calls["count"] += 1
        if calls["count"] == 1:
            raise OSError("注入的游标写入失败")
        return original_save(cursor)

    monkeypatch.setattr(pipeline.cursors, "save", flaky_save)
    first = pipeline.collect("TESTSRC", entry_urls=[entry], include_attachments=False)

    stop = _stops(first)[0]
    assert stop["stop"] == "cursor_save_failed" and stop["complete"] is False
    assert _pending_urls(pipeline) == {_target_url(site_server, 1)}, "第一页目标已提交"
    cursor = DiscoveryCursorStore(tmp_path / "data").load()[
        next(iter(DiscoveryCursorStore(tmp_path / "data").load()))
    ]
    assert cursor.state == "active" and cursor.next_url == f"{site_server}/cm_p1.html"
    assert cursor.last_commit_page == f"{site_server}/cm_p1.html"

    # 模拟目标已处理：重放本页必须保持 processed，不能整页转 refresh。
    item = pipeline.pending.all_items()[0]
    pipeline.pending.mark(item.key, state="processed", attempted_at=FIXED_NOW.isoformat())

    monkeypatch.setattr(pipeline.cursors, "save", original_save)
    second = pipeline.collect("TESTSRC", entry_urls=[entry], include_attachments=False)

    assert _stops(second)[0]["stop"] == "end_of_pages"
    updated = next(row for row in pipeline.pending.all_items() if row.key == item.key)
    assert updated.state == "processed", "重放不得把已处理目标转成 refresh"
    assert second.coverage["queue"]["refreshed"] == 0
    finished = DiscoveryCursorStore(tmp_path / "data").load()[cursor.key]
    assert finished.state == "completed" and finished.pages_fetched == 3


def test_cursor_saved_before_crash_resumes_at_next_page(
    mutable_site, registry_factory, tmp_path
):
    """游标保存后故障：重启从下一页继续，不重取已提交页。"""
    site_server, root = mutable_site
    registry = registry_factory(site_server)
    pipeline = _pipeline(registry, tmp_path)
    entry = f"{site_server}/{_write_pages(root)}"

    first = pipeline.collect(
        "TESTSRC", entry_urls=[entry], include_attachments=False, max_pages=1
    )
    assert _stops(first)[0]["stop"] == "max_pages_reached"
    cursor = next(iter(DiscoveryCursorStore(tmp_path / "data").load().values()))
    assert cursor.state == "active" and cursor.next_url == f"{site_server}/cm_p2.html"

    before = read_jsonl(tmp_path / "data" / "manifests" / "crawl_manifest.jsonl")
    second = pipeline.collect("TESTSRC", entry_urls=[entry], include_attachments=False)

    assert _stops(second)[0]["stop"] == "end_of_pages"
    after = read_jsonl(tmp_path / "data" / "manifests" / "crawl_manifest.jsonl")
    new_rows = after[len(before):]
    fetched = [row["requested_url"] for row in new_rows if "/discovery/" in row["raw_path"]]
    assert fetched == [f"{site_server}/cm_p2.html", f"{site_server}/cm_p3.html"]
    assert f"{site_server}/cm_p1.html" not in fetched, "已提交页不重取"


def test_api_page_targets_are_committed_before_cursor_advances(
    site_server, registry_factory, tmp_path, monkeypatch
):
    """发现 API：页级提交同样先于游标推进，失败时保留已提交页。"""
    registry = registry_factory(site_server)
    pipeline = _pipeline(registry, tmp_path)
    api_url = f"{site_server}/api_paged_1.json"

    original = pipeline.pending.enqueue_targets
    calls = {"count": 0}

    def flaky_enqueue(**kwargs):
        calls["count"] += 1
        if calls["count"] == 2:
            raise OSError("注入的队列写入失败（第二页）")
        return original(**kwargs)

    monkeypatch.setattr(pipeline.pending, "enqueue_targets", flaky_enqueue)
    first = pipeline.collect("TESTSRC", api_urls=[api_url], include_attachments=False)

    stop = _stops(first)[0]
    assert stop["stop"] == "commit_failed" and stop["complete"] is False
    assert stop["next_url"] == f"{site_server}/api_paged_2.json"
    cursor = next(iter(DiscoveryCursorStore(tmp_path / "data").load().values()))
    assert cursor.state == "active" and cursor.next_url == f"{site_server}/api_paged_2.json"
    committed = _pending_urls(pipeline)
    assert committed, "第一页 API 目标已提交"
    assert f"{site_server}/detail_2.html" not in committed, "失败页目标未入队"


def test_later_strategy_failure_keeps_earlier_targets(
    site_server, registry_factory, tmp_path
):
    """后续策略失败不清空先前策略已提交的目标。"""
    registry = registry_factory(site_server)
    pipeline = _pipeline(registry, tmp_path)
    entry = f"{site_server}/index.html"

    report = pipeline.collect(
        "TESTSRC",
        entry_urls=[entry],
        sitemap_urls=[f"{site_server}/bad_sitemap.xml"],
        include_attachments=False,
    )

    sitemap = [row.as_row() for row in report.discovery if row.stage == "sitemap"]
    assert sitemap and sitemap[0]["status"] == "parse_error"
    assert report.counters.failures >= 1
    pending = _pending_urls(pipeline)
    assert f"{site_server}/detail_1.html" in pending, "先前策略的目标必须保留"
    assert report.coverage["queue"]["added"] >= 1


def test_entry_run_lock_blocks_concurrent_old_progress(
    mutable_site, registry_factory, tmp_path
):
    """入口级运行锁：另一个运行持有锁时本轮不读取、不推进游标（旧进度不覆盖）。"""
    site_server, root = mutable_site
    registry = registry_factory(site_server)
    pipeline = _pipeline(registry, tmp_path)
    entry = f"{site_server}/{_write_pages(root)}"

    from crawler.output.atomic import file_lock
    from crawler.schedule.cursor import cursor_key

    store = DiscoveryCursorStore(tmp_path / "data")
    key = cursor_key(source_id="TESTSRC", stage="list", entry=entry, scope_start_date=None)
    with file_lock(store.entry_lock_path(key), blocking=False):
        report = pipeline.collect("TESTSRC", entry_urls=[entry], include_attachments=False)

    stop = _stops(report)[0]
    assert stop["stop"] == "entry_busy" and stop["complete"] is False
    assert report.coverage["queue"]["added"] == 0
    assert DiscoveryCursorStore(tmp_path / "data").load() == {}, "并发占用时不写游标"
