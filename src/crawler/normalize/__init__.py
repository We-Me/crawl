"""字段与结构标准化。"""

from crawler.normalize.block_schema import build_blocks, validate_blocks
from crawler.normalize.document_schema import NormalizationError, build_document

__all__ = [
    "NormalizationError",
    "build_blocks",
    "build_document",
    "validate_blocks",
]
