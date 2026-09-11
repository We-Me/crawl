"""端到端追溯校验（T019，NFR-001 / AT-021）。

对全部 documents 与 blocks 计算追溯率：文档必须能经由 crawl_ids 指向账本记录、再定位到
数据根内的原件并核对 sha256；块必须引用存在的文档。分母是该次交付文件的全部记录，
partial 不免除；分母为零时报 N/A，不能用空集宣称采集成功。悬挂引用逐条列出。
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Mapping, Optional

from crawler.output.layout import DeliveryLayout
from crawler.util.paths import PathSafetyError
from crawler.validate.schema import load_jsonl_rows

logger = logging.getLogger(__name__)


@dataclass
class TraceReport:
    documents_total: int = 0
    documents_traceable: int = 0
    blocks_total: int = 0
    blocks_traceable: int = 0
    problems: List[dict] = field(default_factory=list)

    @property
    def document_rate(self) -> Optional[float]:
        return _rate(self.documents_traceable, self.documents_total)

    @property
    def block_rate(self) -> Optional[float]:
        return _rate(self.blocks_traceable, self.blocks_total)

    @property
    def ok(self) -> bool:
        return not self.problems

    def as_row(self) -> dict:
        return {
            "ok": self.ok,
            "documents": {
                "total": self.documents_total,
                "traceable": self.documents_traceable,
                "rate": self.document_rate,
            },
            "blocks": {
                "total": self.blocks_total,
                "traceable": self.blocks_traceable,
                "rate": self.block_rate,
            },
            "problems": list(self.problems),
        }


def _rate(traceable: int, total: int) -> Optional[float]:
    return None if total == 0 else round(traceable / total, 6)


def trace_delivery(data_dir: Path) -> TraceReport:
    layout = DeliveryLayout(data_dir)
    report = TraceReport()
    manifest = {
        row.get("crawl_id"): row
        for row in _load_rows(layout.manifest_path, "manifests/crawl_manifest.jsonl", report)
        if row.get("crawl_id")
    }
    documents = _load_rows(layout.documents_path, "normalized/documents.jsonl", report)
    blocks = _load_rows(layout.blocks_path, "normalized/blocks.jsonl", report)
    report.documents_total = len(documents)
    report.blocks_total = len(blocks)

    traced_docs = set()
    for index, document in enumerate(documents, 1):
        doc_id = document.get("doc_id")
        problems_before = len(report.problems)
        _check_document(layout, manifest, document, index, report)
        if len(report.problems) == problems_before:
            report.documents_traceable += 1
            traced_docs.add(doc_id)
        elif doc_id:
            traced_docs.discard(doc_id)

    known_docs = {document.get("doc_id") for document in documents}
    for index, block in enumerate(blocks, 1):
        doc_id = block.get("doc_id")
        if doc_id not in known_docs:
            report.problems.append(
                {
                    "where": "normalized/blocks.jsonl",
                    "line": index,
                    "block_id": block.get("block_id"),
                    "reason": f"悬挂块：引用未知 doc_id={doc_id!r}",
                }
            )
        elif doc_id not in traced_docs:
            report.problems.append(
                {
                    "where": "normalized/blocks.jsonl",
                    "line": index,
                    "block_id": block.get("block_id"),
                    "reason": f"块所属文档不可追溯：doc_id={doc_id!r}",
                }
            )
        else:
            report.blocks_traceable += 1

    logger.info(
        "追溯校验 ok=%s documents=%s/%s blocks=%s/%s problems=%d",
        report.ok,
        report.documents_traceable,
        report.documents_total,
        report.blocks_traceable,
        report.blocks_total,
        len(report.problems),
    )
    return report


def _load_rows(path: Path, label: str, report: TraceReport) -> List[dict]:
    """读取 JSONL；语法错误按行登记为追溯问题，不中断后续检查。"""
    rows, errors = load_jsonl_rows(path, label)
    for error in errors:
        report.problems.append(
            {"where": label, "line": error["line"], "reason": error["message"]}
        )
    return [row for _, row in rows]


def _check_document(
    layout: DeliveryLayout,
    manifest: Mapping,
    document: Mapping,
    index: int,
    report: TraceReport,
) -> None:
    where = "normalized/documents.jsonl"
    doc_id = document.get("doc_id")
    crawl_ids = list(document.get("crawl_ids") or [])
    if not crawl_ids:
        report.problems.append({"where": where, "line": index, "reason": "缺少 crawl_ids 引用"})
        return
    for crawl_id in crawl_ids:
        if crawl_id not in manifest:
            report.problems.append(
                {
                    "where": where,
                    "line": index,
                    "reason": f"crawl_id 不在账本中：{crawl_id!r}",
                }
            )
    raw_path = document.get("raw_path")
    if not raw_path:
        report.problems.append({"where": where, "line": index, "reason": f"doc_id={doc_id} 缺少 raw_path"})
        return
    try:
        raw_file = layout.resolve_raw_path(raw_path)
    except PathSafetyError as exc:
        report.problems.append(
            {"where": where, "line": index, "reason": f"raw_path 越界：{exc}"}
        )
        return
    if not raw_file.is_file():
        report.problems.append(
            {"where": where, "line": index, "reason": f"原件不存在：{raw_path}"}
        )
        return
    expected = document.get("sha256")
    actual = _sha256(raw_file)
    if expected and actual != expected:
        report.problems.append(
            {
                "where": where,
                "line": index,
                "reason": f"原件哈希不一致：记录 {expected}，实际 {actual}",
            }
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
