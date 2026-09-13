"""发现游标（S5-06）：按入口保存分页续接位置。

列表/搜索/接口发现受每页请求预算与 --max-pages/--max-items 限制时，未翻到的页不能
丢掉：重新 collect 若每次都从第一页开始，预算会被已看过的页反复消耗。这里按
“来源 + 方式 + 入口 + 运行范围”保存下一页位置，使有限预算多轮运行继续向后推进：

- 站点末页、适配规则终点：游标置 completed，下次仍从入口核对；
- 页数/项目上限、预算停止、请求失败、循环：游标保持 active，指向尚未取得的页；
- 游标只影响从哪一页继续，不放宽访问边界、robots、限速与预算。

游标是抓取行为索引，不属于六项交付成果；格式变化在结构对照中登记。
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Optional

from crawler.output.layout import DeliveryLayout

logger = logging.getLogger(__name__)

CURSOR_ACTIVE = "active"
CURSOR_COMPLETED = "completed"


@dataclass(frozen=True)
class DiscoveryCursor:
    """一个入口的分页续接位置。"""

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

    def save(self, cursor: DiscoveryCursor) -> DiscoveryCursor:
        cursors = self.load()
        cursors[cursor.key] = cursor
        rows = {key: asdict(value) for key, value in sorted(cursors.items())}
        payload = {"version": "0.1.0", "cursors": rows}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        with tmp.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, self.path)
        logger.debug("发现游标更新 key=%s state=%s next=%s", cursor.key, cursor.state, cursor.next_url)
        return cursor
