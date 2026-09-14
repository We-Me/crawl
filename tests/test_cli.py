"""NEXT-01：正式业务 CLI 的子命令、退出码与本机闭环。

用本地回环夹具站点走真实 HTTP 闭环（不是打桩），并覆盖配置错误退出。
"""

import json
from pathlib import Path
from urllib.parse import urlsplit

import pytest
import yaml

from crawler.cli import main
from crawler.output.jsonl import read_jsonl


def _write_sources(path: Path, base_url: str, **overrides) -> Path:
    """写一份本地夹具来源配置；overrides 覆盖默认条目字段。"""
    host = urlsplit(base_url).hostname
    entry = {
        "source_id": "TESTSRC",
        "source_name": "本地夹具来源",
        "base_domain": host,
        "allowed_domains": [host],
        "enabled": True,
        "allowed_paths": [],
        "blocked_paths": [],
        "language": "zh",
        "seed_terms": ["边界"],
        "request_rate_per_second": 1000,
        "max_retries": 0,
        "connect_timeout_seconds": 5,
        "read_timeout_seconds": 5,
    }
    entry.update(overrides)
    path.write_text(
        yaml.safe_dump({"version": "tests", "sources": [entry]}, allow_unicode=True),
        encoding="utf-8",
    )
    return path


@pytest.fixture()
def cli_env(tmp_path, monkeypatch):
    """把 CLI 的配置入口指向临时数据根；其余仍走进程环境变量。"""
    data_dir = tmp_path / "data"
    monkeypatch.setenv("CRAWL_ENV", "development")
    monkeypatch.setenv("CRAWL_DATA_DIR", str(data_dir))
    return data_dir


# ---------- 帮助与版本 ----------


def test_cli_help_lists_commands(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["--help"])
    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    for command in ("sources", "collect", "plan", "resume", "check"):
        assert command in out


