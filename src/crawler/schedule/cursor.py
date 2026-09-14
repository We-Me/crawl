"""发现游标（S5-06；R1 覆盖口径）：按入口保存分页续接位置。

列表/搜索/接口发现受每页请求预算与 --max-pages/--max-items 限制时，未翻到的页不能
丢掉：重新 collect 若每次都从第一页开始，预算会被已看过的页反复消耗。这里按
“来源 + 方式 + 入口 + 运行范围”保存下一页位置，使有限预算多轮运行继续向后推进：

- 站点末页、适配规则终点：游标置 completed（覆盖轮 +1），下次重新从入口开始新一轮
  复查；已登记 URL 不再触发“整页已知即完成”（`incremental_head_checked` 是已失效的
  历史标记），已知目标按更新策略进入 refresh，新链接照常登记；
- 页数/项目上限、预算停止、请求失败、循环：游标保持 active，指向尚未取得的页；
  复查轮因此跨多轮推进，最终覆盖整入口，不会无限停在入口页；
- 游标只影响从哪一页继续，不放宽访问边界、robots、限速与预算。

计数口径（R1）：`pass_pages` 是本次覆盖轮已覆盖页数，`coverage_rounds` 是已完成
的覆盖轮次；`pages_fetched`/`targets_found` 只是累计请求计数，不能当作覆盖页数。

游标是抓取行为索引，不属于六项交付成果；格式变化在结构对照中登记。
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Optional

from crawler.output.atomic import atomic_write_json, file_lock
from crawler.output.layout import DeliveryLayout

logger = logging.getLogger(__name__)

CURSOR_ACTIVE = "active"
CURSOR_COMPLETED = "completed"


@dataclass(frozen=True)
class DiscoveryCursor:
    """一个入口的分页续接位置。

    ``last_commit_page``/``last_commit_digest``（R4）：本入口最后一次已提交目标的
    页及其目标摘要。游标推进前先提交目标；崩溃后重启重放同一页时按该标记识别
    重放，幂等入队，不把已处理目标整体转成 refresh。
    """

    key: str
    source_id: str
    stage: str
    entry: str
    scope_start_date: Optional[str] = None
    next_url: Optional[str] = None
    state: str = CURSOR_ACTIVE
    pages_fetched: int = 0
    targets_found: int = 0
    updated_at: Optional[str] = None
    note: Optional[str] = None
    last_commit_page: Optional[str] = None
    last_commit_digest: Optional[str] = None
    # R1 覆盖口径：pass_pages 是本次覆盖轮已覆盖页数（到终点或从头开始新一轮时归零），
    # coverage_rounds 是已完成的覆盖轮次。pages_fetched 只是累计请求页数，两者不能混用。
    pass_pages: int = 0
    coverage_rounds: int = 0
    last_round_completed_at: Optional[str] = None


class DiscoveryCursorError(ValueError):
    """游标文件损坏或参数非法。"""


def cursor_key(
    *, source_id: str, stage: str, entry: str, scope_start_date: Optional[str]
) -> str:
    """游标身份：同一来源、方式、入口、运行范围共用一个续接位置。"""
    return f"{source_id}|{stage}|{scope_start_date or '-'}|{entry}"


class DiscoveryCursorStore:
    """按数据根保存发现游标；JSON 原子写入。"""

    def __init__(self, data_dir: Path) -> None:
        self.path = DeliveryLayout(data_dir).cursor_path

    def load(self) -> Dict[str, DiscoveryCursor]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise DiscoveryCursorError(f"发现游标文件损坏：{self.path}") from exc
        rows = payload.get("cursors") or {}
        return {key: DiscoveryCursor(**row) for key, row in rows.items()}

    def get(self, key: str) -> Optional[DiscoveryCursor]:
        return self.load().get(key)

    def entry_lock_path(self, key: str) -> Path:
        """入口级运行锁基路径（跨进程）：同一入口同时只有一个运行推进游标（R4）。"""
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
        return self.path.with_name(f"{self.path.name}.run-{digest}")

    def save(self, cursor: DiscoveryCursor) -> DiscoveryCursor:
        """保存一个入口的续接位置；读-改-写在 file_lock 内完成，不覆盖并发运行的游标。"""
        with file_lock(self.path):
            cursors = self.load()
            cursors[cursor.key] = cursor
            rows = {key: asdict(value) for key, value in sorted(cursors.items())}
            payload = {"version": "0.1.0", "cursors": rows}
            atomic_write_json(self.path, payload)
        logger.debug("发现游标更新 key=%s state=%s next=%s", cursor.key, cursor.state, cursor.next_url)
        return cursor
