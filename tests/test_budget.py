"""NEXT-06：collect/resume 的统一请求预算、截止时间与停止报告。

覆盖与既有用例不重复的差异：robots/重定向每跳/重试共用请求计数、预算用尽不再发请求、
等待限速或 Retry-After 超过剩余时间即停、分页与附件停止后已归档数据保留、resume 停止报告。
使用本地回环夹具与可注入时钟，不依赖真实站点限流或真实等待。
"""

from datetime import datetime, timedelta, timezone

import pytest
import requests

from crawler.fetch.budget import (
    STOP_DEADLINE,
    STOP_RATE_LIMIT_WAIT,
    STOP_REQUEST_BUDGET,
    STOP_RETRY_AFTER_WAIT,
    BudgetConfigError,
    BudgetStop,
    RunBudget,
)
from crawler.fetch.http_client import FetchLimits, HttpClient
from crawler.output.failures_writer import FailureWriter
from crawler.output.jsonl import read_jsonl
from crawler.pipeline import CrawlPipeline

FIXED_NOW = datetime(2026, 9, 11, 10, 0, 0, tzinfo=timezone(timedelta(hours=8)))


def fast_limits(**overrides):
    values = {"request_rate_per_second": 1000, "max_retries": 0}
    values.update(overrides)
    return FetchLimits(**values)


class RecordingSession:
    """计数并记录实际发出的请求，用于证明预算用尽后不再发请求。"""

    def __init__(self, **kwargs):
        self.inner = requests.Session(**kwargs)
        self.headers = self.inner.headers
        self.calls = 0
        self.kwargs = []

    def get(self, url, **kwargs):
        self.calls += 1
        self.kwargs.append(kwargs)
        return self.inner.get(url, **kwargs)


def fake_clock():
    state = {"now": 0.0, "sleeps": []}

    def sleep(seconds):
        state["sleeps"].append(seconds)
        state["now"] += seconds

    def clock():
        return state["now"]

    return state, sleep, clock


@pytest.fixture()
def pipeline_factory(tmp_path, site_server):
    def make(registry, http):
        return CrawlPipeline(
            registry,
            tmp_path / "data",
            http=http,
            now=lambda: FIXED_NOW,
        )

    return make


# ---------- HTTP 客户端：统一计数与停止 ----------


def test_request_budget_counts_robots_redirect_hops_and_retries(mutable_site, registry_factory):
    """robots、重定向每跳与重试尝试都扣减同一预算，且预算耗尽后不再发送。

    用函数级夹具站点，避免瞬时失败端点的计数在会话内其他用例之间互相影响。
    """
    base_url, _root = mutable_site
    registry = registry_factory(base_url)
    session = RecordingSession()
    state, sleep, clock = fake_clock()
    budget = RunBudget(max_requests=5, clock=clock)
    client = HttpClient(
        registry,
        limits=fast_limits(max_retries=2),
        session=session,
        sleep=sleep,
        clock=clock,
        budget=budget,
    )

    client.get(f"{base_url}/_redirect?to=/detail_1.html")
    assert budget.used_requests == 3  # robots(1) + 重定向跳(1) + 目标(1)
    assert client.request_attempts == 3

    client.get(f"{base_url}/_flaky/1")
    assert budget.used_requests == 5  # robots 已缓存：500(1) + 成功(1)
    assert client.request_attempts == 5

    with pytest.raises(BudgetStop) as excinfo:
        client.get(f"{base_url}/detail_1.html")
    assert excinfo.value.reason == STOP_REQUEST_BUDGET
    assert session.calls == 5, "预算用尽后不得再发请求"
    assert client.request_attempts == 5
    assert state["sleeps"], "重试仍按既有退避执行（不缩短站点要求）"


def test_request_budget_exhaustion_blocks_send(site_server, registry_factory):
    registry = registry_factory(site_server)
    session = RecordingSession()
    budget = RunBudget(max_requests=2)
    client = HttpClient(
        registry, limits=fast_limits(), session=session, robots=False, budget=budget
    )
    client.get(f"{site_server}/detail_1.html")
    client.get(f"{site_server}/detail_2.html")
    with pytest.raises(BudgetStop) as excinfo:
        client.get(f"{site_server}/page2.html")
    assert excinfo.value.reason == STOP_REQUEST_BUDGET
    assert session.calls == 2 and budget.used_requests == 2


