"""扫描 PDF 与图片的 OCR 解析（T011）。

RapidOCR（ONNX Runtime，自带模型）逐页识别：保留页号、置信度与文本框，
不合并行、不翻译、不补造缺失元数据。页状态区分 ok/empty/failed：空结果与
引擎异常都不静默当作成功；全部页失败才抛 OcrError，部分失败在 page_status
与 metadata_missing 中明确保留。扫描 PDF 先由 pypdfium2 逐页栅格化。
"""

from __future__ import annotations

import io
import logging
import threading
from typing import List, Sequence, Tuple

from crawler.parser.parsed_page import (
    PageStatus,
    ParsedBlock,
    ParsedPage,
    degraded_pages,
)

logger = logging.getLogger(__name__)

EXTRACTION_METHOD = "rapidocr_onnxruntime"
DEFAULT_RENDER_SCALE = 2.0
OCR_BLOCK_TYPE = "text_line"

_engine = None
_engine_lock = threading.Lock()


class OcrError(RuntimeError):
    """OCR 引擎不可用或所有页均失败。"""


def get_engine():
    """共享引擎单例；首次调用时加载 ONNX 模型。"""
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                from rapidocr_onnxruntime import RapidOCR

                _engine = RapidOCR()
    return _engine


def parse_image(
    content: bytes, page_url: str = "", *, page_no: int = 1, engine=None
) -> ParsedPage:
    """单张图片按一页处理；识别失败直接报错，不返回空文档冒充成功。"""
    engine = engine or get_engine()
    try:
        lines = _recognize(engine, content)
    except Exception as exc:  # noqa: BLE001 - 统一为带页号的 OCR 错误
        raise OcrError(f"第 {page_no} 页 OCR 失败：{exc}") from exc
    blocks = _lines_to_blocks(lines, page_no)
    status = _page_status(page_no, blocks, lines)
    metadata_missing = ["publication_date"]
    metadata_missing.extend(degraded_pages((status,)))
    title = blocks[0].text if blocks else ""
    if not title:
        metadata_missing.append("title")
    return ParsedPage(
        title=title,
        full_text="\n".join(block.text for block in blocks),
        blocks=tuple(blocks),
        extraction_method=EXTRACTION_METHOD,
        metadata_missing=tuple(metadata_missing),
        page_status=(status,),
        page_count=1,
        canonical_url=page_url or None,
    )


def parse_scanned_pdf(
    content: bytes,
    page_url: str = "",
    *,
    engine=None,
    render_scale: float = DEFAULT_RENDER_SCALE,
) -> ParsedPage:
    engine = engine or get_engine()
    pages = _render_pdf_pages(content, render_scale)
    blocks: List[ParsedBlock] = []
    statuses: List[PageStatus] = []
    for page_no, image in pages:
        try:
            lines = _recognize(engine, image)
        except Exception as exc:  # noqa: BLE001 - 单页失败记状态，继续其他页
            logger.warning("OCR 第 %d 页失败：%s", page_no, exc)
            statuses.append(
                PageStatus(
                    page_no=page_no,
                    status="failed",
                    extraction_method=EXTRACTION_METHOD,
                    error=str(exc),
                )
            )
            continue
        page_blocks = _lines_to_blocks(lines, page_no)
        blocks.extend(page_blocks)
        statuses.append(_page_status(page_no, page_blocks, lines))

    if statuses and all(status.status == "failed" for status in statuses):
        details = "；".join(f"第 {s.page_no} 页：{s.error}" for s in statuses)
        raise OcrError(f"扫描 PDF 所有页 OCR 失败：{details}")

    metadata_missing = ["publication_date"]
    metadata_missing.extend(degraded_pages(tuple(statuses)))
    title = blocks[0].text if blocks else ""
    if not title:
        metadata_missing.append("title")
    logger.debug(
        "扫描 PDF OCR 完成 url=%s pages=%d blocks=%d", page_url, len(statuses), len(blocks)
    )
    return ParsedPage(
        title=title,
        full_text="\n".join(block.text for block in blocks),
        blocks=tuple(blocks),
        extraction_method=EXTRACTION_METHOD,
        metadata_missing=tuple(metadata_missing),
        page_status=tuple(statuses),
        page_count=len(statuses),
        canonical_url=page_url or None,
    )


def parse_scan(content: bytes, page_url: str = "", *, engine=None) -> ParsedPage:
    """按内容特征分派：PDF 走逐页栅格化 OCR，其余按单页图片处理。"""
    if content.lstrip().startswith(b"%PDF-"):
        return parse_scanned_pdf(content, page_url, engine=engine)
    return parse_image(content, page_url, engine=engine)


def _render_pdf_pages(content: bytes, scale: float) -> List[Tuple[int, object]]:
    import pypdfium2 as pdfium

    try:
        document = pdfium.PdfDocument(io.BytesIO(content))
    except Exception as exc:  # noqa: BLE001 - 栅格化失败统一报错
        raise OcrError(f"扫描 PDF 无法打开：{exc}") from exc
    try:
        count = len(document)
        if count == 0:
            raise OcrError("扫描 PDF 没有页面")
        pages = []
        for index in range(count):
            page = document[index]
            try:
                bitmap = page.render(scale=scale)
                pages.append((index + 1, bitmap.to_pil()))
            finally:
                page.close()
        return pages
    finally:
        document.close()


def _recognize(engine, image) -> List[Tuple[str, float, list]]:
    result, _ = engine(image)
    lines: List[Tuple[str, float, list]] = []
    for item in result or []:
        box, text, score = item[0], str(item[1]), float(item[2])
        cleaned = text.strip()
        if not cleaned:
            continue
        lines.append((cleaned, score, _bbox(box)))
    return lines


def _bbox(box: Sequence) -> list:
    xs = [float(point[0]) for point in box]
    ys = [float(point[1]) for point in box]
    return [round(min(xs), 2), round(min(ys), 2), round(max(xs), 2), round(max(ys), 2)]


def _lines_to_blocks(lines: Sequence[Tuple[str, float, list]], page_no: int) -> List[ParsedBlock]:
    return [
        ParsedBlock(
            block_type=OCR_BLOCK_TYPE,
            text=text,
            page_no=page_no,
            confidence=confidence,
            source_anchor={"page_no": page_no, "bbox": bbox},
        )
        for text, confidence, bbox in lines
    ]


def _page_status(
    page_no: int, blocks: Sequence[ParsedBlock], lines: Sequence[Tuple]
) -> PageStatus:
    mean = sum(confidence for _, confidence, _ in lines) / len(lines) if lines else None
    return PageStatus(
        page_no=page_no,
        status="ok" if blocks else "empty",
        line_count=len(blocks),
        mean_confidence=mean,
        extraction_method=EXTRACTION_METHOD,
    )
