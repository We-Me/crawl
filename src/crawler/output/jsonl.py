"""UTF-8 JSONL 读写：一行一对象，空文件表示零条记录。"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable, List


def append_jsonl(path: Path, rows: Iterable[dict]) -> int:
    """追加 JSONL 行并刷盘；返回写入行数。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=False) + "\n")
            count += 1
        handle.flush()
        os.fsync(handle.fileno())
    return count


def write_jsonl(path: Path, rows: Iterable[dict]) -> int:
    """整文件原子写入 JSONL。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    count = 0
    with tmp.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)
    return count


def read_jsonl(path: Path) -> List[dict]:
    path = Path(path)
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows
