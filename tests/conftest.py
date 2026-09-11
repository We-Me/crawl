"""共享测试夹具：本地回环站点与来源注册表工厂。"""

import contextlib
import hashlib
import http.server
import shutil
import threading
from functools import partial
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
import yaml

from crawler.config.registry import SourceRegistry

SITE_DIR = Path(__file__).resolve().parent / "fixtures" / "site"


class FixtureSiteHandler(http.server.SimpleHTTPRequestHandler):
    """本地夹具站点：分页、附件、重定向、临时失败与 429 端点。"""

    def log_message(self, *args):  # noqa: A002 - 保持测试输出干净
        pass

    def do_GET(self):
        parsed = urlsplit(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        if path.startswith("/_flaky/"):
            self._fail_times_then_ok(path, 500)
            return
        if path.startswith("/_429/"):
            self._fail_times_then_ok(path, 429)
            return
        if path.startswith("/_retry_after/"):
            value = path.rsplit("/", 1)[1]
            self.send_response(429)
            self.send_header("Retry-After", value)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if path == "/search":
            query = query.get("q", [""])[0]
            body = (
                "<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
                "<title>虚构搜索</title></head><body><main><h1>搜索结果</h1><ul>"
                f"<li><a href=\"detail_2.html\">{query} 的虚构结果</a></li>"
                "</ul></main></body></html>"
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/_attachment-cd":
            body = (SITE_DIR / "attachments" / "notice.csv").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header(
                "Content-Disposition", "attachment; filename*=UTF-8''%E9%99%84%E4%BB%B6.csv"
            )
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path.startswith("/_etag/"):
            self._serve_with_etag(path[len("/_etag/"):])
            return
        if path == "/_redirect":
            target = query.get("to", ["/"])[0]
            code = int(query.get("code", ["302"])[0])
            self.send_response(code)
            self.send_header("Location", target)
            self.end_headers()
            return
        if self._serve_dynamic_file(path):
            return
        super().do_GET()

    def _fail_times_then_ok(self, path, code):
        times = int(path.rsplit("/", 1)[1])
        counts = self.server.flaky_counts  # type: ignore[attr-defined]
        with self.server.flaky_lock:  # type: ignore[attr-defined]
            seen = counts.get(path, 0)
            counts[path] = seen + 1
        if seen < times:
            self.send_response(code)
            if code == 429:
                self.send_header("Retry-After", "0")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        body = b"ok"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_dynamic_file(self, path):
        if Path(path).suffix not in (".xml", ".json"):
            return False
        file_path = Path(self.directory) / path.lstrip("/")  # type: ignore[arg-type]
        if not file_path.is_file():
            return False
        body = file_path.read_bytes().replace(
            b"__PORT__", str(self.server.server_port).encode()
        )
        content_type = (
            "application/xml; charset=utf-8"
            if file_path.suffix == ".xml"
            else "application/json; charset=utf-8"
        )
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        return True

    def _serve_with_etag(self, relative):
        """条件请求端点：带 ETag/Last-Modified，命中 If-None-Match 时返回 304。"""
        root = Path(self.directory).resolve()  # type: ignore[arg-type]
        file_path = (root / relative).resolve()
        if not str(file_path).startswith(str(root)) or not file_path.is_file():
            self.send_error(404)
            return
        body = file_path.read_bytes()
        etag = '"' + hashlib.sha256(body).hexdigest()[:16] + '"'
        if self.headers.get("If-None-Match") == etag:
            self.send_response(304)
            self.send_header("ETag", etag)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("ETag", etag)
        self.send_header("Last-Modified", "Fri, 11 Sep 2026 00:00:00 GMT")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class TimeoutInjectingSession:
    """前 failures 次请求抛指定超时异常，之后委托真实 Session；用于确定性超时用例。"""

    def __init__(self, inner, failures, exc):
        self.inner = inner
        self.failures = failures
        self.exc = exc
        self.calls = 0
        self.headers = inner.headers

    def get(self, url, **kwargs):
        self.calls += 1
        if self.calls <= self.failures:
            raise self.exc
        return self.inner.get(url, **kwargs)


@pytest.fixture()
def timeout_session():
    """返回超时注入 Session 包装类，避免依赖真实慢端点造成不稳定用例。"""
    return TimeoutInjectingSession


class QuietThreadingHTTPServer(http.server.ThreadingHTTPServer):
    """本地夹具站点服务器：客户端中止流式下载时不断言失败、不打印堆栈。"""

    def handle_error(self, request, client_address):
        import sys

        exc = sys.exc_info()[1]
        if isinstance(exc, (OSError, ConnectionError)):
            return
        super().handle_error(request, client_address)


@contextlib.contextmanager
def _serve_site(directory: Path):
    handler = partial(FixtureSiteHandler, directory=str(directory))
    server = QuietThreadingHTTPServer(("127.0.0.1", 0), handler)
    server.flaky_counts = {}  # type: ignore[attr-defined]
    server.flaky_lock = threading.Lock()  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture(scope="session")
def site_server():
    with _serve_site(SITE_DIR) as base_url:
        yield base_url


@pytest.fixture()
def mutable_site(tmp_path):
    """site/ 的可写副本站点：供增量用例在两次采集之间修改站点内容。"""
    root = tmp_path / "site"
    shutil.copytree(SITE_DIR, root)
    with _serve_site(root) as base_url:
        yield base_url, root


@pytest.fixture()
def registry_factory(tmp_path):
    def make(base_url, **overrides):
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
            "search_url_template": f"{base_url}/search?q={{query}}",
            "request_rate_per_second": 1000,
            "max_retries": 2,
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

    return make


@pytest.fixture()
def fake_time():
    """可控时钟：sleep 推进会推进 clock，用于验证限速与退避。"""

    state = {"now": 0.0, "sleeps": []}

    def sleep(seconds):
        state["sleeps"].append(seconds)
        state["now"] += seconds

    def clock():
        return state["now"]

    return state, sleep, clock
