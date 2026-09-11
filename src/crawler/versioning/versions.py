"""版本判定与现行版关系（T014）。

规则：
- 同一身份首个文档为 version=1、is_current=true；
- 原件字节与规范化全文哈希都未变时判为 unchanged，不创建新版本（避免虚假版本）；
- 内容变化时创建新版本，version 递增、is_current=true，旧版通过
  related_doc_ids/revision_of 关联并保留，不覆盖、不删除；
- 精确重复（不同身份、同字节或同全文哈希）保留各自抓取身份，只记录
  duplicate_of 关系；近似重复不自动判定为重复，仅按显式阈值标记待评审；
- 不从抓取新旧推断法律有效性，也不写 effective/validity 字段。

版本号用十进制字符串（Q09 候选实现），身份与 ID 对同一次解析可复现。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Mapping, Optional, Sequence, Tuple

from crawler.dedup.fingerprint import document_fingerprint, text_similarity
from crawler.dedup.relations import build_relation
from crawler.versioning.identity import document_identity

logger = logging.getLogger(__name__)

NEW = "new"
UNCHANGED = "unchanged"
REVISION = "revision"


@dataclass(frozen=True)
class VersionDecision:
    kind: str
    identity_key: Optional[str]
    version: str
    is_current: bool
    related_doc_ids: Tuple[str, ...] = ()
    supersedes: Tuple[str, ...] = ()
    duplicate_of: Optional[str] = None
    similarity: Optional[float] = None
    requires_review: bool = False
    relations: Tuple[dict, ...] = ()

    def as_row(self) -> dict:
        row = {
            "kind": self.kind,
            "identity_key": self.identity_key,
            "version": self.version,
            "is_current": self.is_current,
            "related_doc_ids": list(self.related_doc_ids),
            "supersedes": list(self.supersedes),
            "requires_review": self.requires_review,
        }
        if self.duplicate_of:
            row["duplicate_of"] = self.duplicate_of
        if self.similarity is not None:
            row["similarity"] = round(self.similarity, 6)
        return row


def plan_version(
    document: Mapping,
    *,
    existing_documents: Sequence[Mapping] = (),
    similarity_threshold: Optional[float] = None,
) -> VersionDecision:
    identity = document_identity(document)
    fingerprint = document_fingerprint(document)
    same_identity = [
        row for row in existing_documents
        if identity is not None and document_identity(row) == identity
    ]
    current = _current_row(same_identity)
    duplicate = _exact_duplicate(fingerprint, existing_documents, exclude_doc_id=document.get("doc_id"))

    if current is None:
        decision = VersionDecision(
            kind=NEW,
            identity_key=identity,
            version="1",
            is_current=True,
        )
    elif (
        current.get("sha256")
        and current.get("sha256") == fingerprint["sha256"]
        and document_fingerprint(current)["content_hash"] == fingerprint["content_hash"]
    ):
        decision = VersionDecision(
            kind=UNCHANGED,
            identity_key=identity,
            version=str(current.get("version") or "1"),
            is_current=True,
            related_doc_ids=(str(current["doc_id"]),),
        )
    else:
        similarity = text_similarity(current.get("full_text"), document.get("full_text"))
        version = str(version_number(current) + 1)
        relations = [
            build_relation(
                "revision_of",
                str(document.get("doc_id")),
                str(current["doc_id"]),
                evidence={
                    "previous_sha256": current.get("sha256"),
                    "previous_content_hash": document_fingerprint(current)["content_hash"],
                    "new_content_hash": fingerprint["content_hash"],
                    "similarity": round(similarity, 6),
                },
            )
        ]
        requires_review = similarity_threshold is not None and similarity < similarity_threshold
        decision = VersionDecision(
            kind=REVISION,
            identity_key=identity,
            version=version,
            is_current=True,
            related_doc_ids=(str(current["doc_id"]),),
            supersedes=(str(current["doc_id"]),),
            similarity=similarity,
            requires_review=requires_review,
            relations=tuple(relations),
        )
        if requires_review:
            logger.warning(
                "修订相似度低于阈值，需人工复核（不自动合并）doc_id=%s similarity=%.4f",
                document.get("doc_id"),
                similarity,
            )

    if duplicate is not None and duplicate.get("doc_id") != document.get("doc_id"):
        relation = build_relation(
            "duplicate_of",
            str(document.get("doc_id")),
            str(duplicate["doc_id"]),
            evidence={
                "basis": "sha256" if duplicate.get("sha256") == fingerprint["sha256"] else "content_hash",
                "sha256": fingerprint["sha256"],
                "content_hash": fingerprint["content_hash"],
            },
        )
        decision = _with_duplicate(decision, relation)
    return decision


def apply_decision(document: Mapping, decision: VersionDecision) -> dict:
    """把版本判定写入文档行；保留原有字段，不写未决的有效性字段。"""
    updated = dict(document)
    updated["version"] = decision.version
    updated["is_current"] = decision.is_current
    if decision.related_doc_ids:
        related = set(updated.get("related_doc_ids") or [])
        related.update(decision.related_doc_ids)
        updated["related_doc_ids"] = sorted(related)
    if decision.duplicate_of:
        updated["duplicate_of"] = decision.duplicate_of
    if decision.relations:
        existing = list(updated.get("relations") or [])
        updated["relations"] = existing + [dict(relation) for relation in decision.relations]
    return updated


def _with_duplicate(decision: VersionDecision, relation: dict) -> VersionDecision:
    related = tuple(sorted(set(decision.related_doc_ids) | {relation["to_doc_id"]}))
    relations = tuple(relation for relation in decision.relations if relation["relation_type"] != "duplicate_of")
    return VersionDecision(
        kind=decision.kind,
        identity_key=decision.identity_key,
        version=decision.version,
        is_current=decision.is_current,
        related_doc_ids=related,
        supersedes=decision.supersedes,
        duplicate_of=relation["to_doc_id"],
        similarity=decision.similarity,
        requires_review=decision.requires_review,
        relations=relations,
    )


def _current_row(rows: Sequence[Mapping]) -> Optional[Mapping]:
    current = [row for row in rows if row.get("is_current") is not False]
    if not current:
        return None
    return max(current, key=version_number)


def version_number(row: Mapping) -> int:
    """行内版本号；缺失或非数字按 0 处理（兼容旧行）。"""
    raw = str(row.get("version") or "0")
    try:
        return int(raw)
    except ValueError:
        return 0


def _exact_duplicate(
    fingerprint: Mapping, existing_documents: Sequence[Mapping], *, exclude_doc_id: Optional[str]
) -> Optional[Mapping]:
    for row in existing_documents:
        if exclude_doc_id is not None and row.get("doc_id") == exclude_doc_id:
            continue
        if fingerprint.get("sha256") and row.get("sha256") == fingerprint.get("sha256"):
            return row
        if document_fingerprint(row)["content_hash"] == fingerprint.get("content_hash"):
            return row
    return None
