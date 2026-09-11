"""交付校验：契约 schema、端到端追溯与验收用例登记。"""

from crawler.validate.acceptance import (
    ACCEPTANCE_CASES,
    AcceptanceCase,
    build_acceptance_report,
    case_index,
)
from crawler.validate.schema import (
    CONTRACT_FILES,
    SchemaConfigError,
    ValidationReport,
    contracts_dir,
    load_contract,
    validate_delivery,
    validate_instance,
    validate_jsonl_file,
    validate_rows,
)
from crawler.validate.traceability import TraceReport, trace_delivery

__all__ = [
    "ACCEPTANCE_CASES",
    "AcceptanceCase",
    "CONTRACT_FILES",
    "SchemaConfigError",
    "TraceReport",
    "ValidationReport",
    "build_acceptance_report",
    "case_index",
    "contracts_dir",
    "load_contract",
    "trace_delivery",
    "validate_delivery",
    "validate_instance",
    "validate_jsonl_file",
    "validate_rows",
]
