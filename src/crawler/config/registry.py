"""来源注册、配置校验与访问边界检查（T004）。

来源配置只来自登记文件；未登记域名、协议或路径一律拒绝，重定向逐跳复用同一
检查。配置变更通过路径、版本与 SHA-256 摘要留痕，便于追溯。
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence, Tuple
from urllib.parse import urlsplit

import yaml

from crawler.config.settings import ConfigurationError
from crawler.schedule.policy import TRIGGERS, ScheduleConfigError, get_rule

logger = logging.getLogger(__name__)

SOURCE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
DOMAIN_PATTERN = re.compile(
    r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$"
)
AUTHORITY_LEVELS = ("A1", "A2", "B", "C")
STANCE_DEFAULTS = ("CN_OFFICIAL", "IN_OFFICIAL", "BILATERAL", "NEUTRAL")
ALLOWED_SCHEMES = ("http", "https")
RESOURCE_KINDS = ("news", "law", "statistics", "general")

DEFAULT_CONFIG_PATH = Path(__file__).with_name("sources.yaml")


@dataclass(frozen=True)
class AccessDecision:
    """一次访问边界判定；reason 记录拒绝原因或命中来源。"""

    allowed: bool
    reason: str


@dataclass(frozen=True)
class SourceAdapter:
    """来源专属适配规则（T026 机制；未配置时全部使用通用规则）。

    规则是逐来源显式配置：列表页文档链接、分页控件与正文范围。选择器/正则
    未命中时由发现与采集流程显式记录（跳过或失败账），不静默回退到通用规则。
    discovery 声明该来源已实现/已核验的发现方式（list/search/sitemap/api）；
    未声明的发现方式显式记为未实现，不以空结果冒充成功。
    """

    list_link_selector: Optional[str] = None
    list_link_pattern: Optional[str] = None
    list_link_rewrite: Optional[Tuple[Tuple[str, str], ...]] = None
    attachment_pattern: Optional[str] = None
    pagination_selector: Optional[str] = None
    max_pages: Optional[int] = None
    content_selector: Optional[str] = None
    date_selector: Optional[str] = None
    discovery: Optional[Tuple[str, ...]] = None

    @property
    def configured(self) -> bool:
        return any(
            value is not None
            for value in (
                self.list_link_selector,
                self.list_link_pattern,
                self.list_link_rewrite,
                self.attachment_pattern,
                self.pagination_selector,
                self.max_pages,
                self.content_selector,
                self.date_selector,
                self.discovery,
            )
        )


ADAPTER_FIELDS = (
    "list_link_selector",
    "list_link_pattern",
    "list_link_rewrite",
    "attachment_pattern",
    "pagination_selector",
    "max_pages",
    "content_selector",
    "date_selector",
    "discovery",
)

DISCOVERY_STAGE_NAMES = ("list", "search", "sitemap", "api")


@dataclass(frozen=True)
class SourceConfig:
    """一个来源的已校验配置。"""

    source_id: str
    source_name: str
    base_domain: str
    allowed_domains: Tuple[str, ...]
    enabled: bool
    entry_urls: Tuple[str, ...] = ()
    country: Optional[str] = None
    authority_level: Optional[str] = None
    categories: Tuple[str, ...] = ()
    allowed_paths: Tuple[str, ...] = ()
    blocked_paths: Tuple[str, ...] = ()
    crawl_mode: Optional[str] = None
    update_interval: Optional[str] = None
    parser_type: Optional[str] = None
    language: Optional[str] = None
    stance_default: Optional[str] = None
    robots_policy: Optional[str] = None
    seed_terms: Tuple[str, ...] = ()
    supplement_terms: Tuple[str, ...] = ()
    exclude_terms: Tuple[str, ...] = ()
    search_url_template: Optional[str] = None
    request_rate_per_second: float = 1.0
    max_concurrency: int = 1
    connect_timeout_seconds: float = 10.0
    read_timeout_seconds: float = 30.0
    max_retries: int = 2
    resource_kind: Optional[str] = None
    update_policy_key: Optional[str] = None
    update_period_days: Optional[int] = None
    update_triggers: Tuple[str, ...] = ()
    adapter: SourceAdapter = SourceAdapter()


class SourceRegistry:
    """已校验来源集合及其访问边界判定。"""

    def __init__(
        self,
        sources: Sequence[SourceConfig],
        config_path: Path,
        config_digest: str,
        config_version: str,
    ) -> None:
        self.sources: Tuple[SourceConfig, ...] = tuple(sources)
        self.config_path = Path(config_path)
        self.config_digest = config_digest
        self.config_version = config_version
        self._by_id = {source.source_id: source for source in self.sources}

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "SourceRegistry":
        config_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
        if not config_path.is_file():
            raise ConfigurationError(f"来源配置不存在：{config_path}")
        raw_bytes = config_path.read_bytes()
        try:
            data = yaml.safe_load(raw_bytes.decode("utf-8"))
        except (yaml.YAMLError, UnicodeDecodeError) as exc:
            raise ConfigurationError(f"来源配置无法解析：{config_path}：{exc}") from exc
        if not isinstance(data, Mapping):
            raise ConfigurationError(f"来源配置顶层必须是映射：{config_path}")
        if "sources" not in data:
            raise ConfigurationError(f"来源配置缺少 sources 列表：{config_path}")
        entries = data["sources"]
        if not isinstance(entries, list) or not entries:
            raise ConfigurationError(f"来源配置 sources 必须是非空列表：{config_path}")
        version = data.get("version")
        if not isinstance(version, str) or not version.strip():
            raise ConfigurationError(f"来源配置缺少非空 version：{config_path}")
        seen: set = set()
        sources = [
            _parse_source(entry, index, seen, config_path)
            for index, entry in enumerate(entries)
        ]
        registry = cls(
            sources=sources,
            config_path=config_path,
            config_digest=hashlib.sha256(raw_bytes).hexdigest(),
            config_version=version.strip(),
        )
        logger.info(
            "来源配置载入 path=%s version=%s sources=%d digest=%s",
            registry.config_path,
            registry.config_version,
            len(registry.sources),
            registry.config_digest,
        )
        return registry

    def get(self, source_id: str) -> SourceConfig:
        try:
            return self._by_id[source_id]
        except KeyError as exc:
            raise ConfigurationError(f"未登记的 source_id：{source_id}") from exc

    def enabled_sources(self) -> Tuple[SourceConfig, ...]:
        return tuple(source for source in self.sources if source.enabled)

    def source_for_url(self, url: str) -> Optional[SourceConfig]:
        """返回首个登记该 URL 主机的已启用来源；无匹配返回 None。"""
        host = (urlsplit(url).hostname or "").lower()
        if not host:
            return None
        for source in self.enabled_sources():
            if _host_in_domains(host, source.allowed_domains):
                return source
        return None

    def check_access(self, url: str, source_id: Optional[str] = None) -> AccessDecision:
        """检查协议、域名与路径是否在允许范围内；重定向每一跳都要调用。"""
        parts = urlsplit(url)
        if parts.scheme not in ALLOWED_SCHEMES:
            return AccessDecision(False, f"scheme_not_allowed:{parts.scheme or 'missing'}")
        host = (parts.hostname or "").lower()
        if not host:
            return AccessDecision(False, "missing_host")
        source = self.get(source_id) if source_id is not None else self.source_for_url(url)
        if source is None:
            return AccessDecision(False, f"domain_not_registered:{host}")
        if not source.enabled:
            return AccessDecision(False, f"source_disabled:{source.source_id}")
        if not _host_in_domains(host, source.allowed_domains):
            return AccessDecision(False, f"domain_not_allowed:{host}")
        path = parts.path or "/"
        for blocked in source.blocked_paths:
            if path.startswith(blocked):
                return AccessDecision(False, f"path_blocked:{blocked}")
        if source.allowed_paths and not any(
            path.startswith(prefix) for prefix in source.allowed_paths
        ):
            return AccessDecision(False, f"path_not_allowed:{path}")
        return AccessDecision(True, f"source:{source.source_id}")


def load_registry(path: Optional[Path] = None) -> SourceRegistry:
    return SourceRegistry.load(path)


def _host_in_domains(host: str, domains: Sequence[str]) -> bool:
    return any(host == domain or host.endswith("." + domain) for domain in domains)


def _parse_source(
    entry: Any, index: int, seen: set, config_path: Path
) -> SourceConfig:
    where = f"{config_path} sources[{index}]"
    if not isinstance(entry, Mapping):
        raise ConfigurationError(f"{where} 必须是映射")

    source_id = _require_str(entry, "source_id", where)
    if not SOURCE_ID_PATTERN.match(source_id):
        raise ConfigurationError(f"{where} source_id 非法：{source_id!r}")
    if source_id in seen:
        raise ConfigurationError(f"{where} source_id 重复：{source_id}")
    seen.add(source_id)

    source_name = _require_str(entry, "source_name", where)
    base_domain = _require_str(entry, "base_domain", where).lower()
    if not DOMAIN_PATTERN.match(base_domain):
        raise ConfigurationError(f"{where} base_domain 非法：{base_domain!r}")

    allowed_domains = tuple(
        _domain_list(entry, "allowed_domains", where, required=True)
    )
    if base_domain not in allowed_domains:
        raise ConfigurationError(f"{where} base_domain 必须包含在 allowed_domains 中")

    enabled = entry.get("enabled")
    if not isinstance(enabled, bool):
        raise ConfigurationError(f"{where} enabled 必须是布尔值")

    authority_level = _optional_str(entry, "authority_level", where)
    if authority_level is not None and authority_level not in AUTHORITY_LEVELS:
        raise ConfigurationError(f"{where} authority_level 非法：{authority_level!r}")
    stance_default = _optional_str(entry, "stance_default", where)
    if stance_default is not None and stance_default not in STANCE_DEFAULTS:
        raise ConfigurationError(f"{where} stance_default 非法：{stance_default!r}")

    entry_urls = tuple(_str_list(entry, "entry_urls", where))
    for entry_url in entry_urls:
        parts = urlsplit(entry_url)
        if parts.scheme not in ALLOWED_SCHEMES or not parts.hostname:
            raise ConfigurationError(f"{where} entry_urls 必须是 http(s) URL：{entry_url!r}")
        if not _host_in_domains(parts.hostname.lower(), allowed_domains):
            raise ConfigurationError(f"{where} entry_urls 主机未登记：{entry_url!r}")

    search_url_template = _optional_str(entry, "search_url_template", where)
    if search_url_template is not None:
        if "{query}" not in search_url_template:
            raise ConfigurationError(f"{where} search_url_template 必须含 {{query}} 占位符")
        if urlsplit(search_url_template).scheme not in ALLOWED_SCHEMES:
            raise ConfigurationError(f"{where} search_url_template 必须是 http(s) URL")

    rate = _optional_number(entry, "request_rate_per_second", where, default=1.0)
    if rate <= 0:
        raise ConfigurationError(f"{where} request_rate_per_second 必须大于 0")
    max_retries = _optional_int(entry, "max_retries", where, default=2)
    if max_retries < 0:
        raise ConfigurationError(f"{where} max_retries 不能为负数")
    max_concurrency = _optional_int(entry, "max_concurrency", where, default=1)
    if max_concurrency < 1:
        raise ConfigurationError(f"{where} max_concurrency 至少为 1")
    connect_timeout = _optional_number(
        entry, "connect_timeout_seconds", where, default=10.0
    )
    read_timeout = _optional_number(
        entry, "read_timeout_seconds", where, default=30.0
    )
    if connect_timeout <= 0 or read_timeout <= 0:
        raise ConfigurationError(f"{where} 超时必须大于 0")

    resource_kind = _optional_str(entry, "resource_kind", where)
    if resource_kind is not None and resource_kind not in RESOURCE_KINDS:
        raise ConfigurationError(
            f"{where} resource_kind 必须是 {list(RESOURCE_KINDS)} 之一：{resource_kind!r}"
        )
    update_key, update_period_days, update_triggers = _parse_update_policy(entry, where)
    adapter = _parse_adapter(entry, where)

    return SourceConfig(
        source_id=source_id,
        source_name=source_name,
        base_domain=base_domain,
        allowed_domains=allowed_domains,
        enabled=enabled,
        entry_urls=entry_urls,
        country=_optional_str(entry, "country", where),
        authority_level=authority_level,
        categories=tuple(_str_list(entry, "categories", where)),
        allowed_paths=tuple(_str_list(entry, "allowed_paths", where)),
        blocked_paths=tuple(_str_list(entry, "blocked_paths", where)),
        crawl_mode=_optional_str(entry, "crawl_mode", where),
        update_interval=_optional_str(entry, "update_interval", where),
        parser_type=_optional_str(entry, "parser_type", where),
        language=_optional_str(entry, "language", where),
        stance_default=stance_default,
        robots_policy=_optional_str(entry, "robots_policy", where),
        seed_terms=tuple(_str_list(entry, "seed_terms", where)),
        supplement_terms=tuple(_str_list(entry, "supplement_terms", where)),
        exclude_terms=tuple(_str_list(entry, "exclude_terms", where)),
        search_url_template=search_url_template,
        request_rate_per_second=float(rate),
        max_concurrency=int(max_concurrency),
        connect_timeout_seconds=float(connect_timeout),
        read_timeout_seconds=float(read_timeout),
        max_retries=int(max_retries),
        resource_kind=resource_kind,
        update_policy_key=update_key,
        update_period_days=update_period_days,
        update_triggers=update_triggers,
        adapter=adapter,
    )


def _parse_adapter(entry: Mapping[str, Any], where: str) -> SourceAdapter:
    """解析并校验逐来源适配规则；字段与选择器语法在加载期一次校验。"""
    raw = entry.get("adapter")
    if raw is None:
        return SourceAdapter()
    if not isinstance(raw, Mapping):
        raise ConfigurationError(f"{where} adapter 必须是映射")
    unknown = sorted(set(raw) - set(ADAPTER_FIELDS))
    if unknown:
        raise ConfigurationError(
            f"{where} adapter 含未知字段：{unknown}，已知字段 {list(ADAPTER_FIELDS)}"
        )

    selectors = {}
    for field in ("list_link_selector", "pagination_selector", "content_selector"):
        value = _optional_str(raw, field, f"{where} adapter")
        if value is not None:
            _validate_css_selector(value, f"{where} adapter.{field}")
        selectors[field] = value

    pattern = _optional_str(raw, "list_link_pattern", f"{where} adapter")
    if pattern is not None:
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ConfigurationError(
                f"{where} adapter.list_link_pattern 不是合法正则：{exc}"
            ) from exc

    attachment_pattern = _optional_str(raw, "attachment_pattern", f"{where} adapter")
    if attachment_pattern is not None:
        try:
            re.compile(attachment_pattern)
        except re.error as exc:
            raise ConfigurationError(
                f"{where} adapter.attachment_pattern 不是合法正则：{exc}"
            ) from exc

    date_selector = _optional_str(raw, "date_selector", f"{where} adapter")
    if date_selector is not None:
        _validate_css_selector(date_selector, f"{where} adapter.date_selector")

    rewrite = _parse_list_link_rewrite(raw, where)

    max_pages = raw.get("max_pages")
    if max_pages is not None:
        if isinstance(max_pages, bool) or not isinstance(max_pages, int) or max_pages < 1:
            raise ConfigurationError(f"{where} adapter.max_pages 必须是 ≥1 的整数")

    discovery = None
    raw_discovery = raw.get("discovery")
    if raw_discovery is not None:
        if not isinstance(raw_discovery, (list, tuple)):
            raise ConfigurationError(
                f"{where} adapter.discovery 必须是数组，元素取自 {list(DISCOVERY_STAGE_NAMES)}"
            )
        unknown = [
            value for value in raw_discovery if value not in DISCOVERY_STAGE_NAMES
        ]
        if unknown:
            raise ConfigurationError(
                f"{where} adapter.discovery 含未知方式：{unknown}；允许 {list(DISCOVERY_STAGE_NAMES)}"
            )
        discovery = tuple(dict.fromkeys(str(value) for value in raw_discovery))

    return SourceAdapter(
        list_link_selector=selectors["list_link_selector"],
        list_link_pattern=pattern,
        list_link_rewrite=rewrite,
        attachment_pattern=attachment_pattern,
        pagination_selector=selectors["pagination_selector"],
        max_pages=max_pages,
        content_selector=selectors["content_selector"],
        date_selector=date_selector,
        discovery=discovery,
    )


def _parse_list_link_rewrite(
    raw: Mapping[str, Any], where: str
) -> Optional[Tuple[Tuple[str, str], ...]]:
    """解析列表目标 URL 改写规则（逐来源等价形态改写，如站点 reader 页）。

    每条为 [正则, 替换]；正则作用于链接解析后的绝对 URL，替换沿用 re.sub 语法。
    加载期即校验正则与替换引用，避免运行期才发现配置错误。
    """
    value = raw.get("list_link_rewrite")
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or not value:
        raise ConfigurationError(
            f"{where} adapter.list_link_rewrite 必须是非空数组，元素为 [正则, 替换] 两元组"
        )
    parsed = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise ConfigurationError(
                f"{where} adapter.list_link_rewrite 第 {index} 条必须是 [正则, 替换] 两元组"
            )
        source, replacement = item
        if not isinstance(source, str) or not isinstance(replacement, str):
            raise ConfigurationError(
                f"{where} adapter.list_link_rewrite 第 {index} 条的正则与替换必须是字符串"
            )
        try:
            compiled = re.compile(source)
            compiled.sub(replacement, "", count=1)
        except re.error as exc:
            raise ConfigurationError(
                f"{where} adapter.list_link_rewrite 第 {index} 条不是合法正则/替换：{exc}"
            ) from exc
        parsed.append((source, replacement))
    return tuple(parsed)


def _validate_css_selector(selector: str, where: str) -> None:
    """用与解析器相同的 CSS 引擎校验选择器，配置错误在加载期暴露。"""
    try:
        import soupsieve
    except ImportError:  # pragma: no cover - bs4 运行时依赖，缺失时不在加载期阻断
        return
    try:
        soupsieve.compile(selector)
    except soupsieve.SelectorSyntaxError as exc:
        raise ConfigurationError(f"{where} 不是合法 CSS 选择器：{exc}") from exc


def _parse_update_policy(
    entry: Mapping[str, Any], where: str
) -> Tuple[Optional[str], Optional[int], Tuple[str, ...]]:
    policy = entry.get("update_policy")
    if policy is None:
        return None, None, ()
    if not isinstance(policy, Mapping):
        raise ConfigurationError(f"{where} update_policy 必须是映射")
    key = policy.get("key")
    if not isinstance(key, str) or not key.strip():
        raise ConfigurationError(f"{where} update_policy 缺少类别 key")
    try:
        get_rule(key)
    except ScheduleConfigError as exc:
        raise ConfigurationError(f"{where} update_policy 非法：{exc}") from exc
    period_days = policy.get("period_days")
    if period_days is not None:
        if isinstance(period_days, bool) or not isinstance(period_days, int) or period_days <= 0:
            raise ConfigurationError(f"{where} update_policy.period_days 必须是正整数")
    triggers = policy.get("triggers") or []
    if not isinstance(triggers, (list, tuple)) or not all(isinstance(item, str) for item in triggers):
        raise ConfigurationError(f"{where} update_policy.triggers 必须是字符串数组")
    unknown = [item for item in triggers if item not in TRIGGERS]
    if unknown:
        raise ConfigurationError(f"{where} update_policy.triggers 含未知事件：{unknown}")
    return key.strip().upper(), period_days, tuple(triggers)


def _require_str(entry: Mapping[str, Any], key: str, where: str) -> str:
    value = entry.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"{where} 缺少非空字符串 {key}")
    return value.strip()


def _optional_str(entry: Mapping[str, Any], key: str, where: str) -> Optional[str]:
    value = entry.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"{where} {key} 若存在必须是非空字符串")
    return value.strip()


def _str_list(entry: Mapping[str, Any], key: str, where: str) -> list:
    value = entry.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ConfigurationError(f"{where} {key} 必须是字符串列表")
    return [item.strip() for item in value]


def _domain_list(
    entry: Mapping[str, Any], key: str, where: str, required: bool
) -> list:
    domains = _str_list(entry, key, where)
    if required and not domains:
        raise ConfigurationError(f"{where} {key} 不能为空")
    for domain in domains:
        if not DOMAIN_PATTERN.match(domain.lower()):
            raise ConfigurationError(f"{where} {key} 含非法域名：{domain!r}")
    return [domain.lower() for domain in domains]


def _optional_number(
    entry: Mapping[str, Any], key: str, where: str, default: float
) -> float:
    value = entry.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigurationError(f"{where} {key} 必须是数字")
    return float(value)


def _optional_int(
    entry: Mapping[str, Any], key: str, where: str, default: int
) -> int:
    value = entry.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigurationError(f"{where} {key} 必须是整数")
    return int(value)
