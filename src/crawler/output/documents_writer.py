"""文档与块的成组提交（T009）。

提交顺序：先完成跨文件校验，再写 documents，最后写 blocks。先写文档保证
中断时不会出现引用不存在文档的块；重跑可按 doc_id 检查提交是否完整。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Mapping, Sequence, Tuple

from crawler.normalize.document_schema import (
    documents_and_blocks,
    validate_document,
)
from crawler.output.blocks_writer import blocks_path
from crawler.output.jsonl import append_jsonl
from crawler.output.layout import DeliveryLayout

logger = logging.getLogger(__name__)

class DocumentsWriter:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.path = DeliveryLayout(data_dir).documents_path

    def commit(
        self,
        documents: Sequence[Mapping],
        blocks: Sequence[Mapping],
    ) -> Tuple[int, int]:
        documents = list(documents)
        blocks = list(blocks)
        for document in documents:
            validate_document(document)
        documents_and_blocks(documents=documents, blocks=blocks)
        document_count = append_jsonl(self.path, documents)
        block_count = append_jsonl(blocks_path(self.data_dir), blocks)
        logger.info(
            "成组提交 documents=%d blocks=%d", document_count, block_count
        )
        return document_count, block_count
