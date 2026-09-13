"""运行时采集范围（本轮新增）：起始日期与日期判定（T015/T026）。

`--start-date YYYY-MM-DD` 是本次运行的显式范围，语义固定为：

- 以**内容发布日期**（document.publication_date）为包含式下界：发布日期等于起始日期
  属于范围内；早于起始日期为范围外；
- 抓取时间不参与日期判定，不能冒充发布日期；
- 发布日期未知或解析失败时保留候选并记录原因，不静默丢弃；
- 未设置起始日期时不做日期判定（no_scope），不自动回溯全部历史。

站点日期查询（若已核验配置）在发现阶段使用同一范围；页面级判定始终执行，
两者分别记录在同一运行的 scope 记录中。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

IN_WINDOW = "in_window"
BEFORE_START_DATE = "before_start_date"
DATE_UNKNOWN = "date_unknown"
NO_SCOPE = "no_scope"

RETAINED_KINDS = (IN_WINDOW, NO_SCOPE, DATE_UNKNOWN)

DATE_SEMANTICS = (
    "内容发布日期为包含式下界；抓取时间不参与判定；"
    "发布日期未知或解析失败时保留候选并记录原因"
)


class ScopeConfigError(ValueError):
    """起始日期参数非法。"""


def parse_start_date(text: Optional[str]) -> Optional[date]:
    """把 CLI 字符串解析为日期；空值返回 None，非法值明确报错。"""
    if text is None:
        return None
    value = str(text).strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ScopeConfigError(f"--start-date 必须是 YYYY-MM-DD：{text!r}") from exc


@dataclass(frozen=True)
class DateDecision:
    """一条目标（或附件母页）的日期判定结果。"""

    kind: str
    publication_date: Optional[str] = None
    reason: str = ""

    @property
    def retained(self) -> bool:
        """范围内或日期未知都保留；仅“早于起始日期”不进本次交付。"""
        return self.kind in RETAINED_KINDS

    def as_row(self, url: Optional[str] = None) -> dict:
        row = {
            "decision": self.kind,
            "publication_date": self.publication_date,
            "reason": self.reason or None,
        }
        if url:
            row["url"] = url
        return row


@dataclass(frozen=True)
class RunScope:
    """一次采集/补抓的运行范围；恢复任务沿用原范围。"""

    start_date: Optional[date] = None

    @property
    def active(self) -> bool:
        return self.start_date is not None

    def as_row(self) -> dict:
        return {
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "inclusive": True,
            "date_field": "publication_date",
            "date_semantics": DATE_SEMANTICS,
        }

    def decide(self, publication_date: Optional[str]) -> DateDecision:
        """按发布日期判定目标是否属于本次范围。"""
        if self.start_date is None:
            return DateDecision(NO_SCOPE, publication_date, "未设置起始日期，不做日期判定")
        if not publication_date:
            return DateDecision(
                DATE_UNKNOWN, None, "发布日期未知或解析失败：保留候选并记录原因"
            )
        try:
            value = date.fromisoformat(str(publication_date))
        except ValueError:
            return DateDecision(
                DATE_UNKNOWN,
                str(publication_date),
                f"发布日期无法按日解析：{publication_date!r}；保留候选",
            )
        if value < self.start_date:
            return DateDecision(
                BEFORE_START_DATE,
                value.isoformat(),
                f"发布日期 {value.isoformat()} 早于起始日期 {self.start_date.isoformat()}",
            )
        return DateDecision(IN_WINDOW, value.isoformat(), "")
