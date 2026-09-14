"""NEXT-01：正式业务 CLI 的子命令、退出码与本机闭环。

用本地回环夹具站点走真实 HTTP 闭环（不是打桩），并覆盖配置错误退出。
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import pytest
import yaml

from crawler.cli import main
from crawler.discover.discoverer import DiscoveredTarget
from crawler.fetch.retry import MANUAL, RetryPolicy, build_recovery_plan
from crawler.monitor.failures import FailureLedger
from crawler.output.jsonl import read_jsonl
from crawler.schedule.pending import PendingStore
from crawler.validate.reconcile import reconcile_queue_and_failures

NOW_TEXT = "2026-09-11T10:00:00+08:00"


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
        "open_failures_by_stage": {},
        "problems": [],
    }


def test_cli_check_fails_on_corrupt_pending_state(cli_env, capsys):
    """R6：待处理状态损坏时 check 非零退出，并把文件与原因打到输出。"""
    manifests = cli_env / "manifests"
    manifests.mkdir(parents=True, exist_ok=True)
    (manifests / "pending_items.json").write_text('{"items": {"k1"', encoding="utf-8")

    assert main(["check"]) == 1
    out = capsys.readouterr().out
    assert "队列对账：不通过" in out
    assert "manifests/pending_items.json" in out
    assert "JSON 语法错误" in out

    assert main(["check", "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["reconcile"]["ok"] is False
    assert payload["reconcile"]["problems"][0]["file"] == "manifests/pending_items.json"


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


# ---------- 阶段七：失败查询与人工处置 ----------


def _record_failure(data_dir, **overrides):
    from crawler.monitor.failures import FailureLedger

    row = {
        "source_id": "TESTSRC",
        "url": "https://example.invalid/a.pdf",
        "time": "2026-09-14T10:00:00+08:00",
        "stage": "fetch",
        "error_type": "request_error",
        "message": "读取响应失败：连接中断",
        "retry_count": 0,
        "final_action": "retry_later",
    }
    row.update(overrides)
    FailureLedger(data_dir).writer.record(**row)
    return row


def test_cli_failures_lists_open_and_history(cli_env, capsys):
    _record_failure(cli_env)
    _record_failure(cli_env, url="https://example.invalid/b.pdf", final_action="record_only")

    assert main(["failures"]) == 0
    out = capsys.readouterr().out
    assert "未关闭 2" in out
    assert "https://example.invalid/a.pdf" in out and "https://example.invalid/b.pdf" in out

    assert main(["failures", "--url", "https://example.invalid/a.pdf", "--all", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["open"] == 1 and payload["shown"] == 1
    assert payload["rows"][0]["final_action"] == "retry_later"


def test_cli_resolve_closes_failure_and_queries_result(cli_env, capsys):
    _record_failure(cli_env, doc_id="DOC-1", scope_start_date="2026-09-06")

    bad = main(["resolve", "--url", "https://example.invalid/a.pdf", "--action", "skip"])
    assert bad == 2, "归属没写全时必须报错并提示可用身份"
    err = capsys.readouterr().err
    assert "现有身份" in err and "doc=DOC-1" in err

    partial = main(
        [
            "resolve",
            "--url",
            "https://example.invalid/a.pdf",
            "--action",
            "skip",
            "--stage",
            "fetch",
            "--doc-id",
            "DOC-1",
            "--scope-start-date",
            "2026-09-06",
        ]
    )
    assert partial == 2, "记录带来源归属时不得按未确认的来源关闭"
    assert "source=TESTSRC" in capsys.readouterr().err

    assert (
        main(
            [
                "resolve",
                "--url",
                "https://example.invalid/a.pdf",
                "--action",
                "skip",
                "--source",
                "TESTSRC",
                "--stage",
                "fetch",
                "--doc-id",
                "DOC-1",
                "--scope-start-date",
                "2026-09-06",
                "--note",
                "边界拒绝：超过声明上限",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["recorded"]["final_action"] == "skip"
    assert payload["open_failures"] == 0

    assert main(["failures"]) == 0
    assert "未关闭 0" in capsys.readouterr().out
    assert main(["failures", "--all"]) == 0
    out = capsys.readouterr().out
    assert "边界拒绝" in out, "处置结果可按 URL 查询到"


def test_cli_resolve_manual_review_keeps_failure_visible(cli_env, tmp_path, capsys):
    _record_failure(cli_env, stage="parse", error_type="parse_error", final_action="record_only")
    config = _write_sources(tmp_path / "sources.yaml", "http://127.0.0.1:1")

    assert (
        main(
            [
                "resolve",
                "--url",
                "https://example.invalid/a.pdf",
                "--action",
                "manual_review",
                "--source",
                "TESTSRC",
                "--stage",
                "parse",
                "--note",
                "需要人工确认扫描件方向",
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "仍未关闭失败：1" in out, "manual_review 不等于 recovered，必须保持可见"

    assert main(["failures", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["open"] == 1
    assert payload["rows"][0]["final_action"] == "manual_review"

    assert main(["plan", "--source", "TESTSRC", "--config", str(config), "--json"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["summary"] == {"manual": 1}
    assert "manual_review" in plan["tasks"][0]["reason"]


def test_cli_failures_locates_by_scope_and_doc_id(cli_env, capsys):
    """S7-02：失败可按原运行范围与母文档/对象身份定位，不只按 URL。"""
    _record_failure(cli_env, doc_id="DOC-1", scope_start_date="2026-09-06")
    _record_failure(
        cli_env,
        url="https://example.invalid/b.pdf",
        doc_id="DOC-2",
        scope_start_date="2026-09-07",
    )

    assert main(["failures", "--doc-id", "DOC-2", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["open"] == 1 and payload["shown"] == 1
    assert payload["rows"][0]["doc_id"] == "DOC-2"
    assert (payload["events"], payload["identities"], payload["objects"]) == (1, 1, 1)

    assert main(["failures", "--scope-start-date", "2026-09-06", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["shown"] == 1 and payload["rows"][0]["doc_id"] == "DOC-1"


def test_cli_failures_shows_next_action(cli_env, capsys):
    """S7-02：每条未关闭失败带下一动作（补抓计划口径），不支持的续接转人工。"""
    _record_failure(cli_env)
    _record_failure(
        cli_env,
        url="https://example.invalid/b.pdf",
        stage="parse",
        error_type="continuation_not_html",
        final_action="record_only",
    )

    assert main(["failures"]) == 0
    out = capsys.readouterr().out
    assert "next=refetch" in out
    assert "next=manual" in out
    assert "口径：事件 2 行／身份 2／对象 2" in out


def test_cli_failures_summary_reports_calibers(cli_env, capsys):
    """S7-02：有界错误摘要给出开放/人工/待处理/受限跳过/partial 与聚合口径。"""
    from crawler.output.layout import DeliveryLayout

    _record_failure(cli_env)
    _record_failure(cli_env, url="https://example.invalid/b.pdf", final_action="manual_review")

    layout = DeliveryLayout(cli_env)
    layout.pending_path.parent.mkdir(parents=True, exist_ok=True)
    layout.pending_path.write_text(
        json.dumps(
            {
                "version": "0.1.0",
                "items": {
                    "k1": {
                        "key": "k1",
                        "source_id": "TESTSRC",
                        "kind": "target",
                        "url": "https://example.invalid/c.html",
                        "state": "skipped",
                        "note": "robots_disallowed:/",
                    },
                    "k2": {
                        "key": "k2",
                        "source_id": "TESTSRC",
                        "kind": "target",
                        "url": "https://example.invalid/d.html",
                        "state": "pending",
                    },
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    layout.documents_path.parent.mkdir(parents=True, exist_ok=True)
    layout.documents_path.write_text(
        json.dumps({"doc_id": "D1", "parse_status": "partial"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    assert main(["failures", "--summary", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    summary = payload["summary"]
    assert summary["open"] == 2 and summary["manual"] == 1
    assert summary["open_by_action"] == {"manual_review": 1, "retry_later": 1}
    assert summary["pending_items"] == {
        "pending": 1,
        "refresh": 0,
        "failed": 0,
        "skipped": 1,
    }
    assert summary["restricted_skips"] == 1
    assert summary["partial_documents"] == 1
    assert "事件=失败账行数" in payload["caliber"]
    assert payload["samples"]["open"] and payload["samples"]["partial_documents"] == ["D1"]

    assert main(["failures", "--summary"]) == 0
    out = capsys.readouterr().out
    assert "错误摘要" in out and "受限跳过（robots_disallowed）：1" in out and "partial 文档：1" in out


def test_cli_fails_loudly_when_failure_ledger_write_fails(
    cli_env, site_server, tmp_path, monkeypatch, capsys
):
    """S7-02：失败账写不进去时必须显式失败，不能继续按成功报告。"""
    import crawler.output.failures_writer as writer_module

    config = _write_sources(tmp_path / "sources.yaml", site_server)

    def boom(path, rows):
        raise OSError("磁盘只读")

    monkeypatch.setattr(writer_module, "append_jsonl", boom)

    code = main(
        [
            "collect",
            "--source",
            "TESTSRC",
            "--config",
            str(config),
            "--url",
            f"{site_server}/missing-page.html",
        ]
    )

    assert code == 2, "失败账写入失败应以环境错误退出，而不是报告采集成功"
    captured = capsys.readouterr()
    assert "失败账写入失败" in captured.err
    assert "采集完成" not in captured.out


# ---------- P7-02/P7-03：人工处置的失效与可操作性 ----------


def _failed_queue_item(data_dir: Path, url: str, *, stage="fetch", doc_id=None,
                       scope_start_date=None, message="HTTP 500", error_type="http_error"):
    """建一个真实 failed 待处理项并配套一条未关闭失败，返回待处理项 key。"""
    store = PendingStore(data_dir)
    store.enqueue_targets(
        source_id="TESTSRC",
        targets=[DiscoveredTarget(url=url, discovery_method="manual")],
        scope_start_date=scope_start_date,
        enqueued_at=NOW_TEXT,
    )
    item = next(row for row in store.all_items() if row.url == url)
    store.mark(
        item.key,
        state="failed",
        attempted_at=NOW_TEXT,
        note=message,
        doc_id=doc_id,
    )
    FailureLedger(data_dir).writer.record(
        source_id="TESTSRC",
        url=url,
        time=NOW_TEXT,
        stage=stage,
        error_type=error_type,
        message=message,
        retry_count=0,
        final_action="retry_later",
        doc_id=doc_id,
        scope_start_date=scope_start_date,
    )
    return item.key


def test_cli_resolve_skip_syncs_failed_queue_item(cli_env, capsys):
    """P7-02：resolve skip 按完整身份协调失败账与队列，check 不因 failed/已关闭矛盾失败。"""
    url = "https://example.invalid/a.html"
    key = _failed_queue_item(cli_env, url)

    assert (
        main(
            [
                "resolve",
                "--url",
                url,
                "--action",
                "skip",
                "--source",
                "TESTSRC",
                "--stage",
                "fetch",
            ]
        )
        == 0
    )
    updated = PendingStore(cli_env).load()[key]
    assert updated.state == "skipped", "队列必须与账本处置一致"
    assert "人工处置" in (updated.note or "")
    capsys.readouterr()  # 丢弃 resolve 的文本输出，check --json 单独解析

    assert main(["check", "--json"]) == 1, "本数据根没有交付成果，check 仍以 1 退出"
    payload = json.loads(capsys.readouterr().out)
    assert payload["reconcile"]["ok"] is True
    assert payload["reconcile"]["problems"] == []


def test_cli_resolve_skip_respects_other_open_stage_and_other_objects(cli_env, capsys):
    """P7-02：同对象其他开放阶段不得被一条处置关闭；无关对象不受影响。"""
    url = "https://example.invalid/b.html"
    key = _failed_queue_item(cli_env, url)
    FailureLedger(cli_env).writer.record(
        source_id="TESTSRC",
        url=url,
        time=NOW_TEXT,
        stage="parse",
        error_type="parse_error",
        message="解析失败",
        retry_count=0,
        final_action="record_only",
    )
    other_url = "https://example.invalid/c.html"
    other_key = _failed_queue_item(cli_env, other_url)

    assert (
        main(
            [
                "resolve",
                "--url",
                url,
                "--action",
                "skip",
                "--source",
                "TESTSRC",
                "--stage",
                "fetch",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["queue"]["status"] == "blocked"
    assert payload["queue"]["kept_open"] == ["parse"]
    items = PendingStore(cli_env).load()
    assert items[key].state == "failed", "同对象仍有开放阶段时不得标记完成"
    assert items[other_key].state == "failed", "无关对象不得被处置"
    assert reconcile_queue_and_failures(cli_env).ok

    assert (
        main(
            [
                "resolve",
                "--url",
                url,
                "--action",
                "skip",
                "--source",
                "TESTSRC",
                "--stage",
                "parse",
            ]
        )
        == 0
    )
    items = PendingStore(cli_env).load()
    assert items[key].state == "skipped"
    assert items[other_key].state == "failed"
    assert reconcile_queue_and_failures(cli_env).ok


def test_cli_resolve_manual_review_keeps_failed_item_and_blocks_auto_retry(cli_env, capsys):
    """P7-02：manual_review 保持可见、队列不改写、不自动补抓；重复处置结果一致。"""
    url = "https://example.invalid/d.html"
    key = _failed_queue_item(cli_env, url)
    args = [
        "resolve",
        "--url",
        url,
        "--action",
        "manual_review",
        "--source",
        "TESTSRC",
        "--stage",
        "fetch",
        "--note",
        "需要人工确认扫描件方向",
        "--json",
    ]
    assert main(args) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["queue"]["status"] == "manual_review"
    assert payload["open_failures"] == 1
    item = PendingStore(cli_env).load()[key]
    assert item.state == "failed"
    assert "manual_review" in (item.note or ""), "人工处置状态必须对操作者可见"

    open_rows = FailureLedger(cli_env).open_failures()
    assert [row["final_action"] for row in open_rows] == ["manual_review"]
    plan = build_recovery_plan(
        open_rows, policy=RetryPolicy(), now=datetime.now(timezone.utc).astimezone()
    )
    assert [task.action for task in plan] == [MANUAL], "人工态不得自动补抓"
    assert reconcile_queue_and_failures(cli_env).ok

    assert main(args) == 0, "重复处置必须可复跑"
    payload = json.loads(capsys.readouterr().out)
    assert payload["queue"]["status"] == "manual_review"
    assert PendingStore(cli_env).load()[key].state == "failed"
    assert reconcile_queue_and_failures(cli_env).ok


def test_cli_resolve_recovered_keeps_pending_continuation(cli_env, capsys):
    """P7-02/P7-01：recovered 只关闭本次失败；对象仍有正文待续时不得标完成或清续作位置。"""
    url = "https://example.invalid/f.html"
    key = _failed_queue_item(cli_env, url, doc_id="DOC-F")
    continuation = {
        "kind": "body_pagination",
        "doc_id": "DOC-F",
        "mother_url": url,
        "mother_final_url": url,
        "mother_raw_path": "raw/TESTSRC/2026-09-11/html/f.html",
        "mother_sha256": "0" * 64,
        "mother_content_type": "text/html; charset=utf-8",
        "next_url": "https://example.invalid/f_2.html",
        "body_api_url": None,
        "parts": [],
        "stop_reason": "pagination_fetch_failed",
        "attempts": 1,
        "updated_at": NOW_TEXT,
    }
    PendingStore(cli_env).mark(key, state="failed", doc_id="DOC-F", continuation=continuation)

    assert (
        main(
            [
                "resolve",
                "--url",
                url,
                "--action",
                "recovered",
                "--source",
                "TESTSRC",
                "--stage",
                "fetch",
                "--doc-id",
                "DOC-F",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["queue"]["status"] == "synced"
    assert payload["queue"]["updated"][key] == "pending"
    item = PendingStore(cli_env).load()[key]
    assert item.state == "pending", "仍待续对象不得因关闭本次失败被标完成"
    assert item.continuation == continuation, "续作位置不得被清空"
    assert reconcile_queue_and_failures(cli_env).ok


def test_cli_resolve_reports_queue_write_failure_recoverably(cli_env, monkeypatch, capsys):
    """P7-02：队列回写失败有明确结果；处置行保留、重复执行可恢复、不冒充处置成功。"""
    from crawler.schedule import pending as pending_module

    url = "https://example.invalid/e.html"
    key = _failed_queue_item(cli_env, url)
    original_mark = pending_module.PendingStore.mark

    def boom(self, item_key, **kwargs):
        raise OSError("磁盘只读")

    monkeypatch.setattr(pending_module.PendingStore, "mark", boom)
    args = ["resolve", "--url", url, "--action", "skip", "--source", "TESTSRC", "--stage", "fetch"]
    assert main(args) == 2
    captured = capsys.readouterr()
    assert "队列协调失败" in captured.err
    assert "重复执行同一 resolve" in captured.err
    assert "已记录人工处置" not in captured.out, "队列未同步时不得声称处置成功"

    history = FailureLedger(cli_env).history_of(url)
    assert [row["final_action"] for row in history] == ["retry_later", "skip"]
    assert PendingStore(cli_env).load()[key].state == "failed"

    monkeypatch.setattr(pending_module.PendingStore, "mark", original_mark)
    assert main(args) == 0, "修复队列问题后重复执行同一处置应成功"
    assert PendingStore(cli_env).load()[key].state == "skipped"
    assert reconcile_queue_and_failures(cli_env).ok


def test_cli_resolve_selects_explicit_empty_identity(cli_env, capsys):
    """P7-03：同 URL 带/不带日期或 doc_id 时，用显式空字符串准确选中空值身份。"""
    url = "https://example.invalid/a.pdf"
    ledger = FailureLedger(cli_env)
    ledger.writer.record(
        source_id="TESTSRC",
        url=url,
        time=NOW_TEXT,
        stage="fetch",
        error_type="http_error",
        message="带身份",
        retry_count=0,
        final_action="retry_later",
        doc_id="DOC-1",
        scope_start_date="2026-09-06",
    )
    ledger.writer.record(
        source_id="TESTSRC",
        url=url,
        time=NOW_TEXT,
        stage="fetch",
        error_type="request_error",
        message="空身份",
        retry_count=0,
        final_action="retry_later",
    )

    assert (
        main(["resolve", "--url", url, "--action", "skip", "--source", "TESTSRC", "--stage", "fetch"])
        == 2
    ), "未指定归属而存在多种身份时必须报错"
    err = capsys.readouterr().err
    assert "显式传空字符串" in err and "doc=DOC-1" in err

    assert (
        main(
            [
                "resolve",
                "--url",
                url,
                "--action",
                "skip",
                "--source",
                "TESTSRC",
                "--stage",
                "fetch",
                "--doc-id",
                "",
                "--scope-start-date",
                "",
            ]
        )
        == 0
    )
    open_rows = FailureLedger(cli_env).open_failures()
    assert [row["message"] for row in open_rows] == ["带身份"], "只关闭指定的空值身份"
    capsys.readouterr()  # 丢弃 resolve 的文本输出，failures --json 单独解析

    assert main(["failures", "--url", url, "--doc-id", "", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["open"] == 0, "空值身份已关闭，可按显式空值查询"
