"""块契约构造与校验（T009/T010）。

order 从 0 连续递增、block_id 可复现属于候选决定（Q09），本实现采用该候选；
块只按原文结构生成，不做 token 或语义重组。
跨格式定位字段 page_no/confidence/section_path/article_no 按 contracts/block.schema.json
可选保留：存在即校验类型与范围，缺省不补造；同文档页码必须随块顺序不递减。
"""

from __future__ import annotations

from typing import Iterable, Mapping, Sequence

REQUIRED_BLOCK_FIELDS = ("block_id", "doc_id", "order", "block_type", "extraction_method")


class BlockValidationError(ValueError):
    """块记录缺失、重复或引用无效。"""


def build_blocks(
    *, doc_id: str, parsed_blocks: Iterable, extraction_method: str
) -> list:
    blocks = []
    for order, parsed in enumerate(parsed_blocks):
        block = {
            "block_id": f"{doc_id}_B{order:04d}",
            "doc_id": doc_id,
            "order": order,
            "block_type": parsed.block_type,
            "text": parsed.text,
            "extraction_method": extraction_method,
        }
        if parsed.heading_level is not None:
            block["heading_level"] = parsed.heading_level
        if parsed.structured_data is not None:
            block["structured_data"] = parsed.structured_data
        if parsed.source_anchor is not None:
            block["source_anchor"] = parsed.source_anchor
        if parsed.page_no is not None:
            block["page_no"] = parsed.page_no
        if parsed.confidence is not None:
            block["confidence"] = parsed.confidence
        if parsed.section_path is not None:
            block["section_path"] = list(parsed.section_path)
        if parsed.article_no is not None:
            block["article_no"] = parsed.article_no
        blocks.append(block)
    validate_blocks(blocks, {doc_id})
    return blocks


def validate_blocks(blocks: Sequence[Mapping], doc_ids: Iterable[str]) -> None:
    known_docs = set(doc_ids)
    seen_ids = set()
    orders: dict = {}
    page_numbers: dict = {}
    for block in blocks:
        missing = [field for field in REQUIRED_BLOCK_FIELDS if field not in block]
        if missing:
            raise BlockValidationError(f"块缺少必填字段：{missing}")
        block_id = block["block_id"]
        if block_id in seen_ids:
            raise BlockValidationError(f"block_id 重复：{block_id}")
        seen_ids.add(block_id)
        doc_id = block["doc_id"]
        if doc_id not in known_docs:
            raise BlockValidationError(f"block 引用未知 doc_id：{doc_id}")
        if block["block_type"] == "table":
            if not block.get("text") and not block.get("structured_data"):
                raise BlockValidationError(f"表格块缺少文本与结构：{block_id}")
        elif not block.get("text"):
            raise BlockValidationError(f"非表格块缺少 text：{block_id}")
        order = block["order"]
        if not isinstance(order, int) or isinstance(order, bool) or order < 0:
            raise BlockValidationError(f"order 必须是非负整数：{block_id}")
        orders.setdefault(doc_id, []).append(order)
        page_no = block.get("page_no")
        if page_no is not None:
            if not isinstance(page_no, int) or isinstance(page_no, bool) or page_no < 1:
                raise BlockValidationError(f"page_no 必须是 ≥1 的整数：{block_id}")
            page_numbers.setdefault(doc_id, []).append(page_no)
        confidence = block.get("confidence")
        if confidence is not None:
            if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
                raise BlockValidationError(f"confidence 必须是 0—1 数值：{block_id}")
            if not 0 <= float(confidence) <= 1:
                raise BlockValidationError(f"confidence 超出 0—1：{block_id}")
        section_path = block.get("section_path")
        if section_path is not None:
            if not isinstance(section_path, (list, tuple)) or not all(
                isinstance(part, str) and part.strip() for part in section_path
            ):
                raise BlockValidationError(f"section_path 必须是非空字符串数组：{block_id}")
        article_no = block.get("article_no")
        if article_no is not None and (
            not isinstance(article_no, str) or not article_no.strip()
        ):
            raise BlockValidationError(f"article_no 必须是非空字符串：{block_id}")
    for doc_id, values in orders.items():
        expected = list(range(len(values)))
        if sorted(values) != expected:
            raise BlockValidationError(f"{doc_id} 的 order 必须从 0 连续递增：{sorted(values)}")
        pages = page_numbers.get(doc_id, [])
        if pages != sorted(pages):
            raise BlockValidationError(f"{doc_id} 的 page_no 顺序必须不递减：{pages}")
