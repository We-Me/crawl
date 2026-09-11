"""T003 固定样本夹具的离线完整性与契约字段检查。"""

import json
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
CONTRACTS = ROOT / "specs" / "001-public-knowledge-collection" / "contracts"

HTML_FIXTURES = [
    "html/detail_page.html",
    "html/expandable_page.html",
    "html/table_page.html",
    "html/version_v1.html",
    "html/version_v2.html",
]
REQUIRED_FIXTURES = HTML_FIXTURES + [
    "attachments/notice.csv",
    "attachments/notice.pdf",
    "ocr/scanned_notice.png",
    "ocr/scanned_notice.pdf",
    "office/notice.docx",
    "office/notice.xlsx",
    "manifests/failed_records.jsonl",
    "README.md",
]

URL_PATTERN = re.compile(r"https?://([^/\s\"'>]+)")
FICTIONAL_HOST = "example.invalid"


class _Collector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.attrs = []
        self.text_parts = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attrs.extend(attrs)
        if tag in ("h1", "h2", "p", "li", "td", "th", "title", "a"):
            self.text_parts.append((tag, None))

    def handle_data(self, data):
        if data.strip():
            if self.text_parts:
                tag, _ = self.text_parts[-1]
                self.text_parts[-1] = (tag, data.strip())


@pytest.mark.parametrize("relative", REQUIRED_FIXTURES)
def test_required_fixture_exists(relative):
    path = FIXTURES / relative
    assert path.is_file(), relative
    assert path.stat().st_size > 0


@pytest.mark.parametrize("relative", HTML_FIXTURES)
def test_html_fixture_parses_and_uses_fictional_hosts(relative):
    text = (FIXTURES / relative).read_text(encoding="utf-8")
    parser = _Collector()
    parser.feed(text)
    assert "html" in parser.tags and "main" in parser.tags
    hosts = set(URL_PATTERN.findall(text))
    assert hosts <= {FICTIONAL_HOST}, hosts


def test_detail_page_has_structure_and_attachment_links():
    text = (FIXTURES / "html" / "detail_page.html").read_text(encoding="utf-8")
    parser = _Collector()
    parser.feed(text)
    assert parser.tags.count("h2") == 4
    assert parser.tags.count("table") == 1
    hrefs = [value for name, value in parser.attrs if name == "href"]
    assert hrefs == ["../attachments/notice.csv", "../attachments/unavailable.pdf"]


def test_version_fixtures_keep_identity_and_change_revision():
    v1 = (FIXTURES / "html" / "version_v1.html").read_text(encoding="utf-8")
    v2 = (FIXTURES / "html" / "version_v2.html").read_text(encoding="utf-8")
    assert "三十个工作日" in v1 and "三十个工作日" not in v2
    assert "十五个工作日" in v2 and "十五个工作日" not in v1
    assert "本办法适用于虚构示例场景" in v1 and "本办法适用于虚构示例场景" in v2


def test_failure_fixture_matches_contract_types():
    schema = json.loads(
        (CONTRACTS / "failure.schema.json").read_text(encoding="utf-8")
    )
    required = schema["required"]
    properties = schema["properties"]
    rows = [
        json.loads(line)
        for line in (FIXTURES / "manifests" / "failed_records.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    assert rows
    for row in rows:
        assert set(required) <= set(row)
        assert set(row) <= set(properties)
        for field in required:
            field_type = properties[field]["type"]
            assert not isinstance(row[field], type(None))
            if field_type == "string":
                assert isinstance(row[field], str)
            elif field_type == "integer":
                assert isinstance(row[field], int)
        assert URL_PATTERN.findall(row["url"]) == [FICTIONAL_HOST]


def test_binary_fixture_magic_bytes():
    assert (FIXTURES / "attachments" / "notice.pdf").read_bytes().startswith(b"%PDF-")
    assert (FIXTURES / "ocr" / "scanned_notice.pdf").read_bytes().startswith(b"%PDF-")
    assert (FIXTURES / "ocr" / "scanned_notice.png").read_bytes().startswith(
        b"\x89PNG\r\n\x1a\n"
    )
    assert (FIXTURES / "office" / "notice.docx").read_bytes().startswith(b"PK\x03\x04")
    assert (FIXTURES / "office" / "notice.xlsx").read_bytes().startswith(b"PK\x03\x04")
