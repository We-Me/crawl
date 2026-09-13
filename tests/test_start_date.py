"""运行时起始日期（--start-date）边界、记账与恢复测试。"""

import json
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlsplit

import pytest
import yaml

from crawler.cli import main
from crawler.fetch.http_client import FetchLimits, HttpClient
from crawler.output.jsonl import read_jsonl
from crawler.pipeline import CrawlPipeline
from crawler.schedule.scope import (
    BEFORE_START_DATE,
    DATE_UNKNOWN,
    IN_WINDOW,
    NO_SCOPE,
    RunScope,
    ScopeConfigError,
    parse_start_date,
)

NOW = datetime(2026, 9, 11, 10, 0, 0, tzinfo=timezone(timedelta(hours=8)))


def write_sources(path, base_url, **overrides):
    """写一份本地夹具来源配置；与 CLI 用例一致的字段集。"""
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
        "request_rate_per_second": 1000,
        "max_retries": 0,
        "connect_timeout_seconds": 5,
        "read_timeout_seconds": 5,
    }
    entry.update(overrides)
    path.write_text(
        yaml.safe_dump({"version": "tests", "sources": [entry]}, allow_unicode=True),
        encoding="utf-8",
    )
    return path


@pytest.fixture()
def cli_env(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    monkeypatch.setenv("CRAWL_ENV", "development")
    monkeypatch.setenv("CRAWL_DATA_DIR", str(data_dir))
    return data_dir


@pytest.fixture()
def pipeline_factory(tmp_path, site_server):
    def make(registry, **kwargs):
        http = HttpClient(
            registry, limits=FetchLimits(request_rate_per_second=1000, max_retries=2)
        )
        return CrawlPipeline(registry, tmp_path / "data", http=http, now=lambda: NOW, **kwargs)

    return make


def test_parse_start_date_validates_format():
    assert parse_start_date("2026-09-01") == date(2026, 9, 1)
    assert parse_start_date(None) is None
    with pytest.raises(ScopeConfigError):
        parse_start_date("2026/09/01")
    with pytest.raises(ScopeConfigError):
        parse_start_date("2026-09-31")


def test_decide_boundaries_are_inclusive_and_unknown_is_retained():
    scope = RunScope(start_date=date(2026, 9, 10))
    assert scope.decide("2026-09-10").kind == IN_WINDOW
    assert scope.decide("2026-09-11").kind == IN_WINDOW
    before = scope.decide("2026-09-09")
    assert before.kind == BEFORE_START_DATE and before.retained is False
    unknown = scope.decide(None)
    assert unknown.kind == DATE_UNKNOWN and unknown.retained is True
    assert scope.decide("2026-09").kind == DATE_UNKNOWN
    assert RunScope().decide("2026-09-01").kind == NO_SCOPE


def test_collect_keeps_raw_for_out_of_window_without_producing_document(
    site_server, registry_factory, pipeline_factory, tmp_path
):
    registry = registry_factory(site_server)
    pipeline = pipeline_factory(registry)
    report = pipeline.collect(
        "TESTSRC",
        entry_urls=[f"{site_server}/index.html"],
        scope=RunScope(start_date=date(2026, 9, 11)),
    )
    # detail_1 发布日期 2026-09-10 早于起始日：原件与账本保留，不产出文档。
    assert report.counters.out_of_window == 1
    assert report.counters.documents == 1
    assert any(item.reason == "before_start_date:2026-09-10" for item in report.skipped)
    manifest = read_jsonl(tmp_path / "data" / "manifests" / "crawl_manifest.jsonl")
    assert {row["final_url"] for row in manifest} == {
        f"{site_server}/detail_1.html",
        f"{site_server}/detail_2.html",
    }
    documents = read_jsonl(tmp_path / "data" / "normalized" / "documents.jsonl")
    assert [row["source_url"] for row in documents] == [f"{site_server}/detail_2.html"]
    decisions = {row["decision"] for row in report.date_decisions}
    assert decisions == {BEFORE_START_DATE, DATE_UNKNOWN}
    assert report.metrics["scope"]["start_date"] == "2026-09-11"
    assert report.metrics["counters"]["out_of_window"] == 1


def test_collect_start_date_is_inclusive(
    site_server, registry_factory, pipeline_factory
):
    registry = registry_factory(site_server)
    pipeline = pipeline_factory(registry)
    report = pipeline.collect(
        "TESTSRC",
        entry_urls=[f"{site_server}/index.html"],
        scope=RunScope(start_date=date(2026, 9, 10)),
    )
    assert report.counters.out_of_window == 0
    assert report.counters.documents == 2
    kinds = sorted(row["decision"] for row in report.date_decisions)
    assert kinds == [DATE_UNKNOWN, IN_WINDOW]


def test_collect_without_scope_keeps_previous_behavior(
    site_server, registry_factory, pipeline_factory
):
    registry = registry_factory(site_server)
    pipeline = pipeline_factory(registry)
    report = pipeline.collect("TESTSRC", entry_urls=[f"{site_server}/index.html"])
    assert report.counters.documents == 2
    assert report.counters.out_of_window == 0
    assert {row["decision"] for row in report.date_decisions} == {NO_SCOPE}
    assert report.metrics["scope"]["start_date"] is None


def test_resume_keeps_original_scope(
    site_server, registry_factory, pipeline_factory, tmp_path
):
    """原范围随失败记录保存：补抓沿用同一窗口，不把新窗口混入旧任务。"""
    bad_adapter = {
        "content_selector": "div.absent",
        "discovery": ["list"],
    }
    registry = registry_factory(site_server, adapter=bad_adapter)
    pipeline = pipeline_factory(registry)
    report = pipeline.collect(
        "TESTSRC",
        entry_urls=[f"{site_server}/index.html"],
        scope=RunScope(start_date=date(2026, 9, 11)),
    )
    assert report.counters.failures == 2  # detail_1 与 detail_2 的正文选择器未命中
    failures = read_jsonl(tmp_path / "data" / "manifests" / "failed_records.jsonl")
    assert {row["scope_start_date"] for row in failures} == {"2026-09-11"}

    plan = pipeline.recovery_plan()
    assert {task.scope_start_date for task in plan} == {"2026-09-11"}
    assert plan[0].as_row()["scope_start_date"] == "2026-09-11"

    fixed = registry_factory(site_server, adapter={"discovery": ["list"]})
    fixed_pipeline = pipeline_factory(fixed)
    recovered = fixed_pipeline.resume_failures("TESTSRC")
    # detail_1（2026-09-10）在原范围外：原件保留、不产出文档，关闭为跳过；
    # detail_2 无发布日期：保留候选（date_unknown），补出文档。
    assert recovered.counters.documents == 1
    assert len(recovered.skipped) == 1
    assert "原运行范围外" in recovered.skipped[0]["note"]
    documents = read_jsonl(tmp_path / "data" / "normalized" / "documents.jsonl")
    assert [row["source_url"] for row in documents] == [f"{site_server}/detail_2.html"]
    assert documents[0]["metadata_missing"] == ["publication_date"]


def test_cli_start_date_argument(site_server, cli_env, tmp_path, capsys):
    config = write_sources(tmp_path / "sources.yaml", site_server)
    code = main(
        [
            "collect",
            "--config",
            str(config),
            "--source",
            "TESTSRC",
            "--entry-url",
            f"{site_server}/index.html",
            "--start-date",
            "2026-09-11",
            "--json",
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["scope"]["start_date"] == "2026-09-11"
    assert payload["counters"]["out_of_window"] == 1
    assert payload["counters"]["documents"] == 1
    assert payload["date_decisions"]

    assert main(["collect", "--config", str(config), "--source", "TESTSRC", "--start-date", "11/09/2026"]) == 2
    assert "YYYY-MM-DD" in capsys.readouterr().err
