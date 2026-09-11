"""按格式分派解析器（T012）。

分派依据以内容特征为先、扩展名为补充：OLE2 魔数→旧式 DOC/XLS 转换，%PDF-→
PDF（文本层）解析，OOXML/CSV/JSON/XML 按扩展名与内容判定。不支持的格式抛
UnsupportedFormatError，由调用方记录，不静默返回空文档。扫描 PDF/图片由
ocr_parser 的 parse_scan 显式调用，避免在本模块内隐式触发 OCR。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from crawler.parser.api_parser import parse_json, parse_xml
from crawler.parser.docx_parser import parse_docx
from crawler.parser.legacy_parser import LEGACY_EXTENSIONS, is_legacy_office, parse_legacy
from crawler.parser.parsed_page import ParsedPage
from crawler.parser.pdf_parser import is_pdf, parse_pdf
from crawler.parser.tabular_parser import parse_csv
from crawler.parser.xlsx_parser import parse_xlsx

logger = logging.getLogger(__name__)

OOXML_WORD_TYPES = (".docx", ".docm")
OOXML_SHEET_TYPES = (".xlsx", ".xlsm")
CSV_TYPES = (".csv", ".tsv")
JSON_TYPES = (".json",)
XML_TYPES = (".xml", ".rss", ".atom")
FORMAT_EXTENSIONS = {
    "pdf": (".pdf",),
    "docx": OOXML_WORD_TYPES,
    "xlsx": OOXML_SHEET_TYPES,
    "csv": CSV_TYPES,
    "json": JSON_TYPES,
    "xml": XML_TYPES,
    "legacy_office": LEGACY_EXTENSIONS,
}


class UnsupportedFormatError(ValueError):
    """没有可用解析器的格式。"""


def detect_format(content: bytes, filename: str = "") -> Optional[str]:
    extension = Path(filename).suffix.lower()
    if is_legacy_office(content) or extension in LEGACY_EXTENSIONS:
        return "legacy_office"
    if is_pdf(content) or extension == ".pdf":
        return "pdf"
    for name, extensions in FORMAT_EXTENSIONS.items():
        if extension in extensions:
            return name
    return None


def parse_attachment(
    content: bytes,
    filename: str,
    page_url: str = "",
    *,
    converter=None,
) -> ParsedPage:
    format_name = detect_format(content, filename)
    if format_name is None:
        raise UnsupportedFormatError(f"不支持的附件格式：{filename or '<无文件名>'}")
    if format_name == "pdf":
        return parse_pdf(content, page_url)
    if format_name == "docx":
        return parse_docx(content, page_url)
    if format_name == "xlsx":
        return parse_xlsx(content, page_url)
    if format_name == "csv":
        return parse_csv(content, page_url)
    if format_name == "json":
        return parse_json(content, page_url)
    if format_name == "xml":
        return parse_xml(content, page_url)
    return parse_legacy(content, filename, page_url, converter=converter)
