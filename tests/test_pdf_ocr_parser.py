"""T010/T011：跨格式块模型、文本 PDF 页码/表格与 OCR 状态。"""

from pathlib import Path

import pytest

from crawler.normalize.block_schema import (
    BlockValidationError,
    build_blocks,
    validate_blocks,
)
from crawler.parser.html_parser import ParsedBlock
from crawler.parser.ocr_parser import OcrError, parse_image, parse_scan, parse_scanned_pdf
from crawler.parser.pdf_parser import (
    PdfParseError,
    is_pdf,
    parse_pdf,
    pdf_has_text_layer,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
TEXT_PDF = FIXTURES / "attachments" / "notice.pdf"
SCANNED_PDF = FIXTURES / "ocr" / "scanned_notice.pdf"
SCANNED_PNG = FIXTURES / "ocr" / "scanned_notice.png"


class FakeEngine:
    """按页返回固定识别结果或抛错，用于确定性测试部分失败。"""

    def __init__(self, results):
        self.results = list(results)
        self.calls = 0

    def __call__(self, image):
        self.calls += 1
        outcome = self.results[(self.calls - 1) % len(self.results)]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome, 0.01


def _lines(*texts):
    box = [[10.0, 10.0], [200.0, 10.0], [200.0, 30.0], [10.0, 30.0]]
    return [
        (box, text, 0.9)
        for text in texts
    ]


# ---------- T010 块模型 ----------


def test_block_model_keeps_optional_locators():
    blocks = build_blocks(
        doc_id="doc1",
        extraction_method="rapidocr_onnxruntime",
        parsed_blocks=[
            ParsedBlock(
                block_type="text_line",
                text="正文",
                page_no=2,
                confidence=0.87,
                source_anchor={"page_no": 2, "bbox": [1, 2, 3, 4]},
            )
        ],
    )
    assert blocks[0]["page_no"] == 2
    assert blocks[0]["confidence"] == 0.87
    assert blocks[0]["source_anchor"] == {"page_no": 2, "bbox": [1, 2, 3, 4]}
    validate_blocks(blocks, {"doc1"})


def test_block_model_omits_absent_locators():
    blocks = build_blocks(
        doc_id="doc1",
        extraction_method="bs4_lxml_dom",
        parsed_blocks=[ParsedBlock(block_type="paragraph", text="正文")],
    )
    assert "page_no" not in blocks[0] and "confidence" not in blocks[0]


@pytest.mark.parametrize(
    "overrides,message",
    [
        ({"page_no": 0}, "page_no"),
        ({"page_no": True}, "page_no"),
        ({"confidence": 1.2}, "confidence"),
        ({"confidence": True}, "confidence"),
        ({"section_path": [""]}, "section_path"),
        ({"article_no": "  "}, "article_no"),
    ],
)
def test_block_model_rejects_invalid_locators(overrides, message):
    block = {
        "block_id": "doc1_B0000",
        "doc_id": "doc1",
        "order": 0,
        "block_type": "paragraph",
        "text": "正文",
        "extraction_method": "bs4_lxml_dom",
    }
    block.update(overrides)
    with pytest.raises(BlockValidationError, match=message):
        validate_blocks([block], {"doc1"})


def test_block_model_rejects_out_of_order_pages():
    def block(order, page_no):
        return {
            "block_id": f"doc1_B{order:04d}",
            "doc_id": "doc1",
            "order": order,
            "block_type": "paragraph",
            "text": "正文",
            "extraction_method": "pypdf_text",
            "page_no": page_no,
        }

    with pytest.raises(BlockValidationError, match="page_no"):
        validate_blocks([block(0, 2), block(1, 1)], {"doc1"})


# ---------- T011 文本 PDF ----------


def test_text_pdf_pages_and_paragraphs():
    parsed = parse_pdf(TEXT_PDF.read_bytes(), "https://example.invalid/notice.pdf")
    assert parsed.extraction_method == "pypdf_text"
    assert parsed.page_count == 2
    assert [status.status for status in parsed.page_status] == ["ok", "ok"]
    page_one = [block for block in parsed.blocks if block.page_no == 1]
    assert page_one and "Sample Notice - Public Knowledge Collection" in page_one[0].text
    assert parsed.title == "Sample Notice - Public Knowledge Collection"
    assert parsed.publication_date is None and "publication_date" in parsed.metadata_missing


def test_text_pdf_table_structure_and_page_locator():
    parsed = parse_pdf(TEXT_PDF.read_bytes())
    tables = [block for block in parsed.blocks if block.block_type == "table"]
    assert len(tables) == 1
    table = tables[0]
    assert table.page_no == 2
    assert table.structured_data["headers"] == ["Item", "Quantity", "Amount"]
    assert table.structured_data["rows"] == [["Widgets", "12", "340.00"], ["Gadgets", "3", "125.50"]]
    assert "\t" in table.text
    orders = [block["order"] for block in build_blocks(
        doc_id="d", parsed_blocks=parsed.blocks, extraction_method=parsed.extraction_method
    )]
    assert orders == list(range(len(parsed.blocks)))


def test_text_pdf_fixture_has_text_layer():
    content = TEXT_PDF.read_bytes()
    assert is_pdf(content) and pdf_has_text_layer(content) is True
    assert pdf_has_text_layer(SCANNED_PDF.read_bytes()) is False


def test_pdf_invalid_content_raises():
    with pytest.raises(PdfParseError):
        parse_pdf(b"not a pdf")
    with pytest.raises(PdfParseError):
        parse_pdf(b"%PDF-1.4\n%EOF\n")


# ---------- T011 OCR ----------


def test_scanned_image_ocr_keeps_line_confidence_and_page():
    parsed = parse_image(SCANNED_PNG.read_bytes(), "https://example.invalid/scan.png")
    assert parsed.extraction_method == "rapidocr_onnxruntime"
    assert parsed.page_count == 1
    assert parsed.page_status[0].status == "ok"
    assert parsed.page_status[0].mean_confidence and 0 < parsed.page_status[0].mean_confidence <= 1
    texts = [block.text for block in parsed.blocks]
    assert any("OCR SAMPLE 123" in text for text in texts)
    assert all(block.page_no == 1 for block in parsed.blocks)
    assert all(0 < block.confidence <= 1 for block in parsed.blocks)
    assert all(block.source_anchor["page_no"] == 1 for block in parsed.blocks)


def test_scanned_pdf_ocr_pages_and_method():
    parsed = parse_scanned_pdf(SCANNED_PDF.read_bytes(), "https://example.invalid/scan.pdf")
    assert parsed.extraction_method == "rapidocr_onnxruntime"
    assert parsed.page_count == 1
    assert parsed.page_status[0].status == "ok"
    assert all(block.page_no == 1 for block in parsed.blocks)
    assert "2026" in parsed.full_text or "OCR" in parsed.full_text


def test_parse_scan_dispatches_pdf_and_image():
    assert parse_scan(SCANNED_PDF.read_bytes()).page_count == 1
    image_parsed = parse_scan(SCANNED_PNG.read_bytes())
    assert image_parsed.page_status[0].status == "ok"


def test_ocr_partial_failure_keeps_page_status():
    engine = FakeEngine([_lines("PAGE ONE"), RuntimeError("boom")])
    parsed = parse_scanned_pdf(TEXT_PDF.read_bytes(), engine=engine)
    statuses = [(status.page_no, status.status) for status in parsed.page_status]
    assert statuses == [(1, "ok"), (2, "failed")]
    assert "ocr_page_2_failed" in parsed.metadata_missing
    assert [block.page_no for block in parsed.blocks] == [1]
    assert parsed.page_status[1].error and "boom" in parsed.page_status[1].error


def test_ocr_all_pages_failed_raises():
    engine = FakeEngine([RuntimeError("engine down")])
    with pytest.raises(OcrError, match="所有页"):
        parse_scanned_pdf(TEXT_PDF.read_bytes(), engine=engine)
    with pytest.raises(OcrError, match="第 1 页"):
        parse_image(SCANNED_PNG.read_bytes(), engine=FakeEngine([RuntimeError("down")]))


def test_ocr_empty_page_is_explicit():
    engine = FakeEngine([[]])
    parsed = parse_scanned_pdf(TEXT_PDF.read_bytes(), engine=engine)
    assert [status.status for status in parsed.page_status] == ["empty", "empty"]
    assert "ocr_page_1_empty" in parsed.metadata_missing
    assert "title" in parsed.metadata_missing
    assert parsed.full_text == "" and parsed.blocks == ()
    assert all(status.line_count == 0 for status in parsed.page_status)
