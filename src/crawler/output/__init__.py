"""原件归档、交付布局与 JSONL 写出。"""

from crawler.output.delivery import (
    REQUIRED_DELIVERABLES,
    DeliveryReport,
    inspect_delivery,
)
from crawler.output.documents_writer import DocumentsWriter
from crawler.output.failures_writer import FailureWriter
from crawler.output.jsonl import append_jsonl, read_jsonl, write_jsonl
from crawler.output.layout import DeliveryLayout
from crawler.output.manifest_writer import ManifestWriter
from crawler.output.raw_store import RawRecord, RawStore, RawStoreError

__all__ = [
    "DeliveryLayout",
    "DeliveryReport",
    "DocumentsWriter",
    "FailureWriter",
    "ManifestWriter",
    "RawRecord",
    "RawStore",
    "RawStoreError",
    "REQUIRED_DELIVERABLES",
    "inspect_delivery",
    "append_jsonl",
    "read_jsonl",
    "write_jsonl",
]
