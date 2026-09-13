"""分块抽象与最小 dummy 实现测试（T010/T013 新增）。"""

import pytest

from crawler.normalize.segmenter import (
    BlockSegmenter,
    PreParsedSegmenter,
    SegmentRequest,
    SegmenterInputError,
    StructuralBlankLineSegmenter,
    extraction_method_for,
    segmenter_for,
)
from crawler.parser.html_parser import parse_html
from crawler.parser.parsed_page import ParsedBlock


def segments(html):
    page = parse_html(html.encode("utf-8"), "http://example.invalid/page.html")
    return [(block.block_type, block.text) for block in page.blocks]


def test_block_segmenter_is_abstract():
    with pytest.raises(TypeError):
        BlockSegmenter()  # type: ignore[abstract]


def test_structural_blank_line_segmenter_requires_dom():
    with pytest.raises(SegmenterInputError):
        StructuralBlankLineSegmenter().segment(SegmentRequest())


def test_div_blank_lines_split_residual_text():
    """div 中未被结构节点覆盖的正文按空行拆块，单个换行不拆。"""
    result = segments(
        "<html><body><main><div>第一段<br>仍在第一段<br><br>第二段</div>"
        "<div>甲\u3000\n\n\n乙</div></main></body></html>"
    )
    assert result == [
        ("paragraph", "第一段 仍在第一段"),
        ("paragraph", "第二段"),
        ("paragraph", "甲"),
        ("paragraph", "乙"),
    ]


def test_source_indentation_is_not_a_blank_line():
    """元素之间的源码缩进空白不算正文空行，正文空行仍要保留。"""
    result = segments(
        "<html><body><main>\n"
        "  <div>\n    <span>甲</span>\n\n    <span>乙</span>\n  </div>\n"
        "  <div>丙\n\n丁</div>\n"
        "</main></body></html>"
    )
    assert result == [
        ("paragraph", "甲 乙"),
        ("paragraph", "丙"),
        ("paragraph", "丁"),
    ]


def test_nested_div_is_not_double_counted():
    """嵌套 div 与父子节点不重复输出，且保持 DOM 顺序。"""
    result = segments(
        "<html><body><main><div id='outer'>外层前文"
        "<div id='inner'><p>内层段落</p></div>外层后文</div></main></body></html>"
    )
    assert result == [
        ("paragraph", "外层前文"),
        ("paragraph", "内层段落"),
        ("paragraph", "外层后文"),
    ]
    assert len(result) == len({text for _, text in result})


def test_structural_nodes_keep_dom_order_around_residual_text():
    result = segments(
        "<html><body><main><div>正文一<h2>小节</h2><p>段落</p><ul><li>要点</li></ul>"
        "<table><tr><th>年</th></tr><tr><td>2025</td></tr></table>正文二</div></main></body></html>"
    )
    assert result == [
        ("paragraph", "正文一"),
        ("heading", "小节"),
        ("paragraph", "段落"),
        ("list_item", "要点"),
        ("table", "年\n2025"),
        ("paragraph", "正文二"),
    ]


def test_table_and_list_are_not_flattened():
    page = parse_html(
        "<html><body><main><ul><li>一</li><li>二</li></ul>"
        "<table><tr><th>列</th></tr><tr><td>值</td></tr></table></main></body></html>".encode(
            "utf-8"
        ),
        "http://example.invalid/page.html",
    )
    types = [block.block_type for block in page.blocks]
    assert types == ["list_item", "list_item", "table"]
    table = page.blocks[-1]
    assert table.structured_data == {"headers": ["列"], "rows": [["值"]], "caption": None}


def test_residual_blocks_point_at_their_container():
    page = parse_html(
        "<html><body><main><div>第一块\n\n第二块</div></main></body></html>".encode("utf-8"),
        "http://example.invalid/page.html",
    )
    anchors = [block.source_anchor for block in page.blocks]
    assert all(anchor["selector"] == "main > div:nth-of-type(1)" for anchor in anchors)
    assert [anchor["chunk"] for anchor in anchors] == [0, 1]


def test_extraction_method_identifies_segmenter():
    page = parse_html(
        "<html><body><main><p>正文</p></main></body></html>".encode("utf-8"), "http://x/"
    )
    assert page.extraction_method == "bs4_lxml_dom+structural_blank_line_v1"
    segmenter = segmenter_for("html")
    assert segmenter.as_row() == {
        "name": "structural_blank_line",
        "version": "v1",
        "status": "implemented",
        "method": "structural_blank_line_v1",
    }
    assert extraction_method_for("pypdf_text", PreParsedSegmenter()) == (
        "pypdf_text+preparsed_passthrough_v1"
    )


def test_preparsed_passthrough_keeps_existing_capability():
    """已解析格式经同一接口返回，块内容与顺序不变；空文本块显式报错。"""
    blocks = (
        ParsedBlock(block_type="paragraph", text="第一段", page_no=1),
        ParsedBlock(block_type="paragraph", text="第二段", page_no=2),
    )
    assert PreParsedSegmenter().segment(SegmentRequest(blocks=blocks)) == list(blocks)
    with pytest.raises(SegmenterInputError):
        PreParsedSegmenter().segment(
            SegmentRequest(blocks=(ParsedBlock(block_type="paragraph", text="  "),))
        )
    with pytest.raises(SegmenterInputError):
        segmenter_for("unknown-format")
