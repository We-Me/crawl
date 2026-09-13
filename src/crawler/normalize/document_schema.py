"""文档契约构造与状态规则（T009）。

必填字段按 contracts/document.schema.json；元数据缺失不伪造取值，记入
metadata_missing（Q06 候选实现）并影响 parse_status。字段含义与空缺理由
保持可区分，不能把缺标题或空正文当作完整成功文档。
"""

from __future__ import annotations

import logging
from typing import Mapping, Optional, Sequence

from crawler.normalize.block_schema import BlockValidationError, validate_blocks

logger = logging.getLogger(__name__)

REQUIRED_DOCUMENT_FIELDS = (
    "doc_id",
    "source_id",
    "source_name",
    "source_url",
    "title",
    "full_text",
    "language",
    "document_type",
    "raw_path",
    "sha256",
    "crawl_time",
    "extraction_method",
    "parse_status",
)

PARSE_STATUSES = ("ok", "partial", "failed")
# S5-04：附件状态区分成功、失败、边界拒绝（robots/访问边界）与待处理（预算停止，
# 已入待处理存储）；候选扩展已在结构对照与附件契约中登记，不是原文字段。
ATTACHMENT_STATUSES = ("downloaded", "failed", "boundary_rejected", "pending")


class NormalizationError(ValueError):
    """文档或附件记录不符合契约。"""


def build_document(
    *,
    doc_id: str,
    source_id: str,
    source_name: str,
    source_url: str,
    title: str,
    full_text: str,
    language: str,
    document_type: str,
    raw_path: str,
    sha256: str,
    crawl_time: str,
    extraction_method: str,
    crawl_ids: Sequence[str],
    canonical_url: Optional[str] = None,
    publication_date: Optional[str] = None,
    raw_date: Optional[str] = None,
    issuer: Optional[str] = None,
    category_hint: Optional[str] = None,
    attachments: Optional[Sequence[Mapping]] = None,
    metadata_missing: Sequence[str] = (),
    version: Optional[str] = None,
    is_current: Optional[bool] = None,
    parse_status: Optional[str] = None,
) -> dict:
    if parse_status is not None and parse_status not in PARSE_STATUSES:
        raise NormalizationError(f"parse_status 非法：{parse_status!r}")
    parse_status = parse_status or ("ok" if title and full_text else "partial")
    document = {
        "doc_id": doc_id,
        "source_id": source_id,
        "source_name": source_name,
        "source_url": source_url,
        "title": title,
        "full_text": full_text,
        "language": language,
        "document_type": document_type,
        "raw_path": raw_path,
        "sha256": sha256,
        "crawl_time": crawl_time,
        "extraction_method": extraction_method,
        "parse_status": parse_status,
        "crawl_ids": list(crawl_ids),
    }
    for key, value in (
        ("canonical_url", canonical_url),
        ("publication_date", publication_date),
        ("raw_date", raw_date),
        ("issuer", issuer),
        ("category_hint", category_hint),
        ("version", version),
        ("is_current", is_current),
    ):
        if value is not None:
            document[key] = value
    if attachments is not None:
        document["attachments"] = [validate_attachment(item) for item in attachments]
    if metadata_missing:
        document["metadata_missing"] = list(metadata_missing)
    validate_document(document)
    return document


def validate_attachment(attachment: Mapping) -> dict:
    required = ("attachment_id", "filename", "file_type", "url", "status")
    missing = [field for field in required if field not in attachment]
    if missing:
        raise NormalizationError(f"附件缺少必填字段：{missing}")
    if attachment["status"] not in ATTACHMENT_STATUSES:
        raise NormalizationError(f"附件状态非法：{attachment['status']!r}")
    return dict(attachment)


def validate_document(document: Mapping) -> None:
    missing = [
        field
        for field in REQUIRED_DOCUMENT_FIELDS
        if field not in document or document[field] is None
    ]
    if missing:
        raise NormalizationError(f"文档缺少必填字段：{missing}")
    for key in ("doc_id", "source_id", "source_name", "source_url", "language", "document_type"):
        if not str(document[key]).strip():
            raise NormalizationError(f"文档字段不能为空：{key}")
    if document["parse_status"] not in PARSE_STATUSES:
        raise NormalizationError(f"parse_status 非法：{document['parse_status']!r}")
    if not isinstance(document.get("crawl_ids"), list) or not document["crawl_ids"]:
        raise NormalizationError("crawl_ids 必须是非空数组")


def documents_and_blocks(
    *,
    documents: Sequence[Mapping],
    blocks: Sequence[Mapping],
) -> None:
    """跨文件校验：块必须引用本次提交的文档且 order 连续。"""
    doc_ids = set()
    for document in documents:
        doc_id = document.get("doc_id")
        if doc_id in doc_ids:
            raise NormalizationError(f"doc_id 重复：{doc_id}")
        doc_ids.add(doc_id)
    try:
        validate_blocks(blocks, doc_ids)
    except BlockValidationError as exc:
        raise NormalizationError(str(exc)) from exc
