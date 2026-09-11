"""文档指纹与相似度（T014）。

Q04 候选：document.sha256 仍是原件字节哈希（由采集写出），content_hash 表示
规范化全文哈希，二者不互相等同。全文指纹按统一清洗后的折叠文本计算；相似度
用标准库 difflib，仅作候选分组依据，不用于自动丢弃、合并或改写任何文档。
"""

from __future__ import annotations

import difflib
import hashlib
from typing import Mapping, Optional

from crawler.normalize.text_utils import collapse_whitespace

FINGERPRINT_FIELDS = ("doc_id", "source_id", "source_url", "sha256", "content_hash")


def text_hash(full_text: Optional[str]) -> str:
    """规范化全文哈希：NFC/空白折叠后取 sha256；不改变文档内容。"""
    normalized = collapse_whitespace(full_text or "")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def text_similarity(left: Optional[str], right: Optional[str]) -> float:
    """0—1 的确定性相似度（difflib.SequenceMatcher），用于近似重复候选。"""
    left_text = collapse_whitespace(left or "")
    right_text = collapse_whitespace(right or "")
    if not left_text and not right_text:
        return 1.0
    if not left_text or not right_text:
        return 0.0
    return difflib.SequenceMatcher(None, left_text, right_text, autojunk=False).ratio()


def document_fingerprint(document: Mapping) -> dict:
    """返回指纹行；content_hash 缺失时按全文计算，不覆盖已有取值。"""
    return {
        "doc_id": document.get("doc_id"),
        "source_id": document.get("source_id"),
        "source_url": document.get("source_url"),
        "sha256": document.get("sha256"),
        "content_hash": document.get("content_hash") or text_hash(document.get("full_text")),
    }
