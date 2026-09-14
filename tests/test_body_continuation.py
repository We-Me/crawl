"""R2：正文分页/接口正文中断后的待续状态与续作（母页 304 不取消未完成正文）。

覆盖：三页正文在第二页前耗尽预算后，母页 304 重启仍能完成剩余页面、正文接口与
适用附件；全部原件可回指、块顺序正确且无重复拼接；正文请求失败进入失败链并保留
待续；跨多轮预算推进不重复取已取得部分；待续状态最终关闭；损坏的待续状态按完整
重取处理，不猜造进度。
"""

import json
from datetime import datetime, timedelta, timezone

from crawler.fetch.budget import RunBudget
from crawler.fetch.http_client import FetchLimits, HttpClient
from crawler.discover.discoverer import DiscoveredTarget
from crawler.output.jsonl import read_jsonl
from crawler.pipeline import CONTINUATION_KIND, CrawlPipeline
from crawler.validate.traceability import trace_delivery

FIXED_NOW = datetime(2026, 9, 14, 10, 0, 0, tzinfo=timezone(timedelta(hours=8)))
LIMITS = FetchLimits(request_rate_per_second=1000, max_retries=0)


def _page(title, body, head=""):
    return (
        '<!DOCTYPE html>\n<html lang="zh-CN"><head><meta charset="utf-8">'
        f"<title>{title}</title>{head}</head><body><main>{body}</main></body></html>"
    )


def _write_paged_site(root, with_api=True):
    """三页正文 + 可选正文接口 + 第三页附件；入口列表只含这一篇。"""
    api_head = (
        '<link rel="alternate" type="application/json" href="api_body.json">'
        if with_api
        else ""
    )
    (root / "r2_index.html").write_text(
        _page("R2 列表", '<ul><li><a href="r2_paged_1.html">三页正文</a></li></ul>'),
        encoding="utf-8",
    )
    (root / "r2_paged_1.html").write_text(
        _page(
            "三页正文（第一部分）",
            "<h1>三页正文样本</h1>"
            "<p>正文第一部分：背景与目标。</p>"
            '<p class="pager"><a rel="next" href="r2_paged_2.html">下一页</a></p>',
            api_head,
        ),
        encoding="utf-8",
    )
    (root / "r2_paged_2.html").write_text(
        _page(
            "三页正文（第二部分）",
            "<h1>三页正文样本（第二部分）</h1>"
            "<p>正文第二部分：具体安排。</p>"
            '<p class="pager"><a rel="next" href="r2_paged_3.html">下一页</a></p>',
        ),
        encoding="utf-8",
    )
    (root / "r2_paged_3.html").write_text(
        _page(
            "三页正文（第三部分）",
            "<h1>三页正文样本（第三部分）</h1>"
            "<p>正文第三部分：附件与联系方式。</p>"
            '<p><a href="attachments/notice.csv">附件：notice.csv</a></p>',
        ),
        encoding="utf-8",
    )
    (root / "api_body.json").write_text(
        '{"title": "三页正文样本", "body": "<p>接口正文：补充说明。</p>"}',
        encoding="utf-8",
    )


def _pipeline(registry, tmp_path, max_requests):
    budget = RunBudget(max_requests=max_requests)
    http = HttpClient(registry, limits=LIMITS, robots=False, budget=budget)
    pipeline = CrawlPipeline(registry, tmp_path / "data", http=http, now=lambda: FIXED_NOW)
    return pipeline, budget


def _collect(pipeline, base_url, budget):
    return pipeline.collect("TESTSRC", entry_urls=[f"{base_url}/r2_index.html"], budget=budget)


def _pending_item(data, url_suffix):
    payload = json.loads((data / "manifests" / "pending_items.json").read_text(encoding="utf-8"))
    return next(item for item in payload["items"].values() if item["url"].endswith(url_suffix))


def _manifest_names(data):
    return [
        row["final_url"].rsplit("/", 1)[-1]
        for row in read_jsonl(data / "manifests" / "crawl_manifest.jsonl")
    ]


