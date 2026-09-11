"""统一清洗、日期、URL、语言与不改写约束（T013）。

各解析器共用同一规则，避免逐格式重复实现：
- clean_text / collapse_whitespace：Unicode NFC、去控制字符、按行去尾空白，
  不翻译、不改写、不按长度裁剪；
- normalize_date：只在能证明到“日”精度时返回 ISO 日期，仅到年月或无法验证时
  返回 None，由调用方保留 raw_date，绝不补造日期；
- normalize_url：小写 scheme/host、去默认端口、去片段，保留路径与查询串；
- detect_language：先信显式语言标记，否则只按文字系统判定（汉字/假名/谚文/
  西里尔/阿拉伯/泰文/希伯来/天城文），拉丁文一律返回 und，不猜测英语；
- check_text_integrity：复核块顺序、页码与 full_text 与块文本一致。
"""

from __future__ import annotations

import logging
import re
from dataclasses import replace
from datetime import datetime
from typing import Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urlsplit, urlunsplit

from crawler.normalize.block_schema import BlockValidationError, validate_blocks
from crawler.normalize.date_utils import normalize_date
from crawler.normalize.text_utils import clean_text, collapse_whitespace
from crawler.parser.parsed_page import ParsedPage

logger = logging.getLogger(__name__)

LANGUAGE_TAG = re.compile(r"^[A-Za-z]{2,3}(?:[-_][A-Za-z0-9]{2,8})*$")

SCRIPT_RANGES = (
    ("han", ((0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF))),
    ("kana", ((0x3040, 0x30FF), (0x31F0, 0x31FF))),
    ("hangul", ((0x1100, 0x11FF), (0xAC00, 0xD7AF))),
    ("cyrillic", ((0x0400, 0x04FF), (0x0500, 0x052F))),
    ("arabic", ((0x0600, 0x06FF), (0x0750, 0x077F))),
    ("thai", ((0x0E00, 0x0E7F),)),
    ("hebrew", ((0x0590, 0x05FF),)),
    ("devanagari", ((0x0900, 0x097F), (0xA8E0, 0xA8FF))),
)
SCRIPT_LANGUAGE = {
    "han": "zh",
    "kana": "ja",
    "hangul": "ko",
    "cyrillic": "ru",
    "arabic": "ar",
    "thai": "th",
    "hebrew": "he",
    "devanagari": "hi",
}
MIN_HAN_CHARS = 5

def normalize_url(url: Optional[str], base_url: Optional[str] = None) -> Optional[str]:
    """规范化 URL：解析相对地址、统一 scheme/host 大小写、去默认端口与片段。"""
    if not url or not url.strip():
        return None
    candidate = url.strip()
    parts = urlsplit(candidate)
    if base_url and not parts.scheme:
        from urllib.parse import urljoin

        candidate = urljoin(base_url, candidate)
        parts = urlsplit(candidate)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    host = parts.hostname.lower()
    port = parts.port
    if port and not ((parts.scheme == "http" and port == 80) or (parts.scheme == "https" and port == 443)):
        netloc = f"{host}:{port}"
    else:
        netloc = host
    if parts.username:
        credentials = parts.username
        if parts.password:
            credentials = f"{credentials}:{parts.password}"
        netloc = f"{credentials}@{netloc}"
    path = parts.path or "/"
    return urlunsplit((parts.scheme.lower(), netloc, path, parts.query, ""))


def canonical_language(tag: Optional[str]) -> Optional[str]:
    """把 zh-CN / zh_CN / en-US 之类的标记规范为小写主语言；无法识别返回 None。"""
    if not tag or not LANGUAGE_TAG.match(tag.strip()):
        return None
    return tag.strip().replace("_", "-").split("-")[0].lower()


