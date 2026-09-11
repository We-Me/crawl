"""正式业务命令行入口（NEXT-01 / T027 的操作入口子项）。

命令只包装既有能力，不在这里重新实现发现、解析、归档或交付校验：

  sources   校验来源配置（语义校验 + 来源契约 schema）并列出登记来源
  collect   按来源执行一次采集
  plan      查看未关闭失败的补抓计划（只读，不请求网络）
  resume    对指定来源执行补抓
  check     校验数据根的六项成果、契约 schema 与端到端追溯

来源边界、robots 规则、限速、失败账和交付检查仍由被调用模块执行；CLI 不放宽
任何访问规则、失败处理或质量阈值。配置只经 crawler.config.settings 读取
CRAWL_ENV / CRAWL_DATA_DIR，不提供第二套路径优先级。

退出码：0 成功；1 运行完成但仍有失败或交付校验不通过；2 配置、参数或环境错误。
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
from crawler.fetch.retry import RetryConfigError, RetryPolicy, summarize_plan
from crawler.output.delivery import inspect_delivery
from crawler.pipeline import CrawlPipeline
from crawler.validate.schema import SchemaConfigError, load_contract, validate_delivery, validate_instance
from crawler.validate.traceability import trace_delivery

EXIT_OK = 0
EXIT_RUN = 1
EXIT_CONFIG = 2

PROGRAM = "crawl"


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
    collect.add_argument("--max-items", type=int, default=100, help="本次最多采集的目标数")
    collect.add_argument(
        "--no-attachments", action="store_true", help="不下载附件（仅正文页面）"
    )
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
    resume.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    resume.set_defaults(handler=_cmd_resume)

    check = subparsers.add_parser("check", parents=[common], help="校验数据根的交付成果")
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
    pipeline = CrawlPipeline(registry, settings.data_dir, settings=settings)
    report = pipeline.collect(
        source.source_id,
        entry_urls=list(args.entry_url) if args.entry_url else None,
        search_keywords=list(args.keyword),
        sitemap_urls=list(args.sitemap),
        api_urls=list(args.api),
        include_attachments=not args.no_attachments,
        max_items=args.max_items,
    )
    counters = report.counters
    row = {
        "ok": counters.failures == 0,
        "source_id": report.source_id,
        "data_dir": str(settings.data_dir),
        "counters": {
            "requests": counters.requests,
            "resources": counters.resources,
            "documents": counters.documents,
            "blocks": counters.blocks,
            "failures": counters.failures,
            "skipped": counters.skipped,
            "not_modified": counters.not_modified,
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
            f"未修改={counters.not_modified}"
        )
        print(f"数据根 {settings.data_dir}")
        for failure in report.failures:
            print(
                f"  失败 {failure.get('stage')} {failure.get('url')} "
                f"{failure.get('error_type')} {failure.get('message')}"
            )
        for item in report.skipped:
            print(f"  跳过 {item.url} {item.reason}")
        if counters.failures:
            print(f"存在 {counters.failures} 项失败，可用 {PROGRAM} resume 补抓", file=sys.stderr)
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
    pipeline = CrawlPipeline(registry, settings.data_dir, settings=settings)
    report = pipeline.resume_failures(
        args.source,
        policy=policy,
        max_tasks=args.max_tasks,
        respect_backoff=args.respect_backoff,
    )
    remaining = len(report.failures) + len(report.manual) + len(report.pending)
    row = {
        "ok": remaining == 0,
        "source_id": report.source_id,
        "data_dir": str(settings.data_dir),
        "recovered": len(report.recovered),
        "skipped": len(report.skipped),
        "manual": len(report.manual),
        "pending": len(report.pending),
        "failed": len(report.failures),
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
        for task in report.manual:
            print(f"  待人工 {task['url']} {task.get('reason', '')}")
        for task in report.pending:
            print(f"  等待退避 {task['url']} not_before={task['not_before']}")
        if remaining:
            print(f"仍有 {remaining} 项未关闭，需要人工处理或下次补抓", file=sys.stderr)
    return EXIT_RUN if remaining else EXIT_OK


def _cmd_check(args) -> int:
    settings = load_settings()
    delivery = inspect_delivery(settings.data_dir, require_nonempty=args.require_nonempty)
    schema = validate_delivery(settings.data_dir)
    trace = trace_delivery(settings.data_dir)
    ok = bool(delivery.ok and schema.ok and trace.ok)
    if args.json:
        print(
            json.dumps(
                {
                    "ok": ok,
                    "data_dir": str(settings.data_dir),
                    "delivery": delivery.as_row(),
                    "schema": schema.as_row(),
                    "trace": trace.as_row(),
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
    return EXIT_OK if ok else EXIT_RUN


# ---------- 辅助 ----------


def _load_registry(args) -> SourceRegistry:
    config = Path(args.config) if args.config else None
    return SourceRegistry.load(config)


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
