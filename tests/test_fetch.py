"""T006 HTTP 客户端与附件下载测试（本地夹具站点）。"""

import hashlib
from pathlib import Path

import pytest
import requests

from crawler.fetch.downloader import AttachmentBoundaryRejected, Downloader
from crawler.fetch.http_client import FetchError, FetchLimits, HttpClient

SITE = Path(__file__).resolve().parent / "fixtures" / "site"


def fake_time():
    """可控时钟：sleep 推进 clock，便于验证限速与退避而不真实等待。"""
    state = {"now": 0.0, "sleeps": []}

    def sleep(seconds):
        state["sleeps"].append(seconds)
        state["now"] += seconds

    def clock():
        return state["now"]

    return state, sleep, clock


def fast_limits(**overrides):
    values = {"request_rate_per_second": 1000, "max_retries": 2}
    values.update(overrides)
    return FetchLimits(**values)


def make_client(registry, **overrides):
    return HttpClient(registry, limits=fast_limits(**overrides))


def test_get_returns_content_with_metadata(site_server, registry_factory):
    client = make_client(registry_factory(site_server))
    response = client.get(f"{site_server}/detail_1.html")
    assert response.status_code == 200
    assert response.requested_url == f"{site_server}/detail_1.html"
    assert response.final_url == response.requested_url
    assert "虚构公告" in response.content.decode("utf-8")
    assert response.attempts == 1
    assert response.headers["Content-Type"].startswith("text/html")


def test_redirect_is_followed_and_chain_recorded(site_server, registry_factory):
    client = make_client(registry_factory(site_server))
    response = client.get(f"{site_server}/_redirect?to=/detail_1.html")
    assert response.status_code == 200
    assert response.final_url.endswith("/detail_1.html")
    assert response.redirect_chain == (f"{site_server}/_redirect?to=/detail_1.html",)


def test_redirect_out_of_registered_domain_is_rejected(site_server, registry_factory):
    client = make_client(registry_factory(site_server))
    with pytest.raises(FetchError, match="访问边界拒绝") as excinfo:
        client.get(f"{site_server}/_redirect?to=https://outside.invalid/secret")
    assert excinfo.value.retryable is False


def test_redirect_to_blocked_path_is_rejected(site_server, registry_factory):
    registry = registry_factory(site_server, blocked_paths=["/login"])
    client = make_client(registry)
    with pytest.raises(FetchError, match="path_blocked"):
        client.get(f"{site_server}/_redirect?to=/login")


def test_server_error_is_retried_then_succeeds(site_server, registry_factory):
    registry = registry_factory(site_server)
    state, sleep, clock = fake_time()
    client = HttpClient(registry, limits=fast_limits(), sleep=sleep, clock=clock)
    response = client.get(f"{site_server}/_flaky/2")
    assert response.status_code == 200
    assert response.attempts == 3
    assert state["sleeps"], "退避应有等待"


def test_retry_exhaustion_reports_retryable_failure(site_server, registry_factory):
    registry = registry_factory(site_server, max_retries=2)
    state, sleep, clock = fake_time()
    client = HttpClient(registry, limits=fast_limits(max_retries=2), sleep=sleep, clock=clock)
    with pytest.raises(FetchError) as excinfo:
        client.get(f"{site_server}/_flaky/9")
    assert excinfo.value.status_code == 500
    assert excinfo.value.retryable is True
    assert excinfo.value.attempts == 3


def test_429_honours_retry_after(site_server, registry_factory):
    registry = registry_factory(site_server)
    state, sleep, clock = fake_time()
    # 只验证 Retry-After 与限速的等待序列；robots 由 tests/test_robots.py 覆盖。
    client = HttpClient(
        registry, limits=fast_limits(), sleep=sleep, clock=clock, robots=False
    )
    response = client.get(f"{site_server}/_429/1")
    assert response.status_code == 200
    assert response.attempts == 2
    assert state["sleeps"][0] == 0.0  # Retry-After: 0，不叠加退避
    assert all(value >= 0 for value in state["sleeps"])


def test_permanent_404_is_not_retried(site_server, registry_factory):
    client = make_client(registry_factory(site_server))
    with pytest.raises(FetchError) as excinfo:
        client.get(f"{site_server}/attachments/unavailable.pdf")
    assert excinfo.value.status_code == 404
    assert excinfo.value.retryable is False
    assert excinfo.value.attempts == 1


