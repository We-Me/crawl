"""按资料类型的增量策略（T015/FR-016）。

- news：按发布时间增量，只发现上次成功之后的新条目；
- law：检查状态与哈希，用 ETag/Last-Modified 做条件请求；
- statistics：按版本/年份检查，仅在新版本出现时更新；
- general：通用条件请求。

条件请求 304 表示“未变化”，调用方据此复用此前成功原件与账本，不得生成新文档或
新账本行，也不得用空正文冒充新响应。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Mapping, Optional

from crawler.schedule.state import ResourceState

logger = logging.getLogger(__name__)

RESOURCE_KINDS = ("news", "law", "statistics", "general")

FETCH_ALWAYS = "fetch_always"
CONDITIONAL = "conditional"
DISCOVER_NEW = "discover_new"
CHECK_VERSION = "check_version"


class IncrementalConfigError(ValueError):
    """资料类型或状态配置非法。"""


@dataclass(frozen=True)
class IncrementalPlan:
    action: str
    resource_kind: str
    headers: Mapping[str, str]
    reason: str
    last_publication_date: Optional[str] = None
    last_version: Optional[str] = None

    def as_row(self) -> dict:
        row = {
            "action": self.action,
            "resource_kind": self.resource_kind,
            "reason": self.reason,
            "conditional": bool(self.headers),
        }
        if self.last_publication_date:
            row["last_publication_date"] = self.last_publication_date
        if self.last_version:
            row["last_version"] = self.last_version
        return row


def plan_incremental(
    resource_kind: Optional[str],
    state: Optional[ResourceState],
    *,
    now: datetime,
) -> IncrementalPlan:
    """决定本次获取方式；不支持的类型或无状态时按普通获取处理。"""
    kind = (resource_kind or "general").lower()
    if kind not in RESOURCE_KINDS:
        raise IncrementalConfigError(f"未知资料类型：{resource_kind!r}；允许 {list(RESOURCE_KINDS)}")
    headers = conditional_headers(state)
    if kind == "news":
        return IncrementalPlan(
            action=DISCOVER_NEW,
            resource_kind=kind,
            headers=headers,
            reason="按发布时间增量发现新条目",
            last_publication_date=state.last_publication_date if state else None,
        )
    if kind == "statistics":
        return IncrementalPlan(
            action=CHECK_VERSION,
            resource_kind=kind,
            headers=headers,
            reason="按版本/年份检查，仅新版本更新",
            last_version=state.last_version if state else None,
        )
    return IncrementalPlan(
        action=CONDITIONAL if headers else FETCH_ALWAYS,
        resource_kind=kind,
        headers=headers,
        reason="条件请求检查状态与哈希" if headers else "无此前校验信息，完整获取",
    )


def conditional_headers(state: Optional[ResourceState]) -> dict:
    """由 ETag/Last-Modified 生成条件请求头；不使用弱校验以外的猜测。"""
    if state is None:
        return {}
    headers = {}
    if state.etag:
        headers["If-None-Match"] = state.etag
    if state.last_modified:
        headers["If-Modified-Since"] = state.last_modified
    return headers


def is_newer_publication(publication_date: Optional[str], last_publication_date: Optional[str]) -> bool:
    """新闻增量：只判断可比较的 ISO 日期，无法比较时按需要更新处理。"""
    if not publication_date:
        return True
    if not last_publication_date:
        return True
    return publication_date > last_publication_date
