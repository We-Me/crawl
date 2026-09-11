"""T012：DOCX/XLSX/CSV/JSON/XML 结构保留、旧式格式路线与格式分派。"""

import json
from pathlib import Path

import pytest

from crawler.parser import (
    ApiParseError,
    CsvParseError,
    LegacyFormatError,
    UnsupportedFormatError,
    detect_format,
    find_soffice,
    is_legacy_office,
    parse_attachment,
    parse_csv,
    parse_docx,
    parse_json,
    parse_legacy,
    parse_xlsx,
    parse_xml,
)
from crawler.parser.pdf_parser import parse_pdf

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
DOCX = FIXTURES / "office" / "notice.docx"
XLSX = FIXTURES / "office" / "notice.xlsx"
CSV = FIXTURES / "attachments" / "notice.csv"

OLE2_HEADER = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 32


# ---------- DOCX ----------


def test_docx_keeps_heading_list_and_table_order():
    parsed = parse_docx(DOCX.read_bytes(), "https://example.invalid/notice.docx")
    assert parsed.extraction_method == "python_docx"
    types = [block.block_type for block in parsed.blocks]
    assert types[:4] == ["heading", "paragraph", "heading", "list_item"]
    headings = [block for block in parsed.blocks if block.block_type == "heading"]
    assert [(block.heading_level, block.text) for block in headings] == [
        (1, "Fixture Notice - Office Formats"),
        (2, "Scope"),
    ]
    tables = [block for block in parsed.blocks if block.block_type == "table"]
    assert tables[0].structured_data["headers"] == ["Item", "Quantity", "Amount"]
    assert tables[0].structured_data["rows"] == [
        ["Widgets", "12", "340.00"],
        ["Gadgets", "3", "125.50"],
    ]
    assert parsed.title == "Fixture Notice - Office Formats"
    assert "publication_date" in parsed.metadata_missing


def test_docx_invalid_content_raises():
    with pytest.raises(Exception):
        parse_docx(b"not a docx")


# ---------- XLSX ----------


def test_xlsx_sheets_rows_units_and_empty_sheet():
    parsed = parse_xlsx(XLSX.read_bytes(), "https://example.invalid/notice.xlsx")
    assert parsed.extraction_method == "openpyxl_read_only"
    assert parsed.page_count == 3
    assert [(status.page_no, status.status) for status in parsed.page_status] == [
        (1, "ok"),
        (2, "ok"),
        (3, "empty"),
    ]
    assert "sheet_3_empty" in parsed.metadata_missing
    tables = [block for block in parsed.blocks if block.block_type == "table"]
    assert [block.structured_data["sheet"] for block in tables] == ["Summary", "Notes"]
    summary = tables[0]
    assert summary.page_no == 1
    assert summary.structured_data["headers"] == [
        "Item",
        "Quantity（单位：件）",
        "Amount（单位：元）",
    ]
    assert summary.structured_data["rows"] == [["Widgets", "12", "340"], ["Gadgets", "3", "125.5"]]
    assert summary.structured_data["row_numbers"] == [2, 3]
    assert summary.structured_data["units"] == {
        "Quantity（单位：件）": "件",
        "Amount（单位：元）": "元",
    }


# ---------- CSV ----------


def test_csv_headers_rows_and_row_numbers():
    parsed = parse_csv(CSV.read_bytes(), "https://example.invalid/notice.csv")
    assert parsed.extraction_method == "csv_stdlib"
    table = parsed.blocks[0]
    assert table.structured_data["headers"] == ["年份", "数值"]
    assert table.structured_data["rows"] == [["2025", "12"]]
    assert table.structured_data["row_numbers"] == [2]
    assert table.structured_data["encoding"] == "utf-8"
    assert table.structured_data["delimiter"] == ","


def test_csv_decodes_gbk_and_detects_semicolon():
    content = "名称;数值\n甲;1\n".encode("gbk")
    parsed = parse_csv(content)
    table = parsed.blocks[0]
    assert table.structured_data["encoding"] == "gbk"
    assert table.structured_data["delimiter"] == ";"
    assert table.structured_data["headers"] == ["名称", "数值"]


def test_csv_reports_utf8_bom_explicitly():
    parsed = parse_csv("\ufeff名称,数值\n甲,1\n".encode("utf-8"))
    assert parsed.blocks[0].structured_data["encoding"] == "utf-8-sig"
    assert parsed.blocks[0].structured_data["headers"] == ["名称", "数值"]


def test_csv_empty_content_raises():
    with pytest.raises(CsvParseError):
        parse_csv(b"\n\n")


# ---------- JSON/XML ----------


