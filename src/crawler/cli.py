"""正式业务命令行入口（NEXT-01 / T027 的操作入口子项）。

命令只包装既有能力，不在这里重新实现发现、解析、归档或交付校验：

  sources   校验来源配置（语义校验 + 来源契约 schema）并列出登记来源
  collect   按来源执行一次采集
  plan      查看未关闭失败的补抓计划（只读，不请求网络）
  resume    对指定来源执行补抓
  check     校验数据根的六项成果、契约 schema、端到端追溯与队列对账

来源边界、robots 规则、限速、失败账和交付检查仍由被调用模块执行；CLI 不放宽
任何访问规则、失败处理或质量阈值。配置只经 crawler.config.settings 读取
CRAWL_ENV / CRAWL_DATA_DIR，不提供第二套路径优先级。

退出码：0 成功；1 运行完成但仍有失败或交付校验不通过；2 配置、参数或环境错误。
3 运行因请求预算或截止时间提前停止（未完成，已归档成果保留）。
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Optional, Sequence

import yaml

from crawler import __version__
from crawler.config.registry import SourceRegistry
from crawler.config.settings import ConfigurationError, load_settings
from crawler.fetch.budget import BudgetConfigError, RunBudget
from crawler.fetch.retry import RetryConfigError, RetryPolicy, summarize_plan
from crawler.output.delivery import inspect_delivery
from crawler.pipeline import CrawlPipeline
from crawler.schedule.scope import ScopeConfigError, parse_start_date, RunScope
from crawler.validate.reconcile import reconcile_queue_and_failures
from crawler.validate.schema import SchemaConfigError, load_contract, validate_delivery, validate_instance
from crawler.validate.traceability import trace_delivery

EXIT_OK = 0
EXIT_RUN = 1
EXIT_CONFIG = 2
EXIT_STOPPED = 3

PROGRAM = "crawl"


def _add_budget_arguments(parser: argparse.ArgumentParser) -> None:
    """collect/resume 共用的运行预算参数；省略时该运行不受这两项限制。"""
    parser.add_argument(
        "--max-requests",
        type=int,
        default=None,
        metavar="N",
        help="本次运行最多发出的 HTTP 请求数（含 robots、重定向每跳、重试、分页、接口与附件）",
    )
    parser.add_argument(
        "--deadline-seconds",
        type=float,
        default=None,
        metavar="S",
        help="本次运行的墙上时限（秒）；到时不发新请求，等待超过剩余时间也停止",
    )


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--config",
        default=None,
        metavar="PATH",
        help="来源注册表 YAML；缺省使用随包 sources.yaml",
    )
    common.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="输出 crawler 运行日志（默认只打印命令结果）",
    )

    parser = argparse.ArgumentParser(
        prog=PROGRAM,
        description="公开知识采集：来源校验、按来源采集、补抓与交付检查",
        epilog="数据根与运行模式由 CRAWL_ENV / CRAWL_DATA_DIR 决定；退出码 0/1/2 见各子命令说明。",
    )
    parser.add_argument("--version", action="version", version=f"{PROGRAM} {__version__}")
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND", required=True)

    sources = subparsers.add_parser(
        "sources", parents=[common], help="校验来源配置并列出来源"
    )
    sources.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    sources.set_defaults(handler=_cmd_sources)

    collect = subparsers.add_parser(
        "collect", parents=[common], help="按来源执行一次采集"
    )
    collect.add_argument("--source", required=True, metavar="ID", help="source_id")
    collect.add_argument(
        "--entry-url",
        action="append",
        default=[],
        metavar="URL",
        help="覆盖来源配置的栏目入口，可重复",
    )
    collect.add_argument(
        "--keyword", action="append", default=[], metavar="WORD", help="站内搜索关键词，可重复"
    )
    collect.add_argument(
        "--sitemap", action="append", default=[], metavar="URL", help="sitemap 地址，可重复"
    )
    collect.add_argument(
        "--api", action="append", default=[], metavar="URL", help="结构化接口地址，可重复"
    )
    collect.add_argument(
        "--url",
        action="append",
        default=[],
        metavar="URL",
        help="直接采集的页面/附件 URL（discovery_method=manual），可重复；仍受访问边界、robots 与预算约束",
    )
    collect.add_argument("--max-items", type=int, default=100, help="本次最多采集的目标数")
    collect.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="本次运行的每入口页数上限（覆盖来源适配配置，仅本次生效）",
    )
    collect.add_argument(
        "--discover-only",
        action="store_true",
        help="只遍历发现入口并把目标入队，不处理目标（分页覆盖用；发现阶段不受 --max-items 限制）",
    )
    collect.add_argument(
        "--no-attachments", action="store_true", help="不下载附件（仅正文页面）"
    )
    collect.add_argument(
        "--start-date",
        default=None,
        metavar="YYYY-MM-DD",
        help=(
            "按内容发布日期取包含式下界：早于该日期只保留原件与账本、不产出文档；"
            "发布日期未知保留候选并记录原因；省略则不设日期范围"
        ),
    )
    _add_budget_arguments(collect)
    collect.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    collect.set_defaults(handler=_cmd_collect)

    plan = subparsers.add_parser("plan", parents=[common], help="查看未关闭失败的补抓计划")
    plan.add_argument("--source", default=None, metavar="ID", help="只看指定来源")
    plan.add_argument("--ready-only", action="store_true", help="只列出退避已到、当前可执行的任务")
    plan.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    plan.set_defaults(handler=_cmd_plan)

    resume = subparsers.add_parser("resume", parents=[common], help="执行指定来源的补抓")
    resume.add_argument("--source", required=True, metavar="ID", help="source_id")
    resume.add_argument("--max-tasks", type=int, default=None, help="本次最多处理的任务数")
    resume.add_argument(
        "--respect-backoff",
        action="store_true",
        help="跳过退避未到的任务（默认立即执行计划中的任务）",
    )
    resume.add_argument("--max-attempts", type=int, default=3, help="自动补抓的次数上限")
    resume.add_argument(
        "--base-delay-seconds", type=float, default=60.0, help="退避基数秒数（指数增长）"
    )
    resume.add_argument("--max-delay-seconds", type=float, default=3600.0, help="退避上限秒数")
    _add_budget_arguments(resume)
    resume.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    resume.set_defaults(handler=_cmd_resume)

    check = subparsers.add_parser("check", parents=[common], help="校验数据根的交付成果与队列对账")
    check.add_argument(
        "--require-nonempty", action="store_true", help="账本为空时按失败处理"
    )
    check.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    check.set_defaults(handler=_cmd_check)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s %(message)s",
    )
    try:
        return args.handler(args)
    except ConfigurationError as exc:
        print(f"配置错误：{exc}", file=sys.stderr)
        return EXIT_CONFIG
    except SchemaConfigError as exc:
        print(f"契约错误：{exc}", file=sys.stderr)
        return EXIT_CONFIG
    except RetryConfigError as exc:
        print(f"参数错误：{exc}", file=sys.stderr)
        return EXIT_CONFIG
    except ScopeConfigError as exc:
        print(f"参数错误：{exc}", file=sys.stderr)
        return EXIT_CONFIG


# ---------- 子命令 ----------


def _cmd_sources(args) -> int:
    registry = _load_registry(args)
    problems = _validate_contract(registry)
    rows = [
        {
            "source_id": source.source_id,
            "source_name": source.source_name,
            "enabled": source.enabled,
            "base_domain": source.base_domain,
            "allowed_domains": list(source.allowed_domains),
            "entry_urls": list(source.entry_urls),
            "request_rate_per_second": source.request_rate_per_second,
            "max_concurrency": source.max_concurrency,
            "max_retries": source.max_retries,
            "adapter_configured": source.adapter.configured,
        }
        for source in registry.sources
    ]
    if args.json:
        print(
            json.dumps(
                {
                    "ok": not problems,
                    "config_path": str(registry.config_path),
                    "config_version": registry.config_version,
                    "config_digest": registry.config_digest,
                    "sources": rows,
                    "contract_errors": problems,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(
            f"来源配置 {registry.config_path} version={registry.config_version} "
            f"digest={registry.config_digest[:12]} 共 {len(rows)} 条"
            f"（启用 {sum(1 for row in rows if row['enabled'])} 条）"
        )
        for row in rows:
            state = "enabled" if row["enabled"] else "disabled"
            print(
                f"  {row['source_id']:<8} {state:<8} {row['source_name']}  "
                f"域={','.join(row['allowed_domains'])}  入口={len(row['entry_urls'])}  "
                f"速率={row['request_rate_per_second']}/s  并发上限={row['max_concurrency']}  "
                f"重试={row['max_retries']}"
                + ("  适配规则=已配置" if row["adapter_configured"] else "")
            )
        for problem in problems:
            print(f"  契约不符：{problem}", file=sys.stderr)
    return EXIT_CONFIG if problems else EXIT_OK


def _cmd_collect(args) -> int:
    settings = load_settings()
    registry = _load_registry(args)
    source = registry.get(args.source)
    if not source.enabled:
        print(f"配置错误：来源未启用，不能采集：{args.source}", file=sys.stderr)
        return EXIT_CONFIG
    if args.max_items < 0:
        print("参数错误：--max-items 不能为负数", file=sys.stderr)
        return EXIT_CONFIG
    if args.max_pages is not None and args.max_pages < 1:
        print("参数错误：--max-pages 必须是 ≥1 的整数", file=sys.stderr)
        return EXIT_CONFIG
    if args.discover_only and args.url:
        print("参数错误：--discover-only 不能与 --url 同用", file=sys.stderr)
        return EXIT_CONFIG
    try:
        budget = _build_budget(args)
    except BudgetConfigError as exc:
        print(f"参数错误：{exc}", file=sys.stderr)
        return EXIT_CONFIG
    scope = RunScope(start_date=parse_start_date(args.start_date))
    pipeline = CrawlPipeline(registry, settings.data_dir, settings=settings)
    report = pipeline.collect(
        source.source_id,
        entry_urls=list(args.entry_url) if args.entry_url else None,
        search_keywords=list(args.keyword),
        sitemap_urls=list(args.sitemap),
        api_urls=list(args.api),
        manual_urls=list(args.url),
        include_attachments=not args.no_attachments,
        max_items=args.max_items,
        budget=budget,
        scope=scope,
        max_pages=args.max_pages,
        discover_only=args.discover_only,
    )
    counters = report.counters
    row = {
        "ok": counters.failures == 0 and report.stop_reason is None,
        "source_id": report.source_id,
        "data_dir": str(settings.data_dir),
        "scope": scope.as_row(),
        "counters": {
            "requests": counters.requests,
            "resources": counters.resources,
            "documents": counters.documents,
            "blocks": counters.blocks,
            "failures": counters.failures,
            "skipped": counters.skipped,
            "not_modified": counters.not_modified,
            "out_of_window": counters.out_of_window,
        },
        "discovery": [result.as_row() for result in report.discovery],
        "date_decisions": report.date_decisions,
        "coverage": report.coverage,
        "budget": report.budget,
        "stop": {
            "reason": report.stop_reason,
            "message": report.stop_message,
            "unprocessed": report.unprocessed,
        },
        "run_id": (report.metrics or {}).get("run_id"),
        "failures": report.failures,
        "skipped": [{"url": item.url, "reason": item.reason} for item in report.skipped],
    }
    if args.json:
        print(json.dumps(row, ensure_ascii=False, indent=2))
    else:
        print(
            f"采集完成 source={row['source_id']} run_id={row['run_id']} "
            f"请求={counters.requests} 资源={counters.resources} 文档={counters.documents} "
            f"块={counters.blocks} 失败={counters.failures} 跳过={counters.skipped} "
            f"未修改={counters.not_modified} 范围外={counters.out_of_window}"
        )
        if scope.active:
            print(
                f"运行范围：起始日 {scope.start_date.isoformat()}（包含式下界，按 publication_date）"
            )
        for result in report.discovery:
            row_detail = f"  发现 {result.stage} 策略={result.strategy} 状态={result.status} 目标={len(result.targets)}"
            if result.note:
                row_detail += f" 说明={result.note}"
            print(row_detail)
        _print_coverage_line(report.coverage)
        _print_budget_line(report.budget)
        print(f"数据根 {settings.data_dir}")
        for failure in report.failures:
            print(
                f"  失败 {failure.get('stage')} {failure.get('url')} "
                f"{failure.get('error_type')} {failure.get('message')}"
            )
        for item in report.skipped:
            print(f"  跳过 {item.url} {item.reason}")
        if report.stop_reason:
            _print_stop_line(report.stop_reason, report.stop_message, report.unprocessed)
        if counters.failures:
            print(f"存在 {counters.failures} 项失败，可用 {PROGRAM} resume 补抓", file=sys.stderr)
    if report.stop_reason:
        return EXIT_STOPPED
    return EXIT_RUN if counters.failures else EXIT_OK


def _cmd_plan(args) -> int:
    settings = load_settings()
    registry = _load_registry(args)
    pipeline = CrawlPipeline(registry, settings.data_dir, settings=settings)
    tasks = pipeline.recovery_plan()
    moment = pipeline.now()
    if args.source:
        registry.get(args.source)
        tasks = [task for task in tasks if task.source_id == args.source]
    if args.ready_only:
        tasks = [task for task in tasks if task.not_before <= moment]
    summary = summarize_plan(tasks)
    rows = [task.as_row() for task in tasks]
    if args.json:
        print(
            json.dumps(
                {"data_dir": str(settings.data_dir), "summary": summary, "tasks": rows},
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(
            f"补抓计划 {settings.data_dir} 共 {len(rows)} 项"
            + (f"（{'，'.join(f'{k}={v}' for k, v in sorted(summary.items()))}）" if summary else "")
        )
        for row in rows:
            print(
                f"  {row['action']:<8} {row['url']} stage={row['stage']} "
                f"attempt={row['attempt']} not_before={row['not_before']}"
                + (f" 原起始日={row['scope_start_date']}" if row.get("scope_start_date") else "")
                + (f" 原因={row['reason']}" if row.get("reason") else "")
            )
    return EXIT_OK


def _cmd_resume(args) -> int:
    settings = load_settings()
    registry = _load_registry(args)
    registry.get(args.source)
    policy = RetryPolicy(
        max_attempts=args.max_attempts,
        base_delay_seconds=args.base_delay_seconds,
        max_delay_seconds=args.max_delay_seconds,
    )
    try:
        budget = _build_budget(args)
    except BudgetConfigError as exc:
        print(f"参数错误：{exc}", file=sys.stderr)
        return EXIT_CONFIG
    pipeline = CrawlPipeline(registry, settings.data_dir, settings=settings)
    report = pipeline.resume_failures(
        args.source,
        policy=policy,
        max_tasks=args.max_tasks,
        respect_backoff=args.respect_backoff,
        budget=budget,
    )
    remaining = len(report.failures) + len(report.manual) + len(report.pending)
    row = {
        "ok": remaining == 0 and report.stop_reason is None,
        "source_id": report.source_id,
        "data_dir": str(settings.data_dir),
        "recovered": len(report.recovered),
        "skipped": len(report.skipped),
        "manual": len(report.manual),
        "pending": len(report.pending),
        "failed": len(report.failures),
        "scope_start_dates": sorted(
            {
                item.get("scope_start_date")
                for item in [*report.recovered, *report.skipped, *report.manual, *report.failures]
                if item.get("scope_start_date")
            }
        ),
        "budget": report.budget,
        "stop": {
            "reason": report.stop_reason,
            "message": report.stop_message,
            "unprocessed": report.unprocessed,
        },
        "run_id": (report.metrics or {}).get("run_id"),
    }
    if args.json:
        print(json.dumps(row, ensure_ascii=False, indent=2))
    else:
        print(
            f"补抓完成 source={row['source_id']} run_id={row['run_id']} "
            f"恢复={row['recovered']} 跳过={row['skipped']} 待人工={row['manual']} "
            f"退避等待={row['pending']} 仍失败={row['failed']}"
        )
        _print_budget_line(report.budget)
        for task in report.manual:
            scope_note = f" [原起始日 {task['scope_start_date']}]" if task.get("scope_start_date") else ""
            print(f"  待人工 {task['url']}{scope_note} {task.get('reason', '')}")
        for task in report.pending:
            print(f"  等待退避 {task['url']} not_before={task['not_before']}")
        if report.stop_reason:
            _print_stop_line(report.stop_reason, report.stop_message, report.unprocessed)
        if remaining:
            print(f"仍有 {remaining} 项未关闭，需要人工处理或下次补抓", file=sys.stderr)
    if report.stop_reason:
        return EXIT_STOPPED
    return EXIT_RUN if remaining else EXIT_OK


def _cmd_check(args) -> int:
    settings = load_settings()
    delivery = inspect_delivery(settings.data_dir, require_nonempty=args.require_nonempty)
    schema = validate_delivery(settings.data_dir)
    trace = trace_delivery(settings.data_dir)
    reconcile = reconcile_queue_and_failures(settings.data_dir)
    ok = bool(delivery.ok and schema.ok and trace.ok and reconcile.ok)
    if args.json:
        print(
            json.dumps(
                {
                    "ok": ok,
                    "data_dir": str(settings.data_dir),
                    "delivery": delivery.as_row(),
                    "schema": schema.as_row(),
                    "trace": trace.as_row(),
                    "reconcile": reconcile.as_row(),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(f"数据根 {settings.data_dir}")
        print(
            "交付成果："
            + ("齐全" if delivery.ok else f"不通过（缺失 {delivery.missing}）")
            + f" manifest={delivery.counts['manifest_rows']} "
            f"documents={delivery.counts['document_rows']} "
            f"blocks={delivery.counts['block_rows']} "
            f"failures={delivery.counts['failure_rows']} "
            f"raw_files={delivery.counts['raw_files']}"
        )
        for issue in delivery.path_issues:
            print(f"  路径问题：{issue}")
        for name in delivery.forbidden:
            print(f"  禁止的派生成果：{name}")
        print(
            f"契约 schema：{'通过' if schema.ok else f'不通过（{len(schema.errors)} 个错误）'}"
        )
        for error in schema.errors[:10]:
            print(f"  {error['file']}:{error['line']} {error['message']}")
        if len(schema.errors) > 10:
            print(f"  ……其余 {len(schema.errors) - 10} 个错误见 --json 输出")
        doc_rate = _rate_text(trace.document_rate)
        block_rate = _rate_text(trace.block_rate)
        print(
            f"追溯：documents {trace.documents_traceable}/{trace.documents_total}（{doc_rate}）"
            f" blocks {trace.blocks_traceable}/{trace.blocks_total}（{block_rate}）"
        )
        for problem in trace.problems[:10]:
            print(f"  追溯问题：{problem}")
        states = " / ".join(
            f"{state} {count}" for state, count in sorted(reconcile.items_by_state.items())
        ) or "无"
        print(
            "队列对账："
            + ("通过" if reconcile.ok else f"不通过（{len(reconcile.problems)} 处矛盾）")
            + f"（待处理项 {reconcile.items_total}：{states}；失败账未关闭 {reconcile.open_failures}）"
        )
        for problem in reconcile.problems[:10]:
            print(f"  对账矛盾：{problem['message']} url={problem['url']}")
    return EXIT_OK if ok else EXIT_RUN


# ---------- 辅助 ----------


def _load_registry(args) -> SourceRegistry:
    config = Path(args.config) if args.config else None
    return SourceRegistry.load(config)


def _build_budget(args):
    """按 CLI 参数构造本次运行预算；两项都未给出时返回 None（不额外限制）。"""
    if args.max_requests is None and args.deadline_seconds is None:
        return None
    return RunBudget(
        max_requests=args.max_requests,
        deadline_seconds=args.deadline_seconds,
    )


def _print_coverage_line(coverage) -> None:
    """来源报告覆盖口径（S5-03/S5-04/S5-06）：发现完整性、目标与附件分开记录。"""
    coverage = dict(coverage or {})
    if not coverage:
        return
    targets_row = dict(coverage.get("targets") or {})
    attachments_row = dict(coverage.get("attachments") or {})
    discovery_row = dict(coverage.get("discovery") or {})
    target_keys = ("discovered", "attempted", "processed", "failed", "skipped")
    attachment_keys = (
        "discovered",
        "downloaded",
        "resumed",
        "failed",
        "boundary_rejected",
        "rule_excluded",
        "duplicates",
        "pending",
    )
    parts = [
        (
            "主目标 发现={discovered} 尝试={attempted} 成功={processed} "
            "失败={failed} 跳过={skipped}"
        ).format(**{key: targets_row.get(key, 0) for key in target_keys}),
        (
            "附件 发现={discovered} 下载={downloaded} 续传={resumed} 失败={failed} "
            "边界拒绝={boundary_rejected} 规则排除={rule_excluded} 重复={duplicates} 待处理={pending}"
        ).format(**{key: attachments_row.get(key, 0) for key in attachment_keys}),
    ]
    if discovery_row:
        parts.append(
            "发现遍历{}：未完成入口 {} 个".format(
                "完整" if discovery_row.get("complete", True) else "未完整",
                discovery_row.get("incomplete_runs", 0),
            )
        )
    if "pending_total" in coverage:
        parts.append(f"待处理合计={coverage.get('pending_total', 0)}")
    print("覆盖：" + "；".join(parts))


def _print_budget_line(budget) -> None:
    if not budget:
        print("预算：未设置请求数/截止时间上限（参数见 --max-requests、--deadline-seconds）")
        return
    limits = []
    if budget.get("max_requests") is not None:
        limits.append(f"请求上限={budget['max_requests']}")
    if budget.get("deadline_seconds") is not None:
        limits.append(f"截止={budget['deadline_seconds']:.3g}s")
    print(
        "预算：" + "，".join(limits) + f"；实际请求={budget.get('used_requests', 0)} "
        f"用时={budget.get('elapsed_seconds', 0)}s"
    )


def _print_stop_line(reason, message, unprocessed) -> None:
    detail = f"停止原因：{reason}"
    if message:
        detail += f"（{message}）"
    if unprocessed is not None:
        detail += f"；未处理 {unprocessed} 项"
    print(f"{detail}；已归档成果保留，本次运行未完成（退出码 {EXIT_STOPPED}）", file=sys.stderr)


def _validate_contract(registry: SourceRegistry) -> list:
    """用来源契约校验 YAML 中的每个条目；返回值是错误描述列表。"""
    try:
        data = yaml.safe_load(registry.config_path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, UnicodeDecodeError, OSError) as exc:
        return [f"无法重读来源配置进行契约校验：{exc}"]
    entries = data.get("sources") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        return ["来源配置缺少 sources 列表，无法进行契约校验"]
    schema = load_contract("source_registry")
    problems = []
    for index, entry in enumerate(entries):
        for message in validate_instance(entry, schema, path=f"sources[{index}]"):
            problems.append(message)
    return problems


def _rate_text(rate: Optional[float]) -> str:
    if rate is None:
        return "N/A（分母为零）"
    return f"{rate:.4%}"


if __name__ == "__main__":  # pragma: no cover - 模块直接执行入口
    raise SystemExit(main())
