"""T019：project-startup.md 的 CFG-01—CFG-09 环境与目录验收。

CFG-01—CFG-05、CFG-09 为本地无站点场景；CFG-06—CFG-08 用固定夹具站点与真实数据根
执行，覆盖工程外目录、搬迁与路径越界。
"""

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

import pytest
import yaml

from crawler.config.registry import SourceRegistry
from crawler.config.settings import (
    ConfigurationError,
    detect_project_root,
    load_settings,
)
from crawler.fetch.http_client import FetchLimits, HttpClient
from crawler.monitor.logger import close_run_logging
from crawler.output.delivery import inspect_delivery
from crawler.output.jsonl import append_jsonl, read_jsonl
from crawler.output.layout import DeliveryLayout
from crawler.pipeline import CrawlPipeline
from crawler.util.paths import PathSafetyError
from crawler.validate.traceability import trace_delivery

ROOT = Path(__file__).resolve().parents[2]


def test_cfg_01_default_development_data_root(tmp_path):
    project = tmp_path / "project"
    (project / "src" / "crawler").mkdir(parents=True)
    (project / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    settings = load_settings({}, project_root=project)
    assert settings.mode == "development"
    assert settings.data_dir == (project / "data").resolve()
    assert settings.data_dir_from_default is True


def test_cfg_02_process_environment_wins(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    explicit = tmp_path / "from-env"
    settings = load_settings({"CRAWL_DATA_DIR": str(explicit)}, project_root=project)
    assert settings.data_dir == explicit.resolve()
    assert settings.data_dir_from_default is False


def test_cfg_03_relative_path_is_project_root_based(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    settings = load_settings({"CRAWL_DATA_DIR": "./data"}, project_root=project)
    assert settings.data_dir == (project / "data").resolve()


def test_cfg_04_production_requires_absolute_explicit_root(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    with pytest.raises(ConfigurationError, match="必须显式配置"):
        load_settings({"CRAWL_ENV": "production"}, project_root=project)
    with pytest.raises(ConfigurationError, match="绝对路径"):
        load_settings(
            {"CRAWL_ENV": "production", "CRAWL_DATA_DIR": "./data"}, project_root=project
        )
    with pytest.raises(ConfigurationError, match="显式为空"):
        load_settings(
            {"CRAWL_ENV": "production", "CRAWL_DATA_DIR": ""}, project_root=project
        )
    assert not (project / "data").exists()


def test_cfg_05_directory_validation(tmp_path):
    valid = load_settings({"CRAWL_DATA_DIR": str(tmp_path / "ok")}, project_root=tmp_path)
    assert valid.data_dir.is_dir()
    as_file = tmp_path / "file-not-dir"
    as_file.write_text("x", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="不是目录"):
        load_settings({"CRAWL_DATA_DIR": str(as_file)}, project_root=tmp_path)
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)
    try:
        with pytest.raises(ConfigurationError, match="不可写"):
            load_settings({"CRAWL_DATA_DIR": str(locked)}, project_root=tmp_path)
    finally:
        locked.chmod(0o700)


def _registry_for(site_url: str, root: Path, source_id: str = "CFGSRC") -> SourceRegistry:
    host = urlsplit(site_url).hostname
    path = root / "sources.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "version": "cfg",
                "sources": [
                    {
                        "source_id": source_id,
                        "source_name": "夹具来源",
                        "base_domain": host,
                        "allowed_domains": [host],
                        "enabled": True,
                        "language": "zh",
                        "request_rate_per_second": 1000,
                        "max_retries": 2,
                        "connect_timeout_seconds": 5,
                        "read_timeout_seconds": 5,
                    }
                ],
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    return SourceRegistry.load(path)


def _collect(registry, data_dir: Path, site_url: str):
    pipeline = CrawlPipeline(
        registry,
        data_dir,
        http=HttpClient(registry, limits=FetchLimits(request_rate_per_second=1000, max_retries=2)),
    )
    try:
        return pipeline.collect("CFGSRC", entry_urls=[f"{site_url}/index.html"])
    finally:
        close_run_logging(data_dir)


def test_cfg_06_production_root_outside_repository(tmp_path, site_server):
    data_root = tmp_path / "outside-repo-root"
    settings = load_settings(
        {"CRAWL_ENV": "production", "CRAWL_DATA_DIR": str(data_root)},
        project_root=ROOT,
    )
    assert settings.is_production and settings.data_dir == data_root.resolve()
    registry = _registry_for(site_server, tmp_path)
    report = _collect(registry, settings.data_dir, site_server)
    assert report.counters.resources >= 1
    result = inspect_delivery(settings.data_dir)
    assert result.ok is True, result.as_row()
    for name in ("raw", "manifests", "normalized", "logs"):
        assert (data_root / name).is_dir()
    assert not (ROOT / "data" / "raw" / "CFGSRC").exists()  # 不写回开发默认根


def test_cfg_07_relocation_keeps_relative_paths_and_hashes(tmp_path, site_server):
    first = tmp_path / "root-a"
    registry = _registry_for(site_server, tmp_path)
    _collect(registry, first, site_server)
    before = read_jsonl(DeliveryLayout(first).manifest_path)
    second = tmp_path / "root-b"
    shutil.copytree(first, second)
    relocated = load_settings({"CRAWL_DATA_DIR": str(second)}, project_root=tmp_path)
    assert relocated.data_dir == second.resolve()

    after = read_jsonl(DeliveryLayout(second).manifest_path)
    assert [row["raw_path"] for row in after] == [row["raw_path"] for row in before]
    assert inspect_delivery(second).ok is True
    trace = trace_delivery(second)
    assert trace.ok is True and trace.document_rate == 1.0
    for row in after:
        raw = DeliveryLayout(second).resolve_raw_path(row["raw_path"])
        assert hashlib.sha256(raw.read_bytes()).hexdigest() == row["sha256"]


def test_cfg_08_out_of_root_paths_are_rejected(tmp_path, site_server):
    data_root = tmp_path / "root"
    registry = _registry_for(site_server, tmp_path)
    _collect(registry, data_root, site_server)
    layout = DeliveryLayout(data_root)
    outside = tmp_path / "outside.html"
    outside.write_text("<html></html>", encoding="utf-8")
    append_jsonl(
        layout.documents_path,
        [
            {
                "doc_id": "ESCAPE",
                "raw_path": "../outside.html",
                "crawl_ids": ["none"],
                "sha256": "0" * 64,
            }
        ],
    )
    assert inspect_delivery(data_root).ok is False
    trace = trace_delivery(data_root)
    assert any("越界" in problem["reason"] for problem in trace.problems)
    with pytest.raises(PathSafetyError):
        layout.resolve_raw_path("../outside.html")
    (layout.raw_dir / "LINK").symlink_to(tmp_path)
    with pytest.raises(PathSafetyError):
        layout.resolve_raw_path("raw/LINK/outside.html")
    assert outside.read_text(encoding="utf-8") == "<html></html>"


def test_cfg_09_import_from_outside_project(tmp_path):
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    result = subprocess.run(
        [sys.executable, "-c", "import crawler; print(crawler.__version__)"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "0.1.0"
    assert str(ROOT / "src") not in result.stderr
    assert detect_project_root() == ROOT  # 源码工程根仍可识别，供开发默认数据根使用
