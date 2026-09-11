"""跨格式解析结果模型（T010）。

HTML、文本 PDF、OCR 及后续 Office/结构数据解析器共用同一原始结构块模型：
块只描述原件中的原始单元，不合并语义、不重排顺序；page_no、confidence 等
定位字段按来源能力可省略。页码从 1 开始，置信度取 0—1。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple

PAGE_STATUSES = ("ok", "empty", "failed")


@dataclass(frozen=True)
class ParsedBlock:
    block_type: str
    text: str
    heading_level: Optional[int] = None
    structured_data: Optional[dict] = None
    source_anchor: Optional[dict] = None
    page_no: Optional[int] = None
    confidence: Optional[float] = None
    section_path: Optional[Tuple[str, ...]] = None
    article_no: Optional[str] = None


@dataclass(frozen=True)
class PageStatus:
    """单页解析状态；empty/failed 必须可区分，不能用空文本掩盖异常。"""

    page_no: int
    status: str
    line_count: int = 0
    mean_confidence: Optional[float] = None
    extraction_method: str = ""
    error: Optional[str] = None

    def as_dict(self) -> dict:
        if self.status not in PAGE_STATUSES:
            raise ValueError(f"未知页状态：{self.status!r}")
        row = {
            "page_no": self.page_no,
            "status": self.status,
            "line_count": self.line_count,
            "extraction_method": self.extraction_method,
        }
        if self.mean_confidence is not None:
            row["mean_confidence"] = round(self.mean_confidence, 6)
        if self.error:
            row["error"] = self.error
        return row


@dataclass(frozen=True)
class ParsedPage:
    title: str
    full_text: str
    blocks: Tuple[ParsedBlock, ...]
    extraction_method: str
    language_hint: Optional[str] = None
    publication_date: Optional[str] = None
    raw_date_text: Optional[str] = None
    canonical_url: Optional[str] = None
    metadata_missing: Tuple[str, ...] = ()
    page_status: Tuple[PageStatus, ...] = field(default=())
    page_count: Optional[int] = None
    # HTML 正文还原候选：内容区声明的下一页（分页正文）与接口正文档端点。
    # 解析器只报告候选地址，边界校验、获取与合并由管线完成（FR-005）。
    next_page_url: Optional[str] = None
    body_api_url: Optional[str] = None
    # 适配规则（逐来源正文选择器）未命中：调用方必须显式处理，不得当作正常抽取。
    content_selector_missed: bool = False

    def page_status_rows(self) -> list:
        return [status.as_dict() for status in self.page_status]


def degraded_pages(statuses: Tuple[PageStatus, ...]) -> Tuple[str, ...]:
    """把非 ok 页转成文档级 metadata_missing 标记，保留页级状态。"""
    return tuple(
        f"ocr_page_{status.page_no}_{status.status}"
        for status in statuses
        if status.status != "ok"
    )
