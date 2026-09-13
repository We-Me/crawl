"""最小 HTML 正文与结构提取（T008）。

只做确定性抽取：块顺序与原文一致，不做翻译、摘要或语义重组；表格保留完整
行列结构，同时给出确定性的行列文本视图。脚本、样式、导航与页脚不进入正文。
块与页模型见 parsed_page.py（T010），本模块保持 ParsedBlock/ParsedPage 名称兼容。
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Optional, Sequence, Tuple
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from crawler.normalize.date_utils import normalize_date
from crawler.normalize.text_utils import collapse_whitespace
from crawler.parser.parsed_page import ParsedBlock, ParsedPage

if TYPE_CHECKING:  # pragma: no cover - 仅类型标注；运行期在 parse_html 内按需导入
    from crawler.normalize.segmenter import BlockSegmenter

logger = logging.getLogger(__name__)

EXTRACTION_METHOD = "bs4_lxml_dom"
CHARSET_PATTERN = re.compile(rb"""charset=["']?([A-Za-z0-9_\-]+)""")
DATE_PATTERN = re.compile(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})日?")
PUBLISH_DATE_LABEL = re.compile(r"(发布日期|发布时间|公布日期|日期)[:：]?\s*$")
META_DATE_KEYS = (
    "publishdate",
    "publish-date",
    "pubdate",
    "firstpublishedtime",
    "date",
    "article:published_time",
    "dc.date",
)
PAGINATION_TEXTS = frozenset({"下一页", "下一部分", "下页", "后一页", "next", "next page"})
BODY_API_TYPE = "application/json"
DROP_TAGS = ("script", "style", "noscript", "template", "nav", "footer", "aside")
# 表单控件不产出正文；但不整段丢弃 <form>：ASP.NET 等站点把整页内容包在 form 里
# （IN-10 Home.aspx：4 h2/17 p/2 table 全在 form 内），整段丢弃会得到 0 块。
DROP_FORM_CONTROLS = ("input", "select", "option", "textarea", "button")


def decode_html(content: bytes, encoding_hint: Optional[str] = None) -> str:
    """按响应声明、文档 meta 或 UTF-8 解码；不按长度裁剪。"""
    candidates = [encoding_hint]
    match = CHARSET_PATTERN.search(content[:4096])
    if match:
        candidates.append(match.group(1).decode("ascii", errors="ignore"))
    candidates.append("utf-8")
    for candidate in candidates:
        if not candidate:
            continue
        try:
            return content.decode(candidate)
        except (LookupError, UnicodeDecodeError):
            continue
    return content.decode("utf-8", errors="replace")


def parse_html(
    content: bytes,
    page_url: str,
    encoding_hint: Optional[str] = None,
    content_selector: Optional[str] = None,
    date_selector: Optional[str] = None,
    segmenter: Optional[BlockSegmenter] = None,
    pagination_selector: Optional[str] = None,
) -> ParsedPage:
    """解析 HTML 为顺序块。

    content_selector 是逐来源适配规则给出的正文范围（T026）：命中时只抽取该范围，
    并以 `bs4_lxml_selector` 记录抽取方式；未命中时不静默使用通用范围，而是设置
    `content_selector_missed` 交给调用方按失败处理。

    date_selector 是逐来源适配规则给出的发布日期元素（T026）：命中且文本可验证到日精度时
    作为 publication_date；未命中或无法验证时回落到 meta/正文启发式，并保留 raw_date_text，
    不补造日期。

    pagination_selector 是逐来源适配规则给出的正文分页控件（S5-03）：配置后只跟随该
    控件指向的下一页，控件不存在即视为该来源的分页终点（与发现阶段同一语义），不再用
    通用 rel=next/翻页文案启发式；未配置时保持原通用行为。

    segmenter 是分块实现（T010/T013 新增的分块抽象）：默认使用
    StructuralBlankLineSegmenter（独立结构块 + div 空行拆块），记录在
    extraction_method 中；替换实现不改变 ParsedBlock 与输出契约。
    """
    # 延迟导入：normalize.segmenter 依赖 ParsedBlock，而本模块在 parser 包初始化时被导入。
    from crawler.normalize.segmenter import (
        DEFAULT_HTML_SEGMENTER,
        SegmentRequest,
        extraction_method_for,
    )

    segmenter = segmenter or DEFAULT_HTML_SEGMENTER
    text = decode_html(content, encoding_hint)
    soup = BeautifulSoup(text, "lxml")
    base_method = EXTRACTION_METHOD
    selector_missed = False
    if content_selector:
        selected = soup.select_one(content_selector)
        if selected is None:
            selector_missed = True
            logger.warning("正文选择器未命中 url=%s selector=%s", page_url, content_selector)
            scope = soup.find("main") or soup.find("article") or soup.body or soup
        else:
            scope = selected
            base_method = "bs4_lxml_selector"
    else:
        scope = soup.find("main") or soup.find("article") or soup.body or soup
    for tag in scope.find_all(DROP_TAGS):
        tag.decompose()
    for tag in scope.find_all(DROP_FORM_CONTROLS):
        tag.decompose()
    extraction_method = extraction_method_for(base_method, segmenter)

    title = ""
    for heading in scope.find_all(["h1", "h2"]):
        heading_text = _clean_text(heading)
        if heading_text:
            title = heading_text
            break
    if not title and content_selector:
        # 正文选择器只框定正文容器，标题通常在容器之外；
        # 先按文档范围补标题，避免退化到带站点后缀的 <title>。
        for heading in soup.find_all(["h1", "h2"]):
            heading_text = _clean_text(heading)
            if heading_text:
                title = heading_text
                break
    if not title and soup.title is not None:
        title = _clean_text(soup.title)
    metadata_missing = []
    if not title:
        metadata_missing.append("title")

    canonical = soup.find("link", rel=lambda value: value and "canonical" in value)
    canonical_url = canonical.get("href") if isinstance(canonical, Tag) else None
    if pagination_selector:
        next_anchor = _adapter_next_page_anchor(soup, pagination_selector)
        if next_anchor is None:
            logger.debug(
                "正文分页适配控件不存在（按适配规则视为终点） url=%s selector=%s",
                page_url,
                pagination_selector,
            )
    else:
        next_anchor = _next_page_anchor(scope)
    next_page_url = _next_page_url(page_url, next_anchor)
    body_api_url = _body_api_endpoint(soup, page_url)

    blocks = segmenter.segment(
        SegmentRequest(dom=scope, page_url=page_url, next_page_anchor=next_anchor)
    )

    full_text = "\n".join(block.text for block in blocks if block.text)
    publication_date, raw_date_text = _extract_publication_date(
        soup, blocks, date_selector=date_selector, page_url=page_url
    )
    if publication_date is None:
        metadata_missing.append("publication_date")
    language = None
    if soup.html and soup.html.get("lang"):
        language = str(soup.html.get("lang"))

    logger.debug(
        "HTML 解析完成 url=%s blocks=%d title=%s", page_url, len(blocks), bool(title)
    )
    return ParsedPage(
        title=title,
        full_text=full_text,
        blocks=tuple(blocks),
        extraction_method=extraction_method,
        language_hint=language,
        publication_date=publication_date,
        raw_date_text=raw_date_text,
        canonical_url=canonical_url,
        metadata_missing=tuple(metadata_missing),
        next_page_url=next_page_url,
        body_api_url=body_api_url,
        content_selector_missed=selector_missed,
    )


