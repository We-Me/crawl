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


def test_damaged_continuation_is_refetched_fully_and_recorded(
    mutable_site, registry_factory, tmp_path
):
    """待续状态损坏：不猜造进度，忽略条件请求按完整重取，并留下工程失败记录。"""
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
    assert names.count("r2_paged_1.html") == 2, "损坏待续按完整重取（忽略条件请求）"
    final_doc = read_jsonl(data / "normalized" / "documents.jsonl")[-1]
    assert final_doc["parse_status"] == "ok"
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
