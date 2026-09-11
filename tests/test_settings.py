"""CFG-01—CFG-05 配置契约测试（project-startup.md / T004 settings 部分）。"""

import os
from pathlib import Path

import pytest

from crawler.config import settings as settings_module
from crawler.config.settings import (
    ConfigurationError,
    detect_project_root,
    load_settings,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def fake_project(tmp_path):
    root = tmp_path / "project"
    (root / "src" / "crawler").mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        "[project]\nname = 'x'\n", encoding="utf-8"
    )
    return root


def test_source_tree_root_is_detected():
    assert detect_project_root() == REPO_ROOT


def test_cfg01_development_defaults_to_project_data_dir(fake_project):
    loaded = load_settings({}, project_root=fake_project)
    assert loaded.mode == "development"
    assert loaded.is_production is False
    assert loaded.data_dir == (fake_project / "data").resolve()
    assert loaded.data_dir.is_dir()
    assert loaded.data_dir_from_default is True


def test_cfg01_detected_root_is_used_without_injection(fake_project, monkeypatch):
    monkeypatch.setattr(settings_module, "detect_project_root", lambda: fake_project)
    loaded = load_settings({})
    assert loaded.data_dir == (fake_project / "data").resolve()
    assert loaded.project_root == fake_project


def test_cfg02_environment_value_is_used_as_given(tmp_path, fake_project):
    env_dir = tmp_path / "from-process-env"
    loaded = load_settings({"CRAWL_DATA_DIR": str(env_dir)}, project_root=fake_project)
    assert loaded.data_dir == env_dir.resolve()
    assert loaded.data_dir_from_default is False


def test_cfg02_relative_environment_value_beats_default(fake_project):
    loaded = load_settings(
        {"CRAWL_DATA_DIR": "./from-env"}, project_root=fake_project
    )
    assert loaded.data_dir == (fake_project / "from-env").resolve()


def test_cfg03_relative_path_does_not_follow_working_directory(
    tmp_path, fake_project, monkeypatch
):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    loaded = load_settings({"CRAWL_DATA_DIR": "./data"}, project_root=fake_project)
    assert loaded.data_dir == (fake_project / "data").resolve()
    assert not (elsewhere / "data").exists()


@pytest.mark.parametrize("value", [None, "", "./data", "data"])
def test_cfg04_production_requires_explicit_absolute_dir(value, fake_project):
    env = {"CRAWL_ENV": "production"}
    if value is not None:
        env["CRAWL_DATA_DIR"] = value
    with pytest.raises(ConfigurationError):
        load_settings(env, project_root=fake_project)


def test_cfg04_production_accepts_absolute_dir(tmp_path, fake_project):
    target = tmp_path / "outside" / "crawl-data"
    loaded = load_settings(
        {"CRAWL_ENV": "production", "CRAWL_DATA_DIR": str(target)},
        project_root=fake_project,
    )
    assert loaded.is_production is True
    assert loaded.data_dir == target.resolve()
    assert loaded.data_dir.is_dir()


@pytest.mark.parametrize("mode", ["", "staging", "Production", "dev"])
def test_invalid_mode_is_rejected(mode, fake_project):
    with pytest.raises(ConfigurationError):
        load_settings({"CRAWL_ENV": mode}, project_root=fake_project)


def test_empty_data_dir_is_rejected_in_development(fake_project):
    with pytest.raises(ConfigurationError):
        load_settings({"CRAWL_DATA_DIR": ""}, project_root=fake_project)


def test_cfg05_existing_file_is_rejected(tmp_path, fake_project):
    target = tmp_path / "data-file"
    target.write_text("not a directory", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="不是目录"):
        load_settings({"CRAWL_DATA_DIR": str(target)}, project_root=fake_project)


def test_cfg05_nested_directory_is_created(fake_project):
    nested = fake_project / "nested" / "data"
    loaded = load_settings({"CRAWL_DATA_DIR": str(nested)}, project_root=fake_project)
    assert loaded.data_dir == nested.resolve()
    assert loaded.data_dir.is_dir()


def test_cfg05_unwritable_directory_is_rejected(tmp_path, fake_project):
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("root 可写任意目录，无法复现权限失败")
    parent = tmp_path / "locked"
    parent.mkdir()
    target = parent / "data"
    parent.chmod(0o500)
    try:
        with pytest.raises(ConfigurationError):
            load_settings({"CRAWL_DATA_DIR": str(target)}, project_root=fake_project)
    finally:
        parent.chmod(0o700)


def test_installed_without_source_tree_needs_explicit_path(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_module, "detect_project_root", lambda: None)
    with pytest.raises(ConfigurationError):
        load_settings({})
    with pytest.raises(ConfigurationError):
        load_settings({"CRAWL_DATA_DIR": "./data"})
    target = tmp_path / "absolute-data"
    loaded = load_settings({"CRAWL_DATA_DIR": str(target)})
    assert loaded.data_dir == target.resolve()
