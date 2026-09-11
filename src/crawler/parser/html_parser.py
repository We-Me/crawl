"""最小 HTML 正文与结构提取（T008）。

只做确定性抽取：块顺序与原文一致，不做翻译、摘要或语义重组；表格保留完整
行列结构，同时给出确定性的行列文本视图。脚本、样式、导航与页脚不进入正文。
块与页模型见 parsed_page.py（T010），本模块保持 ParsedBlock/ParsedPage 名称兼容。
"""

from __future__ import annotations

import logging
import re
from typing import Optional, Sequence, Tuple
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from crawler.normalize.date_utils import normalize_date
from crawler.normalize.text_utils import collapse_whitespace
from crawler.parser.parsed_page import ParsedBlock, ParsedPage

logger = logging.getLogger(__name__)

EXTRACTION_METHOD = "bs4_lxml_dom"
CHARSET_PATTERN = re.compile(rb"""charset=["']?([A-Za-z0-9_\-]+)""")
DATE_PATTERN = re.compile(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})日?")
PUBLISH_DATE_LABEL = re.compile(r"(发布日期|发布时间|公布日期|日期)[:：]?\s*$")
META_DATE_KEYS = (
    "publishdate",
    "publish-date",
    "pubdate",
    "date",
    "article:published_time",
    "dc.date",
)
HEADING_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6")
PAGINATION_TEXTS = frozenset({"下一页", "下一部分", "下页", "后一页", "next", "next page"})
BODY_API_TYPE = "application/json"
DROP_TAGS = ("script", "style", "noscript", "template", "nav", "footer", "aside", "form")


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
) -> ParsedPage:
    """解析 HTML 为顺序块。

    content_selector 是逐来源适配规则给出的正文范围（T026）：命中时只抽取该范围，
    并以 `bs4_lxml_selector` 记录抽取方式；未命中时不静默使用通用范围，而是设置
    `content_selector_missed` 交给调用方按失败处理。
    """
    text = decode_html(content, encoding_hint)
    soup = BeautifulSoup(text, "lxml")
    extraction_method = EXTRACTION_METHOD
    selector_missed = False
    if content_selector:
        selected = soup.select_one(content_selector)
        if selected is None:
            selector_missed = True
            logger.warning("正文选择器未命中 url=%s selector=%s", page_url, content_selector)
            scope = soup.find("main") or soup.find("article") or soup.body or soup
        else:
            scope = selected
            extraction_method = "bs4_lxml_selector"
    else:
        scope = soup.find("main") or soup.find("article") or soup.body or soup
    for tag in scope.find_all(DROP_TAGS):
        tag.decompose()

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
    next_anchor = _next_page_anchor(scope)
    next_page_url = urljoin(page_url, next_anchor["href"]) if next_anchor is not None else None
    body_api_url = _body_api_endpoint(soup, page_url)

    blocks: list = []
    for element in scope.find_all(HEADING_TAGS + ("p", "li", "table")):
        if element.name != "table" and element.find_parent("table") is not None:
            continue
        if _is_pagination_control(element, next_anchor):
            continue
        if element.name in HEADING_TAGS:
            text = _clean_text(element)
            if text:
                blocks.append(
                    ParsedBlock(
                        block_type="heading",
                        text=text,
                        heading_level=int(element.name[1]),
                        source_anchor=_anchor(element, scope),
                    )
                )
        elif element.name == "p":
            text = _clean_text(element)
            if text:
                blocks.append(
                    ParsedBlock(
                        block_type="paragraph", text=text, source_anchor=_anchor(element, scope)
                    )
                )
        elif element.name == "li":
            text = _clean_text(element)
            if text:
                blocks.append(
                    ParsedBlock(
                        block_type="list_item", text=text, source_anchor=_anchor(element, scope)
                    )
                )
        elif element.name == "table":
            rows, headers = _table_rows(element)
            if not rows:
                continue
            table_text = "\n".join("\t".join(row) for row in rows)
            blocks.append(
                ParsedBlock(
                    block_type="table",
                    text=table_text,
                    structured_data={
                        "headers": headers,
                        "rows": rows[1:] if headers else rows,
                        "caption": _clean_text(element.caption) if element.caption else None,
                    },
                    source_anchor=_anchor(element, scope),
                )
            )

    full_text = "\n".join(block.text for block in blocks if block.text)
    publication_date, raw_date_text = _extract_publication_date(soup, blocks)
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


def _next_page_anchor(scope: Tag) -> Optional[Tag]:
    """内容区内的下一页链接：rel=next 或明确的翻页文案，不跟随站外“上一篇/下一篇”推荐。"""
    for anchor in scope.find_all("a", href=True):
        rels = [str(value).lower() for value in (anchor.get("rel") or [])]
        text = _clean_text(anchor).lower()
        if "next" in rels or text in PAGINATION_TEXTS:
            return anchor
    return None


def _is_pagination_control(element: Tag, next_anchor: Optional[Tag]) -> bool:
    """纯翻页控件不进入正文：段落/列表项文本与下一页链接文本一致时跳过。"""
    if next_anchor is None or element.name not in ("p", "li"):
        return False
    anchors = element.find_all("a", href=True)
    if anchors != [next_anchor]:
        return False
    return _clean_text(element) == _clean_text(next_anchor)


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


def _table_rows(table: Tag) -> Tuple[list, list]:
    rows = []
    headers: list = []
    for row_index, tr in enumerate(table.find_all("tr")):
        cells = tr.find_all(["th", "td"])
        values = [_clean_text(cell) for cell in cells]
        if not values:
            continue
        rows.append(values)
        if row_index == 0 and any(cell.name == "th" for cell in cells):
            headers = values
    return rows, headers


def _anchor(element: Tag, scope: Tag) -> dict:
    parts = []
    current: Optional[Tag] = element
    while isinstance(current, Tag) and current is not scope:
        same_tag = [sib for sib in current.parent.find_all(current.name, recursive=False)]
        position = same_tag.index(current) + 1
        parts.append(f"{current.name}:nth-of-type({position})")
        current = current.parent if isinstance(current.parent, Tag) else None
    parts.append(scope.name)
    return {"selector": " > ".join(reversed(parts))}


def _extract_publication_date(
    soup: BeautifulSoup, blocks: Sequence[ParsedBlock]
) -> Tuple[Optional[str], Optional[str]]:
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