def test_read_timeout_is_retried_then_succeeds(site_server, registry_factory, timeout_session):
    """读取超时按可重试失败处理：退避后重试成功，真实尝试次数计入账目（NFR-003）。"""
    state, sleep, clock = fake_time()
    client = HttpClient(
        registry_factory(site_server),
        limits=fast_limits(),
        session=timeout_session(
            requests.Session(), 1, requests.ReadTimeout("模拟读取超时")
        ),
        sleep=sleep,
        clock=clock,
        robots=False,  # 只测请求重试机制，robots 规则有独立用例
    )
    response = client.get(f"{site_server}/detail_1.html")
    assert response.status_code == 200
    assert response.attempts == 2
    assert client.request_attempts == 2
    assert state["sleeps"] == [1.0]  # 第一次退避 = backoff_base_seconds


def test_connect_timeout_exhaustion_reports_retryable_failure(
    site_server, registry_factory, timeout_session
):
    """连接超时耗尽重试后按可重试失败上报，不无限重试，退避按指数增长。"""
    state, sleep, clock = fake_time()
    client = HttpClient(
        registry_factory(site_server),
        limits=fast_limits(),
        session=timeout_session(
            requests.Session(), 99, requests.ConnectTimeout("模拟连接超时")
        ),
        sleep=sleep,
        clock=clock,
        robots=False,
    )
    with pytest.raises(FetchError) as excinfo:
        client.get(f"{site_server}/detail_1.html")
    assert excinfo.value.retryable is True
    assert excinfo.value.attempts == 3  # max_retries=2 → 共 3 次尝试
    assert state["sleeps"] == [1.0, 2.0]
    assert client.request_attempts == 3


def test_rate_limit_enforces_minimum_interval(site_server, registry_factory):
    registry = registry_factory(site_server)
    state, sleep, clock = fake_time()
    limits = fast_limits(request_rate_per_second=2)
    client = HttpClient(registry, limits=limits, sleep=sleep, clock=clock)
    client.get(f"{site_server}/index.html")
    client.get(f"{site_server}/page2.html")
    assert sum(state["sleeps"]) >= 0.5 - 1e-9


def test_download_streams_attachment_and_hashes(site_server, registry_factory):
    client = make_client(registry_factory(site_server))
    downloader = Downloader(client)
    resource = downloader.download(f"{site_server}/attachments/notice.csv")
    expected = (SITE / "attachments" / "notice.csv").read_bytes()
    assert resource.content == expected
    assert resource.sha256 == hashlib.sha256(expected).hexdigest()
    assert resource.filename == "notice.csv"
    assert resource.content_type == "text/csv"
    assert resource.size == len(expected)


def test_download_uses_content_disposition_filename(site_server, registry_factory):
    client = make_client(registry_factory(site_server))
    resource = Downloader(client).download(f"{site_server}/_attachment-cd")
    assert resource.filename == "附件.csv"


def test_download_enforces_size_cap(site_server, registry_factory):
    """S5-04：超过大小上限是确定性边界拒绝，不是可重试的传输失败。"""
    client = make_client(registry_factory(site_server))
    downloader = Downloader(client, max_bytes=3)
    with pytest.raises(AttachmentBoundaryRejected, match="上限") as excinfo:
        downloader.download(f"{site_server}/attachments/notice.csv")
    assert excinfo.value.reason == "size_limit_exceeded:3"
    assert excinfo.value.url.endswith("/attachments/notice.csv")


def test_disabled_or_unregistered_source_is_denied(site_server, registry_factory):
    registry = registry_factory(site_server, enabled=False)
    client = make_client(registry)
    with pytest.raises(FetchError, match="访问边界拒绝"):
        client.get(f"{site_server}/index.html")


class _RecordingSession:
    """包装真实 Session，记录每次请求的传输参数。"""

    def __init__(self, inner):
        self.inner = inner
        self.headers = inner.headers
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.inner.get(url, **kwargs)


