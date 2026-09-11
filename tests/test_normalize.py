"""T009 文档与块契约构造测试。"""

import pytest

from crawler.normalize.block_schema import BlockValidationError, build_blocks
from crawler.normalize.document_schema import (
    NormalizationError,
    build_document,
    documents_and_blocks,
    validate_attachment,
)
from crawler.output.documents_writer import DocumentsWriter
from crawler.output.jsonl import read_jsonl
from crawler.parser.html_parser import ParsedBlock

CRAWL_TIME = "2026-09-11T10:00:00+08:00"


def base_document(**overrides):
    values = dict(
        doc_id="DEMO_20260911_0001",
        source_id="DEMO",
        source_name="虚构示例来源",
        source_url="https://example.invalid/detail.html",
        title="虚构公告",
        full_text="正文第一段\n正文第二段",
        language="zh",
        document_type="html_page",
        raw_path="raw/DEMO/2026-09-11/html/detail.html",
        sha256="a" * 64,
        crawl_time=CRAWL_TIME,
        extraction_method="bs4_lxml_dom",
        crawl_ids=["DEMO_20260911_0001"],
    )
    values.update(overrides)
    return build_document(**values)


def test_document_required_fields_and_status():
    document = base_document(publication_date="2026-09-10", raw_date="2026-09-10")
    assert document["parse_status"] == "ok"
    assert document["publication_date"] == "2026-09-10"
    assert document["crawl_ids"] == ["DEMO_20260911_0001"]
    assert "metadata_missing" not in document


def test_missing_title_or_text_becomes_partial():
    partial = base_document(title="", metadata_missing=["title"])
    assert partial["parse_status"] == "partial"
    assert partial["metadata_missing"] == ["title"]
    assert base_document(full_text="")["parse_status"] == "partial"


def test_attachment_validation():
    attachment = {
        "attachment_id": "ATT-1",
        "filename": "notice.csv",
        "file_type": "csv",
        "url": "https://example.invalid/attachments/notice.csv",
        "status": "downloaded",
        "raw_path": "raw/DEMO/2026-09-11/attachment/notice.csv",
        "sha256": "b" * 64,
    }
    assert validate_attachment(attachment)["status"] == "downloaded"
    with pytest.raises(NormalizationError, match="必填"):
        validate_attachment({"attachment_id": "ATT-1"})
    with pytest.raises(NormalizationError, match="状态"):
        validate_attachment({**attachment, "status": "unknown"})


def test_document_validation_rejects_empty_or_duplicate_crawl_ids():
    with pytest.raises(NormalizationError, match="crawl_ids"):
        base_document(crawl_ids=[])
    with pytest.raises(NormalizationError, match="parse_status"):
        broken = base_document()
        del broken["parse_status"]
        from crawler.normalize.document_schema import validate_document

        validate_document(broken)


def test_build_blocks_assigns_contiguous_orders_and_ids():
    parsed = [
        ParsedBlock(block_type="heading", text="标题", heading_level=1),
        ParsedBlock(block_type="paragraph", text="正文"),
        ParsedBlock(
            block_type="table",
            text="年份\t数值",
            structured_data={"headers": ["年份", "数值"], "rows": [["2025", "12"]]},
        ),
    ]
    blocks = build_blocks(
        doc_id="DEMO_20260911_0001", parsed_blocks=parsed, extraction_method="bs4_lxml_dom"
    )
    assert [block["order"] for block in blocks] == [0, 1, 2]
    assert blocks[0]["block_id"] == "DEMO_20260911_0001_B0000"
    assert blocks[0]["heading_level"] == 1
    assert blocks[2]["structured_data"]["rows"] == [["2025", "12"]]
    assert all(block["doc_id"] == "DEMO_20260911_0001" for block in blocks)


def test_block_validation_rejects_bad_orders_and_refs():
    good = build_blocks(
        doc_id="DOC",
        parsed_blocks=[ParsedBlock(block_type="paragraph", text="a")],
        extraction_method="m",
    )
    from crawler.normalize.block_schema import validate_blocks

    with pytest.raises(BlockValidationError, match="未知 doc_id"):
        validate_blocks(good, {"OTHER"})
    broken = [dict(good[0]), {**good[0], "block_id": "X", "order": 2}]
    with pytest.raises(BlockValidationError, match="连续"):
        validate_blocks(broken, {"DOC"})
    with pytest.raises(BlockValidationError, match="缺少 text"):
        validate_blocks(
            [{**good[0], "block_id": "Y", "block_type": "paragraph", "text": ""}], {"DOC"}
        )


def test_documents_and_blocks_cross_validation():
    document = base_document()
    block = build_blocks(
        doc_id=document["doc_id"],
        parsed_blocks=[ParsedBlock(block_type="paragraph", text="正文")],
        extraction_method="bs4_lxml_dom",
    )[0]
    documents_and_blocks(documents=[document], blocks=[block])
    with pytest.raises(NormalizationError, match="未知 doc_id"):
        documents_and_blocks(
            documents=[document], blocks=[{**block, "block_id": "B2", "doc_id": "OTHER"}]
        )
    with pytest.raises(NormalizationError, match="重复"):
        documents_and_blocks(documents=[document, dict(document)], blocks=[block])


def test_documents_writer_commits_validated_batch(tmp_path):
    document = base_document()
    blocks = build_blocks(
        doc_id=document["doc_id"],
        parsed_blocks=[
            ParsedBlock(block_type="heading", text="标题", heading_level=1),
            ParsedBlock(block_type="paragraph", text="正文"),
        ],
        extraction_method="bs4_lxml_dom",
    )
    writer = DocumentsWriter(tmp_path / "data")
    counts = writer.commit([document], blocks)
    assert counts == (1, 2)
    assert read_jsonl(writer.path) == [document]
    assert len(read_jsonl(tmp_path / "data/normalized/blocks.jsonl")) == 2

    bad_block = {**blocks[0], "order": 5}
    with pytest.raises(NormalizationError):
        writer.commit([base_document(doc_id="D2")], [bad_block])
    assert len(read_jsonl(writer.path)) == 1
