"""T008 HTML 提取测试。"""

from pathlib import Path

from crawler.parser.html_parser import decode_html, parse_html
from crawler.normalize.block_schema import build_blocks

SITE = Path(__file__).resolve().parent / "fixtures" / "site"


def parse_fixture(name="detail_1.html"):
    content = (SITE / name).read_bytes()
    return parse_html(content, f"http://127.0.0.1/{name}")


def test_blocks_follow_document_order_and_structure():
    page = parse_fixture()
    types = [(block.block_type, block.heading_level) for block in page.blocks]
    assert types[:6] == [
        ("heading", 1),
        ("paragraph", None),
        ("heading", 2),
        ("paragraph", None),
        ("paragraph", None),
        ("heading", 2),
    ]
    assert [block.text for block in page.blocks[6:8]] == [
        "要点一：保持原文结构。",
        "要点二：不翻译、不改写事实。",
    ]
    assert page.blocks[6].block_type == "list_item"
    table = next(block for block in page.blocks if block.block_type == "table")
    assert table.structured_data["headers"] == ["年份", "数值"]
    assert table.structured_data["rows"] == [["2025", "12"]]
    assert table.text == "年份\t数值\n2025\t12"


def test_title_metadata_and_missing_fields():
    page = parse_fixture()
    assert page.title == "虚构公告：试验合作安排"
    assert page.publication_date == "2026-09-10"
    assert page.raw_date_text == "2026-09-10"
    assert page.language_hint == "zh-CN"
    assert page.metadata_missing == ()
    assert "虚构公告" in page.full_text
    assert "页脚" not in page.full_text
    assert "返回列表" not in page.full_text


def test_anchors_point_into_main_scope():
    page = parse_fixture()
    heading = page.blocks[2]
    assert heading.source_anchor == {"selector": "main > h2:nth-of-type(1)"}
    table = next(block for block in page.blocks if block.block_type == "table")
    assert table.source_anchor["selector"].startswith("main > table:nth-of-type(")


def test_missing_title_is_reported():
    page = parse_html(b"<html><body><main><p>only body</p></main></body></html>", "http://x/")
    assert page.title == ""
    assert "title" in page.metadata_missing
    assert page.blocks[0].block_type == "paragraph"


def test_empty_headings_are_skipped_and_do_not_blank_the_title():
    """真实站点（CN-04）出现过内容为空的装饰性 h2：解析阶段不产出空块，标题取首个非空标题。"""
    html = (
        "<html><body><main>"
        "<h2></h2><h2>   </h2><h2><img src='icon.png' alt=''></h2>"
        "<h2>真实标题</h2><p>正文</p>"
        "</main></body></html>"
    ).encode("utf-8")
    page = parse_html(html, "http://x/")
    assert page.title == "真实标题"
    assert [(block.block_type, block.text) for block in page.blocks] == [
        ("heading", "真实标题"),
        ("paragraph", "正文"),
    ]
    blocks = build_blocks(
        doc_id="T", parsed_blocks=page.blocks, extraction_method=page.extraction_method
    )
    assert [block["text"] for block in blocks] == ["真实标题", "正文"]


def test_decode_html_honours_meta_charset():
    content = "标题：虚构公告".encode("gbk")
    html = b"<html><head><meta charset=\"gbk\"></head><body><p>" + content + b"</p></body></html>"
    assert "标题：虚构公告" in decode_html(html)


def test_table_only_page_has_structured_rows():
    page = parse_fixture("detail_2.html")
    table = next(block for block in page.blocks if block.block_type == "table")
    assert table.structured_data["caption"] == "虚构年度统计"
    assert table.structured_data["rows"] == [["2024", "甲", "3"], ["2025", "乙", "12"]]


def test_expandable_content_is_extracted_without_scripting():
    page = parse_fixture("expandable_page.html")
    texts = [block.text for block in page.blocks]
    assert "正文第一部分：始终可见。" in texts
    assert "展开后的正文第二部分：脚本不执行也可从 DOM 抽取。" in texts
    assert all("无脚本提示" not in text for text in texts)


