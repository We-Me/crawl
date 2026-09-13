"""T015：七类频率与触发、增量策略、条件请求与 304 行为。"""

from datetime import datetime, timedelta, timezone

import pytest
import yaml

from crawler.config.registry import SourceRegistry
from crawler.config.settings import ConfigurationError
from crawler.fetch.http_client import FetchLimits, HttpClient
from crawler.output.jsonl import read_jsonl
from crawler.pipeline import CrawlPipeline
from crawler.schedule import (
    CHECK_VERSION,
    CONDITIONAL,
    DISCOVER_NEW,
    FETCH_ALWAYS,
    IncrementalConfigError,
    IncrementalStateStore,
    ScheduleConfigError,
    effective_period_days,
    frequency_table,
    is_newer_publication,
    is_periodic_due,
    is_triggered,
    plan_incremental,
)

NOW = datetime(2026, 9, 11, 10, 0, 0, tzinfo=timezone(timedelta(hours=8)))


def test_frequency_table_matches_kr012():
    table = {row["key"]: row for row in frequency_table()}
    assert set(table) == {"A", "B", "C", "D", "E", "F", "G"}
    assert table["A"]["period_days"] == 7 and table["A"]["triggers"] == ["major_document"]
    assert table["B"]["period_days"] == 1
    assert table["C"]["period_days"] == 7 and table["C"]["triggers"] == ["new_law"]
    assert table["D"]["period_days"] == 1 and table["D"]["triggers"] == ["historical_backfill"]
    assert table["E"]["period_days"] == 30
    assert table["F"]["period_days"] == 90 and table["F"]["triggers"] == ["boundary_change"]
    assert table["G"]["period_days"] is None and table["G"]["sync_with"] == ["A", "B", "C", "F"]
    assert all(row["evidence"].startswith("S2 §12") for row in table.values())


def test_period_due_and_trigger_rules():
    assert is_periodic_due("A", last_success_at=NOW - timedelta(days=8), now=NOW) is True
    assert is_periodic_due("A", last_success_at=NOW - timedelta(days=3), now=NOW) is False
    assert is_periodic_due("B", last_success_at=None, now=NOW) is True
    assert effective_period_days("G", sync_periods={"A": 7, "B": 1, "C": 7, "F": 90}) == 1
    assert is_periodic_due("G", last_success_at=NOW - timedelta(days=2), now=NOW, sync_periods={"A": 7}) is False
    assert effective_period_days("G") is None
    assert is_periodic_due("G", last_success_at=NOW, now=NOW) is None  # 无配置不猜测
    assert is_triggered("C", "new_law") is True
    assert is_triggered("B", "new_law") is False
    with pytest.raises(ScheduleConfigError):
        is_triggered("B", "unknown_event")
    with pytest.raises(ScheduleConfigError):
        is_periodic_due("A", last_success_at=None, now=NOW, period_days=0)


def test_incremental_plan_per_resource_kind():
    store_url = "https://example.invalid/list"
    from crawler.schedule import ResourceState

    state = ResourceState(
        url=store_url,
        etag='"abc"',
        last_modified="Fri, 11 Sep 2026 00:00:00 GMT",
        crawl_id="SRC_20260910_0001",
    )
    news = plan_incremental("news", state, now=NOW)
    assert news.action == DISCOVER_NEW and news.headers["If-None-Match"] == '"abc"'
    law = plan_incremental("law", state, now=NOW)
    assert law.action == CONDITIONAL and law.headers["If-Modified-Since"].startswith("Fri")
    assert plan_incremental("law", None, now=NOW).action == FETCH_ALWAYS
    stats = plan_incremental("statistics", state, now=NOW)
    assert stats.action == CHECK_VERSION
    assert plan_incremental(None, None, now=NOW).action == FETCH_ALWAYS
    with pytest.raises(IncrementalConfigError):
        plan_incremental("unknown-kind", None, now=NOW)
    assert is_newer_publication("2026-09-11", "2026-09-10") is True
    assert is_newer_publication("2026-09-09", "2026-09-10") is False
    assert is_newer_publication(None, "2026-09-10") is True


def test_state_store_records_success_and_not_modified(tmp_path):
    store = IncrementalStateStore(tmp_path)
    url = "https://example.invalid/detail"
    store.record_success(
        url,
        now=NOW,
        etag='"v1"',
        last_modified="Fri, 11 Sep 2026 00:00:00 GMT",
        sha256="a" * 64,
        crawl_id="SRC_20260911_0001",
        publication_date="2026-09-10",
    )
    state = store.get(url)
    assert state.etag == '"v1"' and state.crawl_id == "SRC_20260911_0001"
    updated = store.record_not_modified(url, now=NOW + timedelta(days=1), previous_crawl_id=state.crawl_id)
    assert updated.last_result == "not_modified"
    assert updated.not_modified_crawl_id == "SRC_20260911_0001"
    assert updated.etag == '"v1"'  # 校验信息保留
    assert (tmp_path / "manifests" / "incremental_state.json").is_file()


