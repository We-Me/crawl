"""来源关系记录（T014）。

转载、镜像、正文附件、修订、废止与精确重复以带证据的关系行记录；关系不删除
任何文档，也不推断法律有效性。近似重复只作为待评审候选，不自动写成
duplicate_of。证据必须非空，避免无出处的合并。
"""

from __future__ import annotations

from typing import Mapping, Sequence

RELATION_TYPES = (
    "duplicate_of",
    "reprint_of",
    "mirror_of",
    "attachment_of",
    "revision_of",
    "repealed_by",
)

RELATION_FIELD = {
    "duplicate_of": "duplicate_of",
    "revision_of": "related_doc_ids",
}


class RelationError(ValueError):
    """关系类型、端点或证据不合法。"""


def build_relation(
    relation_type: str,
    from_doc_id: str,
    to_doc_id: str,
    *,
    evidence: Mapping,
) -> dict:
    if relation_type not in RELATION_TYPES:
        raise RelationError(f"未知关系类型：{relation_type!r}")
    if not from_doc_id or not to_doc_id:
        raise RelationError("关系两端都必须有 doc_id")
    if from_doc_id == to_doc_id:
        raise RelationError("关系两端不能是同一文档")
    if not evidence or not isinstance(evidence, Mapping):
        raise RelationError("关系必须带非空证据（来源、哈希或评审记录）")
    return {
        "relation_type": relation_type,
        "from_doc_id": from_doc_id,
        "to_doc_id": to_doc_id,
        "evidence": dict(evidence),
    }


def attach_relations(document: Mapping, relations: Sequence[Mapping]) -> dict:
    """把关系并入文档行：duplicate_of 用专字段，其余关系追加到 relations。"""
    updated = dict(document)
    typed = []
    for relation in relations:
        relation_type = relation.get("relation_type")
        if relation_type not in RELATION_TYPES:
            raise RelationError(f"未知关系类型：{relation_type!r}")
        if relation_type == "duplicate_of" and "duplicate_of" not in updated:
            updated["duplicate_of"] = relation["to_doc_id"]
        else:
            typed.append(dict(relation))
        related = set(updated.get("related_doc_ids") or [])
        related.add(relation["to_doc_id"])
        updated["related_doc_ids"] = sorted(related)
    if typed:
        existing = list(updated.get("relations") or [])
        updated["relations"] = existing + typed
    return updated


def relation_index(documents: Sequence[Mapping]) -> dict:
    """按 doc_id 汇总关系，来源不丢失；供交付整理与验收查询。"""
    index: dict = {}
    for document in documents:
        doc_id = document.get("doc_id")
        entries = list(document.get("relations") or [])
        if document.get("duplicate_of"):
            entries.append(
                {
                    "relation_type": "duplicate_of",
                    "to_doc_id": document["duplicate_of"],
                }
            )
        if entries:
            index[doc_id] = entries
    return index
