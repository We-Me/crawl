"""栏目分页、搜索、sitemap、API 与附件发现（T005；S5-01/S5-03 补齐）。

发现只产出待获取目标与实际策略；关键词用于检索与账本记录，不生成分类结论。
域外或越界链接不请求，记录跳过原因。

本模块承担两类完整性职责：

- 归档（S5-01）：每个成功业务响应（列表/搜索页、sitemap、发现接口）先经
  ResponseArchiver 落原件与账本，再解析；解析失败不丢原件，由上层写失败账。
  发现页不生成 normalized 文档，也不伪造成详情页。
- 终止原因（S5-03）：每个入口的遍历结束都记录确切原因（站点末页、适配规则终点、
  页数/目标上限、预算停止、请求失败、选择器未命中、循环、访问拒绝），失败与截断
  不冒充“零结果”或“遍历完成”。未翻到的页位置保存在发现游标，供下一轮续接。
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Callable, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import parse_qsl, quote_plus, urlencode, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup
from defusedxml import ElementTree

from crawler.config.registry import SourceConfig
from crawler.fetch.budget import BudgetStop
from crawler.fetch.http_client import FetchError, FetchResponse, HttpClient
from crawler.output.archive import ArchivedResponse, ResponseArchiver
from crawler.parser.html_parser import decode_html
from crawler.schedule.cursor import (
    CURSOR_ACTIVE,
    CURSOR_COMPLETED,
    DiscoveryCursor,
    DiscoveryCursorStore,
    cursor_key,
)
from crawler.schedule.scope import RunScope

logger = logging.getLogger(__name__)

ATTACHMENT_EXTENSIONS = frozenset(
    {
        ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv", ".txt", ".json", ".xml",
        ".zip", ".rar", ".rtf", ".ppt", ".pptx", ".odt", ".ods",
    }
)

# 未在正文附件声明范围内的下载类扩展名：只用于“规则排除”计数，不下载、不扩范围。
OTHER_DOWNLOAD_EXTENSIONS = frozenset(
    {
        ".7z", ".apk", ".avi", ".bz2", ".dmg", ".epub", ".exe", ".gz", ".iso", ".m4a",
        ".mobi", ".mov", ".mp3", ".mp4", ".pkg", ".tar", ".tgz", ".wav", ".wmv", ".xz",
    }
)

# 遍历终止原因：complete 表示该入口在已声明规则下遍历完成；否则为截断/失败/未证实。
STOP_END_OF_PAGES = "end_of_pages"
STOP_PAGINATION_RULE_END = "pagination_control_missing"
STOP_MAX_PAGES = "max_pages_reached"
STOP_MAX_ITEMS = "max_items_reached"
STOP_REQUEST_FAILED = "request_failed"
STOP_BUDGET = "budget_stop"
STOP_LOOP = "loop_detected"
STOP_ACCESS_DENIED = "access_denied"
STOP_SELECTOR_MISS = "selector_miss"
STOP_SITEMAP_INDEX = "sitemap_index_not_expanded"
STOP_DATE_SCOPED_QUERY = "date_scoped_query"
STOP_PARSE_ERROR = "parse_error"

STOP_REASON_TEXT = {
    STOP_END_OF_PAGES: "没有下一页链接（站点/规则终点）",
    STOP_PAGINATION_RULE_END: "适配分页控件不存在（适配规则终点）",
    STOP_MAX_PAGES: "达到每入口页数上限",
    STOP_MAX_ITEMS: "达到本次发现目标上限",
    STOP_REQUEST_FAILED: "后续页请求失败",
    STOP_BUDGET: "预算或截止时间停止",
    STOP_LOOP: "分页回到已访问页面（循环）",
    STOP_ACCESS_DENIED: "下一页被访问边界或 robots 拒绝",
    STOP_SELECTOR_MISS: "适配选择器未命中",
    STOP_SITEMAP_INDEX: "sitemap index 的子 sitemap 未展开",
    STOP_DATE_SCOPED_QUERY: "查询本身按日期限定（覆盖以查询范围为准）",
    STOP_PARSE_ERROR: "发现响应无法解析（原件与账本保留）",
}

COMPLETE_STOPS = frozenset(
    {STOP_END_OF_PAGES, STOP_PAGINATION_RULE_END, STOP_DATE_SCOPED_QUERY}
)

# 查询模板日期占位符：与策略层共用同一集合，避免两处各定义一套。
DATE_PLACEHOLDERS = ("{start_date}", "{end_date}", "{year}", "{month}", "{end_year}", "{end_month}")
# 无法自动续接的终止原因：游标不再指向“下一页”。
TERMINAL_STOPS = frozenset(
    {
        STOP_END_OF_PAGES,
        STOP_PAGINATION_RULE_END,
        STOP_SELECTOR_MISS,
        STOP_LOOP,
        STOP_DATE_SCOPED_QUERY,
    }
)


class DiscoveryContentError(Exception):
    """发现响应已归档但内容无法解析；上层写失败账，原件与账本保留。"""

    def __init__(self, url: str, message: str, *, stage: str = "", crawl_id: Optional[str] = None) -> None:
        super().__init__(message)
        self.url = url
        self.stage = stage
        self.crawl_id = crawl_id


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


@dataclass(frozen=True)
class DiscoveryStop:
    """一个入口本次遍历的终止原因；complete 表示在已声明规则下遍历完成。"""

    stage: str
    entry: str
    pages: int
    targets: int
    stop: str
    complete: bool
    detail: Optional[str] = None
    next_url: Optional[str] = None
    cursor: Optional[str] = None
    error_type: Optional[str] = None

    def as_row(self) -> dict:
        row = {
            "stage": self.stage,
            "entry": self.entry,
            "pages": int(self.pages),
            "targets": int(self.targets),
            "stop": self.stop,
            "complete": bool(self.complete),
            "reason": STOP_REASON_TEXT.get(self.stop, self.stop),
        }
        if self.detail:
            row["detail"] = self.detail
        if self.next_url:
            row["next_url"] = self.next_url
        if self.cursor:
            row["cursor"] = self.cursor
        if self.error_type:
            row["error_type"] = self.error_type
        return row


class Discoverer:
    def __init__(
        self,
        http: HttpClient,
        registry,
        source: SourceConfig,
        max_pages: int = 10,
        max_items: int = 1000,
        *,
        archiver: Optional[ResponseArchiver] = None,
        cursors: Optional[DiscoveryCursorStore] = None,
        now: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self.http = http
        self.registry = registry
        self.source = source
        self.max_pages = max_pages
        self.max_items = max_items
        self.archiver = archiver
        self.cursors = cursors
        self._now = now or (lambda: datetime.now(timezone.utc).astimezone())
        self.skipped: List[SkippedTarget] = []
        # 适配选择器未命中的显式记录（T005/T026）：与“真实零结果”分开报告，
        # 由策略层（discover/strategies.py）读取为 selector_miss 状态。
        self.selector_misses: List[dict] = []
        # 通用列表范围（main/article/body）取不到任何目标、按整文档兜底成功的页：
        # 结构不完整（如 CN-04 双 <html>，正文在 body 之外）时避免把范围漏采当真实零结果。
        self.scope_fallbacks: List[dict] = []
        # 每个入口的终止原因（S5-03）；策略层按调用前后差集读取。
        self.stops: List[DiscoveryStop] = []
        # 附件规则排除（聚合计数，S5-04）：说明“已发现但按规则不下载”的原因。
        self.attachment_rule_exclusions: List[dict] = []
        # 跨页/跨文档重复的附件候选（按页聚合）：只计数，不重复下载。
        self.attachment_duplicates: List[dict] = []
        # 预算停止时保存原始异常，由管线在记录发现结果后停止本次运行。
        self.budget_stop: Optional[BudgetStop] = None
        # 本实例成功归档的发现响应数（同一响应对象重复归档不重复计数）。
        self.archived_count = 0
        self._seen: set = set()

    @property
    def effective_max_pages(self) -> int:
        """本来源的页数上限：适配配置优先，其次本轮参数。"""
        return int(self.source.adapter.max_pages or self.max_pages)

    # ------------------------------------------------------------------ 列表/搜索

    def discover_list(
        self, entry_urls: Optional[Sequence[str]] = None, scope: Optional[RunScope] = None
    ) -> List[DiscoveredTarget]:
        entries = list(entry_urls) if entry_urls is not None else list(self.source.entry_urls)
        if not entries:
            raise ValueError(f"来源 {self.source.source_id} 未配置 entry_urls")
        scope = scope or RunScope()
        targets: List[DiscoveredTarget] = []
        for entry in entries:
            targets.extend(self._paginate(stage="list", entry=entry, scope=scope))
        return targets

    def discover_search(
        self,
        keyword: str,
        *,
        url: Optional[str] = None,
        scope: Optional[RunScope] = None,
    ) -> List[DiscoveredTarget]:
        """站内搜索发现；url 已由调用方按运行范围渲染时直接使用，否则用配置模板。"""
        template = self.source.search_url_template
        if url is None and not template:
            raise ValueError(f"来源 {self.source.source_id} 未配置 search_url_template")
        scope = scope or RunScope()
        target_url = url or template.replace("{query}", quote_plus(keyword))
        # 游标身份按渲染后的检索 URL 归属：同一模板的不同关键词（或日期窗口）各自续接，
        # 避免一个关键词截断后把另一个关键词从半途开始，漏掉前者之前的页。
        entry = target_url
        results = self._paginate(
            stage="search", entry=entry, scope=scope, start_url=target_url, keyword=keyword
        )
        return [replace_keyword(target, keyword) for target in results]

    # ------------------------------------------------------------------ sitemap/API

    def discover_sitemap(
        self, sitemap_url: str, scope: Optional[RunScope] = None
    ) -> List[DiscoveredTarget]:
        response = self.http.get(sitemap_url, source_id=self.source.source_id)
        archived = self._archive(response, kind="discovery", discovery_method="sitemap")
        try:
            root = ElementTree.fromstring(response.content)
        except (ElementTree.ParseError, UnicodeDecodeError, ValueError) as exc:
            raise DiscoveryContentError(
                sitemap_url,
                f"sitemap 解析失败：{exc}",
                stage="sitemap",
                crawl_id=archived.crawl_id if archived else None,
            ) from exc
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
        targets = self._dedupe(targets)
        is_index = bool(root.tag) and root.tag.endswith("sitemapindex")
        self._record_stop(
            DiscoveryStop(
                stage="sitemap",
                entry=sitemap_url,
                pages=1,
                targets=len(targets),
                stop=STOP_SITEMAP_INDEX if is_index else STOP_END_OF_PAGES,
                complete=not is_index,
                detail=(
                    "sitemap index：只处理了顶层条目，子 sitemap 未展开"
                    if is_index
                    else "sitemap 条目全部读取（该文件内为全量列表）"
                ),
            )
        )
        return targets

    def discover_api(
        self,
        api_url: str,
        *,
        url_field: str = "url",
        title_field: str = "title",
        scope: Optional[RunScope] = None,
    ) -> List[DiscoveredTarget]:
        """结构化接口发现：只跟随响应自身声明的下一页，不猜测私有端点。"""
        scope = scope or RunScope()
        cursor = self._load_cursor("api", api_url, scope)
        resumed = cursor is not None and cursor.state == CURSOR_ACTIVE and bool(cursor.next_url)
        page_url: Optional[str] = cursor.next_url if resumed else api_url
        targets: List[DiscoveredTarget] = []
        visited: set = set()
        pages = 0
        stop: Optional[DiscoveryStop] = None
        while page_url is not None:
            if page_url in visited:
                stop = DiscoveryStop(
                    stage="api", entry=api_url, pages=pages, targets=len(targets),
                    stop=STOP_LOOP, complete=False, detail=f"接口下一页回到已访问地址：{page_url}",
                    cursor=self._cursor_key("api", api_url, scope),
                )
                break
            if pages >= self.effective_max_pages:
                stop = DiscoveryStop(
                    stage="api", entry=api_url, pages=pages, targets=len(targets),
                    stop=STOP_MAX_PAGES, complete=False,
                    detail=f"达到每入口页数上限 {self.effective_max_pages}",
                    next_url=page_url, cursor=self._cursor_key("api", api_url, scope),
                )
                break
            if len(targets) >= self.max_items:
                stop = DiscoveryStop(
                    stage="api", entry=api_url, pages=pages, targets=len(targets),
                    stop=STOP_MAX_ITEMS, complete=False,
                    detail=f"达到本次发现目标上限 {self.max_items}",
                    next_url=page_url, cursor=self._cursor_key("api", api_url, scope),
                )
                break
            visited.add(page_url)
            try:
                response = self.http.get(page_url, source_id=self.source.source_id)
            except BudgetStop as budget:
                self.budget_stop = budget
                stop = DiscoveryStop(
                    stage="api", entry=api_url, pages=pages, targets=len(targets),
                    stop=STOP_BUDGET, complete=False,
                    detail=f"{budget.reason}: {budget.message}", next_url=page_url,
                    cursor=self._cursor_key("api", api_url, scope),
                )
                break
            except FetchError as exc:
                if pages == 0 and not resumed:
                    raise
                stop = DiscoveryStop(
                    stage="api", entry=api_url, pages=pages, targets=len(targets),
                    stop=STOP_REQUEST_FAILED, complete=False,
                    detail=f"{exc.url}: {exc}", next_url=page_url,
                    cursor=self._cursor_key("api", api_url, scope),
                    error_type="http_error" if exc.status_code else "request_error",
                )
                break
            archived = self._archive(
                response,
                kind="discovery",
                discovery_method="api",
                referrer_url=None if page_url == api_url else api_url,
            )
            pages += 1
            try:
                payload = json.loads(decode_html(response.content))
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                raise DiscoveryContentError(
                    page_url,
                    f"接口响应解析失败：{exc}",
                    stage="api",
                    crawl_id=archived.crawl_id if archived else None,
                ) from exc
            items = []
            if isinstance(payload, list):
                items = payload
            elif isinstance(payload, dict) and isinstance(payload.get("items"), list):
                items = payload["items"]
            for item in items:
                if not isinstance(item, dict) or not item.get(url_field):
                    continue
                url = urljoin(page_url, str(item[url_field]))
                decision = self.registry.check_access(url, self.source.source_id)
                if not decision.allowed:
                    self.skipped.append(SkippedTarget(url, decision.reason, page_url))
                    continue
                targets.append(
                    DiscoveredTarget(
                        url=url,
                        discovery_method="api",
                        referrer_url=page_url,
                        title_hint=item.get(title_field),
                    )
                )
            next_page = _next_api_url(payload, page_url)
            if next_page is None:
                stop = DiscoveryStop(
                    stage="api", entry=api_url, pages=pages, targets=len(targets),
                    stop=STOP_END_OF_PAGES, complete=True,
                    detail="接口未声明下一页（该响应内为全部条目）",
                    cursor=self._cursor_key("api", api_url, scope),
                )
                break
            decision = self.registry.check_access(next_page, self.source.source_id)
            if not decision.allowed:
                self.skipped.append(SkippedTarget(next_page, decision.reason, page_url))
                stop = DiscoveryStop(
                    stage="api", entry=api_url, pages=pages, targets=len(targets),
                    stop=STOP_ACCESS_DENIED, complete=False,
                    detail=f"下一页被拒绝：{decision.reason}", next_url=next_page,
                    cursor=self._cursor_key("api", api_url, scope),
                )
                break
            page_url = next_page
        if stop is None:  # 理论上不可达：循环内每个出口都写入终止原因
            stop = DiscoveryStop(
                stage="api", entry=api_url, pages=pages, targets=len(targets),
                stop=STOP_END_OF_PAGES, complete=True,
            )
        self._record_stop(stop)
        self._update_cursor(stop, scope)
        return self._dedupe(targets)

    def attachments_from_html(self, content: bytes, page_url: str) -> List[DiscoveredTarget]:
        """正文附件候选；按规则排除的下载链接只做可解释计数，不下载、不扩范围。"""
        soup = BeautifulSoup(decode_html(content), "lxml")
        adapter = self.source.adapter
        targets = []
        excluded: dict = {}
        for anchor in soup.find_all("a", href=True):
            url = urljoin(page_url, anchor["href"])
            extension = _attachment_extension(url)
            if extension is None:
                other = _other_download_extension(url)
                if other is not None:
                    # 已知下载类扩展名但不在正文附件声明范围：只计数不下载。
                    key = f"extension_not_declared:{other}"
                    excluded[key] = excluded.get(key, 0) + 1
                continue
            if adapter.attachment_pattern and not re.search(adapter.attachment_pattern, url):
                key = f"adapter_pattern:{extension}"
                excluded[key] = excluded.get(key, 0) + 1
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
        for reason, count in sorted(excluded.items()):
            self.attachment_rule_exclusions.append(
                {"page": page_url, "reason": reason, "count": count, "rule": "attachment_filter"}
            )
        unique = self._dedupe(targets)
        duplicates = len(targets) - len(unique)
        if duplicates:
            self.attachment_duplicates.append({"page": page_url, "count": duplicates})
        return unique

    # ------------------------------------------------------------------ 内部实现
    def _paginate(
        self,
        *,
        stage: str,
        entry: str,
        scope: RunScope,
        start_url: Optional[str] = None,
        keyword: Optional[str] = None,
    ) -> List[DiscoveredTarget]:
        """列表/搜索分页遍历；每个出口都记录终止原因并更新发现游标。"""
        cursor = self._load_cursor(stage, entry, scope)
        resumed = cursor is not None and cursor.state == CURSOR_ACTIVE and bool(cursor.next_url)
        page_url: Optional[str] = start_url or entry
        if resumed:
            page_url = cursor.next_url
        targets: List[DiscoveredTarget] = []
        visited: set = set()
        pages = 0
        referrer: Optional[str] = None
        stop: DiscoveryStop
        while page_url is not None:
            key = self._cursor_key(stage, entry, scope)
            if page_url in visited:
                stop = DiscoveryStop(
                    stage=stage, entry=entry, pages=pages, targets=len(targets),
                    stop=STOP_LOOP, complete=False, detail=f"分页回到已访问页：{page_url}",
                    cursor=key,
                )
                break
            if pages >= self.effective_max_pages:
                stop = DiscoveryStop(
                    stage=stage, entry=entry, pages=pages, targets=len(targets),
                    stop=STOP_MAX_PAGES, complete=False,
                    detail=f"达到每入口页数上限 {self.effective_max_pages}", next_url=page_url, cursor=key,
                )
                break
            if len(targets) >= self.max_items:
                stop = DiscoveryStop(
                    stage=stage, entry=entry, pages=pages, targets=len(targets),
                    stop=STOP_MAX_ITEMS, complete=False,
                    detail=f"达到本次发现目标上限 {self.max_items}", next_url=page_url, cursor=key,
                )
                break
            visited.add(page_url)
            try:
                response = self.http.get(page_url, source_id=self.source.source_id)
            except BudgetStop as budget:
                self.budget_stop = budget
                stop = DiscoveryStop(
                    stage=stage, entry=entry, pages=pages, targets=len(targets),
                    stop=STOP_BUDGET, complete=False,
                    detail=f"{budget.reason}: {budget.message}", next_url=page_url, cursor=key,
                )
                break
            except FetchError as exc:
                if pages == 0 and not resumed:
                    raise  # 入口本身失败：由上层按请求失败记账
                stop = DiscoveryStop(
                    stage=stage, entry=entry, pages=pages, targets=len(targets),
                    stop=STOP_REQUEST_FAILED, complete=False,
                    detail=f"{exc.url}: {exc}", next_url=page_url, cursor=key,
                    error_type="http_error" if exc.status_code else "request_error",
                )
                break
            self._archive(
                response,
                kind="discovery",
                discovery_method=stage,
                keyword=keyword,
                referrer_url=referrer,
            )
            pages += 1
            page_targets, rule_matched = self._list_page_targets(
                response.content, response.final_url, stage
            )
            if not rule_matched:
                stop = DiscoveryStop(
                    stage=stage, entry=entry, pages=pages, targets=len(targets),
                    stop=STOP_SELECTOR_MISS, complete=False,
                    detail=f"适配选择器未命中：{self.source.adapter.list_link_selector}",
                    cursor=key,
                )
                break
            targets.extend(page_targets)
            next_page, blocked = self._next_page_url(
                response.content, response.final_url, entry=entry
            )
            if blocked:
                stop = DiscoveryStop(
                    stage=stage, entry=entry, pages=pages, targets=len(targets),
                    stop=STOP_ACCESS_DENIED, complete=False,
                    detail="下一页被访问边界或 robots 拒绝（见 skipped 记录）",
                    cursor=key,
                )
                break
            if next_page is None:
                if self.source.adapter.pagination_selector:
                    stop = DiscoveryStop(
                        stage=stage, entry=entry, pages=pages, targets=len(targets),
                        stop=STOP_PAGINATION_RULE_END, complete=True,
                        detail=(
                            "适配分页控件不存在（按适配规则视为终点）："
                            f"{self.source.adapter.pagination_selector}"
                        ),
                        cursor=key,
                    )
                else:
                    stop = DiscoveryStop(
                        stage=stage, entry=entry, pages=pages, targets=len(targets),
                        stop=STOP_END_OF_PAGES, complete=True,
                        detail="未发现下一页链接（站点/规则终点）", cursor=key,
                    )
                break
            referrer = response.final_url
            page_url = next_page
        else:  # pragma: no cover - 循环条件为 None 时直接结束
            stop = DiscoveryStop(
                stage=stage, entry=entry, pages=pages, targets=len(targets),
                stop=STOP_END_OF_PAGES, complete=True, cursor=self._cursor_key(stage, entry, scope),
            )
        if stage == "search" and scope.active:
            template = self.source.search_url_template or ""
            if any(placeholder in template for placeholder in DATE_PLACEHOLDERS):
                note = "查询模板按日期限定：覆盖范围由查询参数决定，不逐页按日期提前停止"
                if stop.complete and stop.stop == STOP_END_OF_PAGES:
                    stop = replace(stop, stop=STOP_DATE_SCOPED_QUERY, detail=note)
                else:
                    stop = replace(
                        stop, detail=((stop.detail + "；") if stop.detail else "") + note
                    )
        self._record_stop(stop)
        self._update_cursor(stop, scope)
        return targets

    def _archive(
        self,
        response: FetchResponse,
        *,
        kind: str,
        discovery_method: str,
        keyword: Optional[str] = None,
        referrer_url: Optional[str] = None,
    ) -> Optional[ArchivedResponse]:
        """成功业务响应先归档再解析；未注入归档器时（单元测试）跳过。"""
        if self.archiver is None:
            return None
        archived = self.archiver.archive(
            response,
            source_id=self.source.source_id,
            kind=kind,
            discovery_method=discovery_method,
            keyword=keyword,
            referrer_url=referrer_url,
        )
        if not archived.reused:
            self.archived_count += 1
        return archived

    def _record_stop(self, stop: DiscoveryStop) -> None:
        self.stops.append(stop)

    def _cursor_key(self, stage: str, entry: str, scope: RunScope) -> Optional[str]:
        if self.cursors is None:
            return None
        return cursor_key(
            source_id=self.source.source_id,
            stage=stage,
            entry=entry,
            scope_start_date=scope.start_date.isoformat() if scope.start_date else None,
        )

    def _load_cursor(self, stage: str, entry: str, scope: RunScope) -> Optional[DiscoveryCursor]:
        key = self._cursor_key(stage, entry, scope)
        if key is None:
            return None
        return self.cursors.get(key)

    def _update_cursor(self, stop: DiscoveryStop, scope: RunScope) -> None:
        key = self._cursor_key(stop.stage, stop.entry, scope)
        if key is None:
            return
        previous = self.cursors.get(key)
        cumulative_pages = (previous.pages_fetched if previous else 0) + stop.pages
        cumulative_targets = (previous.targets_found if previous else 0) + stop.targets
        if stop.complete or stop.stop in TERMINAL_STOPS:
            cursor = DiscoveryCursor(
                key=key,
                source_id=self.source.source_id,
                stage=stop.stage,
                entry=stop.entry,
                scope_start_date=scope.start_date.isoformat() if scope.start_date else None,
                next_url=None,
                state=CURSOR_COMPLETED,
                pages_fetched=cumulative_pages,
                targets_found=cumulative_targets,
                updated_at=self._now().isoformat(),
                note=f"{stop.stop}: {stop.detail or STOP_REASON_TEXT.get(stop.stop, '')}",
            )
        else:
            cursor = DiscoveryCursor(
                key=key,
                source_id=self.source.source_id,
                stage=stop.stage,
                entry=stop.entry,
                scope_start_date=scope.start_date.isoformat() if scope.start_date else None,
                next_url=stop.next_url,
                state=CURSOR_ACTIVE,
                pages_fetched=cumulative_pages,
                targets_found=cumulative_targets,
                updated_at=self._now().isoformat(),
                note=f"{stop.stop}: {stop.detail or STOP_REASON_TEXT.get(stop.stop, '')}",
            )
        self.cursors.save(cursor)

    def _list_page_targets(
        self, content: bytes, page_url: str, method: str
    ) -> Tuple[List[DiscoveredTarget], bool]:
        """按适配规则或通用范围提取列表页链接；返回 (目标, 规则是否命中)。"""
        soup = BeautifulSoup(decode_html(content), "lxml")
        adapter = self.source.adapter

        def collect(anchor_list) -> List[DiscoveredTarget]:
            found: List[DiscoveredTarget] = []
            for anchor in anchor_list:
                if "next" in (anchor.get("rel") or []):
                    continue
                url = urljoin(page_url, anchor["href"])
                if adapter.list_link_pattern and not re.search(adapter.list_link_pattern, url):
                    continue
                if adapter.list_link_rewrite:
                    url = _apply_link_rewrite(adapter.list_link_rewrite, url, page_url)
                if _is_fragment_or_action(url):
                    continue
                if url.split("#")[0] == page_url.split("#")[0]:
                    continue
                if _attachment_extension(url) is not None:
                    continue
                decision = self.registry.check_access(url, self.source.source_id)
                if not decision.allowed:
                    reason = SkippedTarget(url, decision.reason, page_url)
                    if not any(
                        item.url == reason.url and item.reason == reason.reason
                        for item in self.skipped
                    ):
                        self.skipped.append(reason)
                    continue
                found.append(
                    DiscoveredTarget(
                        url=url,
                        discovery_method=method,
                        referrer_url=page_url,
                        title_hint=" ".join(anchor.get_text(" ", strip=True).split()) or None,
                    )
                )
            return found

        if adapter.list_link_selector:
            anchors = _selected_anchors(soup, adapter.list_link_selector)
            if anchors is None:
                reason = f"adapter_list_selector_miss:{adapter.list_link_selector}"
                self.skipped.append(SkippedTarget(page_url, reason, page_url))
                self.selector_misses.append(
                    {"url": page_url, "selector": adapter.list_link_selector, "method": method}
                )
                logger.warning(
                    "列表选择器未命中，本页不发现目标 url=%s selector=%s",
                    page_url,
                    adapter.list_link_selector,
                )
                return [], False
            targets = collect(anchors)
        else:
            scope = soup.find("main") or soup.find("article") or soup.body or soup
            targets = collect(scope.find_all("a", href=True))
            if not targets and scope is not soup:
                # 结构不完整（如双 <html>、正文在 body 之外）时通用范围会漏掉文档链接，
                # 若就此结束会把“范围没覆盖”冒充真实零结果；按整文档兜底并显式记录。
                fallback = collect(soup.find_all("a", href=True))
                if fallback:
                    logger.warning(
                        "通用列表范围未取到目标，按整文档兜底 url=%s scope=%s",
                        page_url,
                        scope.name,
                    )
                    self.scope_fallbacks.append(
                        {"url": page_url, "method": method, "scope": scope.name}
                    )
                    targets = fallback
        return self._dedupe(targets), True

    def _next_page_url(
        self, content: bytes, page_url: str, entry: Optional[str] = None
    ) -> Tuple[Optional[str], bool]:
        """下一页地址；blocked 表示存在候选但被访问边界/robots 拒绝。"""
        soup = BeautifulSoup(decode_html(content), "lxml")
        adapter = self.source.adapter
        if adapter.pagination_selector:
            element = soup.select_one(adapter.pagination_selector)
            if element is not None and not element.get("href"):
                element = element.find(["a", "link"], href=True)
            href = element.get("href") if element is not None else None
            if not href:
                return None, False  # 适配规则即分页终止条件：控件不存在则停止翻页
            candidate = urljoin(page_url, str(href))
            if adapter.pagination_merge_entry_params:
                candidate = _merge_entry_url(entry or page_url, page_url, candidate)
            if candidate.split("#")[0] == page_url.split("#")[0]:
                return None, False
            decision = self.registry.check_access(candidate, self.source.source_id)
            if not decision.allowed:
                self.skipped.append(SkippedTarget(candidate, decision.reason, page_url))
                return None, True
            return candidate, False
        for element in list(soup.find_all("a", href=True)) + list(soup.find_all("link", href=True)):
            if "next" not in (element.get("rel") or []):
                continue
            candidate = urljoin(page_url, element["href"])
            if candidate.split("#")[0] == page_url.split("#")[0]:
                continue
            decision = self.registry.check_access(candidate, self.source.source_id)
            if decision.allowed:
                return candidate, False
            self.skipped.append(SkippedTarget(candidate, decision.reason, page_url))
            return None, True
        return None, False

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


def _merge_entry_url(entry: str, page_url: str, target: str) -> str:
    """按入口形态派生下一页 URL：路径与入口参数沿用入口，控件参数覆盖。

    用于站点分页控件省略入口参数、或链接路径与入口大小写不一致的来源
    （IN-02：控件只带 page=N；缺 PageSize/sortBy 时端点返回 “No Record Found”）。
    只做确定性合并：不改域名、不新增入口未声明的参数。
    """
    target_parts = urlsplit(target)
    entry_parts = urlsplit(entry)
    query = dict(parse_qsl(entry_parts.query, keep_blank_values=True))
    query.update(dict(parse_qsl(target_parts.query, keep_blank_values=True)))
    scheme = target_parts.scheme or entry_parts.scheme
    netloc = entry_parts.netloc or target_parts.netloc
    path = entry_parts.path or target_parts.path
    return urlunsplit((scheme, netloc, path, urlencode(query), ""))


def _next_api_url(payload, base_url: str) -> Optional[str]:
    """接口响应自身声明的下一页；只接受明确的字符串字段，不猜测端点。"""
    if not isinstance(payload, dict):
        return None
    for key in ("next", "next_url", "nextPage", "next_page"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return urljoin(base_url, value.strip())
    return None


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


def _other_download_extension(url: str) -> Optional[str]:
    path = urlsplit(url).path.lower()
    for extension in OTHER_DOWNLOAD_EXTENSIONS:
        if path.endswith(extension):
            return extension
    return None


def _is_fragment_or_action(url: str) -> bool:
    parts = urlsplit(url)
    return parts.scheme not in ("http", "https") or not parts.netloc


def _apply_link_rewrite(
    rewrite: Sequence[Tuple[str, str]], url: str, page_url: str
) -> str:
    """按来源登记的等价形态改写列表目标 URL（第一条命中生效）。

    规则作用于链接解析后的绝对 URL（re.sub 语义）；替换结果先按列表页 URL 归一化，
    相对路径与绝对路径都可使用；跨域改写需在正则中匹配完整 URL，改写结果同样要
    通过来源边界检查，越界按跳过记录。
    """
    for pattern, replacement in rewrite:
        if re.search(pattern, url):
            return urljoin(page_url, re.sub(pattern, replacement, url, count=1))
    return url
