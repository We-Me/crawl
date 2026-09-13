"""补抓策略与恢复计划（T016/FR-017）。

失败按阶段分流：发现/获取失败属网络阶段，可重取（refetch）；解析/标准化/校验
失败属本地阶段，原件已保留，可重解析（reparse）。永久 4xx（408/429 除外）不重试，
只记录；重试次数与退避按 RetryPolicy 计算，超过上限转人工处理（manual）。
补抓不删除历史失败记录，也不重写既有原件。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, List, Mapping, Optional, Sequence

logger = logging.getLogger(__name__)

NETWORK_STAGES = ("discover", "fetch")
LOCAL_STAGES = ("parse", "normalize", "validate")

REFETCH = "refetch"
REPARSE = "reparse"
MANUAL = "manual"

STATUS_PATTERN = re.compile(r"\b(?:HTTP\s*)?(\d{3})\b")
PERMANENT_4XX_EXCEPTIONS = (408, 429)


class RetryConfigError(ValueError):
    """重试配置非法。"""


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 60.0
    max_delay_seconds: float = 3600.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise RetryConfigError("max_attempts 至少为 1")
        if self.base_delay_seconds <= 0 or self.max_delay_seconds <= 0:
            raise RetryConfigError("退避时间必须为正数")


@dataclass(frozen=True)
class RecoveryTask:
    action: str
    url: str
    stage: str
    source_id: str
    attempt: int
    retry_count: int
    not_before: datetime
    crawl_id: Optional[str] = None
    referrer_url: Optional[str] = None
    raw_path: Optional[str] = None
    scope_start_date: Optional[str] = None
    reason: str = ""

    def as_row(self) -> dict:
        row = {
            "action": self.action,
            "url": self.url,
            "stage": self.stage,
            "source_id": self.source_id,
            "attempt": self.attempt,
            "retry_count": self.retry_count,
            "not_before": self.not_before.isoformat(),
        }
        for key in ("crawl_id", "referrer_url", "raw_path", "scope_start_date"):
            value = getattr(self, key)
            if value:
                row[key] = value
        if self.reason:
            row["reason"] = self.reason
        return row


def http_status_of(failure: Mapping) -> Optional[int]:
    """从记录或消息中取 HTTP 状态码；取不到返回 None，不猜测。"""
    status = failure.get("http_status")
    if isinstance(status, int) and not isinstance(status, bool):
        return status
    match = STATUS_PATTERN.search(str(failure.get("message") or ""))
    if match:
        return int(match.group(1))
    return None


def is_permanent(failure: Mapping) -> bool:
    status = http_status_of(failure)
    if status is None:
        return False
    return 400 <= status < 500 and status not in PERMANENT_4XX_EXCEPTIONS


def backoff_delay(attempt: int, policy: RetryPolicy) -> float:
    """attempt 为下一次尝试序号（1 起）。"""
    delay = policy.base_delay_seconds * (2 ** max(0, attempt - 1))
    return min(delay, policy.max_delay_seconds)


def plan_retry(
    failure: Mapping,
    *,
    policy: RetryPolicy,
    now: datetime,
    raw_path: Optional[str] = None,
) -> RecoveryTask:
    """返回本次补抓任务；不可自动补抓时 action=manual 并说明原因。"""
    stage = str(failure.get("stage") or "")
    retry_count = int(failure.get("retry_count") or 0)
    attempt = retry_count + 1
    common = {
        "url": str(failure.get("url") or ""),
        "stage": stage,
        "source_id": str(failure.get("source_id") or ""),
        "attempt": attempt,
        "retry_count": retry_count,
        "not_before": now + timedelta(seconds=backoff_delay(attempt, policy)),
        "crawl_id": failure.get("crawl_id"),
        "referrer_url": failure.get("referrer_url"),
        "scope_start_date": failure.get("scope_start_date"),
    }
    if stage in NETWORK_STAGES:
        if is_permanent(failure):
            return RecoveryTask(**common, action=MANUAL, reason="永久 4xx，只记录不重试")
        if attempt > policy.max_attempts:
            return RecoveryTask(**common, action=MANUAL, reason="重试次数已用尽")
        return RecoveryTask(**common, action=REFETCH, reason="网络阶段失败，重新获取")
    if stage in LOCAL_STAGES:
        if attempt > policy.max_attempts:
            return RecoveryTask(**common, action=MANUAL, reason="重解析次数已用尽")
        if not raw_path:
            return RecoveryTask(**common, action=MANUAL, reason="缺少可重解析的原件")
        return RecoveryTask(**common, action=REPARSE, raw_path=raw_path, reason="本地阶段失败，重解析原件")
    return RecoveryTask(**common, action=MANUAL, reason=f"未知阶段：{stage!r}")


def build_recovery_plan(
    failures: Iterable[Mapping],
    *,
    policy: Optional[RetryPolicy] = None,
    now: datetime,
    manifest_by_crawl_id: Optional[Mapping[str, Mapping]] = None,
) -> List[RecoveryTask]:
    """按当前未关闭的失败记录生成补抓计划；不产生任何副作用。"""
    policy = policy or RetryPolicy()
    manifest_by_crawl_id = manifest_by_crawl_id or {}
    tasks: List[RecoveryTask] = []
    for failure in failures:
        crawl_id = failure.get("crawl_id")
        raw_path = None
        if crawl_id and crawl_id in manifest_by_crawl_id:
            raw_path = manifest_by_crawl_id[crawl_id].get("raw_path")
        tasks.append(plan_retry(failure, policy=policy, now=now, raw_path=raw_path))
    return tasks


def plan_is_ready(task: RecoveryTask, *, now: datetime) -> bool:
    """退避未到时返回 False；调用方可保留任务等待下次运行。"""
    return now >= task.not_before


def summarize_plan(tasks: Sequence[RecoveryTask]) -> dict:
    counts: dict = {}
    for task in tasks:
        counts[task.action] = counts.get(task.action, 0) + 1
    return counts
