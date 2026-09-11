"""文本层 PDF 解析（T011）。

按页抽取，页码从 1 开始且逐块保留；只在原件已有结构信号处生成结构：空行分隔
段落、连续的多列行构成表格。不做翻译、摘要、语义合并或按长度裁剪。页脚页码
保留为 page_note 块，不静默丢弃。加密或无法打开的 PDF 明确报错，单页抽取失败
记为 failed 页状态而不影响其他页。
"""

from __future__ import annotations

import io
import logging
import re
from typing import List, Optional, Sequence, Tuple

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from crawler.parser.parsed_page import PageStatus, ParsedBlock, ParsedPage

logger = logging.getLogger(__name__)

EXTRACTION_METHOD = "pypdf_text"
PDF_MAGIC = b"%PDF-"
COLUMN_SPLIT = re.compile(r"\s{2,}|\t+")
PAGE_NOTE_PATTERN = re.compile(
    r"^\s*(?:第\s*\d+\s*页(?:\s*/?\s*共\s*\d+\s*页)?|-\s*\d+\s*-|\d{1,4}|"
    r"page\s+\d+(?:\s+of\s+\d+)?)\s*$",
    re.IGNORECASE,
)
MIN_TABLE_COLUMNS = 2


class PdfParseError(ValueError):
    """PDF 无法打开、已加密或没有页面。"""


def is_pdf(content: bytes) -> bool:
    return content.lstrip()[: len(PDF_MAGIC)].startswith(PDF_MAGIC)


def pdf_has_text_layer(content: bytes) -> bool:
    """扫描件判定：任一页有文本层即视为文本 PDF。无法读取时按无文本处理。"""
    try:
        reader = _open_reader(content)
    except PdfParseError:
        return False
    for page in reader.pages:
        try:
            if (page.extract_text() or "").strip():
                return True
        except Exception:  # noqa: BLE001 - 单页无文本层与抽取异常同等按无文本处理
            continue
    return False


def parse_pdf(content: bytes, page_url: str = "") -> ParsedPage:
    reader = _open_reader(content)
    blocks: List[ParsedBlock] = []
    statuses: List[PageStatus] = []
    for page_no, page in enumerate(reader.pages, start=1):
        try:
            text = _page_text(page)
        except Exception as exc:  # noqa: BLE001 - 单页失败记状态，不掩盖其他页
            statuses.append(
                PageStatus(
                    page_no=page_no,
                    status="failed",
                    extraction_method=EXTRACTION_METHOD,
                    error=str(exc),
                )
            )
            continue
        page_blocks = _page_blocks(text, page_no)
        blocks.extend(page_blocks)
        statuses.append(
            PageStatus(
                page_no=page_no,
                status="ok" if page_blocks else "empty",
                line_count=len(page_blocks),
                extraction_method=EXTRACTION_METHOD,
            )
        )

    metadata_missing = ["publication_date"]
    if any(status.status != "ok" for status in statuses):
        metadata_missing.extend(
            f"pdf_page_{status.page_no}_{status.status}"
            for status in statuses
            if status.status != "ok"
        )
    title = _first_title(blocks)
    if not title:
        metadata_missing.append("title")
    full_text = "\n".join(block.text for block in blocks if block.text)
    logger.debug(
        "PDF 解析完成 url=%s pages=%d blocks=%d", page_url, len(statuses), len(blocks)
    )
    return ParsedPage(
        title=title,
        full_text=full_text,
        blocks=tuple(blocks),
        extraction_method=EXTRACTION_METHOD,
        metadata_missing=tuple(metadata_missing),
        page_status=tuple(statuses),
        page_count=len(statuses),
        canonical_url=page_url or None,
    )


def _open_reader(content: bytes) -> PdfReader:
    try:
        reader = PdfReader(io.BytesIO(content))
    except (PdfReadError, OSError, ValueError) as exc:
        raise PdfParseError(f"PDF 无法解析：{exc}") from exc
    if reader.is_encrypted:
        try:
            opened = reader.decrypt("")
        except Exception as exc:  # noqa: BLE001 - 统一转为明确的加密错误
            raise PdfParseError(f"PDF 已加密且无法用空口令打开：{exc}") from exc
        if not opened:
            raise PdfParseError("PDF 已加密，无法解析")
    if len(reader.pages) == 0:
        raise PdfParseError("PDF 没有页面")
    return reader


def _page_text(page) -> str:
    """优先 layout 抽取以保留列间距；不支持时退化为默认抽取。"""
    try:
        text = page.extract_text(extraction_mode="layout")
    except (TypeError, ValueError):
        text = page.extract_text()
    return text or ""


def _page_blocks(text: str, page_no: int) -> List[ParsedBlock]:
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    blocks: List[ParsedBlock] = []
    chunk: List[str] = []

    def flush_paragraph() -> None:
        if not chunk:
            return
        blocks.append(
            ParsedBlock(block_type="paragraph", text="\n".join(chunk), page_no=page_no)
        )
        chunk.clear()

    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            flush_paragraph()
            index += 1
            continue
        if PAGE_NOTE_PATTERN.match(line):
            flush_paragraph()
            blocks.append(ParsedBlock(block_type="page_note", text=line.strip(), page_no=page_no))
            index += 1
            continue
        rows, consumed = _table_group(lines, index)
        if rows is not None:
            flush_paragraph()
            blocks.append(_table_block(rows, page_no))
            index += consumed
            continue
        chunk.append(line.strip())
        index += 1
    flush_paragraph()
    return blocks


def _table_group(lines: Sequence[str], start: int) -> Tuple[Optional[List[List[str]]], int]:
    """连续同列数（≥2 列）的行构成表格；否则不是表格。"""
    rows: List[List[str]] = []
    index = start
    column_count: Optional[int] = None
    while index < len(lines):
        cells = _split_columns(lines[index])
        if cells is None:
            break
        if column_count is None:
            column_count = len(cells)
        elif len(cells) != column_count:
            break
        rows.append(cells)
        index += 1
    if len(rows) < 2:
        return None, 0
    return rows, index - start


def _split_columns(line: str) -> Optional[List[str]]:
    stripped = line.strip()
    if not stripped:
        return None
    cells = [cell.strip() for cell in COLUMN_SPLIT.split(stripped)]
    if len(cells) < MIN_TABLE_COLUMNS or not all(cells):
        return None
    return cells


def _table_block(rows: List[List[str]], page_no: int) -> ParsedBlock:
    headers = rows[0]
    data_rows = rows[1:]
    table_text = "\n".join("\t".join(row) for row in rows)
    return ParsedBlock(
        block_type="table",
        text=table_text,
        page_no=page_no,
        structured_data={
            "headers": headers,
            "rows": data_rows,
            "column_count": len(headers),
            "caption": None,
        },
    )


def _first_title(blocks: Sequence[ParsedBlock]) -> str:
    for block in blocks:
        if block.block_type == "paragraph" and block.page_no == 1 and block.text:
            return block.text.split("\n", 1)[0].strip()
    return ""