def test_body_pagination_link_is_reported_and_control_excluded():
    page = parse_fixture("detail_paged_1.html")
    assert page.next_page_url == "http://127.0.0.1/detail_paged_2.html"
    assert all("下一页" not in block.text for block in page.blocks)
    assert [block.text for block in page.blocks] == [
        "虚构长文：试验合作安排",
        "正文第一部分：背景与目标。本文件是离线开发夹具，内容为虚构文本。",
    ]


def test_last_pagination_page_has_no_next_link():
    assert parse_fixture("detail_paged_3.html").next_page_url is None


def test_head_rel_next_is_not_treated_as_body_pagination():
    """站外“下一篇”推荐（head 里的 rel=next）不进入正文分页还原。"""
    page = parse_html(
        '<html><head><link rel="next" href="other.html"></head>'
        "<body><main><p>正文</p></main></body></html>".encode("utf-8"),
        "http://x/",
    )
    assert page.next_page_url is None


def test_body_api_endpoint_is_reported():
    page = parse_fixture("api_body_page.html")
    assert page.body_api_url == "http://127.0.0.1/api_body.json"
    assert page.next_page_url is None


def test_body_api_requires_json_alternate():
    page = parse_html(
        '<html><head><link rel="alternate" type="application/rss+xml" href="feed.xml">'
        "</head><body><main><p>正文</p></main></body></html>".encode("utf-8"),
        "http://x/",
    )
    assert page.body_api_url is None


def test_content_selector_limits_scope_and_records_method():
    """T026：逐来源正文选择器命中时只抽取该范围，并记录抽取方式。"""
    content = (SITE / "detail_adapter.html").read_bytes()
    page = parse_html(content, "http://127.0.0.1/detail_adapter.html", content_selector="div.article-body")
    assert page.content_selector_missed is False
    assert page.extraction_method == "bs4_lxml_selector"
    assert page.title == "虚构适配样本：正文与噪声"
    assert [block.text for block in page.blocks] == [
        "虚构适配样本：正文与噪声",
        "只有正文范围的内容应进入块序列。",
        "一、范围",
        "选择器命中时抽取方式记为 bs4_lxml_selector。",
    ]
    assert "分享" not in page.full_text and "相关阅读" not in page.full_text


def test_content_selector_miss_is_reported_not_hidden():
    """选择器未命中：保留标记，通用范围仅作降级结果，不静默当作命中。"""
    content = (SITE / "detail_adapter.html").read_bytes()
    page = parse_html(content, "http://127.0.0.1/detail_adapter.html", content_selector="div.absent")
    assert page.content_selector_missed is True
    assert page.extraction_method == "bs4_lxml_dom"
    assert "相关阅读" in page.full_text  # 降级结果包含相关阅读噪声，因此必须由调用方按失败处理


def test_content_selector_excludes_related_reading_and_keeps_outer_title():
    """NEXT-07：正文容器外的标题仍要提取；相关阅读与工具栏不进入正文。"""
    content = (SITE / "detail_selector_title.html").read_bytes()
    page = parse_html(
        content,
        "http://127.0.0.1/detail_selector_title.html",
        content_selector="#detailContent",
    )
    assert page.content_selector_missed is False
    assert page.extraction_method == "bs4_lxml_selector"
    # 标题在容器之外：按文档范围回退，不退化成带站点后缀的 <title>
    assert page.title == "虚构新闻：标题在正文容器之外"
    assert [block.text for block in page.blocks] == [
        "正文第一段：只保留正文范围内的内容。",
        "正文第二段：容器之外的栏目链接与工具栏不进入正文。",
    ]
    for noise in ("相关阅读", "新闻链接", "责任编辑", "页脚"):
        assert noise not in page.full_text
