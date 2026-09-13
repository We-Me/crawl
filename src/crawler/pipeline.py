"""最小采集闭环编排：发现 → 获取 → 原件与账本 → 解析 → 标准化（T009）。

单进程同步执行；每页在归档与账本完成后才进入解析，文档与块全部校验后才
成组提交。失败按操作记录，不静默丢弃，也不以失败掩盖已成功获取的原件。
collect/resume 可挂统一的 RunBudget：请求上限或截止时间到达时停止后续请求，
保留已成功归档的原件、账本、文档与块，并以 stop_reason 报告未完成部分。
"""

from __future__ import annotations

import json
import logging
import hashlib
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple
from urllib.parse import urlsplit

from crawler.config.registry import SourceRegistry
from crawler.config.settings import Settings
from crawler.discover.discoverer import (
    ATTACHMENT_EXTENSIONS,
    Discoverer,
    DiscoveredTarget,
    SkippedTarget,
)
from crawler.discover.strategies import (
    STATUS_NOT_IMPLEMENTED,
    STATUS_OK,
    STATUS_REQUEST_ERROR,
    STAGE_API,
    STAGE_LIST,
    STAGE_MANUAL,
    STAGE_SEARCH,
    STAGE_SITEMAP,
    DiscoveryContext,
    DiscoveryRequest,
    DiscoveryResult,
    declared_stages,
    resolve_strategy,
)
from crawler.fetch.downloader import Downloader
from crawler.fetch.budget import BudgetStop, RunBudget
from crawler.fetch.http_client import FetchError, HttpClient, RobotsDisallowed
from crawler.normalize.block_schema import build_blocks
from crawler.normalize.document_schema import build_document
from crawler.normalize.metadata_normalizer import normalize_page
from crawler.output.documents_writer import DocumentsWriter
from crawler.output.failures_writer import FailureWriter
from crawler.output.manifest_writer import ManifestWriter
from crawler.output.layout import DeliveryLayout
from crawler.output.raw_store import RawStore
from crawler.output.jsonl import read_jsonl
from crawler.parser.dispatcher import parse_attachment
from crawler.parser.html_parser import decode_html, parse_html
from crawler.parser.legacy_parser import Converter
from crawler.parser.parsed_page import ParsedBlock, ParsedPage
from crawler.dedup.fingerprint import text_hash
from crawler.fetch.retry import (
    MANUAL as RETRY_MANUAL,
    REFETCH,
    REPARSE,
    RecoveryTask,
    RetryPolicy,
    build_recovery_plan,
    plan_is_ready,
    plan_retry,
)
from crawler.monitor.failures import FailureLedger
from crawler.monitor.logger import configure_run_logging, log_run_context
from crawler.monitor.metrics import (
    build_metrics,
    duplicate_stats_from_files,
    output_stats,
    write_metrics,
)
from crawler.schedule.incremental import plan_incremental
from crawler.schedule.scope import RunScope, ScopeConfigError, parse_start_date
from crawler.schedule.state import IncrementalStateStore
from crawler.util.paths import PathSafetyError, sanitize_filename

logger = logging.getLogger(__name__)

HTML_CONTENT_TYPES = ("text/html", "application/xhtml+xml")

# 正文还原上限：分页正文最多合并 5 个部分（含首部分），防止错误跟随翻页链接。
MAX_BODY_PARTS = 5
# 接口正文候选字段：按顺序取第一个非空字符串，不做语义推断。
BODY_API_TEXT_KEYS = ("body", "content", "body_html", "html", "full_text", "text")
BODY_API_CONTAINER_KEYS = ("data", "result", "article")


@dataclass
class RunCounters:
    requests: int = 0
    resources: int = 0
    documents: int = 0
    blocks: int = 0
    failures: int = 0
    skipped: int = 0
    not_modified: int = 0
    out_of_window: int = 0


@dataclass
class RunReport:
    source_id: str
    counters: RunCounters = field(default_factory=RunCounters)
    failures: List[dict] = field(default_factory=list)
    skipped: List[SkippedTarget] = field(default_factory=list)
    documents: List[str] = field(default_factory=list)
    discovery: List[DiscoveryResult] = field(default_factory=list)
    scope: RunScope = RunScope()
    date_decisions: List[dict] = field(default_factory=list)
    metrics: Optional[dict] = None
    stop_reason: Optional[str] = None
    stop_message: str = ""
    unprocessed: Optional[int] = None
    budget: Optional[dict] = None


@dataclass
class BodyExpansion:
    """正文还原结果：合并后的页面、各附加原件与未完成原因。"""

    page: ParsedPage
    extra_crawl_ids: List[str] = field(default_factory=list)
    extra_pages: List[Tuple[bytes, str]] = field(default_factory=list)
    parts: int = 1
    incomplete: Optional[str] = None
    stop: Optional[BudgetStop] = None


@dataclass
class RecoveryReport:
    source_id: str
    counters: RunCounters = field(default_factory=RunCounters)
    recovered: List[dict] = field(default_factory=list)
    skipped: List[dict] = field(default_factory=list)
    manual: List[dict] = field(default_factory=list)
    pending: List[dict] = field(default_factory=list)
    failures: List[dict] = field(default_factory=list)
    stop_reason: Optional[str] = None
    stop_message: str = ""
    unprocessed: Optional[int] = None
    budget: Optional[dict] = None


