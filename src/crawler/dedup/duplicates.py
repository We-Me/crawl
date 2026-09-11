"""精确与近似重复识别（T014）。

精确重复按同一个原件字节哈希（sha256）或同一个规范化全文哈希（content_hash）
分组；近似重复按调用方显式给出的阈值分组。分组只是候选与证据，不删除、不合并、
不改写任何文档：同一内容的多个来源全部保留各自抓取身份（Q05 候选）。

近似阈值属 Q11 待决项，本模块不提供默认值：未显式给出阈值时拒绝执行近似判定，
避免用未决策阈值自动判定通过。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Iterable, List, Mapping, Optional, Sequence, Tuple

from crawler.dedup.fingerprint import document_fingerprint, text_similarity

logger = logging.getLogger(__name__)

EXACT_BYTES = "exact_bytes"
EXACT_TEXT = "exact_text"
NEAR_TEXT = "near_text"


class DuplicateConfigError(ValueError):
    """缺少必要的去重配置（如未决阈值）。"""


@dataclass(frozen=True)
class DuplicateGroup:
    kind: str
    key: str
    members: Tuple[dict, ...]
    similarity: Optional[float] = None

    def as_row(self) -> dict:
        row = {
            "kind": self.kind,
            "key": self.key,
            "member_count": len(self.members),
            "members": [member["doc_id"] for member in self.members],
        }
        if self.similarity is not None:
            row["similarity"] = round(self.similarity, 6)
        return row


def find_exact_duplicates(documents: Sequence[Mapping]) -> List[DuplicateGroup]:
    """按 sha256 与 content_hash 分组；只返回成员≥2 的组，来源全部保留。"""
    groups: List[DuplicateGroup] = []
    for kind, key_name in ((EXACT_BYTES, "sha256"), (EXACT_TEXT, "content_hash")):
        buckets: dict = {}
        for document in documents:
            fingerprint = document_fingerprint(document)
            key = fingerprint.get(key_name)
            if not key:
                continue
            buckets.setdefault(key, []).append(fingerprint)
        for key, members in buckets.items():
            if len(members) >= 2:
                groups.append(DuplicateGroup(kind=kind, key=key, members=tuple(members)))
    logger.debug("精确重复组数=%d", len(groups))
    return groups


def find_near_duplicates(
    documents: Sequence[Mapping],
    *,
    threshold: Optional[float],
    similarity=None,
) -> List[DuplicateGroup]:
    """按显式阈值对折叠全文做近似分组；threshold 未给出时抛错（Q11 未决）。"""
    if threshold is None:
        raise DuplicateConfigError("近似重复阈值未决定（Q11），必须显式提供 threshold")
    if not 0 < threshold <= 1:
        raise DuplicateConfigError(f"threshold 必须在 (0, 1]：{threshold!r}")
    similarity = similarity or text_similarity
    items = list(documents)
    parent = list(range(len(items)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[max(left_root, right_root)] = min(left_root, right_root)

    for left in range(len(items)):
        for right in range(left + 1, len(items)):
            score = similarity(items[left].get("full_text"), items[right].get("full_text"))
            if score >= threshold:
                union(left, right)
    buckets: dict = {}
    for index in range(len(items)):
        buckets.setdefault(find(index), []).append(index)
    groups: List[DuplicateGroup] = []
    for root, indexes in sorted(buckets.items()):
        if len(indexes) < 2:
            continue
        scores = [
            similarity(items[left].get("full_text"), items[right].get("full_text"))
            for position, left in enumerate(indexes)
            for right in indexes[position + 1:]
        ]
        groups.append(
            DuplicateGroup(
                kind=NEAR_TEXT,
                key=f"similarity>={threshold}",
                members=tuple(document_fingerprint(items[index]) for index in indexes),
                similarity=min(scores) if scores else None,
            )
        )
        for member in groups[-1].members:
            logger.info(
                "近似重复候选（需评审，不自动合并）doc_id=%s threshold=%s",
                member["doc_id"],
                threshold,
            )
    return groups


def group_row_counts(groups: Iterable[DuplicateGroup]) -> dict:
    """统计各类型组数，供运行计数与证据记录使用。"""
    counts: dict = {}
    for group in groups:
        counts[group.kind] = counts.get(group.kind, 0) + 1
    return counts
