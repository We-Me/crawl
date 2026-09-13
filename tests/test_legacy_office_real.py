"""T012/NEXT-04：真实旧式 DOC/XLS 的转换、结构保留、原件追溯与失败处理。

样本为 ``tests/fixtures/office/notice.doc``、``notice.xls``：由系统 LibreOffice 从同
目录 OOXML 夹具生成（见 ``tools/make_legacy_fixtures.py``），是真实 OLE2 复合文档而
非改扩展名的伪文件，内容是虚构夹具。因此本文件只证明旧格式转换与追溯链路可用，
不代表真实站点或机构文档验收；缺 LibreOffice 时跳过真实转换用例，失败处理用例仍执行。

注意：在 AppArmor/seccomp 等受限沙箱中 `soffice --version` 可以运行，但完整初始化与
转换会被拒绝（退出码非 0、不产出文件）。``needs_soffice`` 因此以“样本真的转换成功一次”
为准，而不是只看二进制是否存在：这类环境会 skip 并给出转换器错误，不会误报成解析链路
失败，也不会让失败路径用例因组件不可用而以错误的原因通过。请在目标 Linux 的正常 shell
中运行本文件取得真实转换证据。
"""

import functools
import hashlib
import struct
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from crawler.fetch.http_client import FetchLimits, HttpClient
from crawler.output.jsonl import read_jsonl
from crawler.parser import LegacyFormatError, detect_format, find_soffice, parse_attachment
from crawler.parser import legacy_parser
from crawler.pipeline import CrawlPipeline
from crawler.validate.traceability import trace_delivery

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
OFFICE = FIXTURES / "office"
DOC = OFFICE / "notice.doc"
XLS = OFFICE / "notice.xls"
DOCX_BYTES = (OFFICE / "notice.docx").read_bytes()
XLSX_BYTES = (OFFICE / "notice.xlsx").read_bytes()

OLE2_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
ZIP_MAGIC = b"PK\x03\x04"
NOW = datetime(2026, 9, 13, 10, 0, 0, tzinfo=timezone(timedelta(hours=8)))

# 记录值对应 LibreOffice 24.2.7.2 420(Build:2)；重建见 tools/make_legacy_fixtures.py。
RECORDED_SHA256 = {
    "notice.doc": "71dd62f6c722ce3f65d17c1ad83ba070171a63d22c9f930e9c740a4f7f2aa765",
    "notice.xls": "aa8bbcb06f7d8b0a07468ae0f48326e54616aa6142c47b03e7972420c7a8e069",
}


@functools.lru_cache(maxsize=1)
def _soffice_capability():
    """真的转换一份样本，才算“LibreOffice 可用”。

    只用 ``which`` 判断不够：受限沙箱（AppArmor/seccomp）里 ``soffice --version`` 正常
    退出，但完整初始化与转换被拒绝（退出码非 0、不产出文件）。把判定改成能力探测，既能
    把执行环境限制如实报成 skip，也避免“失败路径”用例在组件不可用时以错误的原因通过。
    """

    if find_soffice() is None:
        return False, "未安装 LibreOffice（soffice/libreoffice），无法执行真实旧格式转换"
    try:
        legacy_parser.soffice_converter(DOC.read_bytes(), ".doc")
    except LegacyFormatError as exc:
        return False, f"LibreOffice 无法在当前环境完成真实转换，跳过真实旧格式用例：{exc}"
    return True, ""


_SOFFICE_READY, _SOFFICE_SKIP_REASON = _soffice_capability()

needs_soffice = pytest.mark.skipif(not _SOFFICE_READY, reason=_SOFFICE_SKIP_REASON)


def _pipeline(registry, data_dir, legacy_converter=None):
    return CrawlPipeline(
        registry,
        data_dir,
        http=HttpClient(registry, limits=FetchLimits(request_rate_per_second=1000)),
        now=lambda: NOW,
        legacy_converter=legacy_converter,
    )


# ---------- 样本本身是真实旧格式 ----------


