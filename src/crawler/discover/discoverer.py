"""栏目分页、搜索、sitemap、API 与附件发现（T005）。

发现只产出待获取目标与实际策略；关键词用于检索与账本记录，不生成分类结论。
域外或越界链接不请求，记录跳过原因。
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple
from urllib.parse import quote_plus, urljoin, urlsplit

from bs4 import BeautifulSoup
from defusedxml import ElementTree

from crawler.config.registry import SourceConfig
from crawler.fetch.http_client import FetchError, HttpClient
from crawler.parser.html_parser import decode_html

logger = logging.getLogger(__name__)

ATTACHMENT_EXTENSIONS = frozenset(
    {
        ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv", ".txt", ".json", ".xml",
        ".zip", ".rar", ".rtf", ".ppt", ".pptx", ".odt", ".ods",
    }
)


@dataclass(frozen=True)
class DiscoveredTarget:
    url: str
    discovery_method: str
    referrer_url: Optional[str] = None
    keyword: Optional[str] = None
    title_hint: Optional[str] = None


@dataclass(frozen=True)
class SkippedTarget:
    url: str
    reason: str
    referrer_url: Optional[str] = None


class Discoverer:
    def __init__(
        self,
        http: HttpClient,
        registry,
        source: SourceConfig,
        max_pages: int = 10,
        max_items: int = 1000,
    ) -> None:
        self.http = http
        self.registry = registry
        self.source = source
        self.max_pages = max_pages
        self.max_items = max_items
        self.skipped: List[SkippedTarget] = []
        self._seen: set = set()

    def discover_list(self, entry_urls: Optional[Sequence[str]] = None) -> List[DiscoveredTarget]:
        entries = list(entry_urls) if entry_urls is not None else list(self.source.entry_urls)
        if not entries:
            raise ValueError(f"来源 {self.source.source_id} 未配置 entry_urls")
        targets: List[DiscoveredTarget] = []
        max_pages = self.source.adapter.max_pages or self.max_pages
        for entry in entries:
            page_url: Optional[str] = entry
            pages = 0
            while page_url and pages < max_pages and len(targets) < self.max_items:
                pages += 1
                try:
                    response = self.http.get(page_url, source_id=self.source.source_id)
                except FetchError:
                    if pages == 1:
                        raise
                    logger.warning("分页获取失败，停止该入口：%s", page_url)
                    break
                page_targets, rule_matched = self._list_page_targets(
                    response.content, response.final_url, "list"
                )
                targets.extend(page_targets)
                if not rule_matched:
                    break  # 适配选择器未命中：已记录跳过原因，不再翻页
                page_url = self._next_page_url(response.content, response.final_url)
        return targets[: self.max_items]

    def discover_search(self, keyword: str) -> List[DiscoveredTarget]:
        template = self.source.search_url_template
        if not template:
            raise ValueError(f"来源 {self.source.source_id} 未配置 search_url_template")
        url = template.replace("{query}", quote_plus(keyword))
        response = self.http.get(url, source_id=self.source.source_id)
        results, _ = self._list_page_targets(response.content, response.final_url, "search")
        return [replace_keyword(target, keyword) for target in results]

    def discover_sitemap(self, sitemap_url: str) -> List[DiscoveredTarget]:
        response = self.http.get(sitemap_url, source_id=self.source.source_id)
        root = ElementTree.fromstring(response.content)
        targets = []
        for element in root.iter():
            if not element.tag.endswith("loc") or not (element.text or "").strip():
                continue
            url = element.text.strip()
            decision = self.registry.check_access(url, self.source.source_id)
            if not decision.allowed:
                self.skipped.append(SkippedTarget(url, decision.reason, sitemap_url))
                continue
            targets.append(DiscoveredTarget(url=url, discovery_method="sitemap", referrer_url=sitemap_url))
        return self._dedupe(targets)

    def discover_api(
        self, api_url: str, *, url_field: str = "url", title_field: str = "title"
    ) -> List[DiscoveredTarget]:
        response = self.http.get(api_url, source_id=self.source.source_id)
        payload = json.loads(decode_html(response.content))
        items = payload if isinstance(payload, list) else payload.get("items", [])
        targets = []
        for item in items:
            if not isinstance(item, dict) or not item.get(url_field):
                continue
            url = urljoin(api_url, str(item[url_field]))
            decision = self.registry.check_access(url, self.source.source_id)
            if not decision.allowed:
                self.skipped.append(SkippedTarget(url, decision.reason, api_url))
                continue
            targets.append(
                DiscoveredTarget(
                    url=url,
                    discovery_method="api",
                    referrer_url=api_url,
                    title_hint=item.get(title_field),
                )
            )
        return self._dedupe(targets)

    def attachments_from_html(self, content: bytes, page_url: str) -> List[DiscoveredTarget]:
        soup = BeautifulSoup(decode_html(content), "lxml")
        targets = []
        for anchor in soup.find_all("a", href=True):
            url = urljoin(page_url, anchor["href"])
            if _attachment_extension(url) is None:
                continue
            decision = self.registry.check_access(url, self.source.source_id)
            if not decision.allowed:
                self.skipped.append(SkippedTarget(url, decision.reason, page_url))
                continue
            targets.append(
                DiscoveredTarget(
                    url=url,
                    discovery_method="attachment",
                    referrer_url=page_url,
                    title_hint=" ".join(anchor.get_text(" ", strip=True).split()) or None,
                )
            )
        return self._dedupe(targets)

    def _list_page_targets(
        self, content: bytes, page_url: str, method: str
    ) -> Tuple[List[DiscoveredTarget], bool]:
        """按适配规则或通用范围提取列表页链接；返回 (目标, 规则是否命中)。"""
        soup = BeautifulSoup(decode_html(content), "lxml")
        adapter = self.source.adapter
        if adapter.list_link_selector:
            anchors = _selected_anchors(soup, adapter.list_link_selector)
            if anchors is None:
                reason = f"adapter_list_selector_miss:{adapter.list_link_selector}"
                self.skipped.append(SkippedTarget(page_url, reason, page_url))
                logger.warning(
                    "列表选择器未命中，本页不发现目标 url=%s selector=%s",
                    page_url,
                    adapter.list_link_selector,
                )
                return [], False
        else:
            scope = soup.find("main") or soup.find("article") or soup.body or soup
            anchors = list(scope.find_all("a", href=True))
        targets = []
        for anchor in anchors:
            if "next" in (anchor.get("rel") or []):
                continue
            url = urljoin(page_url, anchor["href"])
            if adapter.list_link_pattern and not re.search(adapter.list_link_pattern, url):
                continue
            if _is_fragment_or_action(url):
                continue
            if url.split("#")[0] == page_url.split("#")[0]:
                continue
            if _attachment_extension(url) is not None:
                continue
            decision = self.registry.check_access(url, self.source.source_id)
            if not decision.allowed:
                self.skipped.append(SkippedTarget(url, decision.reason, page_url))
                continue
            targets.append(
                DiscoveredTarget(
                    url=url,
                    discovery_method=method,
                    referrer_url=page_url,
                    title_hint=" ".join(anchor.get_text(" ", strip=True).split()) or None,
                )
            )
        return self._dedupe(targets), True

    def _next_page_url(self, content: bytes, page_url: str) -> Optional[str]:
        soup = BeautifulSoup(decode_html(content), "lxml")
        adapter = self.source.adapter
        if adapter.pagination_selector:
            element = soup.select_one(adapter.pagination_selector)
            if element is not None and not element.get("href"):
                element = element.find(["a", "link"], href=True)
            href = element.get("href") if element is not None else None
            if not href:
                return None  # 适配规则即分页终止条件：控件不存在则停止翻页
            candidate = urljoin(page_url, str(href))
            decision = self.registry.check_access(candidate, self.source.source_id)
            if not decision.allowed:
                self.skipped.append(SkippedTarget(candidate, decision.reason, page_url))
                return None
            return candidate
        for element in list(soup.find_all("a", href=True)) + list(soup.find_all("link", href=True)):
            if "next" in (element.get("rel") or []):
                candidate = urljoin(page_url, element["href"])
                decision = self.registry.check_access(candidate, self.source.source_id)
                if decision.allowed:
                    return candidate
                self.skipped.append(SkippedTarget(candidate, decision.reason, page_url))
        return None

    def _dedupe(self, targets: Iterable[DiscoveredTarget]) -> List[DiscoveredTarget]:
        result = []
        for target in targets:
            if target.url in self._seen:
                continue
            self._seen.add(target.url)
            result.append(target)
        return result


def replace_keyword(target: DiscoveredTarget, keyword: str) -> DiscoveredTarget:
    return DiscoveredTarget(
        url=target.url,
        discovery_method=target.discovery_method,
        referrer_url=target.referrer_url,
        keyword=keyword,
        title_hint=target.title_hint,
    )


def _selected_anchors(soup: BeautifulSoup, selector: str) -> Optional[List]:
    """按适配选择器取候选链接：选择器可直接命中 `<a>`，也可命中包含链接的容器。

    返回 None 表示选择器未命中（调用方记录跳过原因，不静默回退）。
    """
    elements = soup.select(selector)
    if not elements:
        return None
    anchors: List = []
    seen: set = set()
    for element in elements:
        candidates = (
            [element]
            if element.name == "a" and element.get("href")
            else list(element.find_all("a", href=True))
        )
        for anchor in candidates:
            if id(anchor) in seen:
                continue
            seen.add(id(anchor))
            anchors.append(anchor)
    return anchors


def _attachment_extension(url: str) -> Optional[str]:
    path = urlsplit(url).path.lower()
    for extension in ATTACHMENT_EXTENSIONS:
        if path.endswith(extension):
            return extension
    return None


def _is_fragment_or_action(url: str) -> bool:
    parts = urlsplit(url)
    return parts.scheme not in ("http", "https") or not parts.netloc