def test_redirect_hops_share_request_budget(site_server, registry_factory):
    registry = registry_factory(site_server)
    session = RecordingSession()
    budget = RunBudget(max_requests=1)
    client = HttpClient(
        registry, limits=fast_limits(), session=session, robots=False, budget=budget
    )
    with pytest.raises(BudgetStop) as excinfo:
        client.get(f"{site_server}/_redirect?to=/detail_1.html")
    assert excinfo.value.reason == STOP_REQUEST_BUDGET
    assert session.calls == 1 and client.request_attempts == 1


def test_retry_after_longer_than_remaining_stops_without_waiting(site_server, registry_factory):
    registry = registry_factory(site_server)
    state, sleep, clock = fake_clock()
    budget = RunBudget(max_requests=5, deadline_seconds=30, clock=clock)
    budget.start()
    state["now"] = 25.0  # 剩余 5s
    client = HttpClient(
        registry, limits=fast_limits(max_retries=1), sleep=sleep, clock=clock,
        robots=False, budget=budget,
    )
    with pytest.raises(BudgetStop) as excinfo:
        client.get(f"{site_server}/_retry_after/30")
    assert excinfo.value.reason == STOP_RETRY_AFTER_WAIT
    assert state["sleeps"] == [], "等待超出预算时不缩短站点要求的等待"
    assert budget.used_requests == 1


def test_rate_limit_wait_beyond_remaining_stops(site_server, registry_factory):
    registry = registry_factory(site_server)
    state, sleep, clock = fake_clock()
    budget = RunBudget(max_requests=5, deadline_seconds=30, clock=clock)
    budget.start()
    client = HttpClient(
        registry, limits=fast_limits(request_rate_per_second=0.01), sleep=sleep, clock=clock,
        robots=False, budget=budget,
    )
    client.get(f"{site_server}/detail_1.html")
    with pytest.raises(BudgetStop) as excinfo:
        client.get(f"{site_server}/detail_2.html")
    assert excinfo.value.reason == STOP_RATE_LIMIT_WAIT
    assert state["sleeps"] == [], "限速等待不算作已发送请求，也不缩短等待"
    assert budget.used_requests == 1, "未发出的请求退回配额"
    assert client.request_attempts == 1


def test_attempt_timeouts_are_clamped_to_remaining_time(site_server, registry_factory):
    registry = registry_factory(site_server)
    session = RecordingSession()
    state, sleep, clock = fake_clock()
    budget = RunBudget(max_requests=1, deadline_seconds=4, clock=clock)
    budget.start()
    client = HttpClient(
        registry,
        limits=fast_limits(connect_timeout_seconds=10, read_timeout_seconds=30),
        session=session,
        sleep=sleep,
        clock=clock,
        robots=False,
        budget=budget,
    )
    client.get(f"{site_server}/detail_1.html")
    assert session.kwargs[0]["timeout"] == (4.0, 4.0)


def test_streaming_download_stops_when_deadline_passes(mutable_site, registry_factory):
    """流式读取按块检查截止时间；停止后下载内容不进入原件库。"""
    base_url, root = mutable_site
    (root / "attachments" / "big.pdf").write_bytes(b"%PDF-1.4\n" + b"x" * (1024 * 1024))
    registry = registry_factory(base_url)
    state = {"now": 0.0}

    def clock():
        state["now"] += 1.0
        return state["now"]

    budget = RunBudget(max_requests=2, deadline_seconds=10, clock=clock)
    client = HttpClient(registry, limits=fast_limits(), robots=False, budget=budget)
    with pytest.raises(BudgetStop) as excinfo:
        client.get(f"{base_url}/attachments/big.pdf")
    assert excinfo.value.reason == STOP_DEADLINE
    assert "下载中" in str(excinfo.value), "截止时间在流式读取过程中生效"
    assert client.request_attempts == 1