def _ole2_streams(content):
    """极简 OLE2/CFB 读取器：返回 {流名: 流字节}，用于夹具真实性校验。

    只覆盖本项目夹具用到的标准结构（512/4096 字节扇区、mini 流、FAT/miniFAT 链），
    不替代生产解析——生产仍由 LibreOffice 转换后再交给 DOCX/XLSX 解析器。
    """

    if content[:8] != OLE2_MAGIC:
        raise ValueError("不是 OLE2 复合文档")
    sector_size = 1 << struct.unpack_from("<H", content, 30)[0]
    mini_size = 1 << struct.unpack_from("<H", content, 32)[0]
    mini_cutoff = struct.unpack_from("<I", content, 56)[0]
    fat = []
    for number in struct.unpack_from("<109I", content, 76):
        if number == 0xFFFFFFFF:
            continue
        fat.extend(
            struct.unpack_from(
                "<%dI" % (sector_size // 4), content, (number + 1) * sector_size
            )
        )

    def read_chain(start, size=None):
        chunks, seen = [], set()
        while start not in (0xFFFFFFFE, 0xFFFFFFFF) and start not in seen:
            if start >= len(fat):
                raise ValueError("OLE2 FAT 链越界，疑似伪造或损坏的复合文档")
            seen.add(start)
            chunks.append(content[(start + 1) * sector_size:(start + 2) * sector_size])
            start = fat[start]
        data = b"".join(chunks)
        return data[:size] if size is not None else data

    directory = read_chain(struct.unpack_from("<I", content, 48)[0])
    entries, root = [], None
    for offset in range(0, len(directory), 128):
        entry = directory[offset:offset + 128]
        name_length = struct.unpack_from("<H", entry, 64)[0]
        if name_length < 2:
            continue
        name = entry[:name_length - 2].decode("utf-16-le")
        entry_type = entry[66]
        start = struct.unpack_from("<I", entry, 116)[0]
        size = struct.unpack_from("<Q", entry, 120)[0]
        if entry_type == 5:
            root = (start, size)
        entries.append((name, entry_type, start, size))

    mini_container = read_chain(root[0], root[1]) if root else b""
    mini_fat_raw = read_chain(struct.unpack_from("<I", content, 60)[0]) if root else b""
    mini_fat = list(
        struct.unpack_from("<%dI" % (len(mini_fat_raw) // 4), mini_fat_raw, 0)
    ) if mini_fat_raw else []

    def read_mini(start):
        chunks, seen = [], set()
        while start not in (0xFFFFFFFE, 0xFFFFFFFF) and start not in seen:
            if start >= len(mini_fat):
                raise ValueError("OLE2 miniFAT 链越界，疑似伪造或损坏的复合文档")
            seen.add(start)
            chunks.append(mini_container[start * mini_size:(start + 1) * mini_size])
            start = mini_fat[start]
        return b"".join(chunks)

    streams = {}
    for name, entry_type, start, size in entries:
        if entry_type != 2:
            continue
        data = read_mini(start) if size < mini_cutoff else read_chain(start, size)
        streams[name] = data[:size]
    return streams


@pytest.mark.parametrize("name", ["notice.doc", "notice.xls"])
def test_legacy_samples_are_real_ole2_not_renamed(name):
    content = (OFFICE / name).read_bytes()
    assert content.startswith(OLE2_MAGIC)
    assert not content.startswith(ZIP_MAGIC)
    assert len(content) > 1024
    assert hashlib.sha256(content).hexdigest() == RECORDED_SHA256[name]
    assert detect_format(content, name) == "legacy_office"


@pytest.mark.parametrize(
    "name, stream, header",
    [
        ("notice.doc", "WordDocument", b"\xec\xa5"),  # Word FIB wIdent = 0xA5EC
        ("notice.xls", "Workbook", b"\x09\x08\x10\x00"),  # BIFF8 BOF 记录
    ],
)
def test_legacy_samples_carry_real_word_or_excel_streams(name, stream, header):
    """不止魔数：OLE2 目录里有真实 Word/Excel 流，流首部是 Word FIB / BIFF8 BOF。

    这条用例不依赖 LibreOffice，任何“改了扩展名”或“只有魔数的伪文件”都会在此失败。
    """

    streams = _ole2_streams((OFFICE / name).read_bytes())
    assert stream in streams, sorted(streams)
    assert len(streams[stream]) > 512
    assert streams[stream].startswith(header)
    # CFB 命名约定：属性集流名前缀 \x05，OLE 嵌入对象名前缀 \x01，这里保留原样。
    assert "\x05SummaryInformation" in streams
    assert "\x05DocumentSummaryInformation" in streams


# ---------- 真实转换与结构保留 ----------


@needs_soffice
def test_real_doc_conversion_keeps_paragraphs_lists_and_table():
    parsed = parse_attachment(
        DOC.read_bytes(), "notice.doc", "https://example.invalid/files/notice.doc"
    )
    assert parsed.extraction_method == "python_docx"
    assert parsed.title == "Fixture Notice - Office Formats"
    assert [block.block_type for block in parsed.blocks] == [
        "heading",
        "paragraph",
        "heading",
        "list_item",
        "list_item",
        "table",
    ]
    assert parsed.blocks[0].heading_level == 1
    assert parsed.blocks[2].heading_level == 2
    assert parsed.blocks[1].text == "Fixture only. Not a real institution document."
    assert parsed.blocks[3].text == "Applies to fixture tests only."
    assert parsed.blocks[4].text == "Second fixture step."
    table = parsed.blocks[5].structured_data
    assert table["headers"] == ["Item", "Quantity", "Amount"]
    assert table["rows"] == [["Widgets", "12", "340.00"], ["Gadgets", "3", "125.50"]]
    assert parsed.blocks[1].text in parsed.full_text


@needs_soffice
def test_real_xls_conversion_keeps_sheets_cells_and_empty_status():
    parsed = parse_attachment(
        XLS.read_bytes(), "notice.xls", "https://example.invalid/files/notice.xls"
    )
    assert parsed.extraction_method == "openpyxl_read_only"
    assert parsed.page_count == 3
    assert [status.status for status in parsed.page_status] == ["ok", "ok", "empty"]
    summary = parsed.blocks[0].structured_data
    assert parsed.blocks[0].page_no == 1
    assert summary["sheet"] == "Summary"
    assert summary["headers"] == ["Item", "Quantity（单位：件）", "Amount（单位：元）"]
    assert summary["rows"] == [["Widgets", "12", "340"], ["Gadgets", "3", "125.5"]]
    assert summary["units"] == {"Quantity（单位：件）": "件", "Amount（单位：元）": "元"}
    notes = parsed.blocks[1].structured_data
    assert parsed.blocks[1].page_no == 2
    assert notes["sheet"] == "Notes" and notes["rows"] == [["Fixture only"]]
    assert "sheet_3_empty" in parsed.metadata_missing


# ---------- 失败必须显式，不得空成功或静默降级 ----------


@needs_soffice
def test_corrupt_ole2_raises_instead_of_returning_empty_document():
    """截断 OLE2 必须在转换阶段显式失败，不得靠“组件缺失”骗过用例。"""

    corrupt = DOC.read_bytes()[:600]
    with pytest.raises(LegacyFormatError) as excinfo:
        parse_attachment(corrupt, "broken.doc")
    message = str(excinfo.value)
    assert "未安装 LibreOffice" not in message
    assert "转换" in message


def test_converter_exit_zero_without_output_is_failure(monkeypatch):
    """LibreOffice 24.2 无法加载源文件时以 0 退出且不产出文件，必须仍判失败。"""

    class Result:
        returncode = 0
        stderr = b"Error: source file could not be loaded"

    monkeypatch.setattr(legacy_parser, "find_soffice", lambda: "/usr/bin/soffice")
    monkeypatch.setattr(legacy_parser.subprocess, "run", lambda *args, **kwargs: Result())
    with pytest.raises(LegacyFormatError, match="未生成转换结果"):
        legacy_parser.soffice_converter(DOC.read_bytes(), ".doc")


def test_converter_nonzero_exit_reports_code(monkeypatch):
    class Result:
        returncode = 1
        stderr = b"boom"

    monkeypatch.setattr(legacy_parser, "find_soffice", lambda: "/usr/bin/soffice")
    monkeypatch.setattr(legacy_parser.subprocess, "run", lambda *args, **kwargs: Result())
    with pytest.raises(LegacyFormatError, match="code=1"):
        legacy_parser.soffice_converter(DOC.read_bytes(), ".doc")


def test_missing_converter_reports_install_hint(monkeypatch):
    monkeypatch.setattr(legacy_parser, "find_soffice", lambda: None)
    with pytest.raises(LegacyFormatError, match="LibreOffice"):
        legacy_parser.soffice_converter(DOC.read_bytes(), ".doc")


# ---------- 端到端：原件、账本、块与质量检查 ----------


LEGACY_SAMPLES = (
    ("notice.doc", DOC.read_bytes(), "application/msword"),
    ("notice.xls", XLS.read_bytes(), "application/vnd.ms-excel"),
)


def _stage_attachments(pipeline, data_dir, samples):
    """按 collect 对已下载附件的实际写入形态登记原件与账本，返回附件元数据。"""

    attachments_meta = []
    for index, (filename, content, content_type) in enumerate(samples, start=1):
        url = f"http://127.0.0.1:1/files/{filename}"
        raw = pipeline.store.write_bytes(
            source_id="TESTSRC",
            crawl_date="2026-09-13",
            kind="attachment",
            filename=filename,
            content=content,
        )
        crawl_id = f"TESTSRC_20260913_000{index}"
        pipeline.manifest.record(
            crawl_id=crawl_id,
            source_id="TESTSRC",
            requested_url=url,
            final_url=url,
            crawl_time=NOW.isoformat(),
            http_status=200,
            content_type=content_type,
            raw=raw,
            discovery_method="attachment",
        )
        attachments_meta.append(
            {
                "filename": filename,
                "url": url,
                "crawl_id": crawl_id,
                "raw_path": raw.relative_path,
                "sha256": raw.sha256,
                "file_type": filename.rsplit(".", 1)[1],
            }
        )
    manifest = {
        row["crawl_id"]: row
        for row in read_jsonl(data_dir / "manifests" / "crawl_manifest.jsonl")
    }
    for item, (_, content, _) in zip(attachments_meta, samples):
        assert (data_dir / item["raw_path"]).read_bytes() == content
        assert item["sha256"] == hashlib.sha256(content).hexdigest()
        assert manifest[item["crawl_id"]]["raw_path"] == item["raw_path"]
    return attachments_meta


def _reparse_and_assert_traceable(pipeline, data_dir, samples, attachments_meta):
    """走正式补抓流程，复核原件、documents/blocks 与追溯校验。"""

    for item in attachments_meta:
        pipeline.failures.record(
            source_id="TESTSRC",
            url=item["url"],
            time=NOW.isoformat(),
            stage="parse",
            error_type="parse_error",
            message="附件正文尚未入库",
            retry_count=0,
            final_action="retry_later",
            crawl_id=item["crawl_id"],
        )
    recovered = pipeline.resume_failures("TESTSRC")
    assert recovered.failures == [] and recovered.manual == [] and recovered.pending == []
    assert len(recovered.recovered) == 2
    assert recovered.counters.documents == 2 and recovered.counters.blocks > 0

    by_id = {row["doc_id"]: row for row in read_jsonl(data_dir / "normalized" / "documents.jsonl")}
    expected_bytes = {"notice.doc": samples[0][1], "notice.xls": samples[1][1]}
    for item in attachments_meta:
        document = by_id[item["crawl_id"]]
        assert document["raw_path"] == item["raw_path"]
        assert document["sha256"] == item["sha256"]
        assert document["document_type"] == item["file_type"]
        assert (data_dir / document["raw_path"]).read_bytes() == expected_bytes[item["filename"]]

    blocks_by_doc = {}
    for row in read_jsonl(data_dir / "normalized" / "blocks.jsonl"):
        blocks_by_doc.setdefault(row["doc_id"], []).append(row)
    doc_blocks = blocks_by_doc[attachments_meta[0]["crawl_id"]]
    assert [row["block_type"] for row in doc_blocks] == [
        "heading",
        "paragraph",
        "heading",
        "list_item",
        "list_item",
        "table",
    ]
    xls_blocks = blocks_by_doc[attachments_meta[1]["crawl_id"]]
    assert [row["block_type"] for row in xls_blocks] == ["table", "table"]
    assert xls_blocks[0]["structured_data"]["sheet"] == "Summary"

    trace = trace_delivery(data_dir)
    assert trace.ok is True
    assert trace.document_rate == 1.0 and trace.block_rate == 1.0


def test_pipeline_legacy_reparse_plumbing_with_injected_converter(registry_factory, tmp_path):
    """管线接线：旧格式原件按 raw_path 重解析为 documents/blocks 并通过追溯校验。

    转换器在此被替换为返回既有 OOXML 夹具字节的函数，只验证管线接线与追溯字段；
    真实 LibreOffice 转换由 `test_legacy_attachments_keep_originals_and_trace_through_pipeline`
    和 `test_real_*_conversion_*` 覆盖，不能用本用例冒充转换成功证据。
    """

    converted = {".doc": (DOCX_BYTES, ".docx"), ".xls": (XLSX_BYTES, ".xlsx")}
    data_dir = tmp_path / "data"
    pipeline = _pipeline(
        registry_factory("http://127.0.0.1:1"),
        data_dir,
        legacy_converter=lambda content, extension: converted[extension],
    )
    attachments_meta = _stage_attachments(pipeline, data_dir, LEGACY_SAMPLES)
    _reparse_and_assert_traceable(pipeline, data_dir, LEGACY_SAMPLES, attachments_meta)


@needs_soffice
def test_legacy_attachments_keep_originals_and_trace_through_pipeline(registry_factory, tmp_path):
    """同上链路，但转换器是真实 LibreOffice；附件按设计不在采集阶段解析（Q07 待决）。"""

    data_dir = tmp_path / "data"
    pipeline = _pipeline(registry_factory("http://127.0.0.1:1"), data_dir)
    attachments_meta = _stage_attachments(pipeline, data_dir, LEGACY_SAMPLES)
    _reparse_and_assert_traceable(pipeline, data_dir, LEGACY_SAMPLES, attachments_meta)


@needs_soffice
def test_legacy_reparse_failure_stays_actionable(registry_factory, tmp_path):
    """转换失败时保留原件与未关闭失败，不得记成已恢复。"""

    broken = DOC.read_bytes()[:600]
    data_dir = tmp_path / "data"
    pipeline = _pipeline(registry_factory("http://127.0.0.1:1"), data_dir)
    url = "http://127.0.0.1:1/files/broken.doc"
    raw = pipeline.store.write_bytes(
        source_id="TESTSRC",
        crawl_date="2026-09-13",
        kind="attachment",
        filename="broken.doc",
        content=broken,
    )
    crawl_id = "TESTSRC_20260913_0001"
    pipeline.manifest.record(
        crawl_id=crawl_id,
        source_id="TESTSRC",
        requested_url=url,
        final_url=url,
        crawl_time=NOW.isoformat(),
        http_status=200,
        content_type="application/msword",
        raw=raw,
        discovery_method="attachment",
    )
    pipeline.failures.record(
        source_id="TESTSRC",
        url=url,
        time=NOW.isoformat(),
        stage="parse",
        error_type="parse_error",
        message="附件正文尚未入库",
        retry_count=0,
        final_action="retry_later",
        crawl_id=crawl_id,
    )

    report = pipeline.resume_failures("TESTSRC")
    assert report.recovered == [] and len(report.failures) == 1
    assert report.counters.documents == 0
    assert not (data_dir / "normalized" / "documents.jsonl").exists()
    assert (data_dir / raw.relative_path).read_bytes() == broken  # 原件保留
    assert pipeline.recovery_plan()[0].action == "reparse"  # 失败仍未关闭
