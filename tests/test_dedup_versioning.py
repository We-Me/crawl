"""T014：精确/近似重复、来源关系、版本保留、现行状态与下线记录。"""

from pathlib import Path

import pytest

from crawler.dedup import (
    DuplicateConfigError,
    RelationError,
    attach_relations,
    build_relation,
    find_exact_duplicates,
    find_near_duplicates,
    group_row_counts,
    relation_index,
    text_hash,
    text_similarity,
)
from crawler.normalize.document_schema import build_document
from crawler.parser.html_parser import parse_html
from crawler.versioning import (
    NEW,
    REVISION,
    UNCHANGED,
    VersionStore,
    VersionStoreError,
    apply_decision,
    document_identity,
    plan_version,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


def _document(doc_id, url, sha, title="标题", text="正文", source_id="src", **extra):
    payload = {
        "doc_id": doc_id,
        "source_id": source_id,
        "source_name": "虚构来源",
        "source_url": url,
        "title": title,
        "full_text": text,
        "language": "zh",
        "document_type": "html_page",
        "raw_path": f"raw/{doc_id}.html",
        "sha256": sha,
        "crawl_time": "2026-09-11T10:00:00+08:00",
        "extraction_method": "bs4_lxml_dom",
        "crawl_ids": [doc_id],
        "parse_status": "ok",
    }
    payload.update(extra)
    return payload


def _html_document(doc_id, fixture, url, sha, **extra):
    content = (FIXTURES / "html" / fixture).read_bytes()
    parsed = parse_html(content, url)
    return build_document(
        doc_id=doc_id,
        source_id="src",
        source_name="虚构来源",
        source_url=url,
        title=parsed.title,
        full_text=parsed.full_text,
        language="zh",
        document_type="html_page",
        raw_path=f"raw/{doc_id}.html",
        sha256=sha,
        crawl_time="2026-09-11T10:00:00+08:00",
        extraction_method=parsed.extraction_method,
        crawl_ids=[doc_id],
        canonical_url=parsed.canonical_url,
        **extra,
    )


# ---------- 精确重复 ----------


def test_exact_duplicates_keep_all_sources():
    same_bytes = "a" * 64
    documents = [
        _document("d1", "https://example.invalid/a", same_bytes, source_id="src_a"),
        _document(
            "d2", "https://example.invalid/b", same_bytes, source_id="src_b", text="另一段正文"
        ),
        _document("d3", "https://example.invalid/c", "c" * 64, text="不同正文"),
    ]
    groups = find_exact_duplicates(documents)
    by_kind = {group.kind: group for group in groups}
    assert set(by_kind) == {"exact_bytes"}
    members = by_kind["exact_bytes"].members
    assert {member["doc_id"] for member in members} == {"d1", "d2"}
    assert {member["source_id"] for member in members} == {"src_a", "src_b"}
    assert by_kind["exact_bytes"].as_row()["member_count"] == 2
    assert group_row_counts(groups) == {"exact_bytes": 1}


def test_exact_text_duplicates_detect_same_content_different_bytes():
    text = "同一篇虚构公告正文。"
    documents = [
        _document("d1", "https://example.invalid/a", "a" * 64, text=text),
        _document("d2", "https://example.invalid/b", "b" * 64, text=text),
    ]
    groups = find_exact_duplicates(documents)
    assert {group.kind for group in groups} == {"exact_text"}
    assert text_hash(documents[0]["full_text"]) == groups[0].key


# ---------- 近似重复 ----------


def test_near_duplicates_require_explicit_threshold():
    with pytest.raises(DuplicateConfigError, match="Q11"):
        find_near_duplicates([_document("d1", "https://example.invalid/a", "a" * 64)], threshold=None)
    with pytest.raises(DuplicateConfigError):
        find_near_duplicates([], threshold=1.5)


def test_near_duplicates_group_without_merging():
    v1 = _html_document("v1", "version_v1.html", "https://example.invalid/rule", "1" * 64)
    v2 = _html_document(
        "v2", "version_v2.html", "https://example.invalid/rule", "2" * 64, version="2", is_current=True
    )
    similarity = text_similarity(v1["full_text"], v2["full_text"])
    assert 0.5 < similarity < 1
    groups = find_near_duplicates([v1, v2], threshold=similarity - 1e-6)
    assert len(groups) == 1
    assert {member["doc_id"] for member in groups[0].members} == {"v1", "v2"}
    assert groups[0].similarity is not None and groups[0].similarity >= 0.5
    assert find_near_duplicates([v1, v2], threshold=0.99) == []
    # 分组只是候选：原文档仍在
    assert v1["doc_id"] != v2["doc_id"] and v1["full_text"] != v2["full_text"]


# ---------- 关系 ----------


def test_relations_require_evidence_and_keep_sources():
    relation = build_relation(
        "reprint_of",
        "d2",
        "d1",
        evidence={"matched_url": "https://example.invalid/a", "basis": "content_hash"},
    )
    document = attach_relations(_document("d2", "https://example.invalid/b", "b" * 64), [relation])
    assert document["related_doc_ids"] == ["d1"]
    assert document["relations"][0]["relation_type"] == "reprint_of"
    duplicate = build_relation("duplicate_of", "d2", "d1", evidence={"basis": "sha256"})
    duplicated = attach_relations(_document("d2", "https://example.invalid/b", "b" * 64), [duplicate])
    assert duplicated["duplicate_of"] == "d1"
    index = relation_index([document, duplicated])
    assert index["d2"][0]["relation_type"] in ("reprint_of", "duplicate_of")

    with pytest.raises(RelationError):
        build_relation("mirror_of", "d2", "d1", evidence={})
    with pytest.raises(RelationError):
        build_relation("unknown", "d2", "d1", evidence={"basis": "x"})
    with pytest.raises(RelationError):
        build_relation("mirror_of", "d1", "d1", evidence={"basis": "x"})


# ---------- 版本 ----------


def test_first_document_is_new_version():
    decision = plan_version(_document("d1", "https://example.invalid/rule", "a" * 64))
    assert decision.kind == NEW and decision.version == "1" and decision.is_current
    applied = apply_decision(_document("d1", "https://example.invalid/rule", "a" * 64), decision)
    assert applied["version"] == "1" and applied["is_current"] is True
    assert "effective_from" not in applied and "source_status" not in applied


def test_unchanged_content_does_not_create_version():
    v1 = _document("d1", "https://example.invalid/rule", "a" * 64)
    same = _document("d2", "https://example.invalid/rule#part", "a" * 64)
    decision = plan_version(same, existing_documents=[v1])
    assert decision.kind == UNCHANGED
    assert decision.version == "1" and decision.supersedes == ()
    assert decision.related_doc_ids == ("d1",)


def test_revision_keeps_old_version_and_marks_review():
    v1 = _html_document(
        "v1", "version_v1.html", "https://example.invalid/rule", "1" * 64, version="1", is_current=True
    )
    v2 = _html_document(
        "v2", "version_v2.html", "https://example.invalid/rule", "2" * 64, version="2", is_current=True
    )
    decision = plan_version(v2, existing_documents=[v1], similarity_threshold=0.99)
    assert decision.kind == REVISION and decision.version == "2" and decision.is_current
    assert decision.supersedes == ("v1",) and decision.related_doc_ids == ("v1",)
    assert decision.requires_review is True
    assert decision.relations[0]["relation_type"] == "revision_of"
    applied = apply_decision(v2, decision)
    assert applied["version"] == "2" and applied["is_current"] is True
    assert applied["related_doc_ids"] == ["v1"]


def test_exact_duplicate_between_identities_recorded_not_merged():
    a = _document("a1", "https://example.invalid/a", "a" * 64)
    b = _document("b1", "https://example.invalid/b", "a" * 64)
    decision = plan_version(b, existing_documents=[a])
    assert decision.kind == NEW
    assert decision.duplicate_of == "a1"
    applied = apply_decision(b, decision)
    assert applied["duplicate_of"] == "a1"
    assert applied["related_doc_ids"] == ["a1"]
    assert applied["source_url"] != a["source_url"]


def test_different_source_same_url_is_not_same_identity():
    a = _document("a1", "https://example.invalid/rule", "a" * 64, source_id="src_a")
    b = _document("b1", "https://example.invalid/rule", "b" * 64, source_id="src_b")
    assert document_identity(a) != document_identity(b)
    assert plan_version(b, existing_documents=[a]).kind == NEW


# ---------- 版本库与下线 ----------


def test_store_retires_superseded_without_deleting_history(tmp_path):
    store = VersionStore(tmp_path)
    v1 = _html_document(
        "v1", "version_v1.html", "https://example.invalid/rule", "1" * 64, version="1", is_current=True
    )
    v2 = _html_document(
        "v2", "version_v2.html", "https://example.invalid/rule", "2" * 64, version="2", is_current=True
    )
    (tmp_path / "normalized").mkdir(parents=True, exist_ok=True)
    from crawler.output.jsonl import write_jsonl

    write_jsonl(store.path, [v1, v2])
    changed = store.retire(["v1"])
    rows = {row["doc_id"]: row for row in store.load()}
    assert changed == 1
    assert rows["v1"]["is_current"] is False and rows["v1"]["source_status"] == "superseded"
    assert rows["v1"]["full_text"] == v1["full_text"]
    assert rows["v2"]["is_current"] is True
    current = store.current_documents()
    assert [row["doc_id"] for row in current] == ["v2"]
    assert [row["version"] for row in store.versions_of(document_identity(v1))] == ["1", "2"]


def test_store_records_offline_with_evidence_and_keeps_history(tmp_path):
    from crawler.output.jsonl import write_jsonl

    store = VersionStore(tmp_path)
    (tmp_path / "normalized").mkdir(parents=True, exist_ok=True)
    v1 = _html_document(
        "v1", "version_v1.html", "https://example.invalid/rule", "1" * 64, version="1", is_current=True
    )
    write_jsonl(store.path, [v1])
    changed = store.record_offline(
        "v1", source_status="removed", evidence={"http_status": 404, "checked_at": "2026-09-11T12:00:00+08:00"}
    )
    row = store.load()[0]
    assert changed == 1
    assert row["source_status"] == "removed"
    assert row["is_current"] is True
    assert row["status_history"][0]["evidence"]["http_status"] == 404
    assert row["full_text"] == v1["full_text"]
    with pytest.raises(VersionStoreError):
        store.record_offline("v1", source_status="maybe-valid")


def test_store_errors_on_missing_file(tmp_path):
    with pytest.raises(VersionStoreError):
        VersionStore(tmp_path).retire(["x"])