def test_budget_rejects_non_positive_limits():
    with pytest.raises(BudgetConfigError):
        RunBudget(max_requests=0)
    with pytest.raises(BudgetConfigError):
        RunBudget(deadline_seconds=0)


# ---------- 管线：停止报告与已归档数据 ----------


def _http(registry, **budget_kwargs):
    budget = RunBudget(**budget_kwargs) if budget_kwargs else None
    client = HttpClient(registry, limits=fast_limits(), robots=False, budget=budget)
    return client, budget


def test_collect_budget_stop_keeps_archived_data(
    site_server, registry_factory, pipeline_factory, tmp_path
):
    """请求预算用尽：已归档原件/账本/文档保留，未处理目标可识别，且不记为网站失败。"""
    registry = registry_factory(site_server)
    http, budget = _http(registry, max_requests=3)
    pipeline = pipeline_factory(registry, http)
    report = pipeline.collect(
        "TESTSRC",
        entry_urls=[f"{site_server}/index.html"],
        include_attachments=False,
        budget=budget,
    )
    data = tmp_path / "data"
    assert report.stop_reason == STOP_REQUEST_BUDGET
    assert "请求上限" in report.stop_message
    assert budget.used_requests == 3
    assert report.counters.requests == 3
    assert report.unprocessed == 1
    assert report.counters.failures == 0
    assert read_jsonl(data / "manifests" / "failed_records.jsonl") == []

    rows = read_jsonl(data / "manifests" / "crawl_manifest.jsonl")
    assert len(rows) == 1, "停止前成功归档的原件保留，停止后不再下载"
    assert (data / rows[0]["raw_path"]).is_file()
    documents = read_jsonl(data / "normalized" / "documents.jsonl")
    assert [doc["doc_id"] for doc in documents] == [rows[0]["crawl_id"]]
    assert read_jsonl(data / "normalized" / "blocks.jsonl"), "已提交文档的块保留"

    metrics = report.metrics
    assert metrics["status"] == "partial"
    assert metrics["stop"]["reason"] == STOP_REQUEST_BUDGET
    assert metrics["stop"]["unprocessed"] == 1
    assert metrics["budget"]["used_requests"] == 3


def test_collect_budget_stop_during_attachments_keeps_parent_document(
    site_server, registry_factory, pipeline_factory, tmp_path
):
    """附件阶段停止：正文原件与文档先落盘（parse_status=partial），附件不记成网站失败。"""
    registry = registry_factory(site_server)
    http, budget = _http(registry, max_requests=3)
    pipeline = pipeline_factory(registry, http)
    report = pipeline.collect(
        "TESTSRC",
        entry_urls=[f"{site_server}/index.html"],
        include_attachments=True,
        budget=budget,
    )
    data = tmp_path / "data"
    assert report.stop_reason == STOP_REQUEST_BUDGET
    assert budget.used_requests == 3
    assert report.counters.failures == 0
    assert read_jsonl(data / "manifests" / "failed_records.jsonl") == []

    rows = read_jsonl(data / "manifests" / "crawl_manifest.jsonl")
    assert len(rows) == 1
    assert rows[0]["discovery_method"] == "list"
    documents = read_jsonl(data / "normalized" / "documents.jsonl")
    assert len(documents) == 1
    assert documents[0]["parse_status"] == "partial"
    assert (data / documents[0]["raw_path"]).is_file()
    assert documents[0].get("attachments") is None


def test_resume_budget_stop_reports_unprocessed_tasks(
    site_server, registry_factory, pipeline_factory, tmp_path
):
    """resume 与 collect 共用同一预算语义：恢复一项后预算用尽，其余任务记为未完成。"""
    registry = registry_factory(site_server)
    http, budget = _http(registry, max_requests=1)
    pipeline = pipeline_factory(registry, http)
    data = tmp_path / "data"
    writer = FailureWriter(data)
    for index in (1, 2):
        writer.record(
            source_id="TESTSRC",
            url=f"{site_server}/detail_{index}.html",
            time=FIXED_NOW.isoformat(),
            stage="fetch",
            error_type="http_error",
            message="HTTP 500",
            retry_count=0,
            final_action="retry_later",
        )

    report = pipeline.resume_failures("TESTSRC", budget=budget)
    assert report.stop_reason == STOP_REQUEST_BUDGET
    assert budget.used_requests == 1
    assert len(report.recovered) == 1
    assert report.unprocessed == 1
    assert report.counters.failures == 0
    assert report.metrics["stop"]["reason"] == STOP_REQUEST_BUDGET
    documents = read_jsonl(data / "normalized" / "documents.jsonl")
    assert len(documents) == 1, "已恢复文档保留，未被停止回滚"


