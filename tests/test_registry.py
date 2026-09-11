"""T004 来源注册、配置校验与访问边界测试。"""

from pathlib import Path

import pytest
import yaml

from crawler.config.registry import SourceRegistry, load_registry
from crawler.config.settings import ConfigurationError


def write_config(tmp_path: Path, sources, version="test-0.1") -> Path:
    path = tmp_path / "sources.yaml"
    path.write_text(
        yaml.safe_dump({"version": version, "sources": sources}, allow_unicode=True),
        encoding="utf-8",
    )
    return path


def base_source(**overrides):
    entry = {
        "source_id": "DEMO",
        "source_name": "虚构示例来源",
        "base_domain": "example.invalid",
        "allowed_domains": ["example.invalid"],
        "enabled": True,
        "allowed_paths": [],
        "blocked_paths": [],
        "seed_terms": ["边界"],
        "request_rate_per_second": 1.0,
        "max_retries": 2,
        "connect_timeout_seconds": 5,
        "read_timeout_seconds": 15,
    }
    entry.update(overrides)
    return entry


def test_shipped_config_disables_real_crawling():
    registry = load_registry()
    assert registry.config_version == "0.1.0"
    assert registry.get("DEMO").enabled is False
    assert registry.enabled_sources() == ()
    assert registry.config_digest


def test_valid_config_parses_all_fields(tmp_path):
    entry = base_source(
        country="XX",
        authority_level="A2",
        stance_default="BILATERAL",
        categories=["A", "G"],
        update_interval="daily",
        parser_type="html",
        language="zh",
        search_url_template="https://example.invalid/search?q={query}",
        supplement_terms=["机制"],
        exclude_terms=["广告"],
    )
    registry = SourceRegistry.load(write_config(tmp_path, [entry]))
    source = registry.get("DEMO")
    assert source.allowed_domains == ("example.invalid",)
    assert source.authority_level == "A2"
    assert source.stance_default == "BILATERAL"
    assert source.categories == ("A", "G")
    assert source.search_url_template.endswith("{query}")
    assert source.request_rate_per_second == 1.0
    assert source.read_timeout_seconds == 15.0
    assert registry.enabled_sources() == (source,)


@pytest.mark.parametrize(
    "overrides, match",
    [
        ({"source_id": "bad id"}, "source_id"),
        ({"source_id": "A/B"}, "source_id"),
        ({"source_name": ""}, "source_name"),
        ({"base_domain": "example"}, "base_domain"),
        ({"base_domain": "-bad.invalid"}, "base_domain"),
        ({"allowed_domains": []}, "allowed_domains"),
        ({"allowed_domains": ["other.invalid"]}, "base_domain"),
        ({"enabled": "yes"}, "enabled"),
        ({"authority_level": "D"}, "authority_level"),
        ({"stance_default": "CN"}, "stance_default"),
        ({"search_url_template": "https://example.invalid/search"}, "query"),
        ({"search_url_template": "ftp://example.invalid/s?q={query}"}, "http"),
        ({"request_rate_per_second": 0}, "rate"),
        ({"max_retries": -1}, "max_retries"),
        ({"max_concurrency": 0}, "max_concurrency"),
        ({"read_timeout_seconds": 0}, "超时"),
        ({"allowed_paths": "news"}, "allowed_paths"),
    ],
)
def test_invalid_source_entries_are_rejected(tmp_path, overrides, match):
    path = write_config(tmp_path, [base_source(**overrides)])
    with pytest.raises(ConfigurationError, match=match):
        SourceRegistry.load(path)


def test_duplicate_source_id_is_rejected(tmp_path):
    path = write_config(tmp_path, [base_source(), base_source()])
    with pytest.raises(ConfigurationError, match="重复"):
        SourceRegistry.load(path)


def test_missing_sources_or_version_is_rejected(tmp_path):
    path = tmp_path / "sources.yaml"
    path.write_text("sources: []\nversion: '1'\n", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="非空列表"):
        SourceRegistry.load(path)
    path.write_text("version: '1'\n", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="sources"):
        SourceRegistry.load(path)
    path.write_text(
        yaml.safe_dump({"sources": [base_source()]}, allow_unicode=True),
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError, match="version"):
        SourceRegistry.load(path)
    with pytest.raises(ConfigurationError, match="不存在"):
        SourceRegistry.load(tmp_path / "missing.yaml")


def test_entry_urls_are_parsed_and_checked(tmp_path):
    entry = base_source(entry_urls=["https://www.example.invalid/list"])
    registry = SourceRegistry.load(write_config(tmp_path, [entry]))
    assert registry.get("DEMO").entry_urls == ("https://www.example.invalid/list",)


def test_mixed_case_domain_is_normalized(tmp_path):
    registry = SourceRegistry.load(
        write_config(tmp_path, [base_source(base_domain="Example.INVALID")])
    )
    assert registry.get("DEMO").base_domain == "example.invalid"


def test_access_allows_registered_domain_and_subdomain(tmp_path):
    registry = SourceRegistry.load(write_config(tmp_path, [base_source()]))
    assert registry.check_access("https://example.invalid/news/1").allowed
    assert registry.check_access("https://www.example.invalid/news/1").allowed
    decision = registry.check_access("https://example.invalid/news/1")
    assert decision.reason == "source:DEMO"