def test_body_budget_stop_resumes_after_mother_304_and_completes(
    mutable_site, registry_factory, tmp_path
):
    """验收场景：第二页前预算停止 → 母页 304 重启 → 补齐二/三页、接口与附件。"""
    base_url, root = mutable_site
    _write_paged_site(root)
    registry = registry_factory(base_url)
    data = tmp_path / "data"

    pipeline, budget = _pipeline(registry, tmp_path, max_requests=2)
    report = _collect(pipeline, base_url, budget)
    assert report.stop_reason == "request_budget"
    assert budget.used_requests == 2

    item = _pending_item(data, "r2_paged_1.html")
    assert item["state"] == "pending", "正文未完成的主目标保持待续，不写成整体完成"
    assert item["note"].startswith("partial:budget_stop")
    continuation = item["continuation"]
    assert continuation["kind"] == CONTINUATION_KIND
    assert continuation["next_url"].endswith("r2_paged_2.html")
    assert continuation["parts"] == []
    assert item["crawl_id"] == continuation["doc_id"]

    documents = read_jsonl(data / "normalized" / "documents.jsonl")
    assert len(documents) == 1 and documents[0]["parse_status"] == "partial"
    assert "正文第二部分" not in documents[0]["full_text"]
    rows_before = read_jsonl(data / "manifests" / "crawl_manifest.jsonl")

    pipeline, budget = _pipeline(registry, tmp_path, max_requests=8)
    second = _collect(pipeline, base_url, budget)
    assert second.stop_reason is None

    documents = read_jsonl(data / "normalized" / "documents.jsonl")
    assert len(documents) == 2, "旧 partial 行保留，续作完成后追加完整文档行"
    partial_doc, final_doc = documents
    assert partial_doc["parse_status"] == "partial"
    assert final_doc["parse_status"] == "ok"
    assert final_doc["doc_id"] != partial_doc["doc_id"]
    text = final_doc["full_text"]
    assert text.index("正文第一部分") < text.index("正文第二部分") < text.index("正文第三部分")
    assert text.index("正文第三部分") < text.index("接口正文")
    for phrase in ("正文第一部分", "正文第二部分", "正文第三部分", "接口正文"):
        assert text.count(phrase) == 1, f"续作不得重复拼接已保存块：{phrase}"

    blocks = [
        row
        for row in read_jsonl(data / "normalized" / "blocks.jsonl")
        if row["doc_id"] == final_doc["doc_id"]
    ]
    paged_blocks = [row for row in blocks if "page_no" in row]
    assert [row["page_no"] for row in paged_blocks] == [1, 1, 2, 2, 3, 3, 3]
    assert [row["text"] for row in paged_blocks if row["page_no"] == 2] == [
        "三页正文样本（第二部分）",
        "正文第二部分：具体安排。",
    ]
    assert blocks[-1]["text"] == "接口正文：补充说明。", "接口正文并入同一文档且顺序在后"


    attachments = final_doc.get("attachments") or []
    assert [entry["status"] for entry in attachments] == ["downloaded"]
    assert (data / attachments[0]["raw_path"]).read_bytes() == (
        root / "attachments" / "notice.csv"
    ).read_bytes()

    # 母页 304：本轮不为母页追加新账本行；二/三页与接口各自归档一次
    names = _manifest_names(data)
    assert second.counters.not_modified == 1
    assert names.count("r2_paged_1.html") == 1
    assert names.count("r2_paged_2.html") == 1 and names.count("r2_paged_3.html") == 1
    assert names.count("api_body.json") == 1
    manifest = {row["crawl_id"]: row for row in read_jsonl(data / "manifests" / "crawl_manifest.jsonl")}
    assert set(final_doc["crawl_ids"]) <= set(manifest)
    for crawl_id in final_doc["crawl_ids"]:
        assert (data / manifest[crawl_id]["raw_path"]).is_file()
    assert trace_delivery(data).ok is True

    item = _pending_item(data, "r2_paged_1.html")
    assert item["state"] == "processed" and item["note"] == "ok"
    assert item["continuation"] is None, "续作完成后待续状态关闭"