def test_cli_version(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    assert "crawl 0.1.0" in capsys.readouterr().out


# ---------- sources ----------


def test_cli_sources_lists_registry(site_server, tmp_path, capsys):
    config = _write_sources(tmp_path / "sources.yaml", site_server)
    assert main(["sources", "--config", str(config)]) == 0
    out = capsys.readouterr().out
    assert "TESTSRC" in out and "enabled" in out
    assert "digest=" in out


def test_cli_sources_json_reports_digest(site_server, tmp_path, capsys):
    config = _write_sources(tmp_path / "sources.yaml", site_server)
    assert main(["sources", "--config", str(config), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["sources"][0]["source_id"] == "TESTSRC"
    assert len(payload["config_digest"]) == 64


def test_cli_sources_rejects_invalid_config(tmp_path, capsys):
    config = tmp_path / "sources.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "version": "tests",
                "sources": [
                    {
                        "source_id": "BAD ID",
                        "source_name": "非法来源",
                        "base_domain": "example.invalid",
                        "allowed_domains": ["example.invalid"],
                        "enabled": True,
                    }
                ],
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    assert main(["sources", "--config", str(config)]) == 2
    assert "配置错误" in capsys.readouterr().err


def test_cli_sources_reports_contract_violation(site_server, tmp_path, capsys):
    """语义校验通过的条目仍要过来源契约：last_success_at 必须是日期时间字符串。"""
    config = _write_sources(tmp_path / "sources.yaml", site_server, last_success_at=5)
    assert main(["sources", "--config", str(config)]) == 2
    assert "契约不符" in capsys.readouterr().err


# ---------- collect / check ----------


def test_cli_collect_fixture_closure_then_check(site_server, tmp_path, cli_env, capsys):
    config = _write_sources(tmp_path / "sources.yaml", site_server)
    code = main(
        [
            "collect",
            "--config",
            str(config),
            "--source",
            "TESTSRC",
            "--entry-url",
            f"{site_server}/index.html",
            "--no-attachments",
            "--max-items",
            "1",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "采集完成" in out and "文档=1" in out
    # S5-06：覆盖口径随报告输出，未完整/待处理不冒充完成
    assert "覆盖：" in out and "主目标 发现=" in out

    manifest = read_jsonl(cli_env / "manifests" / "crawl_manifest.jsonl")
    # --max-items 1：发现页（S5-01 归档）+ 一个目标页
    assert len(manifest) == 2
    assert sum(1 for row in manifest if "/discovery/" in row["raw_path"]) == 1
    for row in manifest:
        assert (cli_env / row["raw_path"]).is_file()
    documents = read_jsonl(cli_env / "normalized" / "documents.jsonl")
    assert len(documents) == 1 and documents[0]["source_id"] == "TESTSRC"

    assert main(["check"]) == 0
    report = capsys.readouterr().out
    assert "交付成果：齐全" in report
    assert "契约 schema：通过" in report
    assert "documents 1/1（100.0000%）" in report


def test_cli_discover_only_traverses_without_documents(site_server, tmp_path, cli_env, capsys):
    # S5-03：--discover-only 只遍历发现入口并归档发现页，不产出文档
    config = _write_sources(tmp_path / "sources.yaml", site_server)
    code = main(
        [
            "collect",
            "--config",
            str(config),
            "--source",
            "TESTSRC",
            "--entry-url",
            f"{site_server}/index.html",
            "--discover-only",
            "--max-pages",
            "2",
            "--json",
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["counters"]["documents"] == 0
    assert payload["counters"]["blocks"] == 0
    assert payload["coverage"]["processing"]["mode"] == "discovery_only"
    manifest = read_jsonl(cli_env / "manifests" / "crawl_manifest.jsonl")
    assert manifest and all("/discovery/" in row["raw_path"] for row in manifest)

    bad = main(
        [
            "collect",
            "--config",
            str(config),
            "--source",
            "TESTSRC",
            "--discover-only",
            "--url",
            f"{site_server}/detail_1.html",
        ]
    )
    assert bad == 2  # 只遍历发现时不接受显式 URL 采集


def test_cli_collect_json_reports_counters(site_server, tmp_path, cli_env, capsys):
    config = _write_sources(tmp_path / "sources.yaml", site_server)
    code = main(
        [
            "collect",
            "--config",
            str(config),
            "--source",
            "TESTSRC",
            "--entry-url",
            f"{site_server}/index.html",
            "--no-attachments",
            "--max-items",
            "1",
            "--json",
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["counters"]["documents"] == 1
    assert payload["run_id"]
    coverage = payload["coverage"]
    assert coverage["targets"]["discovered"] == 1
    assert coverage["targets"]["processed"] == 1
    assert coverage["discovery"]["complete"] is False, "--max-items 1 属显式截断"
    assert coverage["pending_total"] == 0


def test_cli_collect_unknown_source_exits_2(site_server, tmp_path, cli_env, capsys):
    config = _write_sources(tmp_path / "sources.yaml", site_server)
    assert main(["collect", "--config", str(config), "--source", "NOPE"]) == 2
    assert "未登记" in capsys.readouterr().err


def test_cli_collect_disabled_source_exits_2(site_server, tmp_path, cli_env, capsys):
    config = _write_sources(tmp_path / "sources.yaml", site_server, enabled=False)
    assert main(["collect", "--config", str(config), "--source", "TESTSRC"]) == 2
    assert "来源未启用" in capsys.readouterr().err


def test_cli_check_fails_on_empty_root(cli_env, capsys):
    assert main(["check"]) == 1
    out = capsys.readouterr().out
    assert "不通过" in out and "缺失" in out


def test_cli_check_reports_queue_reconciliation(cli_env, capsys):
    """check 输出队列对账口径；空数据根没有待处理项，对账本身通过。"""
    assert main(["check", "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["reconcile"] == {
        "ok": True,
        "items_total": 0,
        "items_by_state": {},
        "open_failures": 0,
        "problems": [],
    }


# ---------- plan / resume ----------


def test_cli_plan_and_resume_reparse(site_server, tmp_path, cli_env, capsys):
    """正文选择器未命中 → CLI 计划显示 reparse，修正配置后补抓成功。"""
    broken = _write_sources(
        tmp_path / "broken.yaml",
        site_server,
        adapter={"list_link_selector": "ul li a", "content_selector": "div.not-here"},
    )
    fixed = _write_sources(
        tmp_path / "fixed.yaml",
        site_server,
        adapter={"list_link_selector": "ul li a", "content_selector": "div.article-body"},
    )

    code = main(
        [
            "collect",
            "--config",
            str(broken),
            "--source",
            "TESTSRC",
            "--entry-url",
            f"{site_server}/adapter_index.html",
            "--no-attachments",
        ]
    )
    assert code == 1
    assert "失败=1" in capsys.readouterr().out

    assert main(["plan", "--config", str(broken), "--source", "TESTSRC", "--json"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert len(plan["tasks"]) == 1
    assert plan["tasks"][0]["action"] == "reparse"
    assert plan["summary"] == {"reparse": 1}

    code = main(["resume", "--config", str(fixed), "--source", "TESTSRC"])
    assert code == 0
    out = capsys.readouterr().out
    assert "恢复=1" in out and "仍失败=0" in out
    documents = read_jsonl(cli_env / "normalized" / "documents.jsonl")
    assert documents[0]["extraction_method"].startswith("bs4_lxml_selector+")

    assert main(["check"]) == 0
    assert "追溯：documents 1/1（100.0000%）" in capsys.readouterr().out


def test_cli_resume_waits_for_backoff(site_server, tmp_path, cli_env, capsys):
    """--respect-backoff 时退避未到的任务保持 pending，不冒进重试。"""
    broken = _write_sources(
        tmp_path / "broken.yaml",
        site_server,
        adapter={"list_link_selector": "ul li a", "content_selector": "div.not-here"},
    )
    fixed = _write_sources(
        tmp_path / "fixed.yaml",
        site_server,
        adapter={"list_link_selector": "ul li a", "content_selector": "div.article-body"},
    )
    main(
        [
            "collect",
            "--config",
            str(broken),
            "--source",
            "TESTSRC",
            "--entry-url",
            f"{site_server}/adapter_index.html",
            "--no-attachments",
        ]
    )
    capsys.readouterr()
    assert (
        main(
            [
                "resume",
                "--config",
                str(fixed),
                "--source",
                "TESTSRC",
                "--respect-backoff",
                "--base-delay-seconds",
                "600",
            ]
        )
        == 1
    )
    assert "退避等待=1" in capsys.readouterr().out


def test_cli_resume_reports_manual_failures(site_server, tmp_path, cli_env, capsys):
    """永久 4xx 记录为待人工：计划与补抓都不自动重试。"""
    config = _write_sources(tmp_path / "sources.yaml", site_server)
    code = main(
        [
            "collect",
            "--config",
            str(config),
            "--source",
            "TESTSRC",
            "--entry-url",
            f"{site_server}/attachments/unavailable.pdf",
        ]
    )
    assert code == 1
    capsys.readouterr()
    assert main(["plan", "--config", str(config), "--source", "TESTSRC", "--json"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["summary"] == {"manual": 1}
    assert main(["resume", "--config", str(config), "--source", "TESTSRC"]) == 1
    assert "待人工=1" in capsys.readouterr().out


def test_cli_collect_manual_url_takes_only_given_page(site_server, tmp_path, cli_env, capsys):
    """--url：只按给定 URL 采集（manual），不隐式跑来源入口。"""
    config = _write_sources(tmp_path / "sources.yaml", site_server)
    code = main(
        [
            "collect",
            "--config",
            str(config),
            "--source",
            "TESTSRC",
            "--url",
            f"{site_server}/detail_2.html",
            "--no-attachments",
            "--json",
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["counters"]["resources"] == 1
    assert payload["counters"]["documents"] == 1
    assert [row["stage"] for row in payload["discovery"]] == ["manual"]

    manifest = read_jsonl(cli_env / "manifests" / "crawl_manifest.jsonl")
    assert [row["discovery_method"] for row in manifest] == ["manual"]
    assert manifest[0]["requested_url"] == f"{site_server}/detail_2.html"
