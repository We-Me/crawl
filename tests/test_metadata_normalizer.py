"""T013：统一清洗、日期、URL、语言与全文一致性复核。"""

from pathlib import Path

from crawler.normalize.metadata_normalizer import (
    canonical_language,
    check_text_integrity,
    clean_text,
    collapse_whitespace,
    detect_language,
    normalize_date,
    normalize_page,
    normalize_url,
)
from crawler.parser.api_parser import parse_json
from crawler.parser.docx_parser import parse_docx
from crawler.parser.html_parser import ParsedBlock, ParsedPage, parse_html
from crawler.parser.ocr_parser import parse_image
from crawler.parser.pdf_parser import parse_pdf
from crawler.parser.tabular_parser import parse_csv
from crawler.parser.xlsx_parser import parse_xlsx

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


def _page(**overrides):
    data = {
        "title": "标题",
        "full_text": "正文",
        "blocks": (ParsedBlock(block_type="paragraph", text="正文"),),
        "extraction_method": "test",
    }
    data.update(overrides)
    return ParsedPage(**data)


# ---------- 清洗 ----------


def test_clean_text_normalizes_unicode_and_controls():
    raw = "  cafe\u0301  \u00a0 \x07 hidden \u200b\r\n第二行   \n\n"
    cleaned = clean_text(raw)
    assert "\x07" not in cleaned and "\u00a0" not in cleaned and "\u200b" not in cleaned
    assert "\u00e9" in cleaned  # NFC：é 合成为单码位
    assert collapse_whitespace(cleaned) == "café hidden 第二行"
    assert cleaned.splitlines()[-1] == "第二行"


def test_collapse_whitespace_is_single_line():
    assert collapse_whitespace("  第一行 \n 第二行\t 结束 ") == "第一行 第二行 结束"


def test_clean_text_keeps_multiline_paragraphs():
    assert clean_text("第一行\n第二行") == "第一行\n第二行"


# ---------- 日期 ----------


def test_normalize_date_accepts_known_formats():
    assert normalize_date("2026-09-10") == "2026-09-10"
    assert normalize_date("2026/9/10") == "2026-09-10"
    assert normalize_date("2026年9月10日") == "2026-09-10"
    assert normalize_date("10 September 2026") == "2026-09-10"
    assert normalize_date("September 10, 2026") == "2026-09-10"
    assert normalize_date("2026-09-10T10:30:00+08:00") == "2026-09-10"


def test_normalize_date_accepts_month_abbreviations():
    """IN-06 PIB 发布日期行为 '12 SEP 2026 4:08PM by PIB Delhi'；缩写月份同样只认到日精度。"""
    assert normalize_date("12 SEP 2026 4:08PM by PIB Delhi") == "2026-09-12"
    assert normalize_date("12 Sept 2026") == "2026-09-12"
    assert normalize_date("5 Mar 2026") == "2026-03-05"
    assert normalize_date("SEP 12, 2026") == "2026-09-12"
    assert normalize_date("12 Springfield 2026") is None


def test_normalize_date_does_not_fabricate():
    assert normalize_date("2026-02-30") is None
    assert normalize_date("2026年9月") is None
    assert normalize_date("近期") is None
    assert normalize_date("") is None
    assert normalize_date(None) is None


# ---------- URL ----------


def test_normalize_url_rules():
    assert normalize_url("HTTPS://Example.INVALID:443/a/b?x=1#part") == "https://example.invalid/a/b?x=1"
    assert normalize_url("http://example.invalid:80/") == "http://example.invalid/"
    assert normalize_url("/notice/1?p=2#top", base_url="https://example.invalid/list/") == (
        "https://example.invalid/notice/1?p=2"
    )
    assert normalize_url("ftp://example.invalid/x") is None
    assert normalize_url("not a url") is None
    assert normalize_url(None) is None


# ---------- 语言 ----------


