"""按格式解析原件。"""

from crawler.parser.html_parser import ParsedBlock, ParsedPage, parse_html
from crawler.parser.api_parser import ApiParseError, parse_json, parse_xml
from crawler.parser.dispatcher import (
    UnsupportedFormatError,
    detect_format,
    parse_attachment,
)
from crawler.parser.docx_parser import DocxParseError, parse_docx
from crawler.parser.legacy_parser import (
    LegacyFormatError,
    find_soffice,
    is_legacy_office,
    parse_legacy,
)
from crawler.parser.ocr_parser import (
    OcrError,
    parse_image,
    parse_scan,
    parse_scanned_pdf,
)
from crawler.parser.pdf_parser import (
    PdfParseError,
    is_pdf,
    parse_pdf,
    pdf_has_text_layer,
)
from crawler.parser.tabular_parser import CsvParseError, parse_csv
from crawler.parser.xlsx_parser import XlsxParseError, parse_xlsx

__all__ = [
    "ApiParseError",
    "CsvParseError",
    "DocxParseError",
    "LegacyFormatError",
    "OcrError",
    "ParsedBlock",
    "ParsedPage",
    "PdfParseError",
    "UnsupportedFormatError",
    "XlsxParseError",
    "detect_format",
    "find_soffice",
    "is_legacy_office",
    "is_pdf",
    "parse_attachment",
    "parse_csv",
    "parse_docx",
    "parse_html",
    "parse_image",
    "parse_json",
    "parse_legacy",
    "parse_pdf",
    "parse_scan",
    "parse_scanned_pdf",
    "parse_xlsx",
    "parse_xml",
    "pdf_has_text_layer",
]