def test_access_rejects_unregistered_or_lookalike_domains(tmp_path):
    registry = SourceRegistry.load(write_config(tmp_path, [base_source()]))
    for url in (
        "https://other.invalid/news/1",
        "https://notexample.invalid/news/1",
        "https://example.invalid.evil.test/news/1",
        "https://example.invalid.news/1",
    ):
        assert not registry.check_access(url).allowed
    assert registry.check_access("https://example.invalid./news/1").allowed is False


def test_access_rejects_other_schemes_and_missing_host(tmp_path):
    registry = SourceRegistry.load(write_config(tmp_path, [base_source()]))
    assert not registry.check_access("ftp://example.invalid/a").allowed
    assert not registry.check_access("file:///etc/passwd").allowed
    assert not registry.check_access("https:///no-host").allowed


def test_access_rejects_blocked_and_non_allowed_paths(tmp_path):
    blocked = base_source(blocked_paths=["/login", "/admin"])
    registry = SourceRegistry.load(write_config(tmp_path, [blocked]))
    assert not registry.check_access("https://example.invalid/login").allowed
    assert not registry.check_access("https://example.invalid/admin/tools").allowed
    assert registry.check_access("https://example.invalid/news").allowed

    limited = base_source(allowed_paths=["/news/"])
    registry = SourceRegistry.load(write_config(tmp_path, [limited]))
    assert registry.check_access("https://example.invalid/news/2026").allowed
    assert not registry.check_access("https://example.invalid/other").allowed


def test_access_respects_disabled_and_selected_source(tmp_path):
    enabled = base_source(source_id="ON", allowed_domains=["on.invalid"], base_domain="on.invalid")
    disabled = base_source(
        source_id="OFF",
        allowed_domains=["off.invalid"],
        base_domain="off.invalid",
        enabled=False,
    )
    registry = SourceRegistry.load(write_config(tmp_path, [enabled, disabled]))
    assert registry.check_access("https://on.invalid/a").allowed
    denied = registry.check_access("https://off.invalid/a")
    assert not denied.allowed
    assert denied.reason.startswith("domain_not_registered")
    assert not registry.check_access("https://off.invalid/a", source_id="OFF").allowed
    assert registry.source_for_url("https://www.on.invalid/a").source_id == "ON"
    with pytest.raises(ConfigurationError, match="未登记"):
        registry.get("NOPE")


def test_config_digest_tracks_changes(tmp_path):
    path = write_config(tmp_path, [base_source()])
    first = SourceRegistry.load(path)
    path.write_text(
        path.read_text(encoding="utf-8").replace("seed_terms", "seed_terms"),
        encoding="utf-8",
    )
    second = SourceRegistry.load(path)
    assert first.config_digest == second.config_digest
    path.write_text(path.read_text(encoding="utf-8") + "# changed\n", encoding="utf-8")
    third = SourceRegistry.load(path)
    assert third.config_digest != first.config_digest
    assert third.config_version == "test-0.1"


def test_adapter_rules_are_parsed_and_default_to_generic(tmp_path):
    """T026 适配规则：缺省全空表示通用规则；配置后逐字段校验并保留。"""
    plain = SourceRegistry.load(write_config(tmp_path, [base_source()])).get("DEMO")
    assert plain.adapter.configured is False
    assert plain.adapter.list_link_selector is None

    entry = base_source(
        adapter={
            "list_link_selector": "ul.doc-list li a",
            "list_link_pattern": r"/eng/wjbzhd/.*\.shtml$",
            "pagination_selector": "a.next-page",
            "max_pages": 3,
            "content_selector": "div.article-body",
        }
    )
    adapter = SourceRegistry.load(write_config(tmp_path, [entry])).get("DEMO").adapter
    assert adapter.configured is True
    assert adapter.list_link_selector == "ul.doc-list li a"
    assert adapter.pagination_selector == "a.next-page"
    assert adapter.max_pages == 3
    assert adapter.content_selector == "div.article-body"


@pytest.mark.parametrize(
    "adapter, expected",
    [
        ({"list_link_selector": "ul li["}, "CSS 选择器"),
        ({"list_link_pattern": "("}, "正则"),
        ({"max_pages": 0}, "max_pages"),
        ({"max_pages": True}, "max_pages"),
        ({"content_selector": "div["}, "CSS 选择器"),
        ({"unknown_rule": "x"}, "未知字段"),
        ("not-a-mapping", "必须是映射"),
    ],
)
def test_invalid_adapter_rules_fail_at_load(tmp_path, adapter, expected):
    path = write_config(tmp_path, [base_source(adapter=adapter)])
    with pytest.raises(ConfigurationError) as excinfo:
        SourceRegistry.load(path)
    assert expected in str(excinfo.value)


def test_shipped_config_matches_contract_schema():
    """随包 sources.yaml 的每条来源都必须能通过契约 schema，避免配置与契约漂移。"""
    from crawler.config.registry import DEFAULT_CONFIG_PATH
    from crawler.validate.schema import load_contract, validate_instance

    payload = yaml.safe_load(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))
    schema = load_contract("source_registry")
    for entry in payload["sources"]:
        assert validate_instance(entry, schema) == [], entry.get("source_id")
