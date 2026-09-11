"""七类更新频率与触发关系（T015/KR-012）。

表内周期与触发来自 S2 §12 的建议（原文 P0 为 A/B/C/G），本实现按“建议”登记为
候选策略，不当作已批准排期：启用哪些类别、实际周期与历史范围仍属 Q01/Q13 待决，
未在来源配置中显式声明时不做周期判定。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Mapping, Optional, Sequence, Tuple

TRIGGERS = (
    "major_document",
    "new_law",
    "historical_backfill",
    "boundary_change",
)


class ScheduleConfigError(ValueError):
    """频率或触发配置非法。"""


@dataclass(frozen=True)
class UpdateRule:
    key: str
    label: str
    period_days: Optional[int]
    triggers: Tuple[str, ...]
    priority: str
    sync_with: Tuple[str, ...] = ()
    evidence: str = "S2 §12；S4 三 §12（建议值，Q13 未决）"


UPDATE_RULES: Tuple[UpdateRule, ...] = (
    UpdateRule("A", "协定", 7, ("major_document",), "P0"),
    UpdateRule("B", "事件", 1, (), "P0"),
    UpdateRule("C", "法规", 7, ("new_law",), "P0"),
    UpdateRule("D", "统计数据", 1, ("historical_backfill",), "P1"),
    UpdateRule("E", "文化与地理", 30, (), "P1"),
    UpdateRule("F", "区域与地图", 90, ("boundary_change",), "P1"),
    UpdateRule("G", "术语", None, (), "P0", sync_with=("A", "B", "C", "F")),
)
RULE_BY_KEY = {rule.key: rule for rule in UPDATE_RULES}


def get_rule(key: str) -> UpdateRule:
    try:
        return RULE_BY_KEY[key.upper()]
    except KeyError as exc:
        raise ScheduleConfigError(f"未知类别：{key!r}；允许 {sorted(RULE_BY_KEY)}") from exc


def frequency_table() -> list:
    """供文档、证据与配置核查使用的七类建议频率表。"""
    return [
        {
            "key": rule.key,
            "label": rule.label,
            "period_days": rule.period_days,
            "triggers": list(rule.triggers),
            "priority": rule.priority,
            "sync_with": list(rule.sync_with),
            "evidence": rule.evidence,
        }
        for rule in UPDATE_RULES
    ]


def effective_period_days(
    key: str,
    *,
    period_days: Optional[int] = None,
    sync_periods: Optional[Mapping[str, Optional[int]]] = None,
) -> Optional[int]:
    """显式 period_days 优先；G 类按同步对象的周期取最短值。未配置返回 None。"""
    rule = get_rule(key)
    if period_days is not None:
        if period_days <= 0:
            raise ScheduleConfigError(f"period_days 必须为正数：{period_days!r}")
        return int(period_days)
    if rule.period_days is not None:
        return rule.period_days
    periods = [(sync_periods or {}).get(sync_key) for sync_key in rule.sync_with]
    periods = [period for period in periods if period]
    return min(periods) if periods else None


def is_periodic_due(
    key: str,
    *,
    last_success_at: Optional[datetime],
    now: datetime,
    period_days: Optional[int] = None,
    sync_periods: Optional[Mapping[str, Optional[int]]] = None,
) -> Optional[bool]:
    """返回是否到期；周期无法确定时返回 None（不猜测、不自动调度）。"""
    period = effective_period_days(key, period_days=period_days, sync_periods=sync_periods)
    if period is None:
        return None
    if last_success_at is None:
        return True
    return now - last_success_at >= timedelta(days=period)


def is_triggered(key: str, event: str) -> bool:
    """事件是否触发该类别的立即更新；未知事件抛错，避免静默忽略。"""
    if event not in TRIGGERS:
        raise ScheduleConfigError(f"未知触发事件：{event!r}；允许 {list(TRIGGERS)}")
    return event in get_rule(key).triggers
