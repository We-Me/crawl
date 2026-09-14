#!/usr/bin/env python3
"""阶段七有界闭环自检（开发工具，不是业务程序；只连本机回环夹具站点）。

用途：用真实 CLI 在 `tests/fixtures/site` 的回放站点上走一遍最小代表性闭环——
发现 → 获取归档 → 标准化与最小分块 → 预算停止与续作 → 失败查询/补抓/人工处置 → 对账，
逐步记录命令、退出码与关键计数，供 [交付证据](../specs/001-public-knowledge-collection/evidence/stage-seven-delivery.md)
与 [原型收尾证据](../specs/001-public-knowledge-collection/evidence/stage-seven-prototype.md) 引用。

后审查三项修复也在同一闭环里核验：真实 failed 队列对象的 resolve 协调（P7-02）、
同 URL 多身份时显式空值选中与对象隔离（P7-03）；附件与母页续作的恢复隔离（P7-01）
由 `tests/test_recovery.py` 的定向用例核验（本工具不伪造 partial 母页）。

边界：只请求本地夹具站点（127.0.0.1，不访问真实来源）；数据根写在 --workdir
（默认 /tmp/crawl-s7-loop），不读写正式 data/；--workdir 已存在时拒绝覆盖，除非 --clean。

用法：
  uv run --locked --no-python-downloads python tools/closed_loop_fixture.py \
      [--workdir /tmp/crawl-s7-loop] [--json /tmp/crawl-s7-loop.json] [--clean]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from conftest import SITE_DIR, _serve_site  # noqa: E402 - 复用测试夹具站点的动态端点

START_DATE = "2026-09-01"


def _write_sources(path: Path, base_url: str) -> Path:
    entry = {
        "source_id": "TESTSRC",
        "source_name": "本地夹具来源",
        "base_domain": "127.0.0.1",
        "allowed_domains": ["127.0.0.1"],
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
    path.write_text(
        yaml.safe_dump({"version": "closed-loop", "sources": [entry]}, allow_unicode=True),
        encoding="utf-8",
    )
    return path


def _run(step: str, env: dict, *argv: str) -> dict:
    command = [sys.executable, "-m", "crawler.cli", *argv]
    completed = subprocess.run(
        command, capture_output=True, text=True, env=env, cwd=str(ROOT), check=False
    )
    row = {
        "step": step,
        "command": " ".join(argv),
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr[-2000:],
    }
    try:
        row["payload"] = json.loads(completed.stdout)
    except json.JSONDecodeError:
        row["payload"] = None
    return row


def _check(row: dict, condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(f"{row['step']}：{message}（退出码 {row['exit_code']}）")


def _pending_states(data_dir: Path) -> dict:
    """读取待处理状态文件里的 (URL, 原运行范围) → state（仅供闭环断言，不参与业务逻辑）。"""
    path = data_dir / "manifests" / "pending_items.json"
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        (row["url"], row.get("scope_start_date") or None): row["state"]
        for row in (payload.get("items") or {}).values()
        if row.get("url")
    }


def _open_failure_rows(data_dir: Path) -> List[dict]:
    """按身份取失败账未关闭行（与 FailureLedger.open_failures 同口径，只读）。"""
    from crawler.monitor.failures import OPEN_ACTIONS, FailureLedger

    ledger = FailureLedger(data_dir)
    return [
        row for row in ledger.latest_by_key().values()
        if row.get("final_action") in OPEN_ACTIONS
    ]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="阶段七有界闭环自检（只连本机夹具站点）")
    parser.add_argument("--workdir", default="/tmp/crawl-s7-loop", help="本次闭环的工作目录")
    parser.add_argument("--json", default=None, help="把逐步记录写入该 JSON 文件")
    parser.add_argument("--clean", action="store_true", help="先删除已存在的工作目录再运行")
    args = parser.parse_args(argv)

    workdir = Path(args.workdir)
    if workdir.exists():
        if not args.clean:
            print(f"工作目录已存在：{workdir}（加 --clean 覆盖，或换 --workdir）", file=sys.stderr)
            return 2
        shutil.rmtree(workdir)
    data_dir = workdir / "data"
    data_dir.mkdir(parents=True)

    env = dict(os.environ)
    env["CRAWL_ENV"] = "development"
    env["CRAWL_DATA_DIR"] = str(data_dir)

    rows: List[dict] = []
    try:
        with _serve_site(SITE_DIR) as base_url:
            config = _write_sources(workdir / "sources.yaml", base_url)
            common = ("--config", str(config), "--json")
            index = f"{base_url}/index.html"

            row = _run(
                "1-发现并预算停止",
                env,
                "collect", "--source", "TESTSRC", "--entry-url", index,
                "--start-date", START_DATE, "--max-requests", "3", *common,
            )
            rows.append(row)
            _check(row, row["exit_code"] == 3, "预算耗尽应以退出码 3 停止")
            _check(row, row["payload"]["stop"]["reason"] is not None, "应报告 stop.reason")
            _check(row, row["payload"]["counters"]["resources"] >= 1, "停止前已归档发现响应")
            _check(row, row["payload"]["stop"]["unprocessed"] >= 1, "应留下未处理目标")

            row = _run(
                "2-续作完成归档与最小分块",
                env,
                "collect", "--source", "TESTSRC", "--entry-url", index,
                "--start-date", START_DATE, "--max-items", "3", *common,
            )
            rows.append(row)
            counters = row["payload"]["counters"]
            # 夹具站点自带一个 404 附件（detail_1.html 的 unavailable.pdf），按设计记入失败账。
            _check(row, row["exit_code"] == 1 and counters["failures"] == 1,
                   "续作应完成正文并登记夹具自带的 404 附件失败")
            _check(row, counters["documents"] >= 1, "应产出标准化文档")
            _check(row, counters["blocks"] >= 1, "应产出最小结构块")
            broken = row["payload"]["failures"][0]
            _check(row, broken["stage"] == "fetch" and broken["http_status"] == 404
                   and bool(broken.get("doc_id")), "失败行应带母文档身份")

            flaky = f"{base_url}/_flaky/1"
            row = _run("3a-临时失败入账", env, "collect", "--source", "TESTSRC",
                       "--url", flaky, "--start-date", START_DATE, *common)
            rows.append(row)
            _check(row, row["exit_code"] == 1 and row["payload"]["counters"]["failures"] == 1,
                   "首个 500 应记入失败账并返回 1")

            row = _run("3b-补抓计划", env, "plan", "--source", "TESTSRC",
                       "--config", str(config), "--json")
            rows.append(row)
            tasks = row["payload"]["tasks"]
            _check(row, any(task["url"] == flaky for task in tasks), "计划应包含该失败任务")

            row = _run("3c-补抓恢复", env, "resume", "--source", "TESTSRC",
                       "--config", str(config), "--max-tasks", "5", "--json")
            rows.append(row)
            # 同一轮还留有夹具自带的 404 附件（永久 4xx，转人工），因此退出码为 1。
            _check(row, row["exit_code"] == 1, "补抓后仍有待人工项，应以 1 结束")
            _check(row, row["payload"]["recovered"] >= 1, "该任务应记为 recovered")
            _check(row, row["payload"]["failed"] == 0, "补抓后不应仍失败")
            _check(row, row["payload"]["manual"] >= 1, "永久 4xx 应转人工处置")

            # P7-02：真实 failed 队列对象的 skip 必须同步队列，不留 failed/已关闭矛盾。
            queued = f"{base_url}/_flaky/3"
            row = _run("3d-真实失败队列对象入账", env, "collect", "--source", "TESTSRC",
                       "--url", queued, "--start-date", START_DATE, *common)
            rows.append(row)
            _check(row, row["exit_code"] == 1 and row["payload"]["counters"]["failures"] == 1,
                   "首个 500 应记入失败账并返回 1")
            _check(row, row["payload"]["coverage"]["queue_state"]["targets"]["failed"] >= 1,
                   "该对象应以 failed 待处理项保留在队列")

            row = _run("3e-人工处置同步队列（skip）", env, "resolve", "--url", queued,
                       "--source", "TESTSRC", "--stage", "fetch",
                       "--scope-start-date", START_DATE, "--action", "skip",
                       "--note", "闭环示例：确认该地址不再重试", "--json")
            rows.append(row)
            _check(row, row["exit_code"] == 0, "按显式身份的处置应成功")
            _check(row, row["payload"]["queue"]["status"] == "synced",
                   "resolve 必须按同一身份协调队列")
            _check(row, all(state == "skipped" for state in row["payload"]["queue"]["updated"].values()),
                   "队列项应转为 skipped")
            item_states = _pending_states(data_dir)
            _check(row, item_states.get((queued, START_DATE)) == "skipped",
                   "队列文件里该对象应为 skipped")

            # P7-03：同 URL 不同运行范围时，显式空值身份可选中且不误关另一对象。
            multi = f"{base_url}/_flaky/2"
            for scope in (START_DATE, "2026-09-15"):
                row = _run(f"3f-多身份入账 scope={scope}", env, "collect", "--source", "TESTSRC",
                           "--url", multi, "--start-date", scope, *common)
                rows.append(row)
                _check(row, row["exit_code"] == 1
                       and row["payload"]["counters"]["failures"] == 1,
                       "首个 500 应记入失败账并返回 1")

            row = _run("3g-未指定归属必须报错", env, "resolve", "--url", multi,
                       "--source", "TESTSRC", "--stage", "fetch", "--action", "skip", "--json")
            rows.append(row)
            _check(row, row["exit_code"] == 2, "同一 URL 多身份而未指定归属时应报错")
            _check(row, "显式传空字符串" in (row["stderr"] or ""),
                   "错误提示应给出空值身份的显式传法")

            row = _run("3h-显式空值身份选中", env, "resolve", "--url", multi,
                       "--source", "TESTSRC", "--stage", "fetch",
                       "--scope-start-date", START_DATE, "--doc-id", "", "--action", "skip",
                       "--note", "闭环示例：只处置该范围内该 URL 的空 doc_id 身份", "--json")
            rows.append(row)
            _check(row, row["exit_code"] == 0, "显式空值身份应可选中")
            _check(row, row["payload"]["queue"]["status"] == "synced", "队列应同步该身份")
            item_states = _pending_states(data_dir)
            _check(row, item_states.get((multi, START_DATE)) == "skipped",
                   "该身份对应队列项应转 skipped")
            _check(row, item_states.get((multi, "2026-09-15")) == "failed",
                   "另一运行范围的同名对象队列状态不得被改动")
            open_scopes = {
                item["scope_start_date"] for item in _open_failure_rows(data_dir)
                if item["url"] == multi
            }
            _check(row, open_scopes == {"2026-09-15"},
                   "另一运行范围的同名对象不得被误关")

            row = _run("3i-另一身份单独处置", env, "resolve", "--url", multi,
                       "--source", "TESTSRC", "--stage", "fetch",
                       "--scope-start-date", "2026-09-15", "--action", "skip",
                       "--note", "闭环示例：另一范围单独处置", "--json")
            rows.append(row)
            _check(row, row["exit_code"] == 0, "另一身份应可单独处置")
            remaining = [
                open_row for open_row in _open_failure_rows(data_dir)
                if open_row["url"] == multi
            ]
            _check(row, remaining == [], "该 URL 的两个身份均已关闭")

            row = _run("4a-失败定位", env, "failures", "--source", "TESTSRC", "--json")
            rows.append(row)
            _check(row, any(item["url"] == broken["url"] for item in row["payload"]["rows"]),
                   "failures 应列出该未关闭失败")

            row = _run("4b-人工处置（skip）", env, "resolve",
                       "--url", broken["url"], "--source", broken["source_id"],
                       "--stage", broken["stage"], "--doc-id", broken["doc_id"],
                       "--scope-start-date", broken["scope_start_date"],
                       "--action", "skip", "--note", "闭环示例：确认页面缺失，跳过", "--json")
            rows.append(row)
            _check(row, row["exit_code"] == 0, "按显式身份的处置应成功")
            _check(row, row["payload"]["recorded"]["final_action"] == "skip", "应记为 skip")

            row = _run("4c-处置结果查询", env, "failures", "--source", "TESTSRC",
                       "--url", broken["url"], "--all", "--json")
            rows.append(row)
            _check(row, row["payload"]["open"] == 0, "处置后该身份不应仍是未关闭")
            _check(row, any(item["final_action"] == "skip" and "闭环示例" in str(item["message"])
                            for item in row["payload"]["rows"]), "历史行应能查到处置说明")

            row = _run("5-对账", env, "check", "--json")
            rows.append(row)
            _check(row, row["exit_code"] == 0 and row["payload"]["ok"] is True,
                   "对账与交付校验应通过")
            _check(row, row["payload"]["reconcile"]["ok"] is True, "reconcile 应为 ok")
    except AssertionError as exc:
        print(f"闭环失败：{exc}", file=sys.stderr)
        _dump(rows, args.json)
        return 1

    _dump(rows, args.json)
    return 0


def _dump(rows: List[dict], target: Optional[str]) -> None:
    for row in rows:
        payload = row.get("payload") or {}
        print(f"[{row['step']}] exit={row['exit_code']} {row['command']}")
        summary = payload.get("counters") or payload.get("summary") or {}
        if summary:
            print(f"    {json.dumps(summary, ensure_ascii=False)}")
        if payload.get("stop"):
            print(f"    stop={json.dumps(payload['stop'], ensure_ascii=False)}")
        if payload.get("failures"):
            first = payload["failures"][0]
            print(
                "    failure="
                + json.dumps(
                    {key: first.get(key) for key in ("stage", "error_type", "url", "doc_id")},
                    ensure_ascii=False,
                )
            )
        if "open" in payload:
            print(
                f"    open={payload['open']} shown={payload.get('shown')} "
                f"by_action={json.dumps(payload.get('by_action'), ensure_ascii=False)}"
            )
        if payload.get("recorded"):
            print(
                "    recorded="
                + json.dumps(
                    {key: payload["recorded"].get(key)
                     for key in ("url", "stage", "final_action", "message", "doc_id")},
                    ensure_ascii=False,
                )
            )
        if "recovered" in payload:
            print(
                f"    recovered={payload['recovered']} failed={payload['failed']} "
                f"manual={payload['manual']} pending={payload['pending']}"
            )
        if "reconcile" in payload:
            print(
                f"    ok={payload['ok']} "
                f"reconcile={json.dumps(payload['reconcile'], ensure_ascii=False)}"
            )
    if target:
        Path(target).write_text(
            json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"逐步记录已写入 {target}")


if __name__ == "__main__":
    raise SystemExit(main())