class CrawlPipeline:
    def __init__(
        self,
        registry: SourceRegistry,
        data_dir: Path,
        http: Optional[HttpClient] = None,
        now: Optional[Callable[[], datetime]] = None,
        state_store: Optional[IncrementalStateStore] = None,
        settings: Optional[Settings] = None,
        duplicate_threshold: Optional[float] = None,
        legacy_converter: Optional[Converter] = None,
    ) -> None:
        """编排一次采集/补抓；legacy_converter 用于替换旧式 DOC/XLS 转换器。

        不传时用系统 LibreOffice（parser.legacy_parser.soffice_converter）；注入点与
        parse_legacy(converter=...) 一致，供无组件环境或后续替换实现使用。
        """
        self.registry = registry
        self.data_dir = Path(data_dir)
        self.layout = DeliveryLayout(self.data_dir)
        self.settings = settings
        self.duplicate_threshold = duplicate_threshold
        self.legacy_converter = legacy_converter
        self.http = http or HttpClient(registry)
        self.downloader = Downloader(self.http)
        self.store = RawStore(self.data_dir)
        self.manifest = ManifestWriter(self.data_dir)
        self.failures = FailureWriter(self.data_dir)
        self.writer = DocumentsWriter(self.data_dir)
        self.state = state_store or IncrementalStateStore(self.data_dir)
        self.failures_ledger = FailureLedger(self.data_dir)
        self.now = now or (lambda: datetime.now(timezone.utc).astimezone())
        self._sequences: dict = {}
        # 本次运行范围：失败记录与补抓计划据此保留原窗口（恢复不混入新窗口）。
        self._run_scope: RunScope = RunScope()

    def collect(
        self,
        source_id: str,
        *,
        entry_urls: Optional[Sequence[str]] = None,
        search_keywords: Sequence[str] = (),
        sitemap_urls: Sequence[str] = (),
        api_urls: Sequence[str] = (),
        manual_urls: Sequence[str] = (),
        include_attachments: bool = True,
        max_items: int = 100,
        budget: Optional[RunBudget] = None,
        scope: Optional[RunScope] = None,
    ) -> RunReport:
        """按来源执行一次采集；scope 为本次运行范围（起始日期下界）。"""
        source = self.registry.get(source_id)
        if not source.enabled:
            raise ValueError(f"来源未启用，不能采集：{source_id}")
        scope = scope or RunScope()
        self._run_scope = scope
        started = self.now()
        self.layout.ensure()
        configure_run_logging(self.data_dir)
        if self.settings is not None:
            log_run_context(logger, self.settings)
        before = output_stats(self.data_dir)
        requests_before = self.http.request_attempts
        report = RunReport(source_id=source_id)
        report.scope = scope
        if budget is not None:
            budget.start()
            self.http.attach_budget(budget)
            report.budget = budget
        discoverer = Discoverer(self.http, self.registry, source, max_items=max_items)
        context = DiscoveryContext(
            source=source,
            registry=self.registry,
            http=self.http,
            discoverer=discoverer,
            scope=scope,
            max_items=max_items,
        )
        moment = self.now()
        crawl_date = moment.date().isoformat()
        crawl_time = moment.isoformat()

        targets: List[DiscoveredTarget] = []
        planned = 0
        processed = 0
        try:
            default_list = not (
                manual_urls
                and entry_urls is None
                and not (search_keywords or sitemap_urls or api_urls)
            )
            for request in self._discovery_requests(
                entry_urls,
                search_keywords,
                sitemap_urls,
                api_urls,
                scope,
                max_items,
                include_default_list=default_list,
            ):
                result = self._run_discovery(report, request, context)
                report.discovery.append(result)
                targets.extend(result.targets)
            if any(
                result.status == STATUS_NOT_IMPLEMENTED for result in report.discovery
            ):
                logger.warning(
                    "来源存在未实现的发现方式 source=%s 明细=%s",
                    source_id,
                    [result.as_row() for result in report.discovery],
                )

            if manual_urls:
                targets.extend(self._manual_targets(report, source, manual_urls))
            selected = targets[:max_items]
            planned = len(selected)
            for target in selected:
                self._collect_target(
                    source,
                    discoverer,
                    target,
                    crawl_date,
                    crawl_time,
                    include_attachments,
                    report,
                    scope,
                )
                processed += 1
        except BudgetStop as stop:
            report.stop_reason = stop.reason
            report.stop_message = stop.message
            logger.warning("采集按预算停止 reason=%s message=%s", stop.reason, stop.message)
        report.unprocessed = planned - processed if planned else None
        # 发现阶段的跳过已随策略结果并入；采集阶段（如附件发现）新写入
        # discoverer.skipped 的条目在此补记，避免重复计数。
        accounted = sum(len(result.skipped) for result in report.discovery)
        if len(discoverer.skipped) > accounted:
            report.skipped.extend(discoverer.skipped[accounted:])
        report.counters.skipped = len(report.skipped)
        report.metrics = self._finish_run(
            report,
            kind="collect",
            started_at=started.isoformat(),
            finished_at=self.now().isoformat(),
            before=before,
            requests_before=requests_before,
            request_controls=self._request_controls(source),
        )
        return report

    def _manual_targets(self, report, source, manual_urls: Sequence[str]):
        """把显式 --url 转成发现目标；越界或 robots 规则内的 URL 只记跳过，不请求。"""
        result = DiscoveryResult(
            stage=STAGE_MANUAL,
            strategy="manual_url",
            status=STATUS_OK,
            note="显式 --url：按操作者指定 URL 直接采集（manifest.discovery_method=manual）",
        )
        for url in manual_urls:
            decision = self.registry.check_access(url, source.source_id)
            if not decision.allowed:
                result.skipped.append(SkippedTarget(url, decision.reason, None))
                continue
            result.targets.append(DiscoveredTarget(url=url, discovery_method="manual"))
        report.discovery.append(result)
        report.skipped.extend(result.skipped)
        return result.targets

    @staticmethod
    def _discovery_requests(
        entry_urls: Optional[Sequence[str]],
        search_keywords: Sequence[str],
        sitemap_urls: Sequence[str],
        api_urls: Sequence[str],
        scope: RunScope,
        max_items: int,
        include_default_list: bool = True,
    ) -> List[DiscoveryRequest]:
        """把本轮参数转成发现请求；未给出的方式不发起（不隐式扩大范围）。

        `include_default_list=False` 用于只给了 --url 的显式采集：不隐式跑来源入口，
        避免把“按给定 URL 取一页”扩大成一次栏目采集。
        """
        requests: List[DiscoveryRequest] = []
        if include_default_list and (entry_urls is None or len(entry_urls) > 0):
            requests.append(
                DiscoveryRequest(
                    stage=STAGE_LIST,
                    scope=scope,
                    entries=tuple(entry_urls or ()),
                    max_items=max_items,
                )
            )
        for keyword in search_keywords:
            requests.append(
                DiscoveryRequest(
                    stage=STAGE_SEARCH, scope=scope, keyword=keyword, max_items=max_items
                )
            )
        for sitemap_url in sitemap_urls:
            requests.append(
                DiscoveryRequest(
                    stage=STAGE_SITEMAP, scope=scope, sitemap_url=sitemap_url, max_items=max_items
                )
            )
        for api_url in api_urls:
            requests.append(
                DiscoveryRequest(
                    stage=STAGE_API, scope=scope, api_url=api_url, max_items=max_items
                )
            )
        return requests

    def _run_discovery(
        self,
        report: RunReport,
        request: DiscoveryRequest,
        context: DiscoveryContext,
    ) -> DiscoveryResult:
        """执行一个发现策略；访问受限与请求错误分别记账，不冒充零结果。"""
        strategy = resolve_strategy(
            context.source,
            request.stage,
            explicit_entry=bool(
                request.entries or request.keyword or request.sitemap_url or request.api_url
            ),
        )
        try:
            result = strategy.discover(request, context)
        except RobotsDisallowed as exc:
            reason = f"robots_disallowed: {exc.rule or exc}"
            report.skipped.append(SkippedTarget(exc.url, reason))
            return DiscoveryResult(
                stage=request.stage,
                strategy=strategy.name,
                status="access_restricted",
                note=reason,
            )
        except FetchError as exc:
            self._record_failure(
                report,
                source_id=context.source.source_id,
                url=exc.url,
                stage="discover",
                error_type="http_error" if exc.status_code else "request_error",
                message=str(exc),
                attempts=exc.attempts,
                retryable=exc.retryable,
            )
            return DiscoveryResult(
                stage=request.stage,
                strategy=strategy.name,
                status=STATUS_REQUEST_ERROR,
                note=str(exc),
            )
        if (
            request.stage not in declared_stages(context.source)
            and result.status != STATUS_NOT_IMPLEMENTED
        ):
            # 显式入口可运行通用实现（有限核验/逐站适配），但必须标明来源尚未声明该方式，
            # 不把一次显式核验记成“已实现”。
            marker = "来源未声明该发现方式，本轮按显式入口运行通用实现（未计入已实现）"
            result.note = f"{result.note}；{marker}" if result.note else marker
        report.skipped.extend(result.skipped)
        return result

    @staticmethod
    def _request_controls(source) -> dict:
        """请求控制参数分别建模：速率按来源执行，并发上限按来源声明（AT-023）。

        当前实现是单进程同步执行，生效并发恒为 1；来源声明的 max_concurrency 是上限，
        不换算成速率，也不冒充已生效的并发。两者随 metrics 一起落盘供对账。
        """
        return {
            "request_rate_per_second": float(source.request_rate_per_second),
            "max_concurrency_declared": int(source.max_concurrency),
            "effective_concurrency": 1,
            "note": "单进程同步执行；并发上限按来源声明，速率与并发分别建模",
        }

    def _finish_run(
        self,
        report: RunReport,
        *,
        kind: str,
        started_at: str,
        finished_at: str,
        before,
        expected_deltas: Optional[dict] = None,
        requests_before: Optional[int] = None,
        request_controls: Optional[dict] = None,
    ) -> dict:
        """写出日志计数与 metrics.json，并核对本次运行的交付增量。"""
        after = output_stats(self.data_dir)
        if requests_before is not None:
            report.counters.requests = self.http.request_attempts - requests_before
        duplicates = duplicate_stats_from_files(
            self.data_dir, threshold=self.duplicate_threshold
        )
        budget_row = report.budget
        if budget_row is None and self.http.budget is not None:
            # 直接给客户端挂了预算、未显式传给 collect/resume 时，按实际生效的预算记录。
            budget_row = self.http.budget.as_row()
        if isinstance(budget_row, RunBudget):
            budget_row = budget_row.as_row()
        report.budget = budget_row
        counters = {
            "requests": report.counters.requests,
            "resources": report.counters.resources,
            "documents": report.counters.documents,
            "blocks": report.counters.blocks,
            "failures": report.counters.failures,
            "skipped": report.counters.skipped,
            "not_modified": report.counters.not_modified,
            "out_of_window": report.counters.out_of_window,
        }
        metrics = build_metrics(
            source_id=report.source_id,
            kind=kind,
            started_at=started_at,
            finished_at=finished_at,
            counters=counters,
            before=before,
            after=after,
            failures=report.failures,
            skipped=report.skipped,
            duplicates=duplicates,
            request_controls=request_controls,
            expected_deltas=expected_deltas,
            stop_reason=report.stop_reason,
            stop_message=report.stop_message,
            unprocessed=report.unprocessed,
            budget=budget_row,
            scope=report.scope.as_row(),
            discovery=[result.as_row() for result in report.discovery],
            date_decisions=report.date_decisions,
        )
        write_metrics(self.data_dir, metrics)
        logger.info(
            "运行汇总 kind=%s source=%s run_id=%s status=%s requests=%d resources=%d "
            "documents=%d blocks=%d failures=%d skipped=%d not_modified=%d reconciliation_ok=%s",
            kind,
            report.source_id,
            metrics.run_id,
            metrics.status,
            counters["requests"],
            counters["resources"],
            counters["documents"],
            counters["blocks"],
            counters["failures"],
            counters["skipped"],
            counters["not_modified"],
            metrics.reconciliation.get("ok"),
        )
        if not metrics.reconciliation.get("ok"):
            logger.warning(
                "交付对账差异 kind=%s run_id=%s 差异=%s",
                kind,
                metrics.run_id,
                metrics.reconciliation.get("discrepancies"),
            )
        return metrics.as_row()

    def _collect_target(
        self,
        source,
        discoverer: Discoverer,
        target: DiscoveredTarget,
        crawl_date: str,
        crawl_time: str,
        include_attachments: bool,
        report: RunReport,
        scope: Optional[RunScope] = None,
    ) -> None:
        scope = scope or RunScope()
        try:
            state = self.state.get(target.url)
            plan = plan_incremental(source.resource_kind, state, now=self.now())
            response = self.http.get(
                target.url,
                source_id=source.source_id,
                conditional=plan.headers or None,
            )
        except RobotsDisallowed as exc:
            report.skipped.append(
                SkippedTarget(
                    target.url,
                    f"robots_disallowed: {exc.rule or exc}",
                    target.referrer_url,
                )
            )
            return
        except FetchError as exc:
            self._record_failure(
                report,
                source_id=source.source_id,
                url=target.url,
                stage="fetch",
                error_type="http_error" if exc.status_code else "request_error",
                message=str(exc),
                attempts=exc.attempts,
                retryable=exc.retryable,
                referrer_url=target.referrer_url,
            )
            return

        if response.status_code == 304:
            self.state.record_not_modified(
                target.url,
                now=self.now(),
                previous_crawl_id=state.crawl_id if state else None,
            )
            report.counters.not_modified += 1
            report.skipped.append(
                SkippedTarget(target.url, "304 未变化：复用此前成功原件与账本", target.referrer_url)
            )
            return

        is_html = _is_html(response.headers, response.final_url)
        kind = "html" if is_html else "attachment"
        raw = self.store.write_bytes(
            source_id=source.source_id,
            crawl_date=crawl_date,
            kind=kind,
            filename=_filename_for(response.final_url, kind),
            content=response.content,
        )
        report.counters.resources += 1
        crawl_id = self._next_crawl_id(source.source_id, crawl_date)
        self.manifest.record(
            crawl_id=crawl_id,
            source_id=source.source_id,
            requested_url=response.requested_url,
            final_url=response.final_url,
            crawl_time=crawl_time,
            http_status=response.status_code,
            content_type=response.headers.get("Content-Type", ""),
            raw=raw,
            discovery_method=target.discovery_method,
            keyword=target.keyword,
            referrer_url=target.referrer_url,
            etag=response.headers.get("ETag"),
            last_modified=response.headers.get("Last-Modified"),
        )
        if not is_html:
            return

        try:
            parsed = normalize_page(
                parse_html(
                    response.content,
                    response.final_url,
                    encoding_hint=_charset(response.headers.get("Content-Type", "")),
                    content_selector=source.adapter.content_selector,
                    date_selector=source.adapter.date_selector,
                ),
                language_hints=(source.language,),
                base_url=response.final_url,
            )
        except Exception as exc:  # 解析失败保留原件与账本
            self._record_failure(
                report,
                source_id=source.source_id,
                url=target.url,
                stage="parse",
                error_type="parse_error",
                message=str(exc),
                attempts=1,
                retryable=False,
                referrer_url=target.referrer_url,
                crawl_id=crawl_id,
            )
            return

        if parsed.content_selector_missed:
            self._record_failure(
                report,
                source_id=source.source_id,
                url=target.url,
                stage="parse",
                error_type="adapter_selector_miss",
                message=f"适配正文选择器未命中：{source.adapter.content_selector}",
                attempts=1,
                retryable=False,
                referrer_url=target.referrer_url,
                crawl_id=crawl_id,
            )
            return

        # 运行范围（--start-date）：以内容发布日期为包含式下界。原件与账本已经落盘，
        # 范围外目标只跳过文档产出；日期未知保留候选并记录原因，不静默丢弃。
        decision = scope.decide(parsed.publication_date)
        report.date_decisions.append(
            {
                "url": response.final_url,
                "decision": decision.kind,
                "publication_date": decision.publication_date,
                "reason": decision.reason or None,
                "stage": "content",
            }
        )
        if not decision.retained:
            report.counters.out_of_window += 1
            report.skipped.append(
                SkippedTarget(
                    target.url,
                    f"before_start_date:{decision.publication_date}",
                    target.referrer_url,
                )
            )
            logger.info(
                "目标早于起始日期，保留原件与账本但不产出文档 url=%s publication_date=%s start_date=%s",
                target.url,
                decision.publication_date,
                scope.start_date.isoformat() if scope.start_date else None,
            )
            return

        expansion = self._expand_body(
            source, parsed, response.final_url, crawl_date, crawl_time, report
        )
        parsed = expansion.page

        doc_id = crawl_id
        attachments = []
        attachment_stop: Optional[BudgetStop] = None
        if include_attachments and expansion.stop is None:
            attachments, attachment_stop = self._collect_attachments(
                source,
                discoverer,
                [(response.content, response.final_url), *expansion.extra_pages],
                doc_id,
                crawl_date,
                crawl_time,
                report,
            )
        stop_after_commit = expansion.stop or attachment_stop
        try:
            document = build_document(
                doc_id=doc_id,
                source_id=source.source_id,
                source_name=source.source_name,
                source_url=response.final_url,
                title=parsed.title,
                full_text=parsed.full_text,
                language=source.language or parsed.language_hint or "und",
                document_type=source.parser_type or "html_page",
                raw_path=raw.relative_path,
                sha256=raw.sha256,
                crawl_time=crawl_time,
                extraction_method=parsed.extraction_method,
                crawl_ids=[crawl_id, *expansion.extra_crawl_ids],
                canonical_url=parsed.canonical_url,
                publication_date=parsed.publication_date,
                raw_date=parsed.raw_date_text,
                attachments=attachments or None,
                metadata_missing=parsed.metadata_missing,
                parse_status="partial" if (expansion.incomplete or stop_after_commit) else None,
            )
            blocks = build_blocks(
                doc_id=doc_id,
                parsed_blocks=parsed.blocks,
                extraction_method=parsed.extraction_method,
            )
            document_count, block_count = self.writer.commit([document], blocks)
        except Exception as exc:
            self._record_failure(
                report,
                source_id=source.source_id,
                url=target.url,
                stage="normalize",
                error_type="normalization_error",
                message=str(exc),
                attempts=1,
                retryable=False,
                referrer_url=target.referrer_url,
                crawl_id=crawl_id,
            )
            return
        report.counters.documents += document_count
        report.counters.blocks += block_count
        report.documents.append(doc_id)
        self.state.record_success(
            target.url,
            now=self.now(),
            etag=response.headers.get("ETag"),
            last_modified=response.headers.get("Last-Modified"),
            sha256=raw.sha256,
            content_hash=text_hash(document["full_text"]),
            crawl_id=crawl_id,
            publication_date=document.get("publication_date"),
            version=document.get("version"),
        )
        if stop_after_commit is not None:
            # 已归档页面、附件与文档全部落盘后再停止本次运行。
            raise stop_after_commit

    def _expand_body(
        self,
        source,
        parsed: ParsedPage,
        page_url: str,
        crawl_date: str,
        crawl_time: str,
        report: RunReport,
    ) -> BodyExpansion:
        """还原正文分页与接口加载正文（FR-005）。

        只跟随内容区内的下一页链接（rel=next 或明确翻页文案），上限 MAX_BODY_PARTS；
        每个附加部分独立归档并记账（discovery_method=pagination），块按部分顺序合并到
        同一文档、页码取部分序号。接口正文按页面声明的 JSON 端点获取（discovery_method=api），
        正文为 HTML 时按同一 HTML 解析器抽取，纯文本按单一文本块保留。
        任一部分失败不静默：写入失败账并保持文档 parse_status=partial。
        """
        first_blocks = list(parsed.blocks)
        extra_blocks: List[ParsedBlock] = []
        extra_crawl_ids: List[str] = []
        extra_pages: List[Tuple[bytes, str]] = []
        incomplete: Optional[str] = None
        budget_stop: Optional[BudgetStop] = None
        parts = 1
        visited = {page_url}
        next_url = parsed.next_page_url
        referrer = page_url

        while next_url:
            if parts >= MAX_BODY_PARTS:
                incomplete = f"pagination_cap:{MAX_BODY_PARTS}:{next_url}"
                logger.warning("正文分页超过上限，停止合并 url=%s", next_url)
                break
            if next_url in visited:
                incomplete = f"pagination_loop:{next_url}"
                logger.warning("正文分页出现循环，停止合并 url=%s", next_url)
                break
            visited.add(next_url)
            decision = self.registry.check_access(next_url, source.source_id)
            if not decision.allowed:
                report.skipped.append(SkippedTarget(next_url, decision.reason, referrer))
                incomplete = f"pagination_blocked:{next_url}"
                break
            try:
                part = self.http.get(next_url, source_id=source.source_id)
            except BudgetStop as stop:
                # 预算停止不是抓取失败：已合并的部分保留，停止原因交给运行报告。
                incomplete = f"budget_stop:{stop.reason}"
                budget_stop = stop
                logger.warning("正文分页按预算停止 url=%s reason=%s", next_url, stop.reason)
                break
            except RobotsDisallowed as exc:
                report.skipped.append(
                    SkippedTarget(next_url, f"robots_disallowed: {exc.rule or exc}", referrer)
                )
                incomplete = f"pagination_robots:{next_url}"
                break
            except FetchError as exc:
                self._record_failure(
                    report,
                    source_id=source.source_id,
                    url=next_url,
                    stage="fetch",
                    error_type="http_error" if exc.status_code else "request_error",
                    message=str(exc),
                    attempts=exc.attempts,
                    retryable=exc.retryable,
                    referrer_url=referrer,
                )
                incomplete = f"pagination_fetch_failed:{next_url}"
                break
            raw = self.store.write_bytes(
                source_id=source.source_id,
                crawl_date=crawl_date,
                kind="html",
                filename=_filename_for(part.final_url, "html"),
                content=part.content,
            )
            report.counters.resources += 1
            part_crawl_id = self._next_crawl_id(source.source_id, crawl_date)
            self.manifest.record(
                crawl_id=part_crawl_id,
                source_id=source.source_id,
                requested_url=part.requested_url,
                final_url=part.final_url,
                crawl_time=crawl_time,
                http_status=part.status_code,
                content_type=part.headers.get("Content-Type", ""),
                raw=raw,
                discovery_method="pagination",
                referrer_url=referrer,
                etag=part.headers.get("ETag"),
                last_modified=part.headers.get("Last-Modified"),
            )
            try:
                part_parsed = normalize_page(
                    parse_html(
                        part.content,
                        part.final_url,
                        encoding_hint=_charset(part.headers.get("Content-Type", "")),
                        content_selector=source.adapter.content_selector,
                        date_selector=source.adapter.date_selector,
                    ),
                    language_hints=(source.language,),
                    base_url=part.final_url,
                )
            except Exception as exc:  # 解析失败保留该部分原件与失败记录
                self._record_failure(
                    report,
                    source_id=source.source_id,
                    url=next_url,
                    stage="parse",
                    error_type="parse_error",
                    message=str(exc),
                    attempts=1,
                    retryable=False,
                    referrer_url=referrer,
                    crawl_id=part_crawl_id,
                )
                incomplete = f"pagination_parse_failed:{next_url}"
                break
            if part_parsed.content_selector_missed:
                self._record_failure(
                    report,
                    source_id=source.source_id,
                    url=next_url,
                    stage="parse",
                    error_type="adapter_selector_miss",
                    message=f"适配正文选择器未命中：{source.adapter.content_selector}",
                    attempts=1,
                    retryable=False,
                    referrer_url=referrer,
                    crawl_id=part_crawl_id,
                )
                incomplete = f"pagination_selector_miss:{next_url}"
                break
            parts += 1
            extra_blocks.extend(replace(block, page_no=parts) for block in part_parsed.blocks)
            extra_crawl_ids.append(part_crawl_id)
            extra_pages.append((part.content, part.final_url))
            referrer = part.final_url
            next_url = part_parsed.next_page_url

        if parsed.body_api_url:
            try:
                api_result = self._fetch_body_api(
                    source, parsed.body_api_url, referrer, crawl_date, crawl_time, report
                )
            except BudgetStop as stop:
                api_result = None
                budget_stop = budget_stop or stop
                incomplete = incomplete or f"budget_stop:{stop.reason}"
                logger.warning("接口正文按预算停止 url=%s reason=%s", parsed.body_api_url, stop.reason)
            if api_result is None:
                incomplete = incomplete or f"body_api_failed:{parsed.body_api_url}"
            else:
                api_blocks, api_text, api_crawl_id = api_result
                extra_blocks.extend(api_blocks)
                extra_crawl_ids.append(api_crawl_id)

        if parts > 1:
            blocks = [replace(block, page_no=1) for block in first_blocks] + extra_blocks
        else:
            blocks = first_blocks + extra_blocks
        metadata_missing = list(parsed.metadata_missing)
        if incomplete:
            metadata_missing.append(incomplete)
        merged = replace(
            parsed,
            blocks=tuple(blocks),
            full_text="\n".join(block.text for block in blocks if block.text),
            metadata_missing=tuple(metadata_missing),
            next_page_url=None,
            body_api_url=None,
        )
        return BodyExpansion(
            page=merged,
            extra_crawl_ids=extra_crawl_ids,
            extra_pages=extra_pages,
            parts=parts,
            incomplete=incomplete,
            stop=budget_stop,
        )

    def _fetch_body_api(
        self,
        source,
        api_url: str,
        referrer: str,
        crawl_date: str,
        crawl_time: str,
        report: RunReport,
    ):
        """获取接口正文档：归档、记账后按候选字段取正文；失败返回 None 并留痕。"""
        decision = self.registry.check_access(api_url, source.source_id)
        if not decision.allowed:
            report.skipped.append(SkippedTarget(api_url, decision.reason, referrer))
            return None
        try:
            response = self.http.get(api_url, source_id=source.source_id)
        except RobotsDisallowed as exc:
            report.skipped.append(
                SkippedTarget(api_url, f"robots_disallowed: {exc.rule or exc}", referrer)
            )
            return None
        except FetchError as exc:
            self._record_failure(
                report,
                source_id=source.source_id,
                url=api_url,
                stage="fetch",
                error_type="http_error" if exc.status_code else "request_error",
                message=str(exc),
                attempts=exc.attempts,
                retryable=exc.retryable,
                referrer_url=referrer,
            )
            return None
        raw = self.store.write_bytes(
            source_id=source.source_id,
            crawl_date=crawl_date,
            kind="api",
            filename=_filename_for(response.final_url, "api") or "body.json",
            content=response.content,
        )
        report.counters.resources += 1
        crawl_id = self._next_crawl_id(source.source_id, crawl_date)
        self.manifest.record(
            crawl_id=crawl_id,
            source_id=source.source_id,
            requested_url=response.requested_url,
            final_url=response.final_url,
            crawl_time=crawl_time,
            http_status=response.status_code,
            content_type=response.headers.get("Content-Type", ""),
            raw=raw,
            discovery_method="api",
            referrer_url=referrer,
            etag=response.headers.get("ETag"),
            last_modified=response.headers.get("Last-Modified"),
        )
        try:
            payload = json.loads(decode_html(response.content))
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            self._record_failure(
                report,
                source_id=source.source_id,
                url=api_url,
                stage="parse",
                error_type="body_api_parse_error",
                message=str(exc),
                attempts=1,
                retryable=False,
                referrer_url=referrer,
                crawl_id=crawl_id,
            )
            return None
        body = _body_text_from_payload(payload)
        if not body:
            self._record_failure(
                report,
                source_id=source.source_id,
                url=api_url,
                stage="parse",
                error_type="body_api_empty",
                message=f"接口响应未包含候选正文字段：{', '.join(BODY_API_TEXT_KEYS)}",
                attempts=1,
                retryable=False,
                referrer_url=referrer,
                crawl_id=crawl_id,
            )
            return None
        if "<" in body:
            parsed = normalize_page(
                parse_html(body.encode("utf-8"), response.final_url),
                language_hints=(source.language,),
                base_url=response.final_url,
            )
            return list(parsed.blocks), parsed.full_text, crawl_id
        text = " ".join(body.split())
        block = ParsedBlock(block_type="paragraph", text=text)
        return [block], text, crawl_id

    def _collect_attachments(
        self,
        source,
        discoverer: Discoverer,
        pages: Sequence[Tuple[bytes, str]],
        doc_id: str,
        crawl_date: str,
        crawl_time: str,
        report: RunReport,
    ) -> Tuple[List[dict], Optional[BudgetStop]]:
        """下载附件；预算在附件阶段用尽时返回已完成的附件与停止原因，不丢弃已归档原件。"""
        attachment_targets = []
        for html_bytes, page_url in pages:
            attachment_targets.extend(discoverer.attachments_from_html(html_bytes, page_url))
        attachments = []
        for index, target in enumerate(attachment_targets, 1):
            record = {
                "attachment_id": f"{doc_id}_A{index:02d}",
                "filename": sanitize_filename(_basename(target.url)),
                "file_type": _file_type(target.url),
                "url": target.url,
                "doc_id": doc_id,
            }
            try:
                resource = self.downloader.download(target.url, source_id=source.source_id)
            except BudgetStop as stop:
                logger.warning("附件下载按预算停止 url=%s reason=%s", target.url, stop.reason)
                return attachments, stop
            except RobotsDisallowed as exc:
                self._record_failure(
                    report,
                    source_id=source.source_id,
                    url=target.url,
                    stage="fetch",
                    error_type="robots_disallowed",
                    message=str(exc),
                    attempts=exc.attempts,
                    retryable=False,
                    referrer_url=target.referrer_url,
                    final_action="skip",
                )
                record["status"] = "failed"
                record["filename"] = sanitize_filename(target.url.rsplit("/", 1)[-1]) or record["filename"]
                attachments.append(record)
                continue
            except FetchError as exc:
                self._record_failure(
                    report,
                    source_id=source.source_id,
                    url=target.url,
                    stage="fetch",
                    error_type="http_error" if exc.status_code else "request_error",
                    message=str(exc),
                    attempts=exc.attempts,
                    retryable=exc.retryable,
                    referrer_url=target.referrer_url,
                )
                record["status"] = "failed"
                record["filename"] = sanitize_filename(target.url.rsplit("/", 1)[-1]) or record["filename"]
                attachments.append(record)
                continue
            raw = self.store.write_bytes(
                source_id=source.source_id,
                crawl_date=crawl_date,
                kind="attachment",
                filename=resource.filename,
                content=resource.content,
            )
            report.counters.resources += 1
            attachment_crawl_id = self._next_crawl_id(source.source_id, crawl_date)
            self.manifest.record(
                crawl_id=attachment_crawl_id,
                source_id=source.source_id,
                requested_url=resource.requested_url,
                final_url=resource.final_url,
                crawl_time=crawl_time,
                http_status=resource.status_code,
                content_type=resource.content_type,
                raw=raw,
                discovery_method="attachment",
                referrer_url=target.referrer_url,
            )
            record.update(
                {
                    "filename": resource.filename,
                    "status": "downloaded",
                    "raw_path": raw.relative_path,
                    "sha256": raw.sha256,
                    "crawl_id": attachment_crawl_id,
                }
            )
            attachments.append(record)
        return attachments, None

    def _record_failure(
        self,
        report: RunReport,
        *,
        source_id: str,
        url: str,
        stage: str,
        error_type: str,
        message: str,
        attempts: int,
        retryable: bool,
        referrer_url: Optional[str] = None,
        crawl_id: Optional[str] = None,
        final_action: Optional[str] = None,
    ) -> None:
        row = self.failures.record(
            source_id=source_id,
            url=url,
            time=self.now().isoformat(),
            stage=stage,
            error_type=error_type,
            message=message,
            retry_count=max(0, attempts - 1),
            final_action=final_action or ("retry_later" if retryable else "record_only"),
            crawl_id=crawl_id,
            referrer_url=referrer_url,
            scope_start_date=(
                self._run_scope.start_date.isoformat()
                if self._run_scope and self._run_scope.start_date
                else None
            ),
        )
        report.failures.append(row)
        report.counters.failures += 1

    def _next_crawl_id(self, source_id: str, crawl_date: str) -> str:
        """按账本已落盘序号继续编号：同一来源同一天多次运行不复用 crawl_id。

        补抓按 crawl_id 定位原件；若不同运行的编号重复，失败记录会指向错误的
        原始文件。序号取自账本而不是实例内计数，跨进程运行也保持唯一。
        """
        prefix = f"{source_id}_{crawl_date.replace('-', '')}_"
        if prefix not in self._sequences:
            self._sequences[prefix] = _max_crawl_sequence(self.layout.manifest_path, prefix)
        self._sequences[prefix] += 1
        return f"{prefix}{self._sequences[prefix]:04d}"

    def recovery_plan(
        self, *, policy: Optional[RetryPolicy] = None, now: Optional[datetime] = None
    ) -> List[RecoveryTask]:
        """当前未关闭失败的补抓计划（含退避时间），不产生副作用。"""
        moment = now or self.now()
        def _raw_path(crawl_id):
            return self.failures_ledger.default_raw_path(crawl_id)

        tasks = []
        for failure in self.failures_ledger.open_failures():
            raw_path = _raw_path(failure.get("crawl_id"))
            tasks.append(
                plan_retry(failure, policy=policy or RetryPolicy(), now=moment, raw_path=raw_path)
            )
        return tasks

    def resume_failures(
        self,
        source_id: str,
        *,
        policy: Optional[RetryPolicy] = None,
        max_tasks: Optional[int] = None,
        respect_backoff: bool = False,
        budget: Optional[RunBudget] = None,
    ) -> RecoveryReport:
        """执行补抓：网络阶段重取，本地阶段重解析原件；历史失败与原件保持不变。"""
        source = self.registry.get(source_id)
        moment = self.now()
        started = self.now()
        self.layout.ensure()
        configure_run_logging(self.data_dir)
        if self.settings is not None:
            log_run_context(logger, self.settings)
        before = output_stats(self.data_dir)
        requests_before = self.http.request_attempts
        if budget is not None:
            budget.start()
            self.http.attach_budget(budget)
        policy = policy or RetryPolicy()
        report = RecoveryReport(source_id=source_id)
        tasks = [
            task
            for task in self.recovery_plan(policy=policy, now=moment)
            if task.source_id == source_id
        ]
        if max_tasks is not None:
            tasks = tasks[:max_tasks]
        planned = len(tasks)
        processed = 0
        scopes_used: List[str] = []
        try:
            for task in tasks:
                if task.action == RETRY_MANUAL:
                    report.manual.append(task.as_row())
                    processed += 1
                    continue
                if respect_backoff and not plan_is_ready(task, now=moment):
                    report.pending.append(task.as_row())
                    processed += 1
                    continue
                try:
                    task_scope = RunScope(start_date=parse_start_date(task.scope_start_date))
                except ScopeConfigError as exc:
                    # 原范围无法解析时不猜窗口：转人工，避免把新窗口混入旧任务。
                    report.manual.append(
                        {**task.as_row(), "reason": f"原运行范围无法解析：{exc}"}
                    )
                    processed += 1
                    continue
                if task.scope_start_date:
                    scopes_used.append(task.scope_start_date)
                self._run_scope = task_scope
                failure = self._failure_for(task)
                if task.action == REFETCH:
                    recovered = self._recover_refetch(source, task, moment, task_scope)
                else:
                    recovered = self._recover_reparse(source, task, moment, task_scope)
                if recovered:
                    action = recovered.get("action", "recovered")
                    row = self.failures_ledger.record_resolution(
                        failure,
                        now=self.now(),
                        note=recovered["note"],
                        crawl_id=recovered.get("crawl_id"),
                        action=action,
                    )
                    entry = {
                        **task.as_row(),
                        "resolution": row["final_action"],
                        "note": recovered.get("note", ""),
                    }
                    if action == "skip":
                        report.skipped.append(entry)
                    else:
                        report.recovered.append(entry)
                    report.counters.resources += recovered.get("resources", 0)
                    report.counters.documents += recovered.get("documents", 0)
                    report.counters.blocks += recovered.get("blocks", 0)
                else:
                    report.failures.append(task.as_row())
                processed += 1
        except BudgetStop as stop:
            report.stop_reason = stop.reason
            report.stop_message = stop.message
            logger.warning("补抓按预算停止 reason=%s message=%s", stop.reason, stop.message)
        report.unprocessed = planned - processed if planned else None
        distinct_scopes = sorted(set(scopes_used))
        if len(distinct_scopes) == 1:
            self._run_scope = RunScope(start_date=parse_start_date(distinct_scopes[0]))
        elif len(distinct_scopes) > 1:
            # 多个原范围时不在运行级冒充单一窗口：逐任务记录 scope_start_date。
            logger.warning("本次补抓涉及多个原运行范围：%s", distinct_scopes)
            self._run_scope = RunScope()
        if budget is not None:
            report.budget = budget.as_row()
        report.counters.failures = len(report.failures)
        report.counters.skipped = len(report.skipped)
        logger.info(
            "补抓完成 source=%s recovered=%d skipped=%d manual=%d pending=%d failed=%d",
            source_id,
            len(report.recovered),
            len(report.skipped),
            len(report.manual),
            len(report.pending),
            len(report.failures),
        )
        # 处置行会追加到失败账：本次追加量 = 仍未关闭的失败 + 已关闭的处置记录
        expected_deltas = {
            "failures": report.counters.failures
            + len(report.recovered)
            + len(report.skipped),
        }
        report.metrics = self._finish_run(
            _as_run_report(report, scope=self._run_scope),
            kind="recovery",
            started_at=started.isoformat(),
            finished_at=self.now().isoformat(),
            before=before,
            expected_deltas=expected_deltas,
            requests_before=requests_before,
            request_controls=self._request_controls(source),
        )
        return report

    def _failure_for(self, task: RecoveryTask) -> dict:
        for row in self.failures_ledger.load():
            if row.get("url") == task.url and row.get("stage") == task.stage:
                return row
        return {"source_id": task.source_id, "url": task.url, "stage": task.stage}

    def _recover_refetch(
        self,
        source,
        task: RecoveryTask,
        moment: datetime,
        scope: Optional[RunScope] = None,
    ) -> Optional[dict]:
        report = RunReport(source_id=source.source_id)
        target = DiscoveredTarget(
            url=task.url,
            discovery_method="retry",
            referrer_url=task.referrer_url,
        )
        crawl_date = moment.date().isoformat()
        self._collect_target(
            source, None, target, crawl_date, moment.isoformat(), False, report, scope
        )
        if report.counters.documents or report.counters.resources:
            return {
                "note": "补抓成功，账本与文档已更新",
                "resources": report.counters.resources,
                "documents": report.counters.documents,
                "blocks": report.counters.blocks,
            }
        robots_skip = next(
            (item for item in report.skipped if item.reason.startswith("robots_disallowed:")),
            None,
        )
        if robots_skip is not None:
            return {
                "note": f"robots 规则拒绝，按 skip 关闭：{robots_skip.reason}",
                "action": "skip",
            }
        return None

    def _recover_reparse(
        self,
        source,
        task: RecoveryTask,
        moment: datetime,
        scope: Optional[RunScope] = None,
    ) -> Optional[dict]:
        raw_path = task.raw_path
        if not raw_path:
            return None
        try:
            raw_file = self.layout.resolve_raw_path(raw_path)
        except PathSafetyError as exc:
            logger.warning("重解析拒绝越界 raw_path=%s error=%s", raw_path, exc)
            return None
        if not raw_file.is_file():
            return None
        content = raw_file.read_bytes()
        crawl_id = task.crawl_id or f"{source.source_id}_{moment.date().isoformat().replace('-', '')}_reparse"
        crawl_time = moment.isoformat()
        try:
            document, blocks = self._build_recovered_document(
                source=source,
                content=content,
                url=task.url,
                raw_path=raw_path,
                crawl_id=crawl_id,
                crawl_time=crawl_time,
            )
            # 补抓沿用原运行范围：原范围外的原件保留，但不再产出新文档。
            decision = (scope or RunScope()).decide(document.get("publication_date"))
            if not decision.retained:
                return {
                    "note": (
                        f"原运行范围外（{decision.kind}:{decision.publication_date}）："
                        "原件保留，不产出文档"
                    ),
                    "action": "skip",
                }
            document_count, block_count = self.writer.commit([document], blocks)
        except Exception as exc:  # noqa: BLE001 - 重解析失败保留原件与失败记录
            logger.warning("重解析失败 url=%s error=%s", task.url, exc)
            return None
        self.state.record_success(
            task.url,
            now=moment,
            sha256=document["sha256"],
            content_hash=text_hash(document["full_text"]),
            crawl_id=crawl_id,
            publication_date=document.get("publication_date"),
        )
        return {
            "note": "重解析成功，文档与块已补全",
            "crawl_id": crawl_id,
            "documents": document_count,
            "blocks": block_count,
        }

    def _build_recovered_document(
        self,
        *,
        source,
        content: bytes,
        url: str,
        raw_path: str,
        crawl_id: str,
        crawl_time: str,
    ):
        filename = url.rsplit("/", 1)[-1] or "index.html"
        if _looks_like_html(content, filename):
            parsed = normalize_page(
                parse_html(
                    content,
                    url,
                    content_selector=source.adapter.content_selector,
                    date_selector=source.adapter.date_selector,
                ),
                language_hints=(source.language,),
                base_url=url,
            )
            if parsed.content_selector_missed:
                raise ValueError(f"适配正文选择器未命中：{source.adapter.content_selector}")
            document_type = source.parser_type or "html_page"
        else:
            parsed = normalize_page(
                parse_attachment(content, filename, url, converter=self.legacy_converter),
                language_hints=(source.language,),
                base_url=url,
            )
            document_type = _file_type(url)
        content_hash = hashlib.sha256(content).hexdigest()
        document = build_document(
            doc_id=crawl_id,
            source_id=source.source_id,
            source_name=source.source_name,
            source_url=url,
            title=parsed.title,
            full_text=parsed.full_text,
            language=source.language or parsed.language_hint or "und",
            document_type=document_type,
            raw_path=raw_path,
            sha256=content_hash,
            crawl_time=crawl_time,
            extraction_method=parsed.extraction_method,
            crawl_ids=[crawl_id],
            canonical_url=parsed.canonical_url,
            publication_date=parsed.publication_date,
            raw_date=parsed.raw_date_text,
            metadata_missing=parsed.metadata_missing,
        )
        blocks = build_blocks(
            doc_id=crawl_id,
            parsed_blocks=parsed.blocks,
            extraction_method=parsed.extraction_method,
        )
        return document, blocks