# ---------- CLI：预算参数、停止输出与退出码 ----------


def _write_sources(path, base_url):
    import yaml
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
        "seed_terms": ["边界"],
        "request_rate_per_second": 1000,
        "max_retries": 0,
        "connect_timeout_seconds": 5,
        "read_timeout_seconds": 5,
    }
    path.write_text(
        yaml.safe_dump({"version": "tests", "sources": [entry]}, allow_unicode=True),
        encoding="utf-8",
    )
    return path


@pytest.fixture()
def cli_env(tmp_path, monkeypatch):
    data_dir = tmp_path / "cli-data"
    monkeypatch.setenv("CRAWL_ENV", "development")
    monkeypatch.setenv("CRAWL_DATA_DIR", str(data_dir))
    return data_dir


def test_cli_collect_budget_stop_exit_3(site_server, tmp_path, cli_env, capsys):
    """collect 达到请求预算：退出码 3，JSON 报告 stop 与预算用量，已归档成果保留。"""
    import json

    from crawler.cli import main

    config = _write_sources(tmp_path / "sources.yaml", site_server)
    code = main(
        [
            "collect",
            "--config",
            str(config),
            "--source",
            "TESTSRC",
            "--entry-url",
            f"{site_server}/index.html",
            "--no-attachments",
            "--max-requests",
            "2",
            "--deadline-seconds",
            "600",
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 3
    assert payload["ok"] is False
    assert payload["stop"]["reason"] == STOP_REQUEST_BUDGET
    assert payload["budget"]["max_requests"] == 2
    assert payload["budget"]["used_requests"] == 2
    assert payload["counters"]["requests"] == 2
    assert (cli_env / "logs" / "metrics.json").is_file()
    metrics = json.loads((cli_env / "logs" / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["stop"]["reason"] == STOP_REQUEST_BUDGET


def test_cli_resume_budget_stop_exit_3(site_server, tmp_path, cli_env, capsys):
    import json

    from crawler.cli import main

    config = _write_sources(tmp_path / "sources.yaml", site_server)
    writer = FailureWriter(cli_env)
    for index in (1, 2):
        writer.record(
            source_id="TESTSRC",
            url=f"{site_server}/detail_{index}.html",
            time=FIXED_NOW.isoformat(),
            stage="fetch",
            error_type="http_error",
            message="HTTP 500",
            retry_count=0,
            final_action="retry_later",
        )
    code = main(
        [
            "resume",
            "--config",
            str(config),
            "--source",
            "TESTSRC",
            "--max-requests",
            "2",
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 3
    assert payload["stop"]["reason"] == STOP_REQUEST_BUDGET
    assert payload["recovered"] == 1
    assert payload["stop"]["unprocessed"] == 1
    assert read_jsonl(cli_env / "normalized" / "documents.jsonl"), "已恢复文档保留"


def test_cli_budget_arguments_must_be_positive(site_server, tmp_path, cli_env, capsys):
    from crawler.cli import main

    config = _write_sources(tmp_path / "sources.yaml", site_server)
    base = ["collect", "--config", str(config), "--source", "TESTSRC", "--entry-url",
            f"{site_server}/index.html", "--no-attachments"]
    assert main(base + ["--max-requests", "0"]) == 2
    assert "请求上限必须为正整数" in capsys.readouterr().err
    assert main(base + ["--deadline-seconds", "0"]) == 2
    assert "截止时间必须为正数秒" in capsys.readouterr().err
    assert main(base + ["--deadline-seconds", "-1"]) == 2