def test_json_list_keeps_records_and_paths():
    payload = [
        {"title": "记录一", "page": 1, "next": None},
        {"title": "记录二", "page": 2, "next": "https://example.invalid/api?page=3"},
    ]
    parsed = parse_json(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    assert parsed.extraction_method == "json_stdlib"
    assert [block.structured_data["json_path"] for block in parsed.blocks] == ["$[0]", "$[1]"]
    assert parsed.blocks[0].structured_data["value_type"] == "dict"
    assert "记录一" in parsed.blocks[0].text
    assert '"page": 1' in parsed.blocks[0].text


def test_json_object_keeps_fields_and_title():
    payload = {"title": "接口样例", "page": 1, "total": 2, "items": [1, 2]}
    parsed = parse_json(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    assert parsed.title == "接口样例"
    paths = [block.structured_data["json_path"] for block in parsed.blocks]
    assert paths == ["$.title", "$.page", "$.total", "$.items"]
    assert parsed.blocks[1].text == "1" and parsed.blocks[3].text == "[1, 2]"


def test_json_invalid_raises():
    with pytest.raises(ApiParseError):
        parse_json(b"{not json}")


def test_xml_keeps_paths_attributes_and_fields():
    content = (
        b"<notice><item id=\"1\"><name>Alpha</name><qty>2</qty></item>"
        b"<item id=\"2\"><name>Beta</name><qty>7</qty></item></notice>"
    )
    parsed = parse_xml(content, "https://example.invalid/api.xml")
    assert parsed.extraction_method == "defusedxml_etree"
    assert len(parsed.blocks) == 2
    first = parsed.blocks[0]
    assert first.structured_data["xml_path"] == "/notice/item[1]"
    assert first.structured_data["attributes"] == {"id": "1"}
    assert first.structured_data["fields"] == {"name": "Alpha", "qty": "2"}
    assert first.text == "Alpha 2"
    assert parsed.canonical_url == "https://example.invalid/api.xml"


def test_xml_defused_entities_are_rejected():
    bomb = (
        b"<?xml version=\"1.0\"?>"
        b"<!DOCTYPE lolz [<!ENTITY lol \"lol\">"
        b"<!ENTITY lol2 \"&lol;&lol;&lol;&lol;&lol;\">]>"
        b"<lolz>&lol2;</lolz>"
    )
    with pytest.raises(ApiParseError):
        parse_xml(bomb)


# ---------- 旧式 DOC/XLS 路线 ----------


def test_legacy_detection_and_route_requires_converter():
    assert is_legacy_office(OLE2_HEADER) is True
    assert is_legacy_office(b"PK\x03\x04") is False
    with pytest.raises(LegacyFormatError, match="LibreOffice"):
        parse_legacy(OLE2_HEADER, "old.doc")
    with pytest.raises(LegacyFormatError):
        parse_legacy(b"not ole2", "old.doc")


def test_legacy_route_delegates_to_docx_parser_with_converter():
    converted = DOCX.read_bytes()

    def converter(content, extension):
        assert content == OLE2_HEADER and extension == ".doc"
        return converted, ".docx"

    parsed = parse_legacy(OLE2_HEADER, "old.doc", converter=converter)
    assert parsed.extraction_method == "python_docx"
    assert parsed.title == "Fixture Notice - Office Formats"
    assert find_soffice() is None or Path(find_soffice()).is_file()


# ---------- 分派 ----------


@pytest.mark.parametrize(
    "filename,content,expected",
    [
        ("notice.pdf", b"%PDF-1.4", "pdf"),
        ("notice.docx", DOCX.read_bytes(), "docx"),
        ("notice.xlsx", XLSX.read_bytes(), "xlsx"),
        ("notice.csv", CSV.read_bytes(), "csv"),
        ("data.json", b"{}", "json"),
        ("news.xml", b"<rss/>", "xml"),
        ("old.doc", OLE2_HEADER, "legacy_office"),
        ("photo.png", b"\x89PNG\r\n\x1a\n", None),
    ],
)
def test_detect_format(filename, content, expected):
    assert detect_format(content, filename) == expected


def test_parse_attachment_dispatches_by_content_and_extension():
    assert parse_attachment(DOCX.read_bytes(), "notice.docx").extraction_method == "python_docx"
    with pytest.raises(UnsupportedFormatError):
        parse_attachment(b"\x89PNG\r\n\x1a\n", "photo.png")
    with pytest.raises(UnsupportedFormatError):
        parse_attachment(b"", "")
    with pytest.raises(UnsupportedFormatError):
        parse_attachment(b"{}", "copy.dat")
    parsed = parse_attachment(CSV.read_bytes(), "notice.csv")
    assert parsed.extraction_method == "csv_stdlib"
    with pytest.raises(Exception):
        parse_attachment(b"%PDF-1.4", "notice.pdf")


def test_dispatcher_and_pdf_parser_agree_on_pdf():
    pdf_bytes = (FIXTURES / "attachments" / "notice.pdf").read_bytes()
    assert parse_attachment(pdf_bytes, "notice.pdf").page_count == parse_pdf(pdf_bytes).page_count