def _max_crawl_sequence(manifest_path: Path, prefix: str) -> int:
    """账本中同前缀 crawl_id 的最大序号；没有记录时从 0 开始。"""
    maximum = 0
    for row in read_jsonl(manifest_path):
        crawl_id = str(row.get("crawl_id") or "")
        tail = crawl_id[len(prefix):] if crawl_id.startswith(prefix) else ""
        if tail.isdigit():
            maximum = max(maximum, int(tail))
    return maximum


def _as_run_report(report: RecoveryReport, scope: Optional[RunScope] = None) -> RunReport:
    """把补抓报告映射为运行报告形态，复用同一套指标与日志写出。"""
    return RunReport(
        source_id=report.source_id,
        counters=report.counters,
        failures=report.failures,
        scope=scope or RunScope(),
        skipped=[
            SkippedTarget(
                row.get("url", ""),
                f"robots_disallowed: 补抓时 robots 规则拒绝（stage={row.get('stage')}）",
            )
            for row in report.skipped
        ],
        documents=[item.get("crawl_id") for item in report.recovered if item.get("crawl_id")],
        stop_reason=report.stop_reason,
        stop_message=report.stop_message,
        unprocessed=report.unprocessed,
        budget=report.budget,
    )


def _body_text_from_payload(payload) -> Optional[str]:
    """按候选字段取接口正文；只接受非空字符串，不猜测结构、不拼接 JSON 片段。"""
    if isinstance(payload, str):
        return payload.strip() or None
    if isinstance(payload, dict):
        for key in BODY_API_TEXT_KEYS:
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        for key in BODY_API_CONTAINER_KEYS:
            nested = payload.get(key)
            if isinstance(nested, dict):
                found = _body_text_from_payload(nested)
                if found:
                    return found
    return None


