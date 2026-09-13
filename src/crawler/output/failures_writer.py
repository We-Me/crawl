"""失败账：按失败操作记录阶段、错误类型与处置（T016 的前置）。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from crawler.output.jsonl import append_jsonl
from crawler.output.layout import DeliveryLayout

logger = logging.getLogger(__name__)

FAILURE_STAGES = ("discover", "fetch", "parse", "normalize", "validate")
FINAL_ACTIONS = ("record_only", "retry_later", "skip", "recovered", "manual_review")


class FailureWriter:
    def __init__(self, data_dir: Path) -> None:
        self.path = DeliveryLayout(data_dir).failures_path

    def record(
        self,
        *,
        source_id: str,
        url: str,
        time: str,
        stage: str,
        error_type: str,
        message: str,
        retry_count: int = 0,
        final_action: str = "record_only",
        crawl_id: Optional[str] = None,
        referrer_url: Optional[str] = None,
        scope_start_date: Optional[str] = None,
    ) -> dict:
        if stage not in FAILURE_STAGES:
            raise ValueError(f"未知失败阶段：{stage!r}")
        if final_action not in FINAL_ACTIONS:
            raise ValueError(f"未知处置：{final_action!r}")
        row = {
            "source_id": source_id,
            "url": url,
            "time": time,
            "stage": stage,
            "error_type": error_type,
            "message": message,
            "retry_count": int(retry_count),
            "final_action": final_action,
        }
        if crawl_id is not None:
            row["crawl_id"] = crawl_id
        if referrer_url is not None:
            row["referrer_url"] = referrer_url
        if scope_start_date is not None:
            # 运行范围（--start-date）随失败一起保存：补抓沿用原范围，不混入新窗口。
            row["scope_start_date"] = scope_start_date
        append_jsonl(self.path, [row])
        logger.warning(
            "失败记录 stage=%s url=%s type=%s message=%s", stage, url, error_type, message
        )
        return row
