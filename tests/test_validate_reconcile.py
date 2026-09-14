"""S5-06：队列与失败账对账校验（`crawl check` 的一部分）。"""

import json

from crawler.output.layout import DeliveryLayout
from crawler.validate.reconcile import reconcile_queue_and_failures


def _write_pending(data_dir, items):
    path = DeliveryLayout(data_dir).pending_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"items": items}, ensure_ascii=False), encoding="utf-8")


def _write_failures(data_dir, rows):
    path = DeliveryLayout(data_dir).failures_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _failure(url, final_action, message="x"):
    return {
        "source_id": "S",
        "url": url,
        "time": "2026-09-14T00:00:00+08:00",
        "stage": "fetch",
        "error_type": "request_error",
        "message": message,
        "retry_count": 0 if final_action == "retry_later" else 1,
        "final_action": final_action,
    }


def test_failed_item_closed_in_ledger_is_a_contradiction(tmp_path):
    """第 85 轮回归：队列 failed 与失败账 recovered 并存必须报出。"""
    data = tmp_path / "data"
    url = "https://example.invalid/a.pdf"
    _write_pending(data, {"k1": {"key": "k1", "url": url, "state": "failed"}})
    _write_failures(
        data,
        [_failure(url, "retry_later"), _failure(url, "recovered", "补抓成功，账本与文档已更新")],
    )

    report = reconcile_queue_and_failures(data)

    assert report.ok is False
    assert report.items_by_state == {"failed": 1}
    assert report.open_failures == 0
    assert report.problems[0]["ledger_action"] == "recovered"
    assert report.problems[0]["key"] == "k1"


def test_failed_item_with_open_ledger_is_consistent(tmp_path):
    """失败账仍未关闭属于正常待补抓状态：只计数，不判失败。"""
    data = tmp_path / "data"
    url = "https://example.invalid/b.pdf"
    _write_pending(data, {"k1": {"key": "k1", "url": url, "state": "failed"}})
    _write_failures(data, [_failure(url, "retry_later")])

    report = reconcile_queue_and_failures(data)

    assert report.ok is True and report.problems == []
    assert report.open_failures == 1


def test_processed_item_with_closed_ledger_is_consistent(tmp_path):
    data = tmp_path / "data"
    url = "https://example.invalid/c.pdf"
    _write_pending(data, {"k1": {"key": "k1", "url": url, "state": "processed"}})
    _write_failures(data, [_failure(url, "recovered")])

    report = reconcile_queue_and_failures(data)

    assert report.ok is True
    assert report.items_by_state == {"processed": 1}
    assert report.open_failures == 0


def test_missing_files_report_empty(tmp_path):
    report = reconcile_queue_and_failures(tmp_path / "data")

    assert report.ok is True
    assert report.items_total == 0 and report.items_by_state == {}
    assert report.as_row() == {
        "ok": True,
        "items_total": 0,
        "items_by_state": {},
        "open_failures": 0,
        "problems": [],
    }
