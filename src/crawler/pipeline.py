"""最小采集闭环编排：发现 → 获取 → 原件与账本 → 解析 → 标准化（T009）。

单进程同步执行；每页在归档与账本完成后才进入解析，文档与块全部校验后才
成组提交。失败按操作记录，不静默丢弃，也不以失败掩盖已成功获取的原件。
collect/resume 可挂统一的 RunBudget：请求上限或截止时间到达时停止后续请求，
保留已成功归档的原件、账本、文档与块，并以 stop_reason 报告未完成部分。

失败身份（C）：来源 + URL + 原运行范围 + 母文档。处理具体待处理项时，失败记录的
``scope_start_date`` 取该对象入队时的范围（而不是本次运行的窗口），使失败账、补抓
计划与 ``check`` 对账使用同一对象身份，不跨来源、范围或母文档互相关闭。
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
    DiscoveryContentError,
    DiscoveryStop,
    Discoverer,
    DiscoveredTarget,
    SkippedTarget,
    STOP_PARSE_ERROR,
    STOP_REQUEST_FAILED,
)
from crawler.discover.strategies import (
    STATUS_PARSE_ERROR,
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
from crawler.fetch.downloader import (
    AttachmentBoundaryRejected,
    Downloader,
    iter_capped_chunks,
)
from crawler.fetch.budget import BudgetStop, RunBudget
from crawler.fetch.http_client import (
    FetchError,
    FetchResponse,
    HttpClient,
    RobotsDisallowed,
)
from crawler.normalize.block_schema import build_blocks
from crawler.normalize.document_schema import build_document
from crawler.normalize.metadata_normalizer import normalize_page
from crawler.output.documents_writer import DocumentsWriter
from crawler.output.failures_writer import FailureWriter
from crawler.output.layout import DeliveryLayout
from crawler.output.archive import ResponseArchiver
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
from crawler.schedule.cursor import DiscoveryCursorStore
from crawler.schedule.pending import (
    KIND_ATTACHMENT,
    STATE_FAILED,
    STATE_PENDING,
    STATE_PROCESSED,
    STATE_REFRESH,
    STATE_SKIPPED,
    UNSET as PENDING_UNSET,
    PendingItem,
    PendingStore,
)
from crawler.schedule.scope import RunScope, ScopeConfigError, parse_start_date
from crawler.schedule.state import IncrementalStateStore, ResourceState
from crawler.util.paths import PathSafetyError, sanitize_filename

logger = logging.getLogger(__name__)

# discover_only 运行不受 --max-items 的发现上限约束：分页遍历以页数上限与预算为边界。
DISCOVERY_ONLY_MAX_ITEMS = 10 ** 9

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
    coverage: dict = field(default_factory=dict)
    scope: RunScope = RunScope()
    date_decisions: List[dict] = field(default_factory=list)
    metrics: Optional[dict] = None
    stop_reason: Optional[str] = None
    stop_message: str = ""
    unprocessed: Optional[int] = None
    budget: Optional[dict] = None


@dataclass
class TargetOutcome:
    """一个主目标（或待处理附件）的处理结果；state 与待处理项状态同一口径。"""

    state: str
    note: str = ""
    stop: Optional[BudgetStop] = None
    crawl_id: Optional[str] = None
    raw_path: Optional[str] = None
    sha256: Optional[str] = None
    # R2：正文待续状态；缺省 PENDING_UNSET 表示不改写待处理项既有值，None 表示关闭。
    continuation: object = PENDING_UNSET
    # R2：待续对象的母文档身份；缺省 PENDING_UNSET 表示不改写待处理项既有值。
    doc_id: object = PENDING_UNSET


@dataclass
class BodyExpansion:
    """正文还原结果：合并后的页面、各附加原件与未完成原因。"""

    page: ParsedPage
    extra_crawl_ids: List[str] = field(default_factory=list)
    extra_pages: List[Tuple[bytes, str]] = field(default_factory=list)
    parts: int = 1
    incomplete: Optional[str] = None
    stop: Optional[BudgetStop] = None
    # R2：已取得部分的原件引用（顺序即合并顺序）与未取位置，供待续状态持久化。
    part_refs: List[dict] = field(default_factory=list)
    next_url: Optional[str] = None
    body_api_url: Optional[str] = None


# 正文待续的停止原因前缀：预算停止与可重试的正文请求失败可续作；页面循环/上限/
# 选择器未命中/robots 拒绝是确定性终止，不建立待续状态（避免每轮重复同一失败）。
CONTINUABLE_REASONS = (
    "budget_stop:",
    "pagination_fetch_failed:",
    "body_api_failed:",
    "resume_part_failed:",
)


CONTINUATION_KIND = "body_pagination"


@dataclass(frozen=True)
class BodyContinuation:
    """正文分页/接口正文待续状态（R2）：随主目标待处理项持久化，JSON 可序列化。

    记录母目标/文档身份、原范围（在待处理项上）、已取得部分的 crawl_id/raw 引用、
    顺序、下一正文 URL 或接口与停止原因。下一轮优先续取未取部分；母页 304 只说明
    母响应未变，不取消未完成正文。续作完成后的文档使用新身份（母身份 + 续作序号），
    旧 partial 文档与全部原件保留，不静默覆盖。
    """

    doc_id: str
    mother_url: str
    mother_final_url: str
    mother_raw_path: str
    mother_sha256: str
    mother_content_type: str = ""
    next_url: Optional[str] = None
    body_api_url: Optional[str] = None
    parts: Tuple[dict, ...] = ()
    stop_reason: str = ""
    attempts: int = 0
    updated_at: Optional[str] = None

    def as_dict(self) -> dict:
        return {
            "kind": CONTINUATION_KIND,
            "doc_id": self.doc_id,
            "mother_url": self.mother_url,
            "mother_final_url": self.mother_final_url,
            "mother_raw_path": self.mother_raw_path,
            "mother_sha256": self.mother_sha256,
            "mother_content_type": self.mother_content_type,
            "next_url": self.next_url,
            "body_api_url": self.body_api_url,
            "parts": [dict(part) for part in self.parts],
            "stop_reason": self.stop_reason,
            "attempts": self.attempts,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: Optional[dict]) -> Optional["BodyContinuation"]:
        """宽容读取：种类不符或身份/部分引用不完整时返回 None，按完整重取处理。"""
        if not isinstance(payload, dict) or payload.get("kind") != CONTINUATION_KIND:
            return None
        required = ("doc_id", "mother_url", "mother_raw_path", "mother_sha256")
        if any(not payload.get(key) for key in required):
            return None
        parts = payload.get("parts") or []
        if not isinstance(parts, list):
            return None
        for part in parts:
            if not isinstance(part, dict):
                return None
            if not part.get("raw_path") or not part.get("crawl_id"):
                return None
            if part.get("method") not in ("pagination", "api"):
                return None
        return cls(
            doc_id=str(payload["doc_id"]),
            mother_url=str(payload["mother_url"]),
            mother_final_url=str(payload.get("mother_final_url") or payload["mother_url"]),
            mother_raw_path=str(payload["mother_raw_path"]),
            mother_sha256=str(payload["mother_sha256"]),
            mother_content_type=str(payload.get("mother_content_type") or ""),
            next_url=payload.get("next_url") or None,
            body_api_url=payload.get("body_api_url") or None,
            parts=tuple(dict(part) for part in parts),
            stop_reason=str(payload.get("stop_reason") or ""),
            attempts=int(payload.get("attempts") or 0),
            updated_at=payload.get("updated_at") or None,
        )


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
        self.now = now or (lambda: datetime.now(timezone.utc).astimezone())
        # 统一归档：原件 + 账本 + crawl_id 序号（S5-01）。发现响应与正文资源共用同一实例，
        # 同一运行内序号连续，同一个响应对象不会被写两次账。
        self.archiver = ResponseArchiver(self.data_dir, now=self.now)
        self.failures = FailureWriter(self.data_dir)
        self.writer = DocumentsWriter(self.data_dir)
        self.state = state_store or IncrementalStateStore(self.data_dir)
        self.failures_ledger = FailureLedger(self.data_dir)
        # S5-06：待处理项与发现游标是续接状态，与失败账分开；成功成果不被它们覆盖。
        self.pending = PendingStore(self.data_dir)
        self.cursors = DiscoveryCursorStore(self.data_dir)
        # 本次运行范围：失败记录与补抓计划据此保留原窗口（恢复不混入新窗口）。
        self._run_scope: RunScope = RunScope()
        # 当前正在处理的对象范围（C）：处理待处理项时临时覆盖失败记录范围；未设置时
        # 回落到本次运行范围（如发现阶段失败）。
        self._object_scope_set = False
        self._object_scope_start: Optional[date] = None

    def _object_scope(self) -> RunScope:
        """失败记录使用的对象范围（C）：处理对象期间取该对象自己的窗口。"""
        if self._object_scope_set:
            return RunScope(start_date=self._object_scope_start)
        return self._run_scope

    @property
    def store(self):
        """原件存储（归档器组件）；正常采集请用 archiver，保持“先原件、后账本”顺序。"""
        return self.archiver.store

    @property
    def manifest(self):
        """账本写出（归档器组件）；供补抓与测试构造/核对既有原件使用。"""
        return self.archiver.manifest

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
        max_pages: Optional[int] = None,
        discover_only: bool = False,
    ) -> RunReport:
        """按来源执行一次采集；scope 为本次运行范围（起始日期下界）。

        ``discover_only`` 只遍历发现入口并把全部目标入队（分页覆盖用），不处理目标；
        ``max_pages`` 覆盖来源适配配置里的每入口页数上限（仅本次运行生效）。
        """
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
        # 并行运行时其他来源也写同一批交付文件：增量按来源归属，避免把别的运行的追加
        # 算进本次运行的对账（FR-018）。
        before = output_stats(self.data_dir, source_id=source_id)
        requests_before = self.http.request_attempts
        report = RunReport(source_id=source_id)
        report.scope = scope
        # 预算按次运行生效：未传预算即本次不受限制；上一轮遗留的有限预算
        # 不得继续约束新一轮（S5-06 有限预算分轮续作的前提）。
        self.http.attach_budget(budget)
        if budget is not None:
            budget.start()
            report.budget = budget
        # 只遍历发现时不处理目标：不受 --max-items 的发现上限约束（仍受页数上限、
        # 请求预算与截止时间约束），避免为了翻页先消耗正文预算。
        discovery_max_items = DISCOVERY_ONLY_MAX_ITEMS if discover_only else max_items

        def commit_page_targets(page_targets, page_context: dict) -> dict:
            """R4 页级提交：发现目标先持久化入队，成功后才允许推进发现游标。"""
            counts = self.pending.enqueue_targets(
                source_id=source_id,
                targets=list(page_targets),
                scope_start_date=page_context.get("scope_start_date"),
                enqueued_at=self.now().isoformat(),
                replay=bool(page_context.get("replay")),
            )
            logger.info(
                "发现页目标已入队 page=%s replay=%s added=%d refreshed=%d",
                page_context.get("page_url"),
                page_context.get("replay"),
                counts.get("added", 0),
                counts.get("refreshed", 0),
            )
            return counts

        discoverer = Discoverer(
            self.http,
            self.registry,
            source,
            max_items=discovery_max_items,
            archiver=self.archiver,
            cursors=self.cursors,
            now=self.now,
            max_pages_override=max_pages,
            commit_targets=commit_page_targets,
        )
        context = DiscoveryContext(
            source=source,
            registry=self.registry,
            http=self.http,
            discoverer=discoverer,
            scope=scope,
            max_items=discovery_max_items,
        )
        moment = self.now()
        crawl_date = moment.date().isoformat()
        crawl_time = moment.isoformat()
        scope_start = scope.start_date.isoformat() if scope.start_date else None

        targets: List[DiscoveredTarget] = []
        processed = 0
        report.coverage = self._empty_coverage()
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
                discovery_max_items,
                include_default_list=default_list,
            ):
                result = self._run_discovery(report, request, context)
                report.discovery.append(result)
                targets.extend(result.targets)
                if discoverer.budget_stop is not None:
                    # 先把已发现目标入队（进度不丢），稍后再停止本次运行。
                    break
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

            # 发现页（列表/搜索/sitemap/接口）成功响应同样已归档：计入资源数，
            # 与账本追加行数保持同一口径。
            report.counters.resources += discoverer.archived_count

            # S5-06：发现到的全部目标（含超出本次上限的部分）先入队，保证下一轮
            # 有限预算能推进到未处理部分，而不是每次从入口重选前几项。
            # R4：分页策略已在页级提交（游标随提交推进）；这里只补交未页级提交的目标
            # （显式 --url、sitemap、未实现/失败策略的兜底），避免重复刷新。
            report.coverage["targets"]["discovered"] = len(targets)
            enqueue = self.pending.enqueue_targets(
                source_id=source_id,
                targets=[target for target in targets if target.url not in discoverer.committed_urls],
                scope_start_date=scope_start,
                enqueued_at=crawl_time,
            )
            report.coverage["queue"] = {
                "added": enqueue.get("added", 0) + discoverer.commit_counts.get("added", 0),
                "refreshed": enqueue.get("refreshed", 0)
                + discoverer.commit_counts.get("refreshed", 0),
                "unchanged": enqueue.get("unchanged", 0)
                + discoverer.commit_counts.get("unchanged", 0),
            }

            if discover_only:
                report.coverage["processing"] = {
                    "mode": "discovery_only",
                    "note": "本次只遍历发现入口并把目标入队，未处理目标（遍历覆盖用）",
                }
            candidates = (
                [] if discover_only else self.pending.candidates(source_id, limit=max_items)
            )
            for item in candidates:
                try:
                    # C：处理对象期间，失败记录使用该对象入队时的运行范围（不是本次运行窗口），
                    # 否则失败账、补抓计划与对账会因范围不同而无法按同一身份匹配。
                    item_scope = self._scope_for_item(item)
                    self._object_scope_set = True
                    self._object_scope_start = item_scope.start_date
                    if item.kind == KIND_ATTACHMENT:
                        outcome = self._collect_pending_attachment(
                            source, item, report, crawl_date, crawl_time
                        )
                    else:
                        continuation = BodyContinuation.from_dict(item.continuation)
                        damaged_continuation = (
                            item.continuation is not None and continuation is None
                        )
                        if damaged_continuation:
                            # 待续状态损坏：不猜造进度，也不让 304 冒充完成；按完整重取
                            # 处理（忽略条件请求），并留下可见的工程失败记录。
                            logger.warning("待续状态损坏，按完整重取处理 key=%s", item.key)
                            self._record_failure(
                                report,
                                source_id=source_id,
                                url=item.url,
                                stage="validate",
                                error_type="continuation_state_damaged",
                                message="正文待续状态损坏：按完整重取处理",
                                attempts=1,
                                retryable=False,
                                referrer_url=item.referrer_url,
                                doc_id=item.doc_id,
                            )
                        outcome = self._collect_target(
                            source,
                            discoverer,
                            self._target_from_item(item),
                            crawl_date,
                            crawl_time,
                            include_attachments,
                            report,
                            item_scope,
                            parent_url=item.url,
                            continuation=continuation,
                            ignore_conditional=damaged_continuation,
                        )
                except BudgetStop as stop:
                    # 该目标的主请求未取得响应：保持待处理（不写成失败），下一轮继续。
                    self.pending.mark(
                        item.key,
                        state=STATE_PENDING,
                        attempted_at=self.now().isoformat(),
                        note=f"budget_stop:{stop.reason}",
                    )
                    raise
                except ScopeConfigError as exc:
                    # 原运行范围无法解析时不猜窗口：转跳过并留下原因，不混入当前窗口。
                    self.pending.mark(
                        item.key,
                        state=STATE_SKIPPED,
                        attempted_at=self.now().isoformat(),
                        note=f"scope_unparsable:{exc}",
                    )
                    report.skipped.append(
                        SkippedTarget(item.url, f"scope_unparsable:{exc}", item.referrer_url)
                    )
                    continue
                finally:
                    self._object_scope_set = False
                    self._object_scope_start = None
                self.pending.mark(
                    item.key,
                    state=outcome.state,
                    attempted_at=self.now().isoformat(),
                    note=outcome.note,
                    crawl_id=outcome.crawl_id,
                    raw_path=outcome.raw_path,
                    sha256=outcome.sha256,
                    doc_id=outcome.doc_id,
                    continuation=outcome.continuation,
                )
                processed += 1
                self._count_outcome(report, item, outcome)
                if outcome.stop is not None:
                    raise outcome.stop
            if discoverer.budget_stop is not None:
                raise discoverer.budget_stop
        except BudgetStop as stop:
            report.stop_reason = stop.reason
            report.stop_message = stop.message
            logger.warning("采集按预算停止 reason=%s message=%s", stop.reason, stop.message)
        report.coverage["targets"]["attempted"] = processed
        self._finish_coverage(report, source_id, discoverer)
        report.unprocessed = report.coverage["pending_total"]
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

    # ------------------------------------------------------------------ S5-06 续接辅助

    @staticmethod
    def _empty_coverage() -> dict:
        """本轮覆盖口径：目标、附件与发现完整性分开记录，未完成不冒充完成。"""
        return {
            "targets": {
                "discovered": 0,
                "attempted": 0,
                "processed": 0,
                "failed": 0,
                "skipped": 0,
                "refresh": 0,
            },
            "attachments": {
                "discovered": 0,
                "downloaded": 0,
                "failed": 0,
                "boundary_rejected": 0,
                "rule_excluded": 0,
                "duplicates": 0,
                "pending": 0,
                "resumed": 0,
                "exclusions": [],
            },
            "discovery": {"complete": True, "incomplete_runs": 0, "stops": []},
            "queue": {"added": 0, "refreshed": 0, "unchanged": 0},
            "pending_total": 0,
        }

    @staticmethod
    def _target_from_item(item: PendingItem) -> DiscoveredTarget:
        return DiscoveredTarget(
            url=item.url,
            discovery_method=item.discovery_method or "manual",
            referrer_url=item.referrer_url,
            keyword=item.keyword,
            title_hint=item.title_hint,
        )

    @staticmethod
    def _scope_for_item(item: PendingItem) -> RunScope:
        """待处理项沿用入队时的运行范围；解析失败交给调用方按跳过处理。"""
        return RunScope(start_date=parse_start_date(item.scope_start_date))

    @staticmethod
    def _count_outcome(report: RunReport, item: PendingItem, outcome: TargetOutcome) -> None:
        targets = report.coverage["targets"]
        if outcome.state == STATE_PROCESSED:
            targets["processed"] += 1
        elif outcome.state == STATE_FAILED:
            targets["failed"] += 1
        elif outcome.state == STATE_SKIPPED:
            targets["skipped"] += 1
        if item.state == STATE_REFRESH:
            targets["refresh"] += 1

    def _finish_coverage(self, report: RunReport, source_id: str, discoverer: Discoverer) -> None:
        """补齐队列与发现完整性口径；pending_total 是仍未处理的部分（不含失败账）。"""
        coverage = report.coverage
        counts = self.pending.counts(source_id)
        coverage["queue_state"] = counts
        coverage["pending_total"] = (
            counts["targets"]["pending"] + counts["attachments"]["pending"]
        )
        coverage["attachments"]["pending"] = counts["attachments"]["pending"]
        coverage["attachments"]["rule_excluded"] = sum(
            int(row.get("count", 0)) for row in discoverer.attachment_rule_exclusions
        )
        coverage["attachments"]["exclusions"] = [
            dict(row) for row in discoverer.attachment_rule_exclusions
        ]
        coverage["attachments"]["duplicates"] = sum(
            int(row.get("count", 0)) for row in discoverer.attachment_duplicates
        )
        coverage["discovery"]["stops"] = [stop.as_row() for stop in discoverer.stops]
        incomplete = [row for row in coverage["discovery"]["stops"] if not row["complete"]]
        coverage["discovery"]["complete"] = not incomplete
        coverage["discovery"]["incomplete_runs"] = len(incomplete)

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
        except DiscoveryContentError as exc:
            # 发现响应已归档（原件与账本保留），这里只记录解析失败。
            self._record_failure(
                report,
                source_id=context.source.source_id,
                url=exc.url,
                stage="parse",
                error_type="discovery_parse_error",
                message=str(exc),
                attempts=1,
                retryable=False,
                crawl_id=exc.crawl_id,
            )
            stop = DiscoveryStop(
                stage=request.stage,
                entry=exc.url,
                pages=0,
                targets=0,
                stop=STOP_PARSE_ERROR,
                complete=False,
                detail=str(exc),
            )
            context.discoverer.stops.append(stop)
            return DiscoveryResult(
                stage=request.stage,
                strategy=strategy.name,
                status=STATUS_PARSE_ERROR,
                stops=[stop],
                complete=False,
                note=f"发现响应解析失败（原件已归档）：{exc}",
            )
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
                http_status=exc.status_code,
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
        for stop in result.stops:
            if stop.stop != STOP_REQUEST_FAILED:
                continue
            # 后续页请求失败：写失败账（可补抓），同时保留终止原因与游标位置。
            self._record_failure(
                report,
                source_id=context.source.source_id,
                url=stop.next_url or stop.entry,
                stage="fetch",
                error_type=stop.error_type or "request_error",
                message=stop.detail or "后续页请求失败",
                attempts=1,
                retryable=True,
                referrer_url=stop.entry,
            )
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
        after = output_stats(self.data_dir, source_id=report.source_id)
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
            coverage=report.coverage,
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

    def _fetch_target_response(self, source, target: DiscoveredTarget, plan) -> FetchResponse:
        """获取目标响应；非 HTML 原件与附件下载共用同一大小上限边界。

        HTML 页面不受附件上限约束；直达非 HTML 原件（补抓网络失败的附件、手动目标、
        页面跳转后的原件）必须与附件下载同口径边读边判，否则补抓会绕过 S5-04 的
        已声明边界与边界拒绝计数。
        """
        handle = self.http.open(
            target.url,
            source_id=source.source_id,
            conditional=plan.headers or None,
        )
        try:
            if handle.status_code != 304 and not _is_html(handle.headers, handle.final_url):
                content = b"".join(
                    iter_capped_chunks(handle, self.downloader.max_bytes)
                )
            else:
                content = handle.read()
            return FetchResponse(
                requested_url=handle.requested_url,
                final_url=handle.final_url,
                status_code=handle.status_code,
                headers=handle.headers,
                content=content,
                redirect_chain=handle.redirect_chain,
                attempts=handle.attempts,
            )
        finally:
            handle.close()

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
        *,
        parent_url: Optional[str] = None,
        continuation: Optional[BodyContinuation] = None,
        ignore_conditional: bool = False,
    ) -> TargetOutcome:
        scope = scope or RunScope()
        state = self.state.get(target.url)
        if continuation is None and state is not None and state.continuation is not None:
            # A：待处理项尚未回写（进程中断）或已丢失时，以增量状态里的待续位置为准；
            # 两者是同一原子写入，续作进度不会因队列回写失败而消失。
            state_continuation = BodyContinuation.from_dict(state.continuation)
            if state_continuation is not None and state_continuation.mother_url == target.url:
                logger.warning(
                    "按增量状态续作未完成正文 url=%s（待处理项无待续状态）parts=%d",
                    target.url,
                    len(state_continuation.parts),
                )
                continuation = state_continuation
            else:
                # 待续位置不可用（结构损坏或指向别的母页）：不猜进度，也不让 304 冒充完成，
                # 按完整重取处理并留下可见的工程失败记录。
                logger.warning("增量状态中的待续位置不可用，按完整重取处理 url=%s", target.url)
                self._record_failure(
                    report,
                    source_id=source.source_id,
                    url=target.url,
                    stage="validate",
                    error_type="continuation_state_damaged",
                    message="增量状态中的待续位置不可用：按完整重取处理",
                    attempts=1,
                    retryable=False,
                    referrer_url=target.referrer_url,
                    doc_id=state.crawl_id,
                )
                ignore_conditional = True
        if continuation is not None:
            # R2：主目标带正文待续状态时优先续取未完成部分，不从头重取整篇。
            return self._collect_target_continuation(
                source,
                discoverer,
                target,
                continuation,
                crawl_date,
                crawl_time,
                include_attachments,
                report,
                scope,
                parent_url=parent_url,
                state=state,
            )
        try:
            plan = plan_incremental(
                source.resource_kind, None if ignore_conditional else state, now=self.now()
            )
            response = self._fetch_target_response(source, target, plan)
        except AttachmentBoundaryRejected as exc:
            # 非 HTML 原件超过附件大小上限：与附件下载同口径的确定性边界拒绝，
            # 不写失败账、不进重试（补抓不得绕过已声明边界）。
            report.skipped.append(
                SkippedTarget(
                    target.url,
                    f"boundary_rejected:{exc.reason}",
                    target.referrer_url,
                )
            )
            attachments_coverage = report.coverage.get("attachments")
            if attachments_coverage is not None:
                attachments_coverage["boundary_rejected"] += 1
            return TargetOutcome(STATE_SKIPPED, f"boundary_rejected:{exc.reason}")
        except RobotsDisallowed as exc:
            report.skipped.append(
                SkippedTarget(
                    target.url,
                    f"robots_disallowed: {exc.rule or exc}",
                    target.referrer_url,
                )
            )
            return TargetOutcome(STATE_SKIPPED, f"robots_disallowed:{exc.rule or exc}")
        except FetchError as exc:
            self._record_failure(
                report,
                source_id=source.source_id,
                url=target.url,
                stage="fetch",
                error_type="http_error" if exc.status_code else "request_error",
                http_status=exc.status_code,
                message=str(exc),
                attempts=exc.attempts,
                retryable=exc.retryable,
                referrer_url=target.referrer_url,
            )
            error_type = "http_error" if exc.status_code else "request_error"
            return TargetOutcome(STATE_FAILED, f"{error_type}: {exc}")

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
            return TargetOutcome(
                STATE_PROCESSED, "not_modified:304 未变化：复用此前成功原件与账本"
            )

        is_html = _is_html(response.headers, response.final_url)
        kind = "html" if is_html else "attachment"
        archived = self.archiver.archive(
            response,
            source_id=source.source_id,
            kind=kind,
            discovery_method=target.discovery_method,
            keyword=target.keyword,
            referrer_url=target.referrer_url,
            crawl_time=crawl_time,
        )
        raw = archived.raw
        crawl_id = archived.crawl_id
        report.counters.resources += 1
        if not is_html:
            return TargetOutcome(
                STATE_PROCESSED,
                f"resource:{kind}",
                crawl_id=crawl_id,
                raw_path=raw.relative_path,
                sha256=raw.sha256,
            )

        try:
            parsed = normalize_page(
                parse_html(
                    response.content,
                    response.final_url,
                    encoding_hint=_charset(response.headers.get("Content-Type", "")),
                    content_selector=source.adapter.content_selector,
                    date_selector=source.adapter.date_selector,
                    pagination_selector=source.adapter.pagination_selector,
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
            return TargetOutcome(STATE_FAILED, f"parse_error: {exc}")

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
            return TargetOutcome(
                STATE_FAILED,
                f"adapter_selector_miss: {source.adapter.content_selector}",
                crawl_id=crawl_id,
                raw_path=raw.relative_path,
                sha256=raw.sha256,
            )

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
            return TargetOutcome(
                STATE_SKIPPED,
                f"before_start_date:{decision.publication_date}",
                crawl_id=crawl_id,
                raw_path=raw.relative_path,
                sha256=raw.sha256,
            )

        return self._commit_target_document(
            source=source,
            discoverer=discoverer,
            target=target,
            report=report,
            scope=scope,
            parent_url=parent_url,
            include_attachments=include_attachments,
            crawl_date=crawl_date,
            crawl_time=crawl_time,
            parsed=parsed,
            mother_bytes=response.content,
            mother_final_url=response.final_url,
            mother_crawl_id=crawl_id,
            mother_raw_path=raw.relative_path,
            mother_sha256=raw.sha256,
            mother_content_type=response.headers.get("Content-Type", ""),
            doc_id=crawl_id,
            etag=response.headers.get("ETag"),
            last_modified=response.headers.get("Last-Modified"),
        )

    def _collect_target_continuation(
        self,
        source,
        discoverer: Discoverer,
        target: DiscoveredTarget,
        continuation: BodyContinuation,
        crawl_date: str,
        crawl_time: str,
        include_attachments: bool,
        report: RunReport,
        scope: RunScope,
        *,
        parent_url: Optional[str] = None,
        state: Optional[ResourceState] = None,
    ) -> TargetOutcome:
        """R2 续作：先续取未完成正文，母页只做必要校验，304 不取消未完成部分。

        - 304：母响应未变，沿用既有母原件与已保存部分，直接续取下一页/正文接口；
        - 200 且字节与上一版相同（站点无 304 支持时）：同样续取已保存部分；
        - 200 且内容变化：旧 raw 与旧 partial 文档保留，按新版本重新展开正文，
          不把旧版本部分拼进新版；文档身份用「母身份 + 续作序号」，不与 partial 行冲突。

        B：母页返回成功但不再是 HTML 时，响应字节先按原件与账本留存，再决定后续处置，
        不丢原件；正文待续状态保持打开，等待恢复或人工处置。
        """
        if state is None:
            state = self.state.get(target.url)
        try:
            plan = plan_incremental(source.resource_kind, state, now=self.now())
            response = self._fetch_target_response(source, target, plan)
        except AttachmentBoundaryRejected as exc:
            report.skipped.append(
                SkippedTarget(target.url, f"boundary_rejected:{exc.reason}", target.referrer_url)
            )
            return TargetOutcome(
                STATE_SKIPPED, f"boundary_rejected:{exc.reason}", doc_id=continuation.doc_id
            )
        except RobotsDisallowed as exc:
            report.skipped.append(
                SkippedTarget(
                    target.url, f"robots_disallowed: {exc.rule or exc}", target.referrer_url
                )
            )
            return TargetOutcome(
                STATE_SKIPPED, f"robots_disallowed:{exc.rule or exc}", doc_id=continuation.doc_id
            )
        except FetchError as exc:
            self._record_failure(
                report,
                source_id=source.source_id,
                url=target.url,
                stage="fetch",
                error_type="http_error" if exc.status_code else "request_error",
                http_status=exc.status_code,
                message=str(exc),
                attempts=exc.attempts,
                retryable=exc.retryable,
                referrer_url=target.referrer_url,
                doc_id=continuation.doc_id,
            )
            error_type = "http_error" if exc.status_code else "request_error"
            return TargetOutcome(
                STATE_FAILED, f"{error_type}: {exc}", doc_id=continuation.doc_id
            )

        doc_identity = f"{continuation.doc_id}-R{continuation.attempts + 1}"
        if response.status_code == 304:
            report.counters.not_modified += 1
            try:
                mother_bytes = self.layout.resolve_raw_path(
                    continuation.mother_raw_path
                ).read_bytes()
            except (PathSafetyError, OSError) as exc:
                self._record_failure(
                    report,
                    source_id=source.source_id,
                    url=target.url,
                    stage="parse",
                    error_type="continuation_raw_missing",
                    message=f"续接母原件不可读：{continuation.mother_raw_path}（{exc}）",
                    attempts=1,
                    retryable=False,
                    referrer_url=target.referrer_url,
                    crawl_id=continuation.doc_id,
                    doc_id=continuation.doc_id,
                )
                return TargetOutcome(
                    STATE_FAILED,
                    f"continuation_raw_missing:{continuation.mother_raw_path}",
                    doc_id=continuation.doc_id,
                )
            parsed, parsed_failure = self._parse_continuation_mother(
                source,
                target,
                report,
                mother_bytes,
                continuation.mother_final_url,
                continuation.mother_content_type,
                continuation,
            )
            if parsed_failure is not None:
                return parsed_failure
            logger.info(
                "正文续作：母页 304，沿用既有原件与已取部分 url=%s parts=%d",
                target.url,
                len(continuation.parts),
            )
            return self._commit_target_document(
                source=source,
                discoverer=discoverer,
                target=target,
                report=report,
                scope=scope,
                parent_url=parent_url,
                include_attachments=include_attachments,
                crawl_date=crawl_date,
                crawl_time=crawl_time,
                parsed=parsed,
                mother_bytes=mother_bytes,
                mother_final_url=continuation.mother_final_url,
                mother_crawl_id=continuation.doc_id,
                mother_raw_path=continuation.mother_raw_path,
                mother_sha256=continuation.mother_sha256,
                mother_content_type=continuation.mother_content_type,
                doc_id=doc_identity,
                etag=response.headers.get("ETag") or (state.etag if state else None),
                last_modified=response.headers.get("Last-Modified")
                or (state.last_modified if state else None),
                previous=continuation,
            )

        # B：成功响应先留存原件与账本，再判断能不能继续按 HTML 续作正文。
        is_html = _is_html(response.headers, response.final_url)
        archived = self.archiver.archive(
            response,
            source_id=source.source_id,
            kind="html" if is_html else "attachment",
            discovery_method=target.discovery_method,
            keyword=target.keyword,
            referrer_url=target.referrer_url,
            crawl_time=crawl_time,
        )
        report.counters.resources += 1
        if not is_html:
            # 母页不再是 HTML：无法继续正文分页；原件已留存，保留待续状态等待恢复或人工处置。
            content_type = response.headers.get("Content-Type", "")
            self._record_failure(
                report,
                source_id=source.source_id,
                url=target.url,
                stage="parse",
                error_type="continuation_not_html",
                message=f"续接母页返回成功响应但不再是 HTML：{content_type}",
                attempts=1,
                retryable=False,
                referrer_url=target.referrer_url,
                crawl_id=archived.crawl_id,
                doc_id=continuation.doc_id,
            )
            return TargetOutcome(
                STATE_FAILED,
                f"continuation_not_html:{content_type}",
                crawl_id=archived.crawl_id,
                raw_path=archived.raw.relative_path,
                sha256=archived.raw.sha256,
                doc_id=continuation.doc_id,
            )

        same_version = archived.raw.sha256 == continuation.mother_sha256
        parsed, parsed_failure = self._parse_continuation_mother(
            source,
            target,
            report,
            response.content,
            response.final_url,
            response.headers.get("Content-Type", ""),
            continuation,
            crawl_id=archived.crawl_id,
        )
        if parsed_failure is not None:
            return parsed_failure
        if same_version:
            previous: Optional[BodyContinuation] = continuation
            logger.info("正文续作：母页字节与上一版相同，按续接处理 url=%s", target.url)
        else:
            # 新版本：旧 raw 与旧 partial 文档保留；已保存部分属于旧版本，不并入新版。
            previous = None
            logger.warning(
                "正文续作：母页内容已变化，按新版本重新展开 url=%s（旧原件与 partial 文档保留）",
                target.url,
            )
        return self._commit_target_document(
            source=source,
            discoverer=discoverer,
            target=target,
            report=report,
            scope=scope,
            parent_url=parent_url,
            include_attachments=include_attachments,
            crawl_date=crawl_date,
            crawl_time=crawl_time,
            parsed=parsed,
            mother_bytes=response.content,
            mother_final_url=response.final_url,
            mother_crawl_id=archived.crawl_id,
            mother_raw_path=archived.raw.relative_path,
            mother_sha256=archived.raw.sha256,
            mother_content_type=response.headers.get("Content-Type", ""),
            doc_id=archived.crawl_id,
            etag=response.headers.get("ETag"),
            last_modified=response.headers.get("Last-Modified"),
            previous=previous,
        )

    def _commit_target_document(
        self,
        *,
        source,
        discoverer: Discoverer,
        target: DiscoveredTarget,
        report: RunReport,
        scope: RunScope,
        parent_url: Optional[str],
        include_attachments: bool,
        crawl_date: str,
        crawl_time: str,
        parsed: ParsedPage,
        mother_bytes: bytes,
        mother_final_url: str,
        mother_crawl_id: str,
        mother_raw_path: str,
        mother_sha256: str,
        mother_content_type: str,
        doc_id: str,
        etag: Optional[str] = None,
        last_modified: Optional[str] = None,
        previous: Optional[BodyContinuation] = None,
    ) -> TargetOutcome:
        """正文合并、附件收集与文档提交（正常路径与 R2 续作路径共用）。"""
        resume = previous is not None
        expansion = self._expand_body(
            source,
            parsed,
            mother_final_url,
            crawl_date,
            crawl_time,
            report,
            # 正文部分失败的 doc_id 指向母文档身份：恢复关联与待处理项同一口径（R2/R5）。
            doc_id=mother_crawl_id,
            resume_parts=previous.parts if resume else (),
            resume_next_url=previous.next_url if resume else None,
            resume_body_api_url=previous.body_api_url if resume else None,
            resume=resume,
        )
        parsed = expansion.page

        attachments = []
        attachment_stop: Optional[BudgetStop] = None
        if include_attachments and expansion.stop is None:
            attachments, attachment_stop = self._collect_attachments(
                source,
                discoverer,
                [(mother_bytes, mother_final_url), *expansion.extra_pages],
                doc_id,
                crawl_date,
                crawl_time,
                report,
                scope,
                parent_url or mother_final_url,
            )
        stop_after_commit = expansion.stop or attachment_stop
        try:
            document = build_document(
                doc_id=doc_id,
                source_id=source.source_id,
                source_name=source.source_name,
                source_url=mother_final_url,
                title=parsed.title,
                full_text=parsed.full_text,
                language=source.language or parsed.language_hint or "und",
                document_type=source.parser_type or "html_page",
                raw_path=mother_raw_path,
                sha256=mother_sha256,
                crawl_time=crawl_time,
                extraction_method=parsed.extraction_method,
                crawl_ids=[mother_crawl_id, *expansion.extra_crawl_ids],
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
                crawl_id=mother_crawl_id,
                doc_id=mother_crawl_id if resume else None,
            )
            return TargetOutcome(
                STATE_FAILED,
                f"normalization_error: {exc}",
                crawl_id=doc_id,
                raw_path=mother_raw_path,
                sha256=mother_sha256,
            )
        report.counters.documents += document_count
        report.counters.blocks += block_count
        report.documents.append(doc_id)
        continuation = self._next_continuation(
            target=target,
            expansion=expansion,
            mother_crawl_id=mother_crawl_id,
            mother_final_url=mother_final_url,
            mother_raw_path=mother_raw_path,
            mother_sha256=mother_sha256,
            mother_content_type=mother_content_type,
            previous=previous,
        )
        # A：待续位置与增量状态在同一次原子写入中落盘。进程若在回写待处理项之前中断，
        # 重启后母页 304 仍按这里记录的位置续作，不把未完成正文当作完整实体复用。
        self.state.record_success(
            target.url,
            now=self.now(),
            etag=etag,
            last_modified=last_modified,
            sha256=mother_sha256,
            content_hash=text_hash(document["full_text"]),
            crawl_id=doc_id,
            publication_date=document.get("publication_date"),
            version=document.get("version"),
            continuation=continuation.as_dict() if continuation is not None else None,
        )
        if continuation is not None:
            # R2：正文仍有未取部分时保持待续，不写成请求失败、也不冒充整体完成。
            note = f"partial:{expansion.incomplete or 'budget_stop'}"
            return TargetOutcome(
                STATE_PENDING,
                note,
                stop=expansion.stop,
                crawl_id=doc_id,
                raw_path=mother_raw_path,
                sha256=mother_sha256,
                continuation=continuation.as_dict(),
                doc_id=continuation.doc_id,
            )
        if stop_after_commit is not None:
            # 已归档页面、附件与文档全部落盘后再停止本次运行（目标本身算已完成）。
            note = f"partial:{expansion.incomplete or 'attachment_budget_stop'}"
            return TargetOutcome(
                STATE_PROCESSED,
                note,
                stop=stop_after_commit,
                crawl_id=doc_id,
                raw_path=mother_raw_path,
                sha256=mother_sha256,
                # 附件待续有自己的待处理项；正文待续已关闭时才显式清空。
                continuation=None if expansion.stop is None else PENDING_UNSET,
            )
        if expansion.incomplete:
            # R5：正文分页/接口仍不完整（循环/上限/robots/选择器未命中）时不得报告 ok。
            return TargetOutcome(
                STATE_PROCESSED,
                f"partial:{expansion.incomplete}",
                crawl_id=doc_id,
                raw_path=mother_raw_path,
                sha256=mother_sha256,
                continuation=None,
            )
        return TargetOutcome(
            STATE_PROCESSED,
            "ok",
            crawl_id=doc_id,
            raw_path=mother_raw_path,
            sha256=mother_sha256,
            continuation=None,
        )

    def _next_continuation(
        self,
        *,
        target: DiscoveredTarget,
        expansion: BodyExpansion,
        mother_crawl_id: str,
        mother_final_url: str,
        mother_raw_path: str,
        mother_sha256: str,
        mother_content_type: str,
        previous: Optional[BodyContinuation],
    ) -> Optional[BodyContinuation]:
        """把未完成的正文位置转成待续状态；确定性终止（循环/上限/robots）不建立。"""
        continuable = expansion.stop is not None or (
            bool(expansion.incomplete)
            and expansion.incomplete.startswith(CONTINUABLE_REASONS)
        )
        if not continuable:
            return None
        if not expansion.next_url and not expansion.body_api_url:
            return None
        return BodyContinuation(
            doc_id=mother_crawl_id,
            mother_url=target.url,
            mother_final_url=mother_final_url,
            mother_raw_path=mother_raw_path,
            mother_sha256=mother_sha256,
            mother_content_type=mother_content_type,
            next_url=expansion.next_url,
            body_api_url=expansion.body_api_url,
            parts=tuple(expansion.part_refs),
            stop_reason=expansion.incomplete or "budget_stop",
            attempts=(previous.attempts if previous is not None else 0) + 1,
            updated_at=self.now().isoformat(),
        )

    @staticmethod
    def _parse_html_page(
        source, content: bytes, final_url: str, content_type: str = ""
    ) -> ParsedPage:
        """HTML 解析 + 规范化；与正常采集路径同一解析器与选择器配置。"""
        return normalize_page(
            parse_html(
                content,
                final_url,
                encoding_hint=_charset(content_type or ""),
                content_selector=source.adapter.content_selector,
                date_selector=source.adapter.date_selector,
                pagination_selector=source.adapter.pagination_selector,
            ),
            language_hints=(source.language,),
            base_url=final_url,
        )

    def _parse_continuation_mother(
        self,
        source,
        target: DiscoveredTarget,
        report: RunReport,
        content: bytes,
        final_url: str,
        content_type: str,
        continuation: BodyContinuation,
        *,
        crawl_id: Optional[str] = None,
    ) -> Tuple[Optional[ParsedPage], Optional[TargetOutcome]]:
        """解析续作母页；失败返回 (None, 明确失败结果) 并留痕，不静默继续续作。

        与正常采集路径同一判定：解析异常与适配正文选择器未命中都按失败处理，
        避免母页结构变化后用回退正文冒充“已完成”；待续状态保持打开待恢复或人工处置。
        """
        try:
            parsed = self._parse_html_page(source, content, final_url, content_type)
        except Exception as exc:  # noqa: BLE001 - 解析失败保留原件与失败记录
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
                crawl_id=crawl_id or continuation.doc_id,
                doc_id=continuation.doc_id,
            )
            return None, TargetOutcome(
                STATE_FAILED,
                f"parse_error: {exc}",
                crawl_id=crawl_id,
                doc_id=continuation.doc_id,
            )
        if parsed.content_selector_missed:
            self._record_failure(
                report,
                source_id=source.source_id,
                url=target.url,
                stage="parse",
                error_type="adapter_selector_miss",
                message=f"续接母页适配正文选择器未命中：{source.adapter.content_selector}",
                attempts=1,
                retryable=False,
                referrer_url=target.referrer_url,
                crawl_id=crawl_id or continuation.doc_id,
                doc_id=continuation.doc_id,
            )
            return None, TargetOutcome(
                STATE_FAILED,
                f"adapter_selector_miss: {source.adapter.content_selector}",
                crawl_id=crawl_id,
                doc_id=continuation.doc_id,
            )
        return parsed, None

    def _restore_body_part(
        self,
        source,
        ref: dict,
        report: RunReport,
        *,
        doc_id: Optional[str] = None,
        referrer: Optional[str] = None,
    ) -> Optional[Tuple[List[ParsedBlock], bytes, str]]:
        """从已归档原件重建一个已取得部分；原件缺失/损坏时返回 None 并留痕。"""
        raw_path = str(ref.get("raw_path") or "")
        url = str(ref.get("url") or "")
        method = str(ref.get("method") or "pagination")
        try:
            content = self.layout.resolve_raw_path(raw_path).read_bytes()
        except (PathSafetyError, OSError) as exc:
            self._record_failure(
                report,
                source_id=source.source_id,
                url=url,
                stage="parse",
                error_type="continuation_part_unreadable",
                message=f"已取得正文部分原件不可读：{raw_path}（{exc}）",
                attempts=1,
                retryable=False,
                referrer_url=referrer,
                crawl_id=ref.get("crawl_id"),
                doc_id=doc_id,
            )
            return None
        final_url = str(ref.get("final_url") or url)
        try:
            if method == "api":
                payload = json.loads(decode_html(content))
                body = _body_text_from_payload(payload)
                if not body:
                    raise ValueError("接口原件未包含候选正文字段")
                if "<" in body:
                    parsed = normalize_page(
                        parse_html(body.encode("utf-8"), final_url),
                        language_hints=(source.language,),
                        base_url=final_url,
                    )
                    blocks = list(parsed.blocks)
                else:
                    blocks = [ParsedBlock(block_type="paragraph", text=" ".join(body.split()))]
            else:
                parsed = self._parse_html_page(
                    source, content, final_url, str(ref.get("content_type") or "")
                )
                blocks = list(parsed.blocks)
        except Exception as exc:
            self._record_failure(
                report,
                source_id=source.source_id,
                url=url,
                stage="parse",
                error_type="continuation_part_unreadable",
                message=f"已取得正文部分无法重建：{raw_path}（{exc}）",
                attempts=1,
                retryable=False,
                referrer_url=referrer,
                crawl_id=ref.get("crawl_id"),
                doc_id=doc_id,
            )
            return None
        return blocks, content, final_url

    def _expand_body(
        self,
        source,
        parsed: ParsedPage,
        page_url: str,
        crawl_date: str,
        crawl_time: str,
        report: RunReport,
        doc_id: Optional[str] = None,
        *,
        resume_parts: Sequence[dict] = (),
        resume_next_url: Optional[str] = None,
        resume_body_api_url: Optional[str] = None,
        resume: bool = False,
    ) -> BodyExpansion:
        """还原正文分页与接口加载正文（FR-005）。

        只跟随内容区内的下一页链接（rel=next 或明确翻页文案），上限 MAX_BODY_PARTS；
        每个附加部分独立归档并记账（discovery_method=pagination），块按部分顺序合并到
        同一文档、页码取部分序号。接口正文按页面声明的 JSON 端点获取（discovery_method=api），
        正文为 HTML 时按同一 HTML 解析器抽取，纯文本按单一文本块保留。
        任一部分失败不静默：写入失败账并保持文档 parse_status=partial。失败行带母文档
        doc_id，供恢复关联回到具体母目标（R5），不按 URL 关闭其它窗口。

        R2 续作：``resume_parts`` 按保存顺序从原件重建已取得部分（不重复请求、不重复
        拼接），``resume_next_url``/``resume_body_api_url`` 给出未取位置；母页 304 只
        说明母响应未变，未完成正文与附件继续取，不被首响应阻断。

        D：无论分页与接口正文谁先取得，合并顺序固定为“母页 → 分页各部分 → 接口正文”，
        页码按分页顺序编号；因此“分页失败、接口可用、随后恢复”的文档与一次成功抓取
        在正文顺序、块顺序与页码上一致，也不重复拼接已保存块。
        """

        first_blocks = list(parsed.blocks)
        pagination_blocks: List[ParsedBlock] = []
        pagination_refs: List[dict] = []
        api_blocks: List[ParsedBlock] = []
        api_ref: Optional[dict] = None
        extra_crawl_ids: List[str] = []
        extra_pages: List[Tuple[bytes, str]] = []
        incomplete: Optional[str] = None
        budget_stop: Optional[BudgetStop] = None
        parts = 1
        visited = {page_url}
        next_url = resume_next_url if resume else parsed.next_page_url
        pending_api = resume_body_api_url if resume else parsed.body_api_url
        referrer = page_url

        # R2：已取得部分按保存顺序从原件重建；全部可重建时才继续请求未取部分，
        # 避免把不可重建的部分悄悄跳过或重复拼接。
        for ref in resume_parts:
            part_url = str(ref.get("url") or "")
            if part_url:
                visited.add(part_url)
            restored = self._restore_body_part(
                source, ref, report, doc_id=doc_id, referrer=referrer
            )
            if restored is None:
                incomplete = f"resume_part_failed:{part_url}"
                next_url = part_url or None
                break
            part_blocks, part_content, part_final_url = restored
            if ref.get("method") == "pagination":
                parts += 1
                pagination_blocks.extend(
                    replace(block, page_no=parts) for block in part_blocks
                )
                pagination_refs.append(dict(ref))
            else:
                if pending_api:
                    # 记录里既有接口部分又有未取接口位置：以未取位置为准，避免重复拼接。
                    logger.warning(
                        "续作状态同时含接口部分与未取接口位置，保留未取位置 url=%s",
                        str(ref.get("url") or ""),
                    )
                    referrer = part_final_url
                    continue
                api_blocks = list(part_blocks)
                api_ref = dict(ref)
            extra_crawl_ids.append(str(ref["crawl_id"]))
            extra_pages.append((part_content, part_final_url))
            referrer = part_final_url
        else:
            while next_url:
                requested_url = next_url
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
                        http_status=exc.status_code,
                        message=str(exc),
                        attempts=exc.attempts,
                        retryable=exc.retryable,
                        referrer_url=referrer,
                        doc_id=doc_id,
                    )
                    incomplete = f"pagination_fetch_failed:{next_url}"
                    break
                archived = self.archiver.archive(
                    part,
                    source_id=source.source_id,
                    kind="html",
                    discovery_method="pagination",
                    referrer_url=referrer,
                    crawl_time=crawl_time,
                )
                raw = archived.raw
                part_crawl_id = archived.crawl_id
                report.counters.resources += 1
                try:
                    part_parsed = self._parse_html_page(
                        source, part.content, part.final_url, part.headers.get("Content-Type", "")
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
                        doc_id=doc_id,
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
                        doc_id=doc_id,
                    )
                    incomplete = f"pagination_selector_miss:{next_url}"
                    break
                parts += 1
                pagination_blocks.extend(
                    replace(block, page_no=parts) for block in part_parsed.blocks
                )
                extra_crawl_ids.append(part_crawl_id)
                extra_pages.append((part.content, part.final_url))
                pagination_refs.append(
                    {
                        "url": requested_url,
                        "final_url": part.final_url,
                        "crawl_id": part_crawl_id,
                        "raw_path": raw.relative_path,
                        "sha256": raw.sha256,
                        "method": "pagination",
                        "content_type": part.headers.get("Content-Type", ""),
                    }
                )
                referrer = part.final_url
                next_url = part_parsed.next_page_url

        if pending_api:
            try:
                api_result = self._fetch_body_api(
                    source,
                    pending_api,
                    referrer,
                    crawl_date,
                    crawl_time,
                    report,
                    doc_id=doc_id,
                )
            except BudgetStop as stop:
                api_result = None
                budget_stop = budget_stop or stop
                incomplete = incomplete or f"budget_stop:{stop.reason}"
                logger.warning("接口正文按预算停止 url=%s reason=%s", pending_api, stop.reason)
            if api_result is None:
                incomplete = incomplete or f"body_api_failed:{pending_api}"
            else:
                api_blocks, api_ref = api_result
                extra_crawl_ids.append(str(api_ref["crawl_id"]))
                pending_api = None

        # D：引用与块按“分页（原顺序）→ 接口正文”重排后统一编号，与一次成功抓取一致。
        part_refs: List[dict] = []
        for position, ref in enumerate(pagination_refs, start=2):
            part_refs.append({**ref, "order": position})
        if api_ref is not None:
            part_refs.append({**api_ref, "order": len(part_refs) + 2})

        if pagination_blocks:
            blocks = [replace(block, page_no=1) for block in first_blocks] + pagination_blocks
        else:
            blocks = first_blocks + pagination_blocks
        blocks = list(blocks) + list(api_blocks)
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
            part_refs=part_refs,
            next_url=next_url,
            body_api_url=pending_api,
        )

    def _fetch_body_api(
        self,
        source,
        api_url: str,
        referrer: str,
        crawl_date: str,
        crawl_time: str,
        report: RunReport,
        doc_id: Optional[str] = None,
    ):
        """获取接口正文档：归档、记账后按候选字段取正文；失败返回 None 并留痕。

        成功返回 (blocks, 部分引用)：引用含 crawl_id/raw_path/sha256/顺序，供 R2 待续。
        """
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
                http_status=exc.status_code,
                message=str(exc),
                attempts=exc.attempts,
                retryable=exc.retryable,
                referrer_url=referrer,
                doc_id=doc_id,
            )
            return None
        archived = self.archiver.archive(
            response,
            source_id=source.source_id,
            kind="api",
            discovery_method="api",
            referrer_url=referrer,
            crawl_time=crawl_time,
        )
        raw = archived.raw
        crawl_id = archived.crawl_id
        report.counters.resources += 1
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
                doc_id=doc_id,
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
                doc_id=doc_id,
            )
            return None
        if "<" in body:
            parsed = normalize_page(
                parse_html(body.encode("utf-8"), response.final_url),
                language_hints=(source.language,),
                base_url=response.final_url,
            )
            blocks = list(parsed.blocks)
        else:
            text = " ".join(body.split())
            blocks = [ParsedBlock(block_type="paragraph", text=text)]
        ref = {
            "url": api_url,
            "final_url": response.final_url,
            "crawl_id": crawl_id,
            "raw_path": raw.relative_path,
            "sha256": raw.sha256,
            "method": "api",
            "content_type": response.headers.get("Content-Type", ""),
        }
        return blocks, ref

    def _collect_attachments(
        self,
        source,
        discoverer: Discoverer,
        pages: Sequence[Tuple[bytes, str]],
        doc_id: str,
        crawl_date: str,
        crawl_time: str,
        report: RunReport,
        scope: RunScope,
        parent_url: Optional[str],
    ) -> Tuple[List[dict], Optional[BudgetStop]]:
        """下载附件；成功/失败/边界拒绝/待处理分别记账，预算停止不丢已归档原件。

        - 规则排除（扩展名不在声明范围、适配附件规则不匹配）不下载，只按页聚合计数；
        - robots 或访问边界拒绝记 boundary_rejected 并进 skipped，不写成网站失败；
        - 网络/HTTP 失败写失败账并记 failed；
        - 预算停止时尚未尝试的附件记 pending 并写入待处理存储，下一轮继续下载。
        """
        attachment_targets: List[DiscoveredTarget] = []
        seen = set()
        candidate_count = 0
        for html_bytes, page_url in pages:
            for target in discoverer.attachments_from_html(html_bytes, page_url):
                candidate_count += 1
                if target.url in seen:
                    continue
                seen.add(target.url)
                attachment_targets.append(target)
        duplicates = candidate_count - len(attachment_targets)
        coverage = report.coverage["attachments"]
        coverage["discovered"] += len(attachment_targets)
        if duplicates:
            coverage["duplicates"] += duplicates
            discoverer.attachment_duplicates.append(
                {"page": pages[-1][1] if pages else parent_url or "", "count": duplicates}
            )
        attachments: List[dict] = []
        for index, target in enumerate(attachment_targets, 1):
            record = self._attachment_record(doc_id, index, target)
            try:
                resource = self.downloader.download(target.url, source_id=source.source_id)
            except BudgetStop as stop:
                pending_records = [
                    self._attachment_record(doc_id, index + offset, item)
                    for offset, item in enumerate(attachment_targets[index - 1:])
                ]
                for item in pending_records:
                    item["status"] = STATE_PENDING
                added = 0
                if parent_url:
                    added = self.pending.enqueue_attachments(
                        source_id=source.source_id,
                        scope_start_date=(
                            scope.start_date.isoformat() if scope.start_date else None
                        ),
                        doc_id=doc_id,
                        parent_url=parent_url,
                        records=pending_records,
                        enqueued_at=crawl_time,
                    )
                logger.warning(
                    "附件下载按预算停止 url=%s reason=%s；未尝试附件 %d 项已登记待处理（新增 %d）",
                    target.url,
                    stop.reason,
                    len(pending_records),
                    added,
                )
                return attachments + pending_records, stop
            except RobotsDisallowed as exc:
                report.skipped.append(
                    SkippedTarget(
                        target.url,
                        f"robots_disallowed: {exc.rule or exc}",
                        target.referrer_url,
                    )
                )
                record["status"] = "boundary_rejected"
                record["note"] = f"robots_disallowed:{exc.rule or exc}"
                coverage["boundary_rejected"] += 1
                attachments.append(record)
                continue
            except AttachmentBoundaryRejected as exc:
                report.skipped.append(
                    SkippedTarget(
                        target.url,
                        f"boundary_rejected:{exc.reason}",
                        target.referrer_url,
                    )
                )
                record["status"] = "boundary_rejected"
                record["note"] = f"boundary_rejected:{exc.reason}"
                coverage["boundary_rejected"] += 1
                attachments.append(record)
                continue
            except FetchError as exc:
                self._record_failure(
                    report,
                    source_id=source.source_id,
                    url=target.url,
                    stage="fetch",
                    error_type="http_error" if exc.status_code else "request_error",
                    http_status=exc.status_code,
                    message=str(exc),
                    attempts=exc.attempts,
                    retryable=exc.retryable,
                    referrer_url=target.referrer_url,
                    doc_id=doc_id,
                )
                record["status"] = "failed"
                record["note"] = str(exc)
                coverage["failed"] += 1
                attachments.append(record)
                continue
            archived = self.archiver.archive_bytes(
                resource.content,
                source_id=source.source_id,
                kind="attachment",
                filename=resource.filename,
                discovery_method="attachment",
                requested_url=resource.requested_url,
                final_url=resource.final_url,
                status_code=resource.status_code,
                content_type=resource.content_type,
                referrer_url=target.referrer_url,
                crawl_time=crawl_time,
            )
            report.counters.resources += 1
            record.update(
                {
                    "filename": resource.filename,
                    "status": "downloaded",
                    "raw_path": archived.raw.relative_path,
                    "sha256": archived.raw.sha256,
                    "crawl_id": archived.crawl_id,
                }
            )
            coverage["downloaded"] += 1
            attachments.append(record)
        return attachments, None

    @staticmethod
    def _attachment_record(doc_id: str, index: int, target: DiscoveredTarget) -> dict:
        """附件记录骨架：母文档、序号、URL 与文件名；状态由下载结果填写。"""
        name = sanitize_filename(_basename(target.url)) or f"attachment-{index:02d}"
        return {
            "attachment_id": f"{doc_id}_A{index:02d}",
            "filename": name,
            "file_type": _file_type(target.url),
            "url": target.url,
            "doc_id": doc_id,
            "referrer_url": target.referrer_url,
        }

    def _collect_pending_attachment(
        self,
        source,
        item: PendingItem,
        report: RunReport,
        crawl_date: str,
        crawl_time: str,
    ) -> TargetOutcome:
        """续传上一轮预算停止时留下的附件：重新下载并按原件 + 账本留存。

        附件原件与账本是 raw 优先交付的核对对象；已提交文档不回写（文档追加写入口径
        不变），母文档关联保存在待处理项（doc_id/parent_url）与账本 referrer_url 中。
        """
        target = DiscoveredTarget(
            url=item.url,
            discovery_method="attachment",
            referrer_url=item.referrer_url or item.parent_url,
        )
        coverage = report.coverage["attachments"]
        try:
            resource = self.downloader.download(item.url, source_id=source.source_id)
        except BudgetStop:
            raise
        except RobotsDisallowed as exc:
            report.skipped.append(
                SkippedTarget(
                    item.url,
                    f"robots_disallowed: {exc.rule or exc}",
                    target.referrer_url,
                )
            )
            coverage["boundary_rejected"] += 1
            return TargetOutcome(STATE_SKIPPED, f"robots_disallowed:{exc.rule or exc}")
        except AttachmentBoundaryRejected as exc:
            # 确定性边界拒绝（大小上限等）：不写失败账、不进重试队列。
            report.skipped.append(
                SkippedTarget(item.url, f"boundary_rejected:{exc.reason}", target.referrer_url)
            )
            coverage["boundary_rejected"] += 1
            return TargetOutcome(STATE_SKIPPED, f"boundary_rejected:{exc.reason}")
        except FetchError as exc:
            self._record_failure(
                report,
                source_id=source.source_id,
                url=item.url,
                stage="fetch",
                error_type="http_error" if exc.status_code else "request_error",
                http_status=exc.status_code,
                message=str(exc),
                attempts=exc.attempts,
                retryable=exc.retryable,
                referrer_url=target.referrer_url,
                doc_id=item.doc_id,
            )
            coverage["failed"] += 1
            return TargetOutcome(STATE_FAILED, str(exc))
        archived = self.archiver.archive_bytes(
            resource.content,
            source_id=source.source_id,
            kind="attachment",
            filename=resource.filename,
            discovery_method="attachment",
            requested_url=resource.requested_url,
            final_url=resource.final_url,
            status_code=resource.status_code,
            content_type=resource.content_type,
            referrer_url=target.referrer_url,
            crawl_time=crawl_time,
        )
        report.counters.resources += 1
        # downloaded 统计本轮归档成功的附件；resumed 说明其中来自上一轮待处理项。
        coverage["downloaded"] += 1
        coverage["resumed"] += 1
        return TargetOutcome(
            STATE_PROCESSED,
            f"attachment_resumed:{item.doc_id or '-'}",
            crawl_id=archived.crawl_id,
            raw_path=archived.raw.relative_path,
            sha256=archived.raw.sha256,
        )

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
        http_status: Optional[int] = None,
        referrer_url: Optional[str] = None,
        crawl_id: Optional[str] = None,
        final_action: Optional[str] = None,
        doc_id: Optional[str] = None,
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
            http_status=http_status,
            crawl_id=crawl_id,
            referrer_url=referrer_url,
            scope_start_date=(
                self._object_scope().start_date.isoformat()
                if self._object_scope().start_date
                else None
            ),
            doc_id=doc_id,
        )
        report.failures.append(row)
        report.counters.failures += 1

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
        before = output_stats(self.data_dir, source_id=source_id)
        requests_before = self.http.request_attempts
        # 与 collect 相同：补抓的预算以本次调用传入的为准，遗留预算不跨轮生效。
        self.http.attach_budget(budget)
        if budget is not None:
            budget.start()
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
            if (
                (row.get("source_id") or None) == (task.source_id or None)
                and row.get("url") == task.url
                and row.get("stage") == task.stage
                and (row.get("scope_start_date") or None) == (task.scope_start_date or None)
                and (row.get("doc_id") or None) == (task.doc_id or None)
            ):
                return row
        return {
            "source_id": task.source_id,
            "url": task.url,
            "stage": task.stage,
            "scope_start_date": task.scope_start_date,
            "doc_id": task.doc_id,
        }

    def _recover_refetch(
        self,
        source,
        task: RecoveryTask,
        moment: datetime,
        scope: Optional[RunScope] = None,
    ) -> Optional[dict]:
        """补抓网络阶段失败：以 _collect_target 的显式结果判定，不用资源计数代替状态。

        R5：取得原件（resources 非零）不等于目标已恢复。分支：

        - 完整成功（processed 且非 partial）→ 关闭失败，待处理项按同一身份标 processed；
        - 304：仅当既有实体完整（有 crawl_id 且对应文档已落盘）才算合法未变化；
        - partial（正文/附件仍待续）→ 原件已取得，fetch 阶段可关闭，但待处理项保持
          pending 并记录待续原因，不把主目标当作整体完成；预算停止时保持失败开放；
        - 解析/规范化等派生阶段失败 → 保持 failed 且失败账不追加 recovered 行
          （新增处置行会按同一身份成为“最新处置”，掩盖仍未关闭的派生失败）；
        - 合法跳过（robots/边界/范围外）→ 按 skip 关闭。
        """
        report = RunReport(source_id=source.source_id)
        # C：任务指向正文部分（分页/接口）时回到同一母文档的待续载体，按母页续作；
        # 不为片段单独产出文档，也不按 URL 关闭其它对象。
        continuation, resume_item = self._resume_object(source.source_id, task)
        target = DiscoveredTarget(
            url=resume_item.url if resume_item is not None else task.url,
            discovery_method="retry",
            referrer_url=task.referrer_url,
        )
        crawl_date = moment.date().isoformat()
        # R2：补抓同样按既有待续状态续取未完成正文，不因母页 304 丢掉未取部分。
        outcome = self._collect_target(
            source,
            None,
            target,
            crawl_date,
            moment.isoformat(),
            False,
            report,
            scope,
            continuation=continuation,
        )
        attempt = {
            "crawl_id": outcome.crawl_id,
            "raw_path": outcome.raw_path,
            "sha256": outcome.sha256,
        }
        if outcome.state == STATE_PROCESSED and outcome.note.startswith("not_modified"):
            if not self._previous_entity_complete(task.url):
                logger.warning(
                    "补抓 304 但既有实体不完整，保持失败开放 url=%s", task.url
                )
                return None
        if outcome.state == STATE_PROCESSED and not outcome.note.startswith("partial:"):
            note = "补抓成功，账本与文档已更新"
            self._reconcile_pending_item(
                source,
                task,
                state=STATE_PROCESSED,
                note=note,
                **attempt,
            )
            return {
                "note": note,
                "resources": report.counters.resources,
                "documents": report.counters.documents,
                "blocks": report.counters.blocks,
            }
        if outcome.state == STATE_PROCESSED:
            note = f"原件已取得，内容仍待续（{outcome.note}）；目标保持待处理"
            self._reconcile_pending_item(
                source, task, state=STATE_PENDING, note=note, **attempt
            )
            if outcome.stop is not None:
                # 预算停止：待续状态已保存，本次补抓在这里停下来。
                raise outcome.stop
            return {
                "note": note,
                "resources": report.counters.resources,
                "documents": report.counters.documents,
                "blocks": report.counters.blocks,
            }
        if outcome.state == STATE_FAILED:
            # 派生阶段失败：目标整体仍未恢复，保持失败开放并保留原件定位。
            note = f"补抓取得原件但后续阶段失败：{outcome.note}"
            self._reconcile_pending_item(
                source, task, state=STATE_FAILED, note=note, **attempt
            )
            logger.warning("补抓未完成 url=%s note=%s", task.url, note)
            return None
        robots_skip = next(
            (item for item in report.skipped if item.reason.startswith("robots_disallowed:")),
            None,
        )
        if robots_skip is not None:
            note = f"robots 规则拒绝，按 skip 关闭：{robots_skip.reason}"
            self._reconcile_pending_item(source, task, state=STATE_SKIPPED, note=note)
            return {"note": note, "action": "skip"}
        boundary_skip = next(
            (item for item in report.skipped if item.reason.startswith("boundary_rejected:")),
            None,
        )
        if boundary_skip is not None:
            note = f"边界拒绝，按 skip 关闭：{boundary_skip.reason}"
            self._reconcile_pending_item(source, task, state=STATE_SKIPPED, note=note)
            return {"note": note, "action": "skip"}
        out_of_window = next(
            (item for item in report.skipped if item.reason.startswith("before_start_date:")),
            None,
        )
        if out_of_window is not None:
            note = f"原运行范围外，按 skip 关闭：{out_of_window.reason}"
            self._reconcile_pending_item(
                source, task, state=STATE_SKIPPED, note=note, **attempt
            )
            return {"note": note, "action": "skip"}
        return None

    def _previous_entity_complete(self, url: str) -> bool:
        """304 的关闭前提：既有成功实体完整（有 crawl_id 且对应文档已落盘）。

        只有“未变化 + 既有实体可用”才能复用历史原件；缺少文档时 304 不能证明
        目标已恢复，保持失败开放。
        """
        state = self.state.get(url)
        if state is None or not state.crawl_id:
            return False
        crawl_id = state.crawl_id
        for row in read_jsonl(self.layout.documents_path):
            if row.get("doc_id") == crawl_id or crawl_id in (row.get("crawl_ids") or []):
                return True
        return False

    def _reconcile_pending_item(
        self,
        source,
        task: RecoveryTask,
        *,
        state: str,
        note: str,
        crawl_id: Optional[str] = None,
        raw_path: Optional[str] = None,
        sha256: Optional[str] = None,
    ) -> List[str]:
        """补抓处置回写同对象的待处理项：队列口径与失败账处置对账一致（S5-06）。

        失败账驱动的补抓不改写已提交文档（追加写口径不变），但同一 URL 的待处理项
        必须同步关闭，否则覆盖表长期显示失败/待处理，与账本已关闭的处置互相矛盾。

        R5/C 身份口径：来源 + 对象 URL 或母文档待续载体 + 原运行范围 + 必要的母文档
        关系。同 URL 但不同 scope 或不同母文档（doc_id/母页）的待处理项不互相关闭；
        身份无法判定时宁可不动，也不按 URL 批量关闭。返回实际回写的 key 列表。
        """
        matched: List[str] = []
        for item in self.pending.all_items():
            if item.source_id != source.source_id:
                continue
            if (item.scope_start_date or None) != (task.scope_start_date or None):
                continue
            if not _same_recovery_object(
                item, task, continuation=BodyContinuation.from_dict(item.continuation)
            ):
                logger.info(
                    "补抓身份不一致，跳过待处理项 key=%s（task doc_id=%s referrer=%s）",
                    item.key,
                    task.doc_id,
                    task.referrer_url,
                )
                continue
            if item.state == state and (item.note or "") == (note or ""):
                # 已按同一身份、同一处置登记过：幂等，不重复写。
                matched.append(item.key)
                continue
            self.pending.mark(
                item.key,
                state=state,
                attempted_at=self.now().isoformat(),
                note=note,
                crawl_id=crawl_id,
                raw_path=raw_path,
                sha256=sha256,
                # 完整处理时才清除待续；待续/失败处置保持原续作状态。
                continuation=None if state == STATE_PROCESSED else PENDING_UNSET,
            )
            logger.info("补抓回写待处理项 key=%s state=%s", item.key, state)
            matched.append(item.key)
        if not matched:
            logger.warning(
                "补抓未匹配到同身份待处理项 url=%s scope=%s doc_id=%s（不按 URL 关闭其它对象）",
                task.url,
                task.scope_start_date,
                task.doc_id,
            )
        return matched

    def _resume_object(
        self, source_id: str, task: RecoveryTask
    ) -> Tuple[Optional[BodyContinuation], Optional[PendingItem]]:
        """恢复对象解析（C）：返回 (待续状态, 待处理项)；无匹配返回 (None, None)。

        - 任务 URL 与待处理项一致：按该项目的续作状态（原有补抓行为）；
        - 任务 URL 是母文档的正文分页/接口部分（带母文档身份）：返回该母文档的续作
          载体，按母页续作；这样片段失败不会单独产出文档，也不会丢掉母文档进度。
        """
        fragment: Tuple[Optional[BodyContinuation], Optional[PendingItem]] = (None, None)
        for item in self.pending.all_items():
            if item.source_id != source_id:
                continue
            if (item.scope_start_date or None) != (task.scope_start_date or None):
                continue
            continuation = BodyContinuation.from_dict(item.continuation)
            if item.url == task.url:
                if (item.doc_id or None) != (task.doc_id or None):
                    continue
                if not _same_recovery_object(item, task, continuation=continuation):
                    continue
                return continuation, item
            if not task.doc_id or continuation is None:
                continue
            if continuation.doc_id == task.doc_id and (item.doc_id or None) == task.doc_id:
                fragment = (continuation, item)
        return fragment

    def _recover_reparse(
        self,
        source,
        task: RecoveryTask,
        moment: datetime,
        scope: Optional[RunScope] = None,
    ) -> Optional[dict]:
        continuation, resume_item = self._resume_object(source.source_id, task)
        if resume_item is not None and (
            resume_item.url != task.url or continuation is not None
        ):
            # C：正文分页/接口片段不能独立成文；对象仍有未完成正文时回到母页续作，
            # 这样重解析任务不会产出片段文档，也不会把母文档的待续状态当成已补齐。
            logger.info(
                "重解析任务指向正文片段或未完成正文，转为按母文档续作 url=%s mother=%s",
                task.url,
                resume_item.url,
            )
            return self._recover_refetch(source, task, moment, scope)
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
                note = (
                    f"原运行范围外（{decision.kind}:{decision.publication_date}）："
                    "原件保留，不产出文档"
                )
                self._reconcile_pending_item(
                    source, task, state=STATE_SKIPPED, note=note, raw_path=raw_path
                )
                return {"note": note, "action": "skip"}
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
        self._reconcile_pending_item(
            source,
            task,
            state=STATE_PROCESSED,
            note="重解析成功，文档与块已补全",
            crawl_id=crawl_id,
            raw_path=raw_path,
            sha256=document["sha256"],
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


def _same_recovery_object(
    item: PendingItem,
    task: RecoveryTask,
    *,
    continuation: Optional[BodyContinuation] = None,
) -> bool:
    """恢复身份（R5/C）：任务与待处理项指向同一对象时才允许回写。

    - URL 相同：任务带母文档 doc_id 时，待处理项必须指向同一母文档；待处理项没有
      母文档身份说明对象类型不同（如目标是页面、任务是附件），不匹配；
    - URL 不同：仅当任务带母文档身份，且待处理项正是该母文档的正文待续载体
      （分页/接口部分失败回到母目标）时算同一对象；
    - 任务带 referrer_url 时，同 URL 的待处理项 referrer/parent 必须有一个与之一致
      （同一附件挂在不同母页下不算同一对象）；
    - 来源与原运行范围由调用方先行匹配；任一侧缺字段时按可判定部分判断，
      不凭缺失推断为同一对象。
    """
    if task.doc_id:
        if not item.doc_id or item.doc_id != task.doc_id:
            return False
    if item.url != task.url:
        return bool(
            task.doc_id
            and continuation is not None
            and continuation.doc_id == task.doc_id
            and continuation.mother_url == item.url
        )
    if task.referrer_url:
        candidates = {value for value in (item.referrer_url, item.parent_url) if value}
        if candidates and task.referrer_url not in candidates:
            return False
    return True


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
