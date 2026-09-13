"""日期规范化（T013）。

只在能证明到“日”精度时返回 ISO 日期；仅到年月、非法日期或无法验证时返回 None，
由调用方保留 raw_date，绝不补造日期。放在叶子模块供解析器与标准化模块共用。
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional, Tuple

from crawler.normalize.text_utils import collapse_whitespace

# 月份名：全名在前、缩写在后（"September|Sept|Sep" 依序匹配），兼容 "12 SEP 2026" 类站点格式。
MONTH_NAME_PATTERN = (
    "January|February|March|April|May|June|July|August|September|October|November|December|"
    "Sept|Sep|Aug|Jul|Jun|Jan|Feb|Mar|Apr|Oct|Nov|Dec"
)

DATE_PATTERNS: Tuple[Tuple[re.Pattern, str], ...] = (
    (re.compile(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?![\d])"), "ymd"),
    (re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日"), "ymd"),
    (
        re.compile(r"(\d{1,2})\s+(" + MONTH_NAME_PATTERN + r")\s+(\d{4})", re.IGNORECASE),
        "dmy_en",
    ),
    (
        re.compile(r"(" + MONTH_NAME_PATTERN + r")\s+(\d{1,2}),?\s+(\d{4})", re.IGNORECASE),
        "mdy_en",
    ),
)
EN_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9,
    "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

SUPPORTED_DATE_FORMATS = (
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
)


def normalize_date(raw: Optional[str]) -> Optional[str]:
    """返回 ISO 日期或 None；只有能验证到日精度时才回填。"""
    if not raw or not raw.strip():
        return None
    text = collapse_whitespace(raw)
    for pattern, kind in DATE_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        try:
            if kind == "ymd":
                year, month, day = (int(part) for part in match.groups())
            elif kind == "dmy_en":
                day = int(match.group(1))
                month = EN_MONTHS[match.group(2).lower()]
                year = int(match.group(3))
            else:
                month = EN_MONTHS[match.group(1).lower()]
                day = int(match.group(2))
                year = int(match.group(3))
            return datetime(year, month, day).date().isoformat()
        except ValueError:
            return None
    for date_format in SUPPORTED_DATE_FORMATS:
        try:
            return datetime.strptime(text, date_format).date().isoformat()
        except ValueError:
            continue
    return None
