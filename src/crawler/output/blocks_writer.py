"""块 JSONL 写出（T009）。"""

from __future__ import annotations

from pathlib import Path

from crawler.output.layout import BLOCKS_FILENAME, DeliveryLayout


def blocks_path(data_dir: Path) -> Path:
    return DeliveryLayout(data_dir).blocks_path
