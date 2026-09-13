"""NEXT-08：随包契约资源与规格契约的一致性、源码外读取与失败语义。"""

import json
from pathlib import Path

import pytest

from crawler.validate import schema as schema_module
from crawler.validate.schema import (
    CONTRACT_FILES,
    SchemaConfigError,
    contracts_dir,
    load_contract,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC_CONTRACTS = REPO_ROOT / "specs" / "001-public-knowledge-collection" / "contracts"


def test_packaged_contracts_cover_and_match_spec_sources():
    """规格契约是权威来源；随包副本必须齐全并逐字节一致，避免两套 schema 漂移。"""
    for name, filename in CONTRACT_FILES.items():
        spec = SPEC_CONTRACTS / filename
        packaged = contracts_dir() / filename
        assert spec.is_file(), f"规格契约缺失：{spec}"
        assert packaged.is_file(), f"随包契约缺失：{packaged}"
        assert packaged.read_bytes() == spec.read_bytes(), f"随包契约与规格不一致：{filename}"
        assert load_contract(name) == json.loads(spec.read_text(encoding="utf-8"))


def test_packaged_contracts_cover_every_spec_schema_file():
    """规格目录新增 schema 而未同步随包副本时直接失败。"""
    spec_names = {path.name for path in SPEC_CONTRACTS.glob("*.schema.json")}
    packaged_names = {path.name for path in contracts_dir().glob("*.schema.json")}
    assert spec_names == packaged_names == set(CONTRACT_FILES.values())


def test_contracts_load_outside_source_tree(monkeypatch, tmp_path):
    """契约按包资源读取：当前工作目录脱离源码树、也没有工程根时仍可加载。"""
    monkeypatch.chdir(tmp_path)
    schema = load_contract("document")
    assert schema["title"] and "properties" in schema
    assert (tmp_path / "specs").exists() is False


def test_missing_contract_resource_fails_clearly(monkeypatch):
    monkeypatch.setattr(schema_module, "CONTRACTS_RESOURCE", "contracts_missing")
    with pytest.raises(SchemaConfigError, match="随包契约资源缺失"):
        contracts_dir()
    with pytest.raises(SchemaConfigError, match="随包契约文件缺失"):
        load_contract("manifest")


def test_corrupt_and_missing_contract_files_fail_clearly(tmp_path):
    (tmp_path / "manifest.schema.json").write_text("{不是 JSON", encoding="utf-8")
    with pytest.raises(SchemaConfigError, match="不是合法 JSON"):
        load_contract("manifest", directory=tmp_path)
    with pytest.raises(SchemaConfigError, match="契约文件不存在"):
        load_contract("block", directory=tmp_path)
    with pytest.raises(SchemaConfigError, match="未知契约"):
        load_contract("absent")


def test_manifest_discovery_method_includes_pagination_and_retry_extensions():
    """正文分页部分与补抓重取的账本值必须在枚举内，否则 crawl check 会判契约不通过。"""
    manifest = load_contract("manifest")
    enum = manifest["properties"]["discovery_method"]["enum"]
    assert {"list", "search", "sitemap", "api", "attachment", "manual"} <= set(enum)
    assert {"pagination", "retry"} <= set(enum)
    assert "候选扩展" in manifest["properties"]["discovery_method"]["description"]