def test_body_part_failure_stays_in_failure_ledger_and_resumes(
    mutable_site, registry_factory, tmp_path
):
    """正文请求失败进入失败链并保留待续；原件补齐后重启完成。"""
    base_url, root = mutable_site
    _write_paged_site(root)
    missing = root / "r2_paged_2.html"
    missing.unlink()
    registry = registry_factory(base_url)
    data = tmp_path / "data"

    pipeline, budget = _pipeline(registry, tmp_path, max_requests=3)
    report = _collect(pipeline, base_url, budget)
    assert budget.used_requests == 3

    failures = read_jsonl(data / "manifests" / "failed_records.jsonl")
    failed = [row for row in failures if row["url"].endswith("r2_paged_2.html")]
    assert len(failed) == 1 and failed[0]["stage"] == "fetch" and failed[0]["http_status"] == 404
    item = _pending_item(data, "r2_paged_1.html")
    assert item["state"] == "pending"
    assert item["note"].startswith("partial:pagination_fetch_failed")
    assert item["continuation"]["next_url"].endswith("r2_paged_2.html")
    assert failed[0].get("doc_id") == item["continuation"]["doc_id"]
    document = read_jsonl(data / "normalized" / "documents.jsonl")[0]
    assert document["parse_status"] == "partial"
    assert "正文第二部分" not in document["full_text"]

    (root / "r2_paged_2.html").write_text(
        _page(
            "三页正文（第二部分）",
            "<h1>三页正文样本（第二部分）</h1><p>正文第二部分：具体安排。</p>"
            '<p class="pager"><a rel="next" href="r2_paged_3.html">下一页</a></p>',
        ),
        encoding="utf-8",
    )
    pipeline, budget = _pipeline(registry, tmp_path, max_requests=8)
    second = _collect(pipeline, base_url, budget)
    assert second.stop_reason is None
    final_doc = read_jsonl(data / "normalized" / "documents.jsonl")[-1]
    assert final_doc["parse_status"] == "ok"
    assert "正文第二部分" in final_doc["full_text"]
    assert final_doc.get("attachments")
    assert _pending_item(data, "r2_paged_1.html")["continuation"] is None


def test_resume_advances_across_budget_stops_without_refetching_parts(
    mutable_site, registry_factory, tmp_path
):
    """跨预算推进：每轮只取未取部分，已取得部分不重复请求、不重复归档。"""
    base_url, root = mutable_site
    _write_paged_site(root)
    registry = registry_factory(base_url)
    data = tmp_path / "data"

    pipeline, budget = _pipeline(registry, tmp_path, max_requests=2)
    _collect(pipeline, base_url, budget)

    # 第二轮：列表 + 母页 304 + 第二页，随后第三页前预算停止
    pipeline, budget = _pipeline(registry, tmp_path, max_requests=3)
    second = _collect(pipeline, base_url, budget)
    assert second.stop_reason == "request_budget"
    item = _pending_item(data, "r2_paged_1.html")
    assert item["state"] == "pending"
    assert item["continuation"]["next_url"].endswith("r2_paged_3.html")
    assert [ref["url"].rsplit("/", 1)[-1] for ref in item["continuation"]["parts"]] == [
        "r2_paged_2.html"
    ]
    page2_crawl_id = item["continuation"]["parts"][0]["crawl_id"]
    assert second.counters.not_modified == 1

    # 第三轮：列表 + 母页 304 + 第三页 + 接口 + 附件
    pipeline, budget = _pipeline(registry, tmp_path, max_requests=8)
    third = _collect(pipeline, base_url, budget)
    assert third.stop_reason is None
    names = _manifest_names(data)
    assert names.count("r2_paged_2.html") == 1, "已取得部分不在续作轮重复归档"
    assert names.count("r2_paged_3.html") == 1
    final_doc = read_jsonl(data / "normalized" / "documents.jsonl")[-1]
    assert page2_crawl_id in final_doc["crawl_ids"]
    assert final_doc["parse_status"] == "ok"
    assert _pending_item(data, "r2_paged_1.html")["continuation"] is None


