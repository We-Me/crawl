"""JSON/XML/API 结构解析（T012）。

保留字段结构：JSON 列表逐项、对象逐顶层字段生成 record 块，嵌套结构以确定性
JSON 文本保留；XML 逐子元素生成 record 块，保留元素路径、属性与子字段文本。
请求参数由 canonical_url 保留（完整 URL 含查询串），分页字段按原样保留在字段块
中，不推断语义。解析失败明确报错，不返回空文档。
"""

from __future__ import annotations

import json
import logging
from typing import Any, List, Optional
from xml.etree import ElementTree

from defusedxml.ElementTree import fromstring as safe_fromstring
from defusedxml.common import DefusedXmlException

from crawler.parser.parsed_page import ParsedBlock, ParsedPage

logger = logging.getLogger(__name__)

JSON_METHOD = "json_stdlib"
XML_METHOD = "defusedxml_etree"
TEXT_JOIN = " ".join


class ApiParseError(ValueError):
    """JSON/XML 无法解析。"""


def parse_json(content: bytes, page_url: str = "") -> ParsedPage:
    try:
        payload = json.loads(content.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ApiParseError(f"JSON 无法解析：{exc}") from exc
    blocks: List[ParsedBlock] = []
    if isinstance(payload, list):
        for index, item in enumerate(payload):
            blocks.append(_json_block(item, f"$[{index}]"))
    elif isinstance(payload, dict):
        for key, value in payload.items():
            blocks.append(_json_block(value, f"$.{key}", field=str(key)))
    else:
        blocks.append(_json_block(payload, "$"))
    title = ""
    if isinstance(payload, dict) and isinstance(payload.get("title"), str):
        title = payload["title"].strip()
    return _result(
        blocks=blocks,
        page_url=page_url,
        method=JSON_METHOD,
        title=title,
        raw=payload,
    )


def parse_xml(content: bytes, page_url: str = "") -> ParsedPage:
    try:
        root = safe_fromstring(content)
    except (ElementTree.ParseError, DefusedXmlException, ValueError) as exc:
        raise ApiParseError(f"XML 无法解析：{exc}") from exc
    children = list(root)
    blocks: List[ParsedBlock] = []
    if children:
        for index, child in enumerate(children, start=1):
            blocks.append(_xml_block(child, f"/{root.tag}/{child.tag}[{index}]"))
    else:
        blocks.append(_xml_block(root, f"/{root.tag}[1]"))
    return _result(
        blocks=blocks,
        page_url=page_url,
        method=XML_METHOD,
        title="",
        raw=root,
    )


def _json_block(value: Any, json_path: str, field: Optional[str] = None) -> ParsedBlock:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    structured = {
        "json_path": json_path,
        "value_type": type(value).__name__,
    }
    if field is not None:
        structured["field"] = field
    return ParsedBlock(block_type="record", text=text, structured_data=structured)


def _xml_block(element: ElementTree.Element, xml_path: str) -> ParsedBlock:
    structured = {
        "xml_path": xml_path,
        "element": element.tag,
        "fields": {child.tag: _xml_value(child) for child in element},
    }
    if element.attrib:
        structured["attributes"] = dict(element.attrib)
    text = _element_text(element)
    return ParsedBlock(block_type="record", text=text, structured_data=structured)


def _xml_value(element: ElementTree.Element):
    value = _element_text(element, children_separated=False)
    if element.attrib:
        return {"text": value, "attributes": dict(element.attrib)}
    return value


def _element_text(element: ElementTree.Element, children_separated: bool = True) -> str:
    """确定性文本视图：子字段之间保留分隔，避免相邻字段文本粘连。"""
    if children_separated:
        parts = [TEXT_JOIN("".join(child.itertext()).split()) for child in element]
        parts = [part for part in parts if part]
        if parts:
            return " ".join(parts)
    return TEXT_JOIN("".join(element.itertext()).split())


def _result(*, blocks: List[ParsedBlock], page_url: str, method: str, title: str, raw) -> ParsedPage:
    metadata_missing = ["publication_date"]
    if not title:
        metadata_missing.append("title")
    logger.debug("结构数据解析完成 url=%s blocks=%d", page_url, len(blocks))
    return ParsedPage(
        title=title,
        full_text="\n".join(block.text for block in blocks if block.text),
        blocks=tuple(blocks),
        extraction_method=method,
        metadata_missing=tuple(metadata_missing),
        canonical_url=page_url or None,
    )