def detect_language(text: str, hints: Sequence[Optional[str]] = ()) -> str:
    """先使用显式语言标记，再按文字系统判定；拉丁文不猜具体语言。"""
    for hint in hints:
        language = canonical_language(hint)
        if language:
            return language
    counts = _script_counts(text)
    if not counts:
        return "und"
    kana = counts.get("kana", 0)
    han = counts.get("han", 0)
    if kana and kana >= han * 0.1:
        return "ja"
    if han >= MIN_HAN_CHARS:
        return "zh"
    for script in ("hangul", "cyrillic", "arabic", "thai", "hebrew", "devanagari"):
        if counts.get(script):
            return SCRIPT_LANGUAGE[script]
    return "und"


def _script_counts(text: str) -> dict:
    counts: dict = {}
    for char in text:
        code = ord(char)
        for name, ranges in SCRIPT_RANGES:
            if any(start <= code <= end for start, end in ranges):
                counts[name] = counts.get(name, 0) + 1
                break
    return counts


def check_text_integrity(page: ParsedPage) -> List[str]:
    """复核单个解析结果：清洗一致、full_text 与块一致、页码与置信度合法。"""
    issues: List[str] = []
    for block in page.blocks:
        if block.text != clean_text(block.text):
            issues.append(f"{page.extraction_method} 块文本未按统一规则清洗：{block.block_type}")
        if block.block_type != "table" and not block.text.strip():
            issues.append(f"{page.extraction_method} 非表格块文本为空：{block.block_type}")
        if block.confidence is not None and not 0 <= float(block.confidence) <= 1:
            issues.append(f"{page.extraction_method} 置信度越界：{block.confidence}")
    expected = "\n".join(clean_text(block.text) for block in page.blocks if block.text)
    if collapse_whitespace(expected) != collapse_whitespace(page.full_text):
        issues.append(f"{page.extraction_method} full_text 与块文本不一致")
    pages = [block.page_no for block in page.blocks if block.page_no is not None]
    if pages != sorted(pages):
        issues.append(f"{page.extraction_method} 块页码顺序不一致：{pages}")
    if page.page_count is not None and any(page_no > page.page_count for page_no in pages):
        issues.append(f"{page.extraction_method} 块页码超出总页数：{pages}")
    try:
        validate_blocks(
            [
                {
                    "block_id": f"check_B{index:04d}",
                    "doc_id": "check",
                    "order": index,
                    "block_type": block.block_type,
                    "text": block.text,
                    "extraction_method": page.extraction_method,
                    **({"page_no": block.page_no} if block.page_no is not None else {}),
                    **({"confidence": block.confidence} if block.confidence is not None else {}),
                }
                for index, block in enumerate(page.blocks)
            ],
            {"check"},
        )
    except BlockValidationError as exc:
        issues.append(f"块契约校验失败：{exc}")
    return issues


def normalize_page(
    page: ParsedPage,
    *,
    language_hints: Iterable[Optional[str]] = (),
    base_url: Optional[str] = None,
) -> ParsedPage:
    """返回按统一规则清洗后的解析结果；不改变块顺序，不新增或删除正文。"""
    blocks = tuple(
        replace(block, text=clean_text(block.text)) for block in page.blocks
    )
    full_text = "\n".join(block.text for block in blocks if block.text)
    metadata_missing = list(page.metadata_missing)
    publication_date = page.publication_date
    if publication_date is None and page.raw_date_text:
        publication_date = normalize_date(page.raw_date_text)
        if publication_date and "publication_date" in metadata_missing:
            metadata_missing.remove("publication_date")
    language_hint = page.language_hint
    language = detect_language(full_text, [language_hint, *language_hints])
    canonical_url = normalize_url(page.canonical_url, base_url) or page.canonical_url
    cleaned_title = clean_text(page.title)
    if not cleaned_title and "title" not in metadata_missing:
        metadata_missing.append("title")
    return replace(
        page,
        title=cleaned_title,
        full_text=full_text,
        blocks=blocks,
        language_hint=language,
        publication_date=publication_date,
        canonical_url=canonical_url,
        metadata_missing=tuple(metadata_missing),
    )
