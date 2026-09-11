"""文本清洗基础原语（T013）。

放在叶子模块，供各解析器与标准化模块共用，避免 parser/normalize 互相导入形成环。
只做确定性规范化，不翻译、不改写、不按长度裁剪。
"""

from __future__ import annotations

import re
import unicodedata

CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
ZERO_WIDTH = re.compile(r"[\u200b-\u200f\ufeff]")


def clean_text(text: str) -> str:
    """统一清洗单个文本：NFC、去控制字符与零宽字符、按行去尾空白。"""
    if not text:
        return ""
    normalized = unicodedata.normalize("NFC", text)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalized.replace("\u00a0", " ")
    normalized = ZERO_WIDTH.sub("", normalized)
    normalized = CONTROL_CHARS.sub("", normalized)
    lines = [re.sub(r"[ \t]+$", "", line) for line in normalized.split("\n")]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def collapse_whitespace(text: str) -> str:
    return " ".join(clean_text(text).split())