def _registry_with_update_policy(tmp_path, base_url, **policy):
    entry = {
        "source_id": "TESTSRC",
        "source_name": "本地夹具来源",
        "base_domain": "127.0.0.1",
        "allowed_domains": ["127.0.0.1"],
        "enabled": True,
        "allowed_paths": [],
        "blocked_paths": [],
        "language": "zh",
        "seed_terms": ["边界"],
        "request_rate_per_second": 1000,
        "resource_kind": "law",
        "update_policy": {"key": "C", "period_days": 7, "triggers": ["new_law"]},
    }
    entry["update_policy"].update(policy)
    path = tmp_path / "sources.yaml"
    path.write_text(
        yaml.safe_dump({"version": "tests", "sources": [entry]}, allow_unicode=True),
        encoding="utf-8",
    )
    return SourceRegistry.load(path)


def test_registry_parses_update_policy(tmp_path):
    base_url = "http://127.0.0.1:1"
    registry = _registry_with_update_policy(tmp_path, base_url)
    source = registry.get("TESTSRC")
    assert source.resource_kind == "law"
    assert source.update_policy_key == "C"
    assert source.update_period_days == 7
    assert source.update_triggers == ("new_law",)

    with pytest.raises(ConfigurationError, match="类别"):
        _registry_with_update_policy(tmp_path, base_url, key="Z")
    with pytest.raises(ConfigurationError, match="triggers"):
        _registry_with_update_policy(tmp_path, base_url, triggers=["unknown"])
    with pytest.raises(ConfigurationError, match="period_days"):
        _registry_with_update_policy(tmp_path, base_url, period_days=0)


def test_pipeline_304_reuses_previous_without_new_documents(
    site_server, tmp_path, monkeypatch
):
    registry = _registry_with_update_policy(tmp_path, site_server)
    pipeline = CrawlPipeline(
        registry,
        tmp_path / "data",
        http=HttpClient(registry, limits=FetchLimits(request_rate_per_second=1000)),
        now=lambda: NOW,
    )
    url = f"{site_server}/_etag/index.html"
    first = pipeline.collect(
        "TESTSRC", entry_urls=[url], include_attachments=False, max_items=10
    )
    assert first.counters.documents == 2 and first.counters.not_modified == 0
    data = tmp_path / "data"
    manifest_after_first = read_jsonl(data / "manifests" / "crawl_manifest.jsonl")
    documents_after_first = read_jsonl(data / "normalized" / "documents.jsonl")
    raw_after_first = sorted((data / "raw").rglob("*"))
    documents_by_url = {row["source_url"]: row["doc_id"] for row in documents_after_first}

    # 第二轮：两个目标重新被发现 → 条件请求 → 304，不产生新文档；发现页按 S5-01 另行归档
    second = pipeline.collect(
        "TESTSRC", entry_urls=[url], include_attachments=False, max_items=10
    )
    assert second.counters.documents == 0
    assert second.counters.not_modified == 2
    assert second.counters.resources == 2  # 两个发现页的成功响应仍会归档
    assert any("304" in item.reason for item in second.skipped)
    manifest_after_second = read_jsonl(data / "manifests" / "crawl_manifest.jsonl")
    assert manifest_after_second[: len(manifest_after_first)] == manifest_after_first
    new_rows = manifest_after_second[len(manifest_after_first):]
    assert len(new_rows) == 2
    assert all("/discovery/" in row["raw_path"] for row in new_rows)
    assert read_jsonl(data / "normalized" / "documents.jsonl") == documents_after_first
    assert sorted((data / "raw").rglob("*")) == raw_after_first

    states = IncrementalStateStore(data).load()
    assert len(states) == 2  # 只有详情目标被记录，发现页不产生文档状态
    assert {state.last_result for state in states.values()} == {"not_modified"}
    checked = {state.url: state for state in states.values()}
    for detail in (f"{site_server}/_etag/detail_1.html", f"{site_server}/_etag/detail_2.html"):
        assert checked[detail].not_modified_crawl_id == documents_by_url[detail]


def test_conditional_headers_are_sent(fake_time, site_server, tmp_path):
    registry = _registry_with_update_policy(tmp_path, site_server)
    state = {"seen": []}

    class RecordingSession:
        headers = {}

        def get(self, url, headers=None, **kwargs):
            state["seen"].append(dict(headers or {}))
            raise AssertionError("不需要真实请求：仅检查条件头")

    # 本用例只验证条件请求头透传；关闭 robots 以免先取 robots.txt 干扰记录。
    client = HttpClient(
        registry, limits=FetchLimits(request_rate_per_second=1000), robots=False
    )
    client.session = RecordingSession()
    with pytest.raises(AssertionError):
        client.get(
            f"{site_server}/_etag/detail_1.html",
            source_id="TESTSRC",
            conditional={"If-None-Match": '"x"'},
        )
    assert state["seen"][0]["If-None-Match"] == '"x"'
