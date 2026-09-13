#!/usr/bin/env python3
"""已归档原件的离线复算（开发工具，不是业务程序；不发任何网络请求）。

用途：对 `data/raw/<source_id>/...` 中已保存的真实原件，用**当前**的按站发现
规则与分块实现重新复算，得到逐来源的发现目标数、解析块数与日期判定；用于
“优先使用已有原件离线开发”（raw-first-development.md），不替代真实站点验证。

实现方式：把本地原件包装成 `OfflineHttpClient` 的响应，交给真实
`Discoverer`/`parse_html` 代码路径处理；因此复算结果与线上运行使用同一套
选择器、边界检查与分块规则，只是不建立网络连接（robots 判定不参与复算）。

用法：
  uv run --locked --no-python-downloads python tools/offline_replay.py \
      --config src/crawler/config/sources.yaml --data-dir data \
      [--source CN-08] [--json /tmp/offline-replay.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Mapping, Optional

from crawler.config.registry import SourceRegistry
from crawler.discover.discoverer import Discoverer
from crawler.discover.strategies import (
    DiscoveryContext,
    DiscoveryRequest,
    resolve_strategy,
)
from crawler.fetch.http_client import FetchError, FetchResponse
from crawler.normalize.metadata_normalizer import normalize_page
from crawler.output.jsonl import read_jsonl
from crawler.output.layout import DeliveryLayout
from crawler.parser.html_parser import parse_html
from crawler.schedule.scope import RunScope

ROOT = Path(__file__).resolve().parents[1]


class OfflineHttpClient:
    """离线回放客户端：按 URL 返回本地原件；缺原件时明确失败，不伪造响应。"""

    def __init__(self, pages: Mapping[str, Path]) -> None:
        self.pages: Dict[str, Path] = dict(pages)
        self.request_attempts = 0
        self.budget = None
        self.offline_reads = 0

    def attach_budget(self, budget) -> None:  # 与 HttpClient 接口兼容
        self.budget = budget

    def get(
        self,
        url: str,
        *,
        source_id: Optional[str] = None,
        conditional: Optional[Mapping[str, str]] = None,
    ) -> FetchResponse:
        path = self.pages.get(url) or self.pages.get(url.rstrip("/"))
        if path is None:
            raise FetchError(f"离线回放缺少原件：{url}", url=url)
        self.offline_reads += 1
        return FetchResponse(
            requested_url=url,
            final_url=url,
            status_code=200,
            headers={"Content-Type": "text/html; charset=utf-8"},
            content=path.read_bytes(),
            redirect_chain=(),
            attempts=1,
        )


def archived_pages(data_dir: Path, source_id: str) -> Dict[str, Path]:
    """从账本读取该来源已归档的 URL → 原件路径映射（只读，不写交付）。"""
    layout = DeliveryLayout(data_dir)
    pages: Dict[str, Path] = {}
    for row in read_jsonl(layout.manifest_path):
        if row.get("source_id") != source_id:
            continue
        raw_path = row.get("raw_path")
        if not raw_path:
            continue
        file_path = layout.resolve_raw_path(raw_path)
        if file_path.is_file():
            pages.setdefault(str(row.get("final_url")), file_path)
    return pages


def replay_source(
    registry: SourceRegistry,
    data_dir: Path,
    source_id: str,
    *,
    scope: RunScope,
) -> dict:
    source = registry.get(source_id)
    pages = archived_pages(data_dir, source_id)
    if not pages:
        return {
            "source_id": source_id,
            "originals": 0,
            "status": "no_originals",
            "note": "没有已归档原件，无法离线复算",
        }
    http = OfflineHttpClient(pages)
    discoverer = Discoverer(http, registry, source, max_items=len(pages) + 5)
    context = DiscoveryContext(
        source=source, registry=registry, http=http, discoverer=discoverer, scope=scope
    )
    pages_out: List[dict] = []
    discovered_urls: set = set()
    for url, path in pages.items():
        page = parse_html(path.read_bytes(), url, content_selector=source.adapter.content_selector)
        page = normalize_page(page, language_hints=(source.language,), base_url=url)
        # 列表规则复算：只对本来源入口（含已归档栏目页）应用配置的发现规则。
        discovery_note = None
        strategy = resolve_strategy(source, "list")
        if url in set(source.entry_urls) or source.adapter.list_link_selector:
            result = strategy.discover(
                DiscoveryRequest(stage="list", entries=(url,), scope=scope), context
            )
            discovered_urls.update(target.url for target in result.targets)
            discovery_note = result.as_row()
        pages_out.append(
            {
                "url": url,
                "raw_path": str(path.resolve().relative_to(data_dir.resolve())),
                "title": page.title,
                "blocks": len(page.blocks),
                "block_types": _count_types(page.blocks),
                "publication_date": page.publication_date,
                "date_decision": scope.decide(page.publication_date).kind,
                "content_selector_missed": page.content_selector_missed,
                "extraction_method": page.extraction_method,
                "discovery": discovery_note,
            }
        )
    return {
        "source_id": source_id,
        "originals": len(pages),
        "offline_reads": http.offline_reads,
        "discovered_targets": sorted(discovered_urls),
        "pages": pages_out,
        "status": "replayed",
    }


def _count_types(blocks) -> dict:
    counts: dict = {}
    for block in blocks:
        counts[block.block_type] = counts.get(block.block_type, 0) + 1
    return dict(sorted(counts.items()))


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="已归档原件离线复算（不发网络请求）")
    parser.add_argument("--config", default=None, help="来源注册表；缺省用随包 sources.yaml")
    parser.add_argument("--data-dir", default=str(ROOT / "data"), help="数据根（默认工程 data/）")
    parser.add_argument("--source", action="append", default=[], help="只复算指定 source_id，可重复")
    parser.add_argument("--start-date", default=None, help="按该起始日期复算日期判定（YYYY-MM-DD）")
    parser.add_argument("--json", default=None, help="把结果写入该 JSON 文件")
    args = parser.parse_args(argv)

    from crawler.schedule.scope import parse_start_date

    registry = SourceRegistry.load(Path(args.config) if args.config else None)
    data_dir = Path(args.data_dir).resolve()
    scope = RunScope(start_date=parse_start_date(args.start_date))
    source_ids = args.source or [
        source.source_id for source in registry.enabled_sources()
    ]
    results = []
    for source_id in source_ids:
        results.append(replay_source(registry, data_dir, source_id, scope=scope))

    for row in results:
        if row["status"] == "no_originals":
            print(f"{row['source_id']:<6} 无已归档原件：离线复算不适用")
            continue
        print(f"{row['source_id']:<6} 原件={row['originals']} 离线读取={row['offline_reads']}")
        for page in row["pages"]:
            discovery = page["discovery"]
            detail = (
                f"  发现状态={discovery['status']} 目标={discovery['targets']}"
                if discovery
                else "  发现：(未适用)"
            )
            print(
                f"  {page['raw_path']} 标题={page['title'][:32]!r} 块={page['blocks']} "
                f"类型={page['block_types']} 发布日期={page['publication_date']} "
                f"日期判定={page['date_decision']} 抽取={page['extraction_method']}"
            )
            print(detail)
        if row["discovered_targets"]:
            for url in row["discovered_targets"]:
                print(f"  目标 {url}")
    if args.json:
        Path(args.json).write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"结果写入 {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
