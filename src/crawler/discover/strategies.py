"""按站发现策略抽象与实现（本轮新增；T005/T026）。

Discoverer 保持为共享发现引擎（列表分页、搜索、sitemap、API、附件、边界与跳过记录）；
本模块在其上定义可替换的策略接口、来源发现计划与结果状态：

- DiscoveryStrategy（abc）：一次策略运行，输入 DiscoveryRequest，输出 DiscoveryResult；
- ListDiscovery / SearchDiscovery / SitemapDiscovery / ApiDiscovery：复用 Discoverer 的实现；
- resolve_strategy：按来源配置与本轮参数选择实现，来源未声明的方式返回未实现策略。

所有策略共用同一个 HttpClient，因此共享 robots 判定、访问边界、重定向逐跳检查、
限速、重试与请求预算；策略本身不再新建客户端，也不放宽任何访问规则。

状态分别记录，不以空结果冒充成功：

  ok                 命中规则并返回候选
  zero_results       命中规则但确实没有候选（真实零结果）
  selector_miss      适配选择器未命中（配置与页面不匹配）
  not_implemented    来源未声明/未核验该发现方式，或缺少必需入口
  request_error      网络或 HTTP 错误（由调用方写失败账，不写成零结果）

访问限制（robots 拒绝、域外链接）仍由 Discoverer 逐条记入 skipped，原因保持不变。
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Sequence, Tuple
from urllib.parse import quote_plus

from crawler.config.registry import SourceConfig, SourceRegistry
from crawler.discover.discoverer import DiscoveredTarget, Discoverer, SkippedTarget
from crawler.fetch.http_client import HttpClient
from crawler.schedule.scope import RunScope

logger = logging.getLogger(__name__)

STAGE_LIST = "list"
STAGE_SEARCH = "search"
STAGE_SITEMAP = "sitemap"
STAGE_API = "api"
DISCOVERY_STAGES = (STAGE_LIST, STAGE_SEARCH, STAGE_SITEMAP, STAGE_API)

# 显式 --url 指定的目标：不是站内发现策略，按操作者明确意图直接采集（manifest.discovery_method=manual）。
# 不加入 DISCOVERY_STAGES，来源配置不能声明它，也不参与按站适配状态判定。
STAGE_MANUAL = "manual"

STATUS_OK = "ok"
STATUS_ZERO_RESULTS = "zero_results"
STATUS_SELECTOR_MISS = "selector_miss"
STATUS_NOT_IMPLEMENTED = "not_implemented"
STATUS_REQUEST_ERROR = "request_error"

# 模板占位符：{query} 关键词；{start_date}/{end_date} 与 {year}/{month} 日期查询。
DATE_PLACEHOLDERS = ("{start_date}", "{end_date}", "{year}", "{month}", "{end_year}", "{end_month}")


@dataclass(frozen=True)
class DiscoveryRequest:
    """一次发现请求：方式、入口与运行范围。"""

    stage: str
    scope: RunScope = RunScope()
    entries: Tuple[str, ...] = ()
    keyword: Optional[str] = None
    sitemap_url: Optional[str] = None
    api_url: Optional[str] = None
    max_items: int = 100

    def __post_init__(self) -> None:
        if self.stage not in DISCOVERY_STAGES:
            raise ValueError(f"未知发现方式：{self.stage!r}；允许 {list(DISCOVERY_STAGES)}")


@dataclass
class DiscoveryResult:
    """一次策略运行的结果与状态；targets/skipped 只含本次新增项。"""

    stage: str
    strategy: str
    status: str
    targets: List[DiscoveredTarget] = field(default_factory=list)
    skipped: List[SkippedTarget] = field(default_factory=list)
    note: str = ""

    @property
    def ok(self) -> bool:
        return self.status in (STATUS_OK, STATUS_ZERO_RESULTS)

    def as_row(self) -> dict:
        row = {
            "stage": self.stage,
            "strategy": self.strategy,
            "status": self.status,
            "targets": len(self.targets),
            "skipped": len(self.skipped),
        }
        if self.note:
            row["note"] = self.note
        return row


@dataclass(frozen=True)
class DiscoveryContext:
    """策略共享的上下文；发现能力全部来自既有 Discoverer 与 HttpClient。"""

    source: SourceConfig
    registry: SourceRegistry
    http: HttpClient
    discoverer: Discoverer
    scope: RunScope = RunScope()
    max_items: int = 100


class DiscoveryStrategy(ABC):
    """发现策略接口：实现类只负责把一种站内发现方式转成候选目标。"""

    stage: str = ""
    name: str = ""

    @abstractmethod
    def discover(self, request: DiscoveryRequest, context: DiscoveryContext) -> DiscoveryResult:
        """执行一次发现；不得吞掉访问限制或伪造成功。"""

    # -- 共享辅助：复用同一 Discoverer，按调用前后差集报告跳过与选择器未命中 --

    def _run(
        self,
        context: DiscoveryContext,
        action,
        *,
        note_if_empty: str = "",
    ) -> DiscoveryResult:
        skipped_before = len(context.discoverer.skipped)
        misses_before = len(context.discoverer.selector_misses)
        targets = list(action())
        skipped = list(context.discoverer.skipped[skipped_before:])
        misses = list(context.discoverer.selector_misses[misses_before:])
        if misses:
            detail = "; ".join(
                f"{item['selector']}@{item['url']}" for item in misses if item.get("selector")
            )
            return DiscoveryResult(
                stage=self.stage,
                strategy=self.name,
                status=STATUS_SELECTOR_MISS,
                targets=targets,
                skipped=skipped,
                note=f"适配选择器未命中：{detail}" if detail else "适配选择器未命中",
            )
        status = STATUS_OK if targets else STATUS_ZERO_RESULTS
        return DiscoveryResult(
            stage=self.stage,
            strategy=self.name,
            status=status,
            targets=targets,
            skipped=skipped,
            note=note_if_empty if not targets else "",
        )


class ListDiscovery(DiscoveryStrategy):
    """栏目/列表页发现：入口 → 列表页 → 文档链接 → 分页（逐来源规则）。"""

    stage = STAGE_LIST
    name = "list_pagination"

    def discover(self, request: DiscoveryRequest, context: DiscoveryContext) -> DiscoveryResult:
        entries = tuple(request.entries) or tuple(context.source.entry_urls)
        if not entries:
            return DiscoveryResult(
                stage=self.stage,
                strategy=self.name,
                status=STATUS_NOT_IMPLEMENTED,
                note="来源未配置入口 URL，本次也未提供 --entry-url：未实现该发现方式",
            )
        return self._run(
            context,
            lambda: context.discoverer.discover_list(entries),
            note_if_empty="列表页规则命中但未发现文档链接（真实零结果）",
        )


class SearchDiscovery(DiscoveryStrategy):
    """站内搜索发现：需要已核验的搜索模板；日期占位符按运行范围填充。"""

    stage = STAGE_SEARCH
    name = "site_search"

    def discover(self, request: DiscoveryRequest, context: DiscoveryContext) -> DiscoveryResult:
        template = context.source.search_url_template
        if not template:
            return DiscoveryResult(
                stage=self.stage,
                strategy=self.name,
                status=STATUS_NOT_IMPLEMENTED,
                note="来源未配置 search_url_template：未实现该发现方式",
            )
        if not request.keyword:
            return DiscoveryResult(
                stage=self.stage,
                strategy=self.name,
                status=STATUS_NOT_IMPLEMENTED,
                note="未提供搜索关键词",
            )
        if any(placeholder in template for placeholder in DATE_PLACEHOLDERS) and not context.scope.active:
            return DiscoveryResult(
                stage=self.stage,
                strategy=self.name,
                status=STATUS_NOT_IMPLEMENTED,
                note="搜索模板含日期占位符，但本次未提供 --start-date；不静默改用无日期模板",
            )
        url = render_search_url(template, request.keyword, context.scope)
        keyword = request.keyword
        return self._run(
            context,
            lambda: [
                replace_keyword(target, keyword)
                for target in context.discoverer.discover_search(keyword, url=url)
            ],
            note_if_empty="搜索结果规则命中但未发现文档链接（真实零结果）",
        )


class SitemapDiscovery(DiscoveryStrategy):
    """sitemap 发现：入口来自本轮显式参数（来源未声明时由调用方记录）。"""

    stage = STAGE_SITEMAP
    name = "sitemap"

    def discover(self, request: DiscoveryRequest, context: DiscoveryContext) -> DiscoveryResult:
        if not request.sitemap_url:
            return DiscoveryResult(
                stage=self.stage,
                strategy=self.name,
                status=STATUS_NOT_IMPLEMENTED,
                note="未提供 sitemap 地址",
            )
        return self._run(
            context,
            lambda: context.discoverer.discover_sitemap(request.sitemap_url),
            note_if_empty="sitemap 解析成功但没有可用条目（真实零结果）",
        )


class ApiDiscovery(DiscoveryStrategy):
    """结构化接口发现：入口来自本轮显式参数或来源配置。"""

    stage = STAGE_API
    name = "structured_api"

    def discover(self, request: DiscoveryRequest, context: DiscoveryContext) -> DiscoveryResult:
        if not request.api_url:
            return DiscoveryResult(
                stage=self.stage,
                strategy=self.name,
                status=STATUS_NOT_IMPLEMENTED,
                note="未提供结构化接口地址",
            )
        return self._run(
            context,
            lambda: context.discoverer.discover_api(request.api_url),
            note_if_empty="接口返回成功但没有可用条目（真实零结果）",
        )


class UnimplementedDiscovery(DiscoveryStrategy):
    """来源未声明/未核验的发现方式：显式未实现，不发请求、不返回空结果冒充成功。"""

    name = "unimplemented"

    def __init__(self, stage: str, reason: str) -> None:
        self.stage = stage
        self.reason = reason

    def discover(self, request: DiscoveryRequest, context: DiscoveryContext) -> DiscoveryResult:
        return DiscoveryResult(
            stage=self.stage,
            strategy=self.name,
            status=STATUS_NOT_IMPLEMENTED,
            note=self.reason,
        )


IMPLEMENTATIONS: Dict[str, DiscoveryStrategy] = {
    STAGE_LIST: ListDiscovery(),
    STAGE_SEARCH: SearchDiscovery(),
    STAGE_SITEMAP: SitemapDiscovery(),
    STAGE_API: ApiDiscovery(),
}


def declared_stages(source: SourceConfig) -> Tuple[str, ...]:
    """来源已声明（已实现/已核验）的发现方式。

    显式配置 `adapter.discovery` 优先；缺省按既有配置推断：栏目列表始终可用，
    配置了搜索模板时搜索可用。sitemap/API 不在缺省集合内——它们需要逐来源核验，
    本轮显式提供地址时才运行（见 resolve_strategy）。
    """
    configured = source.adapter.discovery
    if configured is not None:
        return tuple(configured)
    stages = [STAGE_LIST]
    if source.search_url_template:
        stages.append(STAGE_SEARCH)
    return tuple(stages)


def resolve_strategy(
    source: SourceConfig, stage: str, *, explicit_entry: bool = False
) -> DiscoveryStrategy:
    """选择该来源本次运行的策略实现。

    `explicit_entry` 表示本轮由命令行显式给出了该方式的入口（--entry-url/--keyword/--sitemap/--api）：
    此时按用户明确意图运行通用实现（供有限核验与逐站适配），调用方仍标记来源未声明该方式，
    便于逐站核验收口；未显式给出入口时保守返回未实现，不发请求。
    """
    stages = declared_stages(source)
    if stage in stages:
        return IMPLEMENTATIONS[stage]
    if explicit_entry and stage in (STAGE_LIST, STAGE_SITEMAP, STAGE_API, STAGE_SEARCH):
        return IMPLEMENTATIONS[stage]
    return UnimplementedDiscovery(
        stage,
        f"来源 {source.source_id} 未声明发现方式 {stage}（adapter.discovery={list(stages)}）：未实现",
    )


def render_search_url(template: str, keyword: str, scope: RunScope) -> str:
    """填充搜索模板：关键词与日期占位符；日期只来自运行范围，不猜测当天。"""
    url = template.replace("{query}", quote_plus(keyword))
    if not scope.start_date:
        return url
    start = scope.start_date
    replacements = {
        "{start_date}": start.isoformat(),
        "{end_date}": start.isoformat(),
        "{year}": f"{start.year:04d}",
        "{month}": f"{start.month:02d}",
        "{end_year}": f"{start.year:04d}",
        "{end_month}": f"{start.month:02d}",
    }
    for placeholder, value in replacements.items():
        url = url.replace(placeholder, value)
    return url


def replace_keyword(target: DiscoveredTarget, keyword: str) -> DiscoveredTarget:
    return DiscoveredTarget(
        url=target.url,
        discovery_method=target.discovery_method,
        referrer_url=target.referrer_url,
        keyword=keyword,
        title_hint=target.title_hint,
    )


def discovery_rows(results: Sequence[DiscoveryResult]) -> List[dict]:
    return [result.as_row() for result in results]


def summarize_discovery(results: Sequence[DiscoveryResult]) -> dict:
    """按状态汇总本轮发现；未实现与零结果分开计数。"""
    counts: Dict[str, int] = {}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1
    return {
        "runs": len(results),
        "targets": sum(len(result.targets) for result in results),
        "by_status": dict(sorted(counts.items())),
    }
