"""S5-06：队列与失败账对账校验（`crawl check` 的一部分）。"""

import json

from crawler.output.layout import DeliveryLayout
from crawler.validate.reconcile import reconcile_queue_and_failures


def _write_pending(data_dir, items):
    path = DeliveryLayout(data_dir).pending_path
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = {}
    for key, item in items.items():
        row = {"key": key, "source_id": "S", "kind": "target", "state": "pending"}
        row.update(item)
        rows[key] = row
    path.write_text(
        json.dumps({"version": "0.1.0", "items": rows}, ensure_ascii=False), encoding="utf-8"
    )


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
        "open_failures_by_stage": {},
        "problems": [],
    }


# ---------- R6：损坏状态必须使对账失败 ----------


def _pending_path(data_dir):
    return DeliveryLayout(data_dir).pending_path


def test_truncated_pending_json_is_a_problem_and_file_is_untouched(tmp_path):
    """R6：截断的 pending_items.json 不能被当作空队列；检查不得改写输入。"""
    data = tmp_path / "data"
    path = _pending_path(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    original = '{"version": "0.1.0", "items": {"k1": {"key": "k1"'
    path.write_text(original, encoding="utf-8")
    before = path.read_bytes()

    report = reconcile_queue_and_failures(data)

    assert report.ok is False
    assert report.items_total == 0
    assert len(report.problems) == 1
    problem = report.problems[0]
    assert problem["file"] == "manifests/pending_items.json"
    assert "JSON 语法错误" in problem["message"]
    assert path.read_bytes() == before, "只读检查不得覆盖或重建损坏文件"
    assert report.as_row()["ok"] is False


def test_pending_items_wrong_type_is_a_problem(tmp_path):
    """R6：items 不是映射时报结构错误，不静默转成空队列。"""
    data = tmp_path / "data"
    _pending_path(data).parent.mkdir(parents=True, exist_ok=True)
    _pending_path(data).write_text(
        json.dumps({"version": "0.1.0", "items": ["k1"]}), encoding="utf-8"
    )

    report = reconcile_queue_and_failures(data)

    assert report.ok is False
    assert any("items 应为 JSON 对象" in problem["message"] for problem in report.problems)
    assert report.items_total == 0


def test_pending_entry_must_be_object_with_valid_identity(tmp_path):
    """R6：非法条目（非对象、缺身份、非法状态/种类、身份键不一致）逐条报错。"""
    data = tmp_path / "data"
    _pending_path(data).parent.mkdir(parents=True, exist_ok=True)
    _pending_path(data).write_text(
        json.dumps(
            {
                "version": "0.1.0",
                "items": {
                    "k1": "not-an-object",
                    "k2": {"key": "k2", "source_id": "S", "kind": "target"},
                    "k3": {
                        "key": "k3",
                        "source_id": "S",
                        "kind": "target",
                        "url": "https://example.invalid/a",
                        "state": "done",
                    },
                    "k4": {
                        "key": "k4",
                        "source_id": "S",
                        "kind": "attachment",
                        "url": "https://example.invalid/b",
                        "state": None,
                    },
                    "k5": {
                        "key": "other-key",
                        "source_id": "S",
                        "kind": "target",
                        "url": "https://example.invalid/c",
                        "state": "pending",
                    },
                    "k6": {
                        "key": "k6",
                        "source_id": "S",
                        "kind": "widget",
                        "url": "https://example.invalid/d",
                        "state": "pending",
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    report = reconcile_queue_and_failures(data)

    assert report.ok is False
    messages = " | ".join(problem["message"] for problem in report.problems)
    assert "条目 'k1' 应为 JSON 对象" in messages
    assert "缺少合法身份字段" in messages
    assert "状态非法" in messages
    assert "种类非法" in messages
    assert "身份不一致" in messages
    assert report.items_total == 0, "没有条目通过结构校验"


def test_corrupted_failure_ledger_is_a_problem(tmp_path):
    """R6：失败账的截断行与非对象行都要报错，不能按零条记录通过。"""
    data = tmp_path / "data"
    _write_pending(data, {"k1": {"key": "k1", "url": "https://example.invalid/a", "state": "failed"}})
    path = DeliveryLayout(data).failures_path
    path.write_text(
        json.dumps(_failure("https://example.invalid/a", "retry_later"), ensure_ascii=False)
        + "\n"
        + '{"source_id": "S", "url": "https://example.invalid/b"\n'
        + '["not-an-object"]\n',
        encoding="utf-8",
    )
    before = path.read_bytes()

    report = reconcile_queue_and_failures(data)

    assert report.ok is False
    assert report.open_failures == 1, "已解析行仍参与计数"
    assert len(report.problems) == 2
    assert all(problem["file"] == "manifests/failed_records.jsonl" for problem in report.problems)
    assert any("JSON 语法错误" in problem["message"] for problem in report.problems)
    assert any("必须是 JSON 对象" in problem["message"] for problem in report.problems)
    assert path.read_bytes() == before


def test_legal_empty_states_still_pass(tmp_path):
    """R6：缺失文件、items 为空映射、空失败账都是合法零记录状态。"""
    data = tmp_path / "data"
    _pending_path(data).parent.mkdir(parents=True, exist_ok=True)
    _pending_path(data).write_text(
        json.dumps({"version": "0.1.0", "items": {}}), encoding="utf-8"
    )
    DeliveryLayout(data).failures_path.write_text("", encoding="utf-8")

    report = reconcile_queue_and_failures(data)

    assert report.ok is True and report.problems == []
    assert report.items_total == 0 and report.open_failures == 0


def test_read_error_prevents_cascading_contradiction(tmp_path):
    """R6：状态不可信时不再做“某任务已恢复”的推断，只报告读取问题。"""
    data = tmp_path / "data"
    _write_failures(data, [_failure("https://example.invalid/a", "recovered")])
    _pending_path(data).parent.mkdir(parents=True, exist_ok=True)
    _pending_path(data).write_text("{broken", encoding="utf-8")

    report = reconcile_queue_and_failures(data)

    assert report.ok is False
    assert len(report.problems) == 1
    assert "JSON 语法错误" in report.problems[0]["message"]


# ---------- C：身份统一（来源 + URL + 范围 + 母文档） ----------


def test_cross_source_closed_row_does_not_close_other_source_item(tmp_path):
    """C：同一 URL 在别的来源已关闭时，本来源仍未关闭的失败不得被掩盖。"""
    data = tmp_path / "data"
    url = "https://example.invalid/shared.pdf"
    _write_pending(data, {"k1": {"key": "k1", "source_id": "A", "url": url, "state": "failed"}})
    _write_failures(
        data,
        [
            {**_failure(url, "retry_later"), "source_id": "A"},
            {**_failure(url, "recovered"), "source_id": "B"},
        ],
    )

    report = reconcile_queue_and_failures(data)

    assert report.ok is True, "来源 B 的 closed 行不是同一对象的处置"
    assert report.open_failures == 1, "来源 A 的失败仍未关闭"

    # 同一来源的 closed 行仍然按同一身份判为矛盾
    _write_failures(
        data,
        [
            {**_failure(url, "retry_later"), "source_id": "A"},
            {**_failure(url, "recovered"), "source_id": "A"},
        ],
    )
    report = reconcile_queue_and_failures(data)
    assert report.ok is False and report.problems[0]["ledger_action"] == "recovered"


def test_cross_source_open_failures_are_counted_separately(tmp_path):
    data = tmp_path / "data"
    url = "https://example.invalid/shared.pdf"
    _write_failures(
        data,
        [
            {**_failure(url, "retry_later"), "source_id": "A"},
            {**_failure(url, "retry_later", "另一来源"), "source_id": "B"},
        ],
    )

    report = reconcile_queue_and_failures(data)

    assert report.ok is True and report.open_failures == 2, "身份含来源，两个来源各自未关闭"


def test_cross_source_doc_id_identity_does_not_close_item(tmp_path):
    """C：来源不同、doc_id 相同时，本来源待处理项不因别的来源处置而被关闭。"""
    data = tmp_path / "data"
    url = "https://example.invalid/shared.pdf"
    _write_pending(
        data,
        {
            "k1": {
                "key": "k1",
                "source_id": "A",
                "url": url,
                "state": "failed",
                "doc_id": "DOC-1",
            }
        },
    )
    _write_failures(
        data,
        [
            {
                **_failure(url, "retry_later"),
                "source_id": "A",
                "doc_id": "DOC-1",
            },
            {
                **_failure(url, "skip"),
                "source_id": "B",
                "doc_id": "DOC-1",
            },
        ],
    )

    report = reconcile_queue_and_failures(data)

    assert report.ok is True and report.problems == []
    assert report.open_failures == 1, "来源 A 的失败仍未关闭"


def test_cross_stage_rows_do_not_close_each_other(tmp_path):
    """C：同一对象不同阶段各自计数；已关闭的 fetch 行不得掩盖未关闭的 parse 行。"""
    data = tmp_path / "data"
    url = "https://example.invalid/page.html"
    _write_pending(data, {"k1": {"key": "k1", "url": url, "state": "failed"}})
    _write_failures(
        data,
        [
            {**_failure(url, "skip"), "stage": "fetch"},
            {**_failure(url, "retry_later"), "stage": "parse", "error_type": "parse_error"},
        ],
    )

    report = reconcile_queue_and_failures(data)

    assert report.open_failures == 1, "parse 阶段仍未关闭"
    assert report.open_failures_by_stage == {"parse": 1}
    assert report.ok is True and report.problems == [], "对象仍有未关闭失败，不产生矛盾"


def test_item_failed_with_all_stages_closed_is_a_contradiction(tmp_path):
    """C：对象的所有阶段都按 recovered/skip 关闭后，队列 failed 仍是矛盾（带阶段清单）。"""
    data = tmp_path / "data"
    url = "https://example.invalid/page.html"
    _write_pending(data, {"k1": {"key": "k1", "url": url, "state": "failed"}})
    _write_failures(
        data,
        [
            {**_failure(url, "recovered"), "stage": "fetch"},
            {**_failure(url, "skip"), "stage": "parse", "error_type": "parse_error"},
        ],
    )

    report = reconcile_queue_and_failures(data)

    assert report.ok is False
    assert report.open_failures == 0 and report.open_failures_by_stage == {}
    assert report.problems[0]["ledger_stages"] == ["fetch", "parse"]
