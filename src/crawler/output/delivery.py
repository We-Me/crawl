"""采集交付包检查（T018，FR-019/FR-020）。

检查六项成果是否齐全、raw_path 是否都是可定位的相对路径、数据根内是否出现
采集阶段禁止的 RAG 派生成果（chunks、向量、索引、重排、Prompt/答案等）。
只读检查，不创建、不修改任何交付内容。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from crawler.output.jsonl import read_jsonl
from crawler.output.layout import DeliveryLayout
from crawler.util.paths import PathSafetyError

logger = logging.getLogger(__name__)

# 六项成果：名称、相对位置、类型（dir / file / file_optional_if_empty）
REQUIRED_DELIVERABLES = (
    ("raw/", "raw", "dir"),
    ("manifests/crawl_manifest.jsonl", "manifests/crawl_manifest.jsonl", "file"),
    ("normalized/documents.jsonl", "normalized/documents.jsonl", "file"),
    ("normalized/blocks.jsonl", "normalized/blocks.jsonl", "file"),
    ("manifests/failed_records.jsonl", "manifests/failed_records.jsonl", "file_optional_if_empty"),
    ("logs/", "logs", "dir"),
)

# 采集阶段禁止生成的派生成果（FR-020）；命名按常见实现，包含即报告
FORBIDDEN_NAMES = frozenset(
    {
        "chunks.jsonl",
        "chunks",
        "embeddings",
        "embedding",
        "vectors",
        "vector_store",
        "vectordb",
        "faiss",
        "bm25",
        "index",
        "rerank",
        "reranker",
        "prompts",
        "prompt_store",
        "answers",
        "answer_store",
        "token_slices",
    }
)
FORBIDDEN_SUFFIXES = (".faiss", ".bm25", ".hnsw", ".ann", ".emb", ".vec")


@dataclass
class DeliveryReport:
    data_dir: str
    ok: bool = True
    present: List[dict] = field(default_factory=list)
    missing: List[str] = field(default_factory=list)
    counts: dict = field(default_factory=dict)
    forbidden: List[str] = field(default_factory=list)
    path_issues: List[dict] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def as_row(self) -> dict:
        return {
            "data_dir": self.data_dir,
            "ok": self.ok,
            "deliverables": list(self.present),
            "missing": list(self.missing),
            "counts": dict(self.counts),
            "forbidden_artifacts": list(self.forbidden),
            "path_issues": list(self.path_issues),
            "notes": list(self.notes),
        }


def inspect_delivery(data_dir: Path, *, require_nonempty: bool = False) -> DeliveryReport:
    """检查数据根是否构成完整、未越界的采集交付包。"""
    layout = DeliveryLayout(data_dir)
    report = DeliveryReport(data_dir=str(layout.data_dir))

    for name, relative, kind in REQUIRED_DELIVERABLES:
        target = layout.data_dir / relative
        if kind == "dir":
            exists = target.is_dir()
        else:
            exists = target.is_file()
        entry = {"name": name, "path": relative, "kind": kind, "present": bool(exists)}
        if kind == "file_optional_if_empty" and not exists:
            entry["present"] = True
            entry["optional"] = True
            report.notes.append("零失败：failed_records.jsonl 可为空或不存在")
        if not entry["present"]:
            report.missing.append(name)
        report.present.append(entry)

    for key, path in (
        ("manifest_rows", layout.manifest_path),
        ("document_rows", layout.documents_path),
        ("block_rows", layout.blocks_path),
        ("failure_rows", layout.failures_path),
    ):
        report.counts[key] = _count_rows(path)
    report.counts["raw_files"] = (
        sum(1 for item in layout.raw_dir.rglob("*") if item.is_file())
        if layout.raw_dir.is_dir()
        else 0
    )

    _check_manifest(layout, report)
    _check_documents(layout, report)
    report.forbidden = _find_forbidden(layout)
    if require_nonempty and report.counts["manifest_rows"] == 0:
        report.notes.append("空交付：账本没有记录，不能据此宣称采集成功")

    report.ok = not report.missing and not report.forbidden and not report.path_issues
    logger.info(
        "交付检查 ok=%s missing=%s forbidden=%s path_issues=%s",
        report.ok,
        report.missing,
        report.forbidden,
        len(report.path_issues),
    )
    return report


def _check_manifest(layout: DeliveryLayout, report: DeliveryReport) -> None:
    for index, row in enumerate(_read_rows(layout.manifest_path, report, "crawl_manifest.jsonl"), 1):
        _check_raw_path(
            layout,
            row.get("raw_path"),
            where="manifests/crawl_manifest.jsonl",
            index=index,
            report=report,
        )


def _check_documents(layout: DeliveryLayout, report: DeliveryReport) -> None:
    for index, row in enumerate(_read_rows(layout.documents_path, report, "documents.jsonl"), 1):
        _check_raw_path(
            layout,
            row.get("raw_path"),
            where="normalized/documents.jsonl",
            index=index,
            report=report,
        )
        for attachment in row.get("attachments") or []:
            if not isinstance(attachment, dict) or attachment.get("status") != "downloaded":
                continue
            _check_raw_path(
                layout,
                attachment.get("raw_path"),
                where=f"normalized/documents.jsonl#{row.get('doc_id')}",
                index=index,
                report=report,
                context=attachment.get("filename"),
            )


def _check_raw_path(
    layout: DeliveryLayout,
    raw_path: Optional[str],
    *,
    where: str,
    index: int,
    report: DeliveryReport,
    context: Optional[str] = None,
) -> None:
    issue = {"where": where, "row": index, "raw_path": raw_path}
    if context:
        issue["context"] = context
    if not raw_path:
        issue["reason"] = "缺少 raw_path，原件无法定位"
        report.path_issues.append(issue)
        return
    try:
        resolved = layout.resolve_raw_path(raw_path)
    except PathSafetyError as exc:
        issue["reason"] = f"raw_path 越界或非法：{exc}"
        report.path_issues.append(issue)
        return
    if not resolved.is_file():
        issue["reason"] = "raw_path 指向的原件不存在"
        report.path_issues.append(issue)


def _read_rows(path: Path, report: DeliveryReport, label: str) -> List[dict]:
    if not path.is_file():
        return []
    try:
        return read_jsonl(path)
    except (ValueError, UnicodeDecodeError) as exc:
        report.path_issues.append(
            {"where": label, "row": 0, "raw_path": None, "reason": f"文件不可读：{exc}"}
        )
        return []


def _count_rows(path: Path) -> int:
    if not path.is_file():
        return 0
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def _find_forbidden(layout: DeliveryLayout) -> List[str]:
    found = []
    if not layout.data_dir.is_dir():
        return found
    for item in sorted(layout.data_dir.rglob("*")):
        if item.name.lower() in FORBIDDEN_NAMES:
            found.append(item.relative_to(layout.data_dir).as_posix())
        elif item.suffix.lower() in FORBIDDEN_SUFFIXES:
            found.append(item.relative_to(layout.data_dir).as_posix())
    return found