def test_damaged_queue_continuation_resumes_from_incremental_state(
    mutable_site, registry_factory, tmp_path
):
    """队列待续损坏、增量状态待续可用：按增量状态续作，并留下工程失败记录。

    阶段七 A：待续位置与增量状态同一次原子写入，队列回写损坏时以状态记录为准；
    母页 304 只说明母响应未变，不把未完成正文当完整实体。
    """
    base_url, root = mutable_site
    _write_paged_site(root)
    registry = registry_factory(base_url)
    data = tmp_path / "data"

    pipeline, budget = _pipeline(registry, tmp_path, max_requests=2)
    _collect(pipeline, base_url, budget)

    path = data / "manifests" / "pending_items.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    key = next(key for key, item in payload["items"].items() if item["url"].endswith("r2_paged_1.html"))
    payload["items"][key]["continuation"] = {"kind": CONTINUATION_KIND, "doc_id": "BAD"}
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    pipeline, budget = _pipeline(registry, tmp_path, max_requests=8)
    report = _collect(pipeline, base_url, budget)
    assert report.stop_reason is None
    failures = read_jsonl(data / "manifests" / "failed_records.jsonl")
    assert any(row["error_type"] == "continuation_state_damaged" for row in failures)
    names = _manifest_names(data)
    assert names.count("r2_paged_1.html") == 1, "状态记录可用时按续作处理，不重取母页"
    final_doc = read_jsonl(data / "normalized" / "documents.jsonl")[-1]
    assert final_doc["parse_status"] == "ok"
    assert "正文第三部分" in final_doc["full_text"]
    assert "接口正文" in final_doc["full_text"]
    assert _pending_item(data, "r2_paged_1.html")["continuation"] is None


def test_damaged_continuation_without_state_record_is_refetched_fully(
    mutable_site, registry_factory, tmp_path
):
    """队列与增量状态的待续都不可用：不猜进度，忽略条件请求按完整重取并记录。"""
    base_url, root = mutable_site
    _write_paged_site(root)
    registry = registry_factory(base_url)
    data = tmp_path / "data"

    pipeline, budget = _pipeline(registry, tmp_path, max_requests=2)
    _collect(pipeline, base_url, budget)

    path = data / "manifests" / "pending_items.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    key = next(key for key, item in payload["items"].items() if item["url"].endswith("r2_paged_1.html"))
    payload["items"][key]["continuation"] = {"kind": CONTINUATION_KIND, "doc_id": "BAD"}
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    state_path = data / "manifests" / "incremental_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    mother = next(
        row for row in state["resources"].values() if row["url"].endswith("r2_paged_1.html")
    )
    mother["continuation"] = {"kind": CONTINUATION_KIND, "doc_id": "BAD"}
    state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    pipeline, budget = _pipeline(registry, tmp_path, max_requests=8)
    report = _collect(pipeline, base_url, budget)
    assert report.stop_reason is None
    names = _manifest_names(data)
    assert names.count("r2_paged_1.html") == 2, "无可信待续时按完整重取（忽略条件请求）"
    final_doc = read_jsonl(data / "normalized" / "documents.jsonl")[-1]
    assert final_doc["parse_status"] == "ok"
    assert "正文第三部分" in final_doc["full_text"]
    assert _pending_item(data, "r2_paged_1.html")["continuation"] is None


def test_recovery_refetch_resumes_open_body_continuation(
    mutable_site, registry_factory, tmp_path
):
    """母页补抓按既有待续续取：内容未变（无 304）也不丢弃未完成正文。"""
    base_url, root = mutable_site
    _write_paged_site(root)
    registry = registry_factory(base_url)
    data = tmp_path / "data"

    pipeline, budget = _pipeline(registry, tmp_path, max_requests=2)
    _collect(pipeline, base_url, budget)
    item = _pending_item(data, "r2_paged_1.html")
    mother_crawl_id = item["continuation"]["doc_id"]
    assert item["doc_id"] == mother_crawl_id, "待处理项保存母文档身份供恢复关联"

    # 母页补抓任务（网络阶段、可重试）沿用同一身份
    pipeline.failures.record(
        source_id="TESTSRC",
        url=item["url"],
        time=FIXED_NOW.isoformat(),
        stage="fetch",
        error_type="request_error",
        message="连接中断",
        retry_count=0,
        final_action="retry_later",
        doc_id=mother_crawl_id,
    )
    report = pipeline.resume_failures("TESTSRC")
    assert [row["note"] for row in report.recovered] == ["补抓成功，账本与文档已更新"]
    documents = read_jsonl(data / "normalized" / "documents.jsonl")
    assert documents[-1]["parse_status"] == "ok"
    assert "正文第三部分" in documents[-1]["full_text"]
    item = _pending_item(data, "r2_paged_1.html")
    assert item["state"] == "processed" and item["continuation"] is None
    assert trace_delivery(data).ok is True