def test_canonical_language_tag():
    assert canonical_language("zh-CN") == "zh"
    assert canonical_language("EN_us") == "en"
    assert canonical_language("und") == "und"
    assert canonical_language("不是语言标记") is None


def test_detect_language_prefers_hints_and_script_rules():
    assert detect_language("plain latin text", ["zh-CN"]) == "zh"
    assert detect_language("यह एक परीक्षण दस्तावेज़ है।") == "hi"
    assert detect_language("यह दस्तावेज़ है।", ["mr"]) == "mr"  # 显式标记优先于天城文推断
    assert detect_language("本办法适用于虚构示例场景，字段说明如下。") == "zh"
    assert detect_language("これはふりがなのテストです。") == "ja"
    assert detect_language("한국어 테스트 문서입니다.") == "ko"
    assert detect_language("Это тестовый документ.") == "ru"
    assert detect_language("plain latin text only") == "und"
    assert canonical_language("hi-IN") == "hi"
    assert detect_language("", []) == "und"


# ---------- 全文一致性 ----------


def test_check_text_integrity_passes_for_consistent_page():
    assert check_text_integrity(_page()) == []


def test_check_text_integrity_detects_problems():
    inconsistent = _page(full_text="完全不同", blocks=(ParsedBlock(block_type="paragraph", text="正文"),))
    assert any("full_text" in issue for issue in check_text_integrity(inconsistent))
    dirty = _page(
        full_text="文本  ",
        blocks=(ParsedBlock(block_type="paragraph", text="文本  "),),
    )
    assert any("未按统一规则清洗" in issue for issue in check_text_integrity(dirty))
    out_of_order = _page(
        full_text="二\n一",
        blocks=(
            ParsedBlock(block_type="paragraph", text="二", page_no=2),
            ParsedBlock(block_type="paragraph", text="一", page_no=1),
        ),
    )
    assert any("页码顺序" in issue for issue in check_text_integrity(out_of_order))


def test_normalize_page_unifies_fields_without_fabrication():
    page = _page(
        title="标题 ",
        raw_date_text="发布日期：2026年9月10日",
        metadata_missing=("publication_date",),
        blocks=(ParsedBlock(block_type="paragraph", text="正文  "),),
        full_text="正文  ",
        canonical_url="HTTP://Example.INVALID:80/a#frag",
    )
    normalized = normalize_page(page, language_hints=("zh-CN",), base_url="https://example.invalid/")
    assert normalized.title == "标题"
    assert normalized.blocks[0].text == "正文"
    assert normalized.publication_date == "2026-09-10"
    assert "publication_date" not in normalized.metadata_missing
    assert normalized.language_hint == "zh"
    assert normalized.canonical_url == "http://example.invalid/a"
    assert page.raw_date_text == "发布日期：2026年9月10日"

    undated = _page(raw_date_text="近期", metadata_missing=("publication_date",))
    kept = normalize_page(undated)
    assert kept.publication_date is None
    assert kept.raw_date_text == "近期"
    assert "publication_date" in kept.metadata_missing


# ---------- 各解析器全文一致性复核 ----------


def test_all_parsers_keep_full_text_consistent():
    pages = [
        parse_html((FIXTURES / "html" / "detail_page.html").read_bytes(), "https://example.invalid/d.html"),
        parse_pdf((FIXTURES / "attachments" / "notice.pdf").read_bytes()),
        parse_csv((FIXTURES / "attachments" / "notice.csv").read_bytes()),
        parse_docx((FIXTURES / "office" / "notice.docx").read_bytes()),
        parse_xlsx((FIXTURES / "office" / "notice.xlsx").read_bytes()),
        parse_json(b'{"title": "x", "items": [1, 2]}'),
        parse_image((FIXTURES / "ocr" / "scanned_notice.png").read_bytes()),
    ]
    for page in pages:
        assert check_text_integrity(page) == [], page.extraction_method