def _is_html(headers, url: str) -> bool:
    content_type = headers.get("Content-Type", "").split(";")[0].strip().lower()
    if content_type in HTML_CONTENT_TYPES:
        return True
    if content_type:
        return False
    return urlsplit(url).path.lower().endswith((".html", ".htm", "/"))


def _looks_like_html(content: bytes, filename: str) -> bool:
    """重解析时按扩展名与内容特征判断 HTML，不依赖已丢失的响应头。"""
    if filename.lower().endswith((".html", ".htm")):
        return True
    head = content.lstrip()[:64].lower()
    return head.startswith((b"<!doctype", b"<html", b"<?xml-stylesheet"))


def _charset(content_type: str) -> Optional[str]:
    for part in content_type.split(";")[1:]:
        key, _, value = part.strip().partition("=")
        if key.lower() == "charset" and value:
            return value.strip('"').strip("'")
    return None


def _basename(url: str) -> str:
    return urlsplit(url).path.rsplit("/", 1)[-1] or "index.html"


def _file_type(url: str) -> str:
    name = _basename(url).lower()
    for extension in sorted(ATTACHMENT_EXTENSIONS, key=len, reverse=True):
        if name.endswith(extension):
            return extension.lstrip(".")
    return "unknown"


def _filename_for(url: str, kind: str) -> str:
    name = _basename(url)
    if kind == "html" and not name.lower().endswith((".html", ".htm")):
        name = f"{name}.html" if name else "index.html"
    return name
