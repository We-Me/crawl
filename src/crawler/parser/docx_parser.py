"""DOCX 解析（T012）。

按正文顺序保留标题样式、段落、列表与表格；标题层级取自样式名（Heading N），
列表按 List 样式识别，表格首行按布局约定作为表头，文本视图与结构数据同时保留。
不翻译、不改写、不做语义合并。旧式二进制 DOC 见 legacy_parser.py。
"""

from __future__ import annotations

import io
import logging
import re
from typing import Iterable, List, Optional

from docx import Document
from docx.document import Document as DocumentType
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from crawler.parser.parsed_page import ParsedBlock, ParsedPage

logger = logging.getLogger(__name__)

EXTRACTION_METHOD = "python_docx"
HEADING_STYLE = re.compile(r"^Heading\s+(\d)$", re.IGNORECASE)
LIST_STYLE = re.compile(r"^(List|列表)", re.IGNORECASE)


class DocxParseError(ValueError):
    """DOCX 无法打开或不是有效的 Word 文档。"""


def parse_docx(content: bytes, page_url: str = "") -> ParsedPage:
    try:
        document = Document(io.BytesIO(content))
    except Exception as exc:  # noqa: BLE001 - 统一为明确的解析错误
        raise DocxParseError(f"DOCX 无法解析：{exc}") from exc

    blocks: List[ParsedBlock] = []
    for element in _iter_body(document):
        if isinstance(element, Paragraph):
            block = _paragraph_block(element)
            if block is not None:
                blocks.append(block)
        else:
            table = _table_block(element)
            if table is not None:
                blocks.append(table)

    metadata_missing = ["publication_date"]
    title = _title(document, blocks)
    if not title:
        metadata_missing.append("title")
    logger.debug("DOCX 解析完成 url=%s blocks=%d", page_url, len(blocks))
    return ParsedPage(
        title=title,
        full_text="\n".join(block.text for block in blocks if block.text),
        blocks=tuple(blocks),
        extraction_method=EXTRACTION_METHOD,
        metadata_missing=tuple(metadata_missing),
        canonical_url=page_url or None,
    )


def _iter_body(document: DocumentType) -> Iterable:
    body = document.element.body
    for child in body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, document)
        elif child.tag == qn("w:tbl"):
            yield Table(child, document)


def _paragraph_block(paragraph: Paragraph) -> Optional[ParsedBlock]:
    text = paragraph.text.strip()
    if not text:
        return None
    style_name = paragraph.style.name if paragraph.style is not None else ""
    match = HEADING_STYLE.match(style_name or "")
    if match:
        return ParsedBlock(block_type="heading", text=text, heading_level=int(match.group(1)))
    if LIST_STYLE.match(style_name or ""):
        return ParsedBlock(block_type="list_item", text=text)
    return ParsedBlock(block_type="paragraph", text=text)


def _table_block(table: Table) -> Optional[ParsedBlock]:
    rows: List[List[str]] = []
    for row in table.rows:
        values = []
        for cell in row.cells:
            values.append(" ".join(cell.text.split()))
        if any(values):
            rows.append(values)
    if not rows:
        return None
    headers = rows[0]
    data_rows = rows[1:]
    return ParsedBlock(
        block_type="table",
        text="\n".join("\t".join(row) for row in rows),
        structured_data={"headers": headers, "rows": data_rows, "caption": None},
    )


def _title(document: DocumentType, blocks: List[ParsedBlock]) -> str:
    for block in blocks:
        if block.block_type == "heading" and block.heading_level == 1:
            return block.text
    core_title = (document.core_properties.title or "").strip()
    if core_title:
        return core_title
    for block in blocks:
        if block.block_type == "paragraph":
            return block.text
    return ""