def test_interrupted_progress_without_queue_continuation_resumes_not_complete(
    mutable_site, registry_factory, tmp_path
):
    """A：队列回写前中断（待处理项无待续）时，重启母页 304 不得误报完整。

    第二轮仍取不到第二页：目标必须保持待续并留下失败记录，不能以 304 关闭为“已处理”。
    """
    base_url, root = mutable_site
    _write_paged_site(root)
    missing = root / "r2_paged_2.html"
    missing.unlink()
    registry = registry_factory(base_url)
    data = tmp_path / "data"

    pipeline, budget = _pipeline(registry, tmp_path, max_requests=3)
    _collect(pipeline, base_url, budget)
    item = _pending_item(data, "r2_paged_1.html")
    assert item["state"] == "pending" and item["continuation"]["kind"] == CONTINUATION_KIND

    # 模拟“正文续抓进度已随增量状态原子写入，但待处理项还没回写”的中断窗口
    path = data / "manifests" / "pending_items.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    key = next(key for key, row in payload["items"].items() if row["url"].endswith("r2_paged_1.html"))
    payload["items"][key]["continuation"] = None
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    pipeline, budget = _pipeline(registry, tmp_path, max_requests=8)
    second = _collect(pipeline, base_url, budget)
    assert second.stop_reason is None
    assert second.counters.not_modified == 1, "母页按条件请求得到 304"

    item = _pending_item(data, "r2_paged_1.html")
    assert item["state"] == "pending", "正文未完成时不得因母页 304 关闭目标"
    assert item["note"].startswith("partial:pagination_fetch_failed")
    resumed = item["continuation"]["next_url"]
    assert resumed.endswith("r2_paged_2.html")
    doc = read_jsonl(data / "normalized" / "documents.jsonl")[-1]
    assert doc["parse_status"] == "partial"
    assert "正文第二部分" not in doc["full_text"]
    failures = read_jsonl(data / "manifests" / "failed_records.jsonl")
    assert [row["error_type"] for row in failures] == ["http_error", "http_error"]
    assert all(row["url"].endswith("r2_paged_2.html") for row in failures)
    assert all(row["final_action"] in ("record_only", "retry_later") for row in failures)


def test_continuation_mother_non_html_success_is_archived_before_failing(
    mutable_site, registry_factory, tmp_path
):
    """B：续抓母页返回成功但非 HTML 时，先留存 raw 与账本，再按失败处置。"""
    base_url, root = mutable_site
    _write_paged_site(root)
    registry = registry_factory(base_url)
    data = tmp_path / "data"
    pipeline, budget = _pipeline(registry, tmp_path, max_requests=2)

    mother_url = f"{base_url}/_as_pdf/mother.html"
    pipeline.pending.enqueue_targets(
        source_id="TESTSRC",
        targets=[
            DiscoveredTarget(url=mother_url, discovery_method="manual"),
        ],
        scope_start_date=None,
        enqueued_at=FIXED_NOW.isoformat(),
    )
    item = next(row for row in pipeline.pending.all_items() if row.url == mother_url)
    continuation = {
        "kind": CONTINUATION_KIND,
        "doc_id": "TESTSRC_20260914_9001",
        "mother_url": mother_url,
        "mother_final_url": mother_url,
        "mother_raw_path": "raw/TESTSRC/2026-09-14/html/mother.html",
        "mother_sha256": "0" * 64,
        "mother_content_type": "text/html; charset=utf-8",
        "next_url": None,
        "body_api_url": f"{base_url}/api_body.json",
        "parts": [],
        "stop_reason": "body_api_failed",
        "attempts": 1,
        "updated_at": FIXED_NOW.isoformat(),
    }
    pipeline.pending.mark(item.key, state="pending", continuation=continuation)

    report = pipeline.collect("TESTSRC", manual_urls=[mother_url], budget=budget)
    assert report.stop_reason is None

    manifest = read_jsonl(data / "manifests" / "crawl_manifest.jsonl")
    rows = [
        row
        for row in manifest
        if row["requested_url"] == mother_url or row["final_url"] == mother_url
    ]
    assert len(rows) == 1, "成功响应先归档，不丢原件"
    raw_file = data / rows[0]["raw_path"]
    assert raw_file.is_file() and raw_file.read_bytes().startswith(b"%PDF-1.4")
    assert rows[0]["content_type"].startswith("application/pdf")

    failures = read_jsonl(data / "manifests" / "failed_records.jsonl")
    failed = [row for row in failures if row["error_type"] == "continuation_not_html"]
    assert len(failed) == 1
    assert failed[0]["crawl_id"] == rows[0]["crawl_id"]
    assert failed[0]["doc_id"] == continuation["doc_id"]

    item = next(row for row in pipeline.pending.all_items() if row.url == mother_url)
    assert item.state == "failed"
    assert item.continuation == continuation, "待续状态保留，等待恢复或人工处置"
    assert trace_delivery(data).ok is True


