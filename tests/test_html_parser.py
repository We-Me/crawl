"""T008 HTML 提取测试。"""

from pathlib import Path

from crawler.parser.html_parser import decode_html, parse_html
from crawler.normalize.block_schema import build_blocks
from crawler.normalize.segmenter import DEFAULT_HTML_SEGMENTER, extraction_method_for

SITE = Path(__file__).resolve().parent / "fixtures" / "site"

DOM_METHOD = extraction_method_for("bs4_lxml_dom", DEFAULT_HTML_SEGMENTER)
SELECTOR_METHOD = extraction_method_for("bs4_lxml_selector", DEFAULT_HTML_SEGMENTER)


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
    assert page.extraction_method == SELECTOR_METHOD
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
    assert page.extraction_method == DOM_METHOD
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
    assert page.extraction_method == SELECTOR_METHOD
    # 标题在容器之外：按文档范围回退，不退化成带站点后缀的 <title>
    assert page.title == "虚构新闻：标题在正文容器之外"
    assert [block.text for block in page.blocks] == [
        "正文第一段：只保留正文范围内的内容。",
        "正文第二段：容器之外的栏目链接与工具栏不进入正文。",
    ]
    for noise in ("相关阅读", "新闻链接", "责任编辑", "页脚"):
        assert noise not in page.full_text


def test_date_selector_extracts_publication_date_from_element():
    """IN-06 PIB reader 页：日期在 `#PrDateTime` 元素文本中（英文缩写月份）。"""
    html = """<html lang="en"><body><main>
    <h2>Press Release</h2>
    <div id="PrDateTime" class="text-center">प्रविष्टि तिथि: 12 SEP 2026 4:08PM by PIB Delhi</div>
    <p>Release body.</p>
    </main></body></html>"""
    page = parse_html(
        html.encode("utf-8"),
        "https://example.invalid/release",
        date_selector="#PrDateTime",
    )
    assert page.publication_date == "2026-09-12"
    assert page.raw_date_text == "प्रविष्टि तिथि: 12 SEP 2026 4:08PM by PIB Delhi"


def test_date_selector_miss_falls_back_without_fabricating():
    html = """<html><body><main><h2>无日期页</h2><p>正文。</p></main></body></html>"""
    page = parse_html(
        html.encode("utf-8"),
        "https://example.invalid/release",
        date_selector="#PrDateTime",
    )
    assert page.publication_date is None
    assert page.raw_date_text is None
    assert "publication_date" in page.metadata_missing


def test_firstpublishedtime_meta_is_used_as_publication_date():
    """CN-04 政策文件页用 <meta name="firstpublishedtime">：首次发布日期即 publication_date。"""
    html = (
        '<html><head>'
        '<meta name="firstpublishedtime" content="2026-09-11-17:00:00">'
        '<meta name="lastmodifiedtime" content="2026-09-12-09:30:00">'
        "</head><body><main><p>政策正文</p></main></body></html>"
    ).encode("utf-8")
    page = parse_html(html, "https://www.gov.cn/zhengce/content/202609/content_1.htm")
    assert page.publication_date == "2026-09-11"
    assert page.raw_date_text == "2026-09-11-17:00:00"
    assert "publication_date" not in page.metadata_missing


def test_content_inside_form_is_kept_but_controls_are_dropped():
    """ASP.NET 等站点把整页包在 <form> 内（IN-10）：保留正文，只丢控件。"""
    html = (
        '<html><body><form action="./Home.aspx" method="post">'
        '<h2>Quick Access</h2><p>Administrative Boundary Database</p>'
        '<ul><li>State Maps</li></ul>'
        '<input type="text" value="Search"><select><option>选项A</option></select>'
        '<button>Go</button>'
        "</form></body></html>"
    ).encode("utf-8")
    page = parse_html(html, "https://example.invalid/Home.aspx")
    kinds = [block.block_type for block in page.blocks]
    assert kinds == ["heading", "paragraph", "list_item"]
    assert page.blocks[0].text == "Quick Access"
    assert page.blocks[1].text == "Administrative Boundary Database"
    assert "Search" not in page.full_text
    assert "选项A" not in page.full_text
    assert "Go" not in page.full_text


