#!/usr/bin/env python3
"""真实来源受限连通性核验（开发工具，不是业务程序）。

用途：在 Q13 未决、T026 未启动前，以最小请求量核验真实来源的 robots.txt、
入口可达性、发现/获取/解析/交付写入链路是否可用。它不替代 T026 的来源核验
（至少 10 词、歧义与站点专属规则），也不读写真 .env。

默认即最小面：
- 每个来源最多 3 个请求：robots.txt、一个入口页（发现用）和至多一个发现到的目标；
- 遵守 robots.txt（HttpClient 默认开启），遇到登录/验证码/访问控制即停，不绕过；
- 速率、连接/读取超时与重试上限逐站取自来源配置（NFR-003）；
- 不下载附件、不并发、不递归；原件与账本写入统一数据根（默认 data/）。

用法：
  UV_CACHE_DIR=/tmp/crawl-uv-cache uv run --locked --no-python-downloads \\
      python tools/realsite_smoke.py --config data/dev-sources.yaml \\
      --out data/realsite-smoke.json [--source CN-01] [--max-items 1]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from crawler.config.registry import SourceRegistry
from crawler.config.settings import load_settings
from crawler.monitor.logger import close_run_logging
from crawler.pipeline import CrawlPipeline

ROOT = Path(__file__).resolve().parents[1]


class _CollectHandler(logging.Handler):
    """收集 crawler 日志行，供摘要记录 robots 判定等证据。"""

    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self.lines = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(f"{record.levelname} {record.name} {record.getMessage()}")


def _summary_line(row: dict) -> str:
    counters = row["counters"]
    status = row.get("error") or (
        f"documents={counters['documents']} resources={counters['resources']} "
        f"failures={counters['failures']} skipped={counters['skipped']} "
        f"not_modified={counters['not_modified']}"
    )
    return f"{row['source_id']:<6} {row['entry_url']:<48} {status}"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="来源注册表 YAML（本次核验专用）")
    parser.add_argument("--out", default=None, help="摘要 JSON 路径，默认写数据根")
    parser.add_argument("--source", action="append", default=[], help="只核验指定 source_id，可重复")
    parser.add_argument("--max-items", type=int, default=1, help="每个来源最多采集的目标数")
    args = parser.parse_args(argv)

    settings = load_settings()
    registry = SourceRegistry.load(Path(args.config))
    out_path = Path(args.out) if args.out else settings.data_dir / "realsite-smoke.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    handler = _CollectHandler()
    logging.getLogger("crawler").addHandler(handler)

    rows = []
    for source in registry.enabled_sources():
        if args.source and source.source_id not in args.source:
            continue
        entry_url = source.entry_urls[0] if source.entry_urls else ""
        row = {
            "source_id": source.source_id,
            "source_name": source.source_name,
            "entry_url": entry_url,
            "rate_per_second": source.request_rate_per_second,
            "max_retries": source.max_retries,
            "connect_timeout_seconds": source.connect_timeout_seconds,
            "read_timeout_seconds": source.read_timeout_seconds,
        }
        if not entry_url:
            row["error"] = "未登记 entry_urls"
            rows.append(row)
            continue
        pipeline = CrawlPipeline(registry, settings.data_dir, settings=settings)
        before = len(handler.lines)
        try:
            report = pipeline.collect(
                source.source_id,
                entry_urls=[entry_url],
                include_attachments=False,
                max_items=max(0, args.max_items),
            )
            row["counters"] = {
                "requests": report.counters.requests,
                "resources": report.counters.resources,
                "documents": report.counters.documents,
                "blocks": report.counters.blocks,
                "failures": report.counters.failures,
                "skipped": report.counters.skipped,
                "not_modified": report.counters.not_modified,
            }
            row["skipped"] = [
                {"url": item.url, "reason": item.reason} for item in report.skipped
            ]
            row["failures"] = [
                {
                    "url": item.get("url"),
                    "stage": item.get("stage"),
                    "error_type": item.get("error_type"),
                    "final_action": item.get("final_action"),
                }
                for item in report.failures
            ]
        except Exception as exc:  # 单站失败不阻断其他来源
            row["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            close_run_logging(settings.data_dir)
        row["robots_log"] = [
            line for line in handler.lines[before:] if "robots.txt" in line
        ]
        rows.append(row)
        print(_summary_line(row))

    payload = {
        "tool": "tools/realsite_smoke.py",
        "data_dir": str(settings.data_dir),
        "sources": rows,
    }
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"摘要写入 {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
