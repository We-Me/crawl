"""统一请求预算与运行截止时间（NEXT-06，FR-001/NFR-003）。

一次 CLI 运行（collect 或 resume）共享一个预算对象：

- 每次实际 HTTP 尝试（robots.txt、重定向每一跳、重试、发现页、正文接口、附件）
  在发送前扣减；扣减失败即停止，不再发请求；
- 等待限速或 Retry-After 前检查剩余时间，网站要求的等待超过剩余时间就停止，
  不缩短网站等待去抢发请求；
- 截止时间使用单调时钟，与运行日志里的墙上时间分开；
- 预算停止是工程限制，不是网站失败：已归档原件、账本与文档保持不动，
  由上层报告 stop_reason 与非成功退出码。

max-items/max-tasks 是结果目标数量限制，不是请求预算，两者分别建模。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable, Optional

logger = logging.getLogger(__name__)

STOP_REQUEST_BUDGET = "request_budget"
STOP_DEADLINE = "deadline"
STOP_RATE_LIMIT_WAIT = "rate_limit_wait"
STOP_RETRY_WAIT = "retry_wait"
STOP_RETRY_AFTER_WAIT = "retry_after_wait"

STOP_REASON_TEXT = {
    STOP_REQUEST_BUDGET: "达到请求数上限",
    STOP_DEADLINE: "达到运行截止时间",
    STOP_RATE_LIMIT_WAIT: "限速等待超过剩余时间",
    STOP_RETRY_WAIT: "重试退避等待超过剩余时间",
    STOP_RETRY_AFTER_WAIT: "Retry-After 等待超过剩余时间",
}

# 单次同步请求/读取的最小超时：剩余时间更短时不再对半压缩到不可用值，
# 允许本次调用略微越过截止时间（最长终止延迟约等于该值 + 底层 socket 行为）。
MIN_ATTEMPT_SECONDS = 0.1


class BudgetConfigError(ValueError):
    """预算参数非法（上限必须为正）。"""


class BudgetStop(Exception):
    """预算或截止时间要求停止本次运行；与 FetchError 区分，不记为网站失败。"""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message


@dataclass
class RunBudget:
    """一次运行的请求数与截止时间预算；线程内单进程执行，不做跨进程协调。"""

    max_requests: Optional[int] = None
    deadline_seconds: Optional[float] = None
    clock: Optional[Callable[[], float]] = None
    started_at: Optional[float] = None
    used_requests: int = 0

    def __post_init__(self) -> None:
        if self.max_requests is not None and self.max_requests < 1:
            raise BudgetConfigError(f"请求上限必须为正整数：{self.max_requests!r}")
        if self.deadline_seconds is not None and self.deadline_seconds <= 0:
            raise BudgetConfigError(f"截止时间必须为正数秒：{self.deadline_seconds!r}")

    def now(self) -> float:
        return (self.clock or time.monotonic)()

    def start(self) -> "RunBudget":
        """开始计时；重复调用不重置起点（同一运行内预算不因换客户端而重置）。"""
        if self.started_at is None:
            self.started_at = self.now()
        return self

    def elapsed_seconds(self) -> float:
        if self.started_at is None:
            return 0.0
        return max(0.0, self.now() - self.started_at)

    def remaining_seconds(self) -> Optional[float]:
        if self.deadline_seconds is None:
            return None
        return max(0.0, float(self.deadline_seconds) - self.elapsed_seconds())

    def remaining_requests(self) -> Optional[int]:
        if self.max_requests is None:
            return None
        return max(0, int(self.max_requests) - self.used_requests)

    def begin_request(self) -> None:
        """发送前检查并扣减；不满足预算时抛 BudgetStop，调用方不得再发请求。"""
        self.start()
        remaining_time = self.remaining_seconds()
        if remaining_time is not None and remaining_time <= 0:
            raise BudgetStop(
                STOP_DEADLINE,
                f"运行已达截止时间 {self.deadline_seconds:.3g}s（已用 {self.elapsed_seconds():.2f}s）",
            )
        remaining = self.remaining_requests()
        if remaining is not None and remaining <= 0:
            raise BudgetStop(
                STOP_REQUEST_BUDGET,
                f"运行已发出 {self.used_requests} 个请求，达到请求上限 {self.max_requests}",
            )
        self.used_requests += 1

    def enforce_deadline(self) -> None:
        """流式读取按块检查截止时间；超时抛 BudgetStop 停止继续读取。"""
        remaining_time = self.remaining_seconds()
        if remaining_time is not None and remaining_time <= 0:
            raise BudgetStop(
                STOP_DEADLINE,
                f"下载中超过截止时间 {self.deadline_seconds:.3g}s（已用 {self.elapsed_seconds():.2f}s）",
            )

    def attempt_timeout(self, limit: float) -> float:
        """把单次连接/读取超时限制在剩余时间内（不低于 MIN_ATTEMPT_SECONDS）。"""
        remaining_time = self.remaining_seconds()
        if remaining_time is None:
            return float(limit)
        return max(MIN_ATTEMPT_SECONDS, min(float(limit), remaining_time))

    def wait(self, seconds: float, *, sleep: Callable[[float], None], reason: str) -> None:
        """执行网站要求的等待；超过剩余时间就停止，不缩短等待。"""
        seconds = max(0.0, float(seconds))
        remaining_time = self.remaining_seconds()
        if remaining_time is not None and seconds > remaining_time:
            raise BudgetStop(
                reason,
                f"{STOP_REASON_TEXT.get(reason, reason)}：需要等待 {seconds:.2f}s，"
                f"剩余 {remaining_time:.2f}s",
            )
        sleep(seconds)

    def as_row(self) -> dict:
        remaining_seconds = self.remaining_seconds()
        return {
            "max_requests": self.max_requests,
            "deadline_seconds": self.deadline_seconds,
            "used_requests": self.used_requests,
            "elapsed_seconds": round(self.elapsed_seconds(), 3),
            "remaining_requests": self.remaining_requests(),
            "remaining_seconds": (
                None if remaining_seconds is None else round(remaining_seconds, 3)
            ),
            "note": (
                "一次运行共享的请求数与截止时间预算；所有实际 HTTP 尝试发送前扣减，"
                "max-items/max-tasks 不计入"
            ),
        }
