"""S5-06 并发写入回归：多个 collect 进程共用一个数据根时状态不得互相覆盖。

第 62 轮真实运行发现：固定临时名 ``<file>.tmp`` 在并发 ``os.replace`` 下互相覆盖，
部分运行以 FileNotFoundError 崩溃；“读-改-写”无锁时后写者会整段丢失先写者的更新。
这里用多线程模拟并发运行，验证待处理项与发现游标既不报错也不丢更新。
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from crawler.discover.discoverer import DiscoveredTarget
from crawler.output.atomic import atomic_write_text
from crawler.schedule.cursor import DiscoveryCursor, DiscoveryCursorStore
from crawler.schedule.pending import STATE_PROCESSED, PendingStore

NOW = datetime(2026, 9, 13, 10, 0, 0, tzinfo=timezone(timedelta(hours=8)))


def _run_concurrently(worker, count):
    barrier = threading.Barrier(count)

    def wrapped(index):
        barrier.wait()
        return worker(index)

    with ThreadPoolExecutor(max_workers=count) as pool:
        futures = [pool.submit(wrapped, index) for index in range(count)]
        return [future.result() for future in futures]


def test_concurrent_pending_marks_keep_all_updates(tmp_path):
    store = PendingStore(tmp_path / "data")
    count = 8
    targets = [
        DiscoveredTarget(url=f"https://example.invalid/item/{index}", discovery_method="list")
        for index in range(count)
    ]
    store.enqueue_targets(
        source_id="SRC",
        targets=targets,
        scope_start_date="2026-09-06",
        enqueued_at=NOW.isoformat(),
    )
    keys = [item.key for item in store.candidates("SRC")]
    assert len(keys) == count

    _run_concurrently(
        lambda index: store.mark(
            keys[index], state=STATE_PROCESSED, attempted_at=NOW.isoformat()
        ),
        count,
    )

    items = store.load()
    states = {items[key].state for key in keys}
    assert states == {STATE_PROCESSED}, "并发标记不得丢失其他运行的更新"


def test_concurrent_cursor_saves_keep_all_entries(tmp_path):
    store = DiscoveryCursorStore(tmp_path / "data")
    count = 8

    def save(index):
        entry = f"https://example.invalid/list/page/{index}"
        return store.save(
            DiscoveryCursor(
                key=f"SRC|list|2026-09-06|{entry}",
                source_id="SRC",
                stage="list",
                entry=entry,
                scope_start_date="2026-09-06",
                next_url=f"{entry}?next=1",
                state="active",
                pages_fetched=index + 1,
                targets_found=10 * (index + 1),
                updated_at=NOW.isoformat(),
            )
        )

    _run_concurrently(save, count)

    cursors = store.load()
    assert len(cursors) == count, "并发保存游标不得丢掉其他入口的续接位置"


def test_atomic_write_text_replaces_whole_file_without_leftover_tmp(tmp_path):
    path = tmp_path / "logs" / "metrics.json"
    atomic_write_text(path, '{"run": 1}\n')
    atomic_write_text(path, '{"run": 2}\n')
    assert path.read_text(encoding="utf-8") == '{"run": 2}\n'
    leftovers = [item.name for item in path.parent.iterdir() if ".tmp-" in item.name]
    assert leftovers == [], "临时文件必须用唯一名并在替换后不留残留"