def test_fragment_only_next_link_is_not_body_pagination():
    """轮播/回到顶部等 rel=next 只指向本页锚点时，不得当作正文分页继续取。"""
    html = (
        '<html><body><main><p>正文一段</p>'
        '<a rel="next" href="#myCarousel">下一页</a>'
        "</main></body></html>"
    ).encode("utf-8")
    page = parse_html(html, "https://example.invalid/Home.aspx")
    assert page.next_page_url is None

    html2 = (
        '<html><body><main><p>正文一段</p>'
        '<a rel="next" href="part2.html">下一页</a>'
        "</main></body></html>"
    ).encode("utf-8")
    page2 = parse_html(html2, "https://example.invalid/a/part1.html")
    assert page2.next_page_url == "https://example.invalid/a/part2.html"


def test_adapter_pagination_selector_wins_over_rel_next_trap():
    """S5-03：配置分页选择器后只跟随适配控件，不跟随省略号 rel=next 误报（IN-02 真实形态：… → page=5）。"""
    html = (
        '<html><body><main><p>正文一段</p>'
        '<ul class="pagination">'
        '<li class="page-item"><a class="page-link" href="?page=2">2</a></li>'
        '<li class="PagedList-ellipses page-item">'
        '<a class="page-link" rel="next" href="?page=5">…</a></li>'
        '<li class="PagedList-skipToNext page-item">'
        '<a class="page-link" rel="next" href="?page=2">›</a></li>'
        '<li class="PagedList-skipToLast page-item">'
        '<a class="page-link" href="?page=433">»</a></li>'
        "</ul></main></body></html>"
    ).encode("utf-8")
    url = "https://example.invalid/list?page=1"
    selector = "ul.pagination li.PagedList-skipToNext.page-item a.page-link"

    assert parse_html(html, url).next_page_url == "https://example.invalid/list?page=5"
    assert (
        parse_html(html, url, pagination_selector=selector).next_page_url
        == "https://example.invalid/list?page=2"
    )


def test_adapter_pagination_selector_absent_is_rule_end():
    """S5-03：适配分页控件不存在即终点；即使存在通用“下一页”文本也不再跟随。"""
    html = (
        '<html><body><main><p>正文一段</p>'
        '<a href="part2.html">下一页</a>'
        "</main></body></html>"
    ).encode("utf-8")
    url = "https://example.invalid/a/part1.html"
    selector = "ul.pagination li.PagedList-skipToNext.page-item a.page-link"

    assert parse_html(html, url).next_page_url == "https://example.invalid/a/part2.html"
    assert parse_html(html, url, pagination_selector=selector).next_page_url is None


def test_adapter_pagination_selector_container_and_self_pointer():
    """S5-03：选择器命中容器时向内找链接；控件自指当前页按终点处理（CN-02 末页形态）。"""
    html = (
        '<html><body><main><p>正文一段</p>'
        '<ul class="page"><li><a href="part1.html?n=1">首页</a></li>'
        '<li><a href="part1.html?n=1">上一页</a></li>'
        '<li><a href="part2.html?n=2">下一页</a></li></ul>'
        "</main></body></html>"
    ).encode("utf-8")
    page = parse_html(
        html, "https://example.invalid/a/part1.html?n=1", pagination_selector=".page li:nth-child(3)"
    )
    assert page.next_page_url == "https://example.invalid/a/part2.html?n=2"

    last = (
        '<html><body><main><p>正文一段</p>'
        '<ul class="page"><li><a href="part1.html?n=2">首页</a></li>'
        '<li><a href="part1.html?n=1">上一页</a></li>'
        '<li><a href="part1.html?n=2">下一页</a></li></ul>'
        "</main></body></html>"
    ).encode("utf-8")
    assert (
        parse_html(
            last,
            "https://example.invalid/a/part1.html?n=2",
            pagination_selector=".page li:nth-child(3)",
        ).next_page_url
        is None
    )
