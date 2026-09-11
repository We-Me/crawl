"""带访问边界、robots 规则、限速与退避重试的 HTTP 客户端（T006）。

重定向不交给底层库自动跟随：每一跳都先用来源注册表检查，越界立即停止；
429 与 5xx 按可配置退避重试，Retry-After 优先。
每个主机首次请求前按 robots.txt 判定（FR-001）；规则获取走同一客户端，
因此同样受限速与访问边界约束，且不写入抓取账本。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Iterator, Mapping, Optional, Tuple
from urllib.parse import urljoin, urlsplit

import requests
from requests.structures import CaseInsensitiveDict

from crawler.fetch.robots import RobotsRules, group_summary, parse_robots, rules_for_unavailable

logger = logging.getLogger(__name__)

USER_AGENT = "public-knowledge-collection/0.1 (fixture-driven development)"
RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
REDIRECT_STATUS = frozenset({301, 302, 303, 307, 308})


@dataclass(frozen=True)
class FetchLimits:
    request_rate_per_second: float = 1.0
    max_retries: int = 2
    connect_timeout_seconds: float = 10.0
    read_timeout_seconds: float = 30.0
    max_redirects: int = 5
    backoff_base_seconds: float = 1.0
    backoff_max_seconds: float = 30.0

    @classmethod
    def from_source(
        cls, source, *, base: Optional["FetchLimits"] = None
    ) -> "FetchLimits":
        """按来源配置生成逐站限速与超时；来源未登记的项沿用 base。"""
        current = base or cls()
        return cls(
            request_rate_per_second=float(source.request_rate_per_second),
            max_retries=int(source.max_retries),
            connect_timeout_seconds=float(source.connect_timeout_seconds),
            read_timeout_seconds=float(source.read_timeout_seconds),
            max_redirects=current.max_redirects,
            backoff_base_seconds=current.backoff_base_seconds,
            backoff_max_seconds=current.backoff_max_seconds,
        )


class FetchError(Exception):
    """获取失败；retryable 说明是否已用尽可重试机会。"""

    def __init__(
        self,
        message: str,
        *,
        url: str,
        status_code: Optional[int] = None,
        retryable: bool = False,
        attempts: int = 1,
    ) -> None:
        super().__init__(message)
        self.url = url
        self.status_code = status_code
        self.retryable = retryable
        self.attempts = attempts


class RobotsDisallowed(FetchError):
    """robots.txt 拒绝访问；属于策略跳过，不是可重试的抓取失败。"""

    def __init__(self, message: str, *, url: str, rule: str = "") -> None:
        super().__init__(message, url=url, retryable=False)
        self.rule = rule


@dataclass(frozen=True)
class FetchResponse:
    requested_url: str
    final_url: str
    status_code: int
    headers: Mapping[str, str]
    content: bytes
    redirect_chain: Tuple[str, ...]
    attempts: int


class StreamHandle:
    """已通过状态与边界检查的流式响应；按块读取，读取失败不可重试。"""

    def __init__(
        self,
        *,
        requested_url: str,
        final_url: str,
        response: requests.Response,
        raw: "HttpClient",
        attempts: int,
        redirect_chain: Tuple[str, ...] = (),
    ) -> None:
        self.requested_url = requested_url
        self.redirect_chain = redirect_chain
        self.final_url = final_url
        self.status_code = response.status_code
        self.headers = CaseInsensitiveDict(response.headers)
        self.content_type = _content_type(response.headers)
        self._response = response
        self._raw = raw
        self.attempts = attempts

    def iter_chunks(self, chunk_size: int = 64 * 1024) -> Iterator[bytes]:
        try:
            for chunk in self._response.iter_content(chunk_size=chunk_size):
                if chunk:
                    yield chunk
        finally:
            self.close()

    def read(self) -> bytes:
        return b"".join(self.iter_chunks())

    def close(self) -> None:
        self._response.close()


class HttpClient:
    """同步 HTTP 客户端；每次请求前检查访问边界与 robots 规则，按域限速。"""

    def __init__(
        self,
        registry,
        limits: Optional[FetchLimits] = None,
        session: Optional[requests.Session] = None,
        sleep=time.sleep,
        clock=time.monotonic,
        robots: bool = True,
        user_agent: str = USER_AGENT,
    ) -> None:
        self.registry = registry
        # 调用方显式给出 FetchLimits 时以它为准（测试与批量运行用）；
        # 未给出时逐站读取来源配置的速率、超时与重试上限。
        self._explicit_limits = limits is not None
        self.limits = limits or FetchLimits()
        self.session = session or requests.Session()
        self.session.headers.setdefault("User-Agent", user_agent)
        self.user_agent = self.session.headers.get("User-Agent", user_agent)
        self._sleep = sleep
        self._clock = clock
        self._next_allowed: dict = {}
        self.robots_enabled = bool(robots)
        self._robots: dict = {}
        # 实际发出的 HTTP 尝试次数（含重试与逐跳重定向），供运行计数使用
        self.request_attempts = 0

    def limits_for(self, url: str, source_id: Optional[str] = None) -> FetchLimits:
        """本次请求适用的限速与超时：显式 FetchLimits 优先，否则按来源配置。"""
        if self._explicit_limits:
            return self.limits
        source = (
            self.registry.get(source_id)
            if source_id is not None
            else self.registry.source_for_url(url)
        )
        if source is None:
            return self.limits
        return FetchLimits.from_source(source, base=self.limits)

    def get(
        self,
        url: str,
        *,
        source_id: Optional[str] = None,
        conditional: Optional[Mapping[str, str]] = None,
        _resolving_robots: bool = False,
    ) -> FetchResponse:
        handle = self.open(
            url,
            source_id=source_id,
            conditional=conditional,
            _resolving_robots=_resolving_robots,
        )
        try:
            content = handle.read()
        finally:
            handle.close()
        return FetchResponse(
            requested_url=handle.requested_url,
            final_url=handle.final_url,
            status_code=handle.status_code,
            headers=handle.headers,
            content=content,
            redirect_chain=handle.redirect_chain,
            attempts=handle.attempts,
        )

    def open(
        self,
        url: str,
        *,
        source_id: Optional[str] = None,
        conditional: Optional[Mapping[str, str]] = None,
        _resolving_robots: bool = False,
    ) -> StreamHandle:
        """打开流式响应，完成逐跳边界检查、限速与重试。

        conditional 传入 If-None-Match / If-Modified-Since 等条件请求头；
        304 按状态原样返回空正文，由调用方决定复用既有原件。
        _resolving_robots 仅供 robots.txt 自身获取使用，避免递归判定。
        """
        current = url
        hops = []
        for _ in range(self.limits.max_redirects + 1):
            limits = self.limits_for(current, source_id)
            self._check_boundary(current, source_id)
            if not _resolving_robots:
                self._check_robots(current, source_id)
            response, attempts = self._request_with_retry(current, conditional, limits)
            if response.status_code in REDIRECT_STATUS:
                location = response.headers.get("Location")
                response.close()
                if not location:
                    raise FetchError(
                        "重定向响应缺少 Location",
                        url=current,
                        status_code=response.status_code,
                    )
                hops.append(current)
                current = urljoin(current, location)
                continue
            logger.debug(
                "获取成功 url=%s status=%s attempts=%s redirects=%s",
                current,
                response.status_code,
                attempts,
                len(hops),
            )
            return StreamHandle(
                requested_url=url,
                final_url=current,
                response=response,
                raw=self,
                attempts=attempts,
                redirect_chain=tuple(hops),
            )
        raise FetchError(
            f"重定向超过 {self.limits.max_redirects} 跳",
            url=url,
            retryable=False,
            attempts=1,
        )

    def _check_boundary(self, url: str, source_id: Optional[str]) -> None:
        decision = self.registry.check_access(url, source_id)
        if not decision.allowed:
            raise FetchError(
                f"访问边界拒绝：{decision.reason}", url=url, retryable=False
            )

    def _check_robots(self, url: str, source_id: Optional[str]) -> None:
        """按主机缓存 robots 规则并判定；拒绝时抛 RobotsDisallowed（不重试）。"""
        if not self.robots_enabled:
            return
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.netloc:
            return
        base = f"{parts.scheme}://{parts.netloc}"
        rules = self._robots.get(base)
        if rules is None:
            rules = self._load_robots(base, source_id)
            self._robots[base] = rules
        allowed, reason = rules.decision(parts.path or "/", self.user_agent)
        if not allowed:
            raise RobotsDisallowed(f"robots.txt 拒绝访问：{reason}", url=url, rule=reason)

    def _load_robots(self, base: str, source_id: Optional[str]) -> RobotsRules:
        """获取并解析 <base>/robots.txt；不可用时按 rules_for_unavailable 处理。"""
        robots_url = f"{base}/robots.txt"
        try:
            response = self.get(robots_url, source_id=source_id, _resolving_robots=True)
        except FetchError as exc:
            rules = rules_for_unavailable(exc.status_code)
            logger.warning(
                "robots.txt 不可用 host=%s status=%s 处理=%s",
                base,
                exc.status_code,
                rules.reason,
            )
            return rules
        rules = parse_robots(_decode_text(response.content, response.headers))
        logger.info("robots.txt 已加载 host=%s %s", base, group_summary(rules))
        return rules

    def _request_with_retry(
        self,
        url: str,
        headers: Optional[Mapping[str, str]] = None,
        limits: Optional[FetchLimits] = None,
    ):
        limits = limits or self.limits_for(url)
        attempt = 0
        while True:
            attempt += 1
            self._wait_for_rate_limit(url, limits)
            self.request_attempts += 1
            try:
                response = self.session.get(
                    url,
                    headers=dict(headers) if headers else None,
                    allow_redirects=False,
                    stream=True,
                    timeout=(
                        limits.connect_timeout_seconds,
                        limits.read_timeout_seconds,
                    ),
                )
            except requests.RequestException as exc:
                if attempt <= limits.max_retries:
                    logger.info("请求失败将重试 url=%s attempt=%s error=%s", url, attempt, exc)
                    self._sleep(self._backoff(attempt, limits))
                    continue
                raise FetchError(
                    f"请求失败：{exc}", url=url, retryable=True, attempts=attempt
                ) from exc
            if response.status_code in RETRY_STATUS:
                if attempt <= limits.max_retries:
                    delay = self._retry_after(response)
                    if delay is None:
                        delay = self._backoff(attempt, limits)
                    logger.info(
                        "状态 %s 将重试 url=%s attempt=%s delay=%.2f",
                        response.status_code,
                        url,
                        attempt,
                        delay,
                    )
                    response.close()
                    self._sleep(delay)
                    continue
                status = response.status_code
                response.close()
                raise FetchError(
                    f"重试后仍返回 {status}",
                    url=url,
                    status_code=status,
                    retryable=True,
                    attempts=attempt,
                )
            if response.status_code >= 400:
                status = response.status_code
                response.close()
                raise FetchError(
                    f"HTTP {status}",
                    url=url,
                    status_code=status,
                    retryable=False,
                    attempts=attempt,
                )
            return response, attempt

    def _wait_for_rate_limit(self, url: str, limits: Optional[FetchLimits] = None) -> None:
        limits = limits or self.limits
        host = urlsplit(url).hostname or ""
        interval = (
            1.0 / limits.request_rate_per_second
            if limits.request_rate_per_second > 0
            else 0.0
        )
        now = self._clock()
        next_allowed = self._next_allowed.get(host, 0.0)
        if next_allowed > now:
            self._sleep(next_allowed - now)
            now = self._clock()
        self._next_allowed[host] = now + interval

    def _backoff(self, attempt: int, limits: Optional[FetchLimits] = None) -> float:
        limits = limits or self.limits
        delay = limits.backoff_base_seconds * (2 ** (attempt - 1))
        return min(delay, limits.backoff_max_seconds)

    @staticmethod
    def _retry_after(response: requests.Response) -> Optional[float]:
        value = response.headers.get("Retry-After")
        if value is None:
            return None
        try:
            return max(0.0, float(value))
        except ValueError:
            return None


def _content_type(headers: Mapping[str, str]) -> str:
    return headers.get("Content-Type", "").split(";")[0].strip().lower()


def _decode_text(content: bytes, headers: Mapping[str, str]) -> str:
    """按响应头字符集解码 robots.txt，未声明时按 UTF-8，失败不抛错。"""
    charset = None
    for part in headers.get("Content-Type", "").split(";")[1:]:
        key, _, value = part.partition("=")
        if key.strip().lower() == "charset" and value.strip():
            charset = value.strip().strip('"')
    for encoding in (charset, "utf-8"):
        if not encoding:
            continue
        try:
            return content.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return content.decode("utf-8", errors="replace")