def _document_block_sequence(data, doc_id):
    rows = [
        row
        for row in read_jsonl(data / "normalized" / "blocks.jsonl")
        if row["doc_id"] == doc_id
    ]
    return [(row.get("page_no"), row.get("text")) for row in rows]


def test_pagination_failure_then_api_recovery_matches_single_successful_crawl(
    mutable_site, registry_factory, tmp_path
):
    """D：分页失败但接口可用，随后恢复时正文与块顺序同一次成功抓取一致。"""
    base_url, root = mutable_site
    _write_paged_site(root)
    registry = registry_factory(base_url)
    page3 = root / "r2_paged_3.html"
    page3_bytes = page3.read_bytes()

    # 参考：page3 一直可用的一次成功抓取
    reference_data = tmp_path / "reference"
    reference_pipeline = CrawlPipeline(
        registry, reference_data, http=HttpClient(registry, limits=LIMITS, robots=False),
        now=lambda: FIXED_NOW,
    )
    reference_report = reference_pipeline.collect(
        "TESTSRC", entry_urls=[f"{base_url}/r2_index.html"]
    )
    assert reference_report.stop_reason is None
    reference_doc = read_jsonl(reference_data / "normalized" / "documents.jsonl")[-1]
    assert reference_doc["parse_status"] == "ok"

    # 失败轮：page3 暂时不可用，接口正文可用 → partial 文档 + 待续（分页未完、接口已取）
    page3.unlink()
    data = tmp_path / "data"
    pipeline, budget = _pipeline(registry, tmp_path, max_requests=8)
    first = _collect(pipeline, base_url, budget)
    assert first.stop_reason is None
    item = _pending_item(data, "r2_paged_1.html")
    assert item["state"] == "pending"
    assert item["continuation"]["next_url"].endswith("r2_paged_3.html")
    methods = [ref["method"] for ref in item["continuation"]["parts"]]
    assert methods == ["pagination", "api"], "接口正文已取得并记录在待续状态中"
    partial_doc = read_jsonl(data / "normalized" / "documents.jsonl")[-1]
    assert "接口正文" in partial_doc["full_text"]
    assert "正文第三部分" not in partial_doc["full_text"]

    # 恢复轮：page3 恢复可用 → 合并顺序与参考一致
    page3.write_bytes(page3_bytes)
    pipeline, budget = _pipeline(registry, tmp_path, max_requests=8)
    second = _collect(pipeline, base_url, budget)
    assert second.stop_reason is None
    final_doc = read_jsonl(data / "normalized" / "documents.jsonl")[-1]
    assert final_doc["doc_id"] != partial_doc["doc_id"]
    assert final_doc["parse_status"] == "ok"
    assert final_doc["full_text"] == reference_doc["full_text"]
    assert _document_block_sequence(data, final_doc["doc_id"]) == _document_block_sequence(
        reference_data, reference_doc["doc_id"]
    ), "块顺序与页码必须与一次成功抓取一致"
    for phrase in ("正文第一部分", "正文第二部分", "正文第三部分", "接口正文"):
        assert final_doc["full_text"].count(phrase) == 1
    assert _pending_item(data, "r2_paged_1.html")["continuation"] is None
    assert trace_delivery(data).ok is True