def _next_page_url(page_url: str, anchor: Optional[Tag]) -> Optional[str]:
    """下一页地址；忽略只改锚点的“翻页”链接（轮播/回到顶部等 rel=next 误报）。"""
    if anchor is None:
        return None
    candidate = urljoin(page_url, str(anchor["href"]))
    if candidate.split("#")[0] == str(page_url).split("#")[0]:
        return None
    return candidate


def _adapter_next_page_anchor(soup: BeautifulSoup, selector: str) -> Optional[Tag]:
    """适配规则指定的下一页控件：选择器可直接命中链接或包含链接的容器。

    与发现阶段（Discoverer._next_page_url）同一语义：控件不存在即分页终点，
    不退化为通用启发式，避免跟随与本站分页无关的 rel=next 或“下一页”文本。
    """
    element = soup.select_one(selector)
    if element is not None and not element.get("href"):
        element = element.find(["a", "link"], href=True)
    return element if isinstance(element, Tag) else None


def _next_page_anchor(scope: Tag) -> Optional[Tag]:
    """内容区内的下一页链接：rel=next 或明确的翻页文案，不跟随站外“上一篇/下一篇”推荐。"""
    for anchor in scope.find_all("a", href=True):
        rels = [str(value).lower() for value in (anchor.get("rel") or [])]
        text = _clean_text(anchor).lower()
        if "next" in rels or text in PAGINATION_TEXTS:
            return anchor
    return None


def _body_api_endpoint(soup: BeautifulSoup, page_url: str) -> Optional[str]:
    """页面声明接口正文档端点：<link rel="alternate" type="application/json" href=...>。

    仅在解析器层面报告候选；未经边界校验前不发请求。
    """
    for link in soup.find_all("link", href=True):
        rels = [str(value).lower() for value in (link.get("rel") or [])]
        media_type = str(link.get("type", "")).split(";")[0].strip().lower()
        if "alternate" in rels and media_type == BODY_API_TYPE:
            return urljoin(page_url, link["href"])
    return None


def _clean_text(element: Tag) -> str:
    return collapse_whitespace(element.get_text(" ", strip=True))


def _extract_publication_date(
    soup: BeautifulSoup,
    blocks: Sequence[ParsedBlock],
    date_selector: Optional[str] = None,
    page_url: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    if date_selector:
        element = soup.select_one(date_selector)
        if element is None:
            logger.warning(
                "发布日期选择器未命中 url=%s selector=%s；回落 meta/正文启发式",
                page_url,
                date_selector,
            )
        else:
            raw = _clean_text(element)
            normalized = _normalize_date(raw)
            if normalized:
                return normalized, raw or None
            logger.warning(
                "发布日期选择器文本无法验证到日精度 url=%s selector=%s text=%r",
                page_url,
                date_selector,
                raw,
            )
    for meta in soup.find_all("meta"):
        key = (meta.get("name") or meta.get("property") or "").lower()
        if key in META_DATE_KEYS:
            raw = (meta.get("content") or "").strip()
            normalized = _normalize_date(raw)
            if normalized:
                return normalized, raw or None
    for block in blocks[:6]:
        if block.block_type not in ("paragraph", "list_item"):
            continue
        if "日期" not in block.text and "时间" not in block.text:
            continue
        match = DATE_PATTERN.search(block.text)
        if match:
            normalized = _normalize_date(match.group(0))
            if normalized:
                return normalized, match.group(0)
    return None, None


def _normalize_date(raw: str) -> Optional[str]:
    return normalize_date(raw)
