"""路径与文件名安全工具。"""

from __future__ import annotations

import re
from pathlib import Path

_FILENAME_SAFE = re.compile(r"[^A-Za-z0-9._\-\u4e00-\u9fff]+")
_PATH_SEGMENT_SAFE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class PathSafetyError(ValueError):
    """路径越界或组件非法。"""


def sanitize_filename(name: str, *, fallback: str = "attachment.bin") -> str:
    cleaned = _FILENAME_SAFE.sub("_", name).strip("._") or fallback
    return cleaned[:120]


def safe_segment(value: str, *, field: str) -> str:
    if not _PATH_SEGMENT_SAFE.match(value):
        raise PathSafetyError(f"{field} 不是合法路径片段：{value!r}")
    return value


def ensure_within(root: Path, target: Path) -> Path:
    """确保 target 解析后仍位于 root 之内，否则拒绝。"""
    root_resolved = Path(root).resolve()
    target_resolved = Path(target).resolve()
    if target_resolved != root_resolved and not target_resolved.is_relative_to(root_resolved):
        raise PathSafetyError(f"路径越出数据根：{target_resolved} 不在 {root_resolved} 内")
    return target_resolved