def test_source_limits_apply_when_limits_not_given(site_server, registry_factory):
    """未显式传入 FetchLimits 时，限速按来源配置生效（NFR-003 按站点调整）。"""
    state, sleep, clock = fake_time()
    registry = registry_factory(site_server, request_rate_per_second=0.5)
    client = HttpClient(registry, sleep=sleep, clock=clock)
    assert client.get(f"{site_server}/detail_1.html").status_code == 200
    assert client.get(f"{site_server}/detail_2.html").status_code == 200
    # robots.txt、detail_1、detail_2 同主机：1 / 0.5 = 2.0 秒
    assert state["sleeps"] == [2.0, 2.0]


def test_explicit_limits_override_source_config(site_server, registry_factory):
    """调用方显式给出的 FetchLimits 覆盖来源配置（离线用例不等待）。"""
    state, sleep, clock = fake_time()
    registry = registry_factory(site_server, request_rate_per_second=0.5)
    client = HttpClient(registry, limits=fast_limits(), sleep=sleep, clock=clock)
    assert client.get(f"{site_server}/detail_1.html").status_code == 200
    assert client.get(f"{site_server}/detail_2.html").status_code == 200
    assert all(value < 0.01 for value in state["sleeps"]), state["sleeps"]


def test_source_timeouts_reach_transport(site_server, registry_factory):
    """来源声明的连接/读取超时进入实际请求参数。"""
    registry = registry_factory(
        site_server, connect_timeout_seconds=3, read_timeout_seconds=7
    )
    session = _RecordingSession(requests.Session())
    client = HttpClient(registry, session=session)
    assert client.get(f"{site_server}/detail_1.html").status_code == 200
    assert session.calls[-1][1]["timeout"] == (3.0, 7.0)


def test_source_max_retries_limits_attempts(site_server, registry_factory):
    """来源声明 max_retries=0 时永久不重试，按可重试失败上报。"""
    registry = registry_factory(site_server, max_retries=0)
    client = HttpClient(registry, robots=False)  # 隔离 robots 请求，只看该次尝试
    with pytest.raises(FetchError) as excinfo:
        client.get(f"{site_server}/_flaky/3")
    assert excinfo.value.retryable is True
    assert excinfo.value.attempts == 1
    assert client.request_attempts == 1


def test_stream_read_failure_is_fetch_error():
    """S5-04：附件流式读取中断转 FetchError（记失败），不向调用方抛原始库异常。"""
    from crawler.fetch.http_client import StreamHandle

    class BrokenResponse:
        status_code = 200
        headers: dict = {}

        def __init__(self):
            self.closed = False

        def iter_content(self, chunk_size=65536):
            yield b"%PDF-1.4 partial"
            raise requests.exceptions.ConnectionError("Read timed out")

        def close(self):
            self.closed = True

    response = BrokenResponse()
    handle = StreamHandle(
        requested_url="http://example.invalid/a.pdf",
        final_url="http://example.invalid/a.pdf",
        response=response,
        raw=None,
        attempts=1,
    )
    with pytest.raises(FetchError) as excinfo:
        handle.read()
    assert "读取响应失败" in str(excinfo.value)
    assert excinfo.value.retryable is False
    assert response.closed is True


def test_broken_attachment_download_is_recorded_as_failed(
    site_server, registry_factory, tmp_path
):
    """S5-04：真实中断的附件下载记为 failed（含失败账），文档与其余流程不受影响。"""
    import json

    from crawler.fetch.budget import RunBudget
    from crawler.fetch.http_client import HttpClient
    from crawler.pipeline import CrawlPipeline

    registry = registry_factory(site_server)
    http = HttpClient(registry, limits=fast_limits())
    pipeline = CrawlPipeline(registry, tmp_path / "data", http=http)
    report = pipeline.collect(
        "TESTSRC",
        entry_urls=[],
        manual_urls=[f"{site_server}/attachment_broken.html"],
        include_attachments=True,
    )
    assert report.counters.documents == 1, "附件失败不影响正文文档产出"
    assert report.counters.failures == 1
    documents = [
        json.loads(line)
        for line in (tmp_path / "data" / "normalized" / "documents.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    attachment = documents[0]["attachments"][0]
    assert attachment["status"] == "failed"
    assert "读取响应失败" in attachment["note"]
    failures = [
        json.loads(line)
        for line in (tmp_path / "data" / "manifests" / "failed_records.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    assert any(row["url"].endswith("_broken_attachment.pdf") for row in failures)
