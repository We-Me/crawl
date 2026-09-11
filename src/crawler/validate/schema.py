"""契约 schema 校验（T019，NFR-002）。

用标准库实现评审契约 contracts/*.schema.json 实际使用到的 JSON Schema 子集：
type、properties、required、items、enum、const、pattern、format（date/date-time/uri）、
数值与长度边界、minItems/minProperties、additionalProperties、allOf、anyOf、if/then/else。
不引入新依赖；校验结果带文件、行号和路径，便于定位到 JSONL 的具体记录。
"""

from __future__ import annotations

import json
import logging
import re
from importlib import resources
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import List, Mapping, Optional, Sequence
from urllib.parse import urlsplit

from crawler.output.layout import DeliveryLayout

logger = logging.getLogger(__name__)

CONTRACT_FILES = {
    "manifest": "manifest.schema.json",
    "document": "document.schema.json",
    "block": "block.schema.json",
    "attachment": "attachment.schema.json",
    "failure": "failure.schema.json",
    "source_registry": "source-registry.schema.json",
}

# 随包契约资源（NEXT-08）：规格 contracts/ 是权威来源，构建/提交流程用
# tools/sync_contracts.py 同步并校验，运行时只读这一份，不再依赖源码树。
PACKAGE_NAME = "crawler"
CONTRACTS_RESOURCE = "contracts"

_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class SchemaConfigError(ValueError):
    """契约文件缺失或不可读。"""


@dataclass
class ValidationReport:
    ok: bool = True
    errors: List[dict] = field(default_factory=list)
    by_file: dict = field(default_factory=dict)

    def as_row(self) -> dict:
        return {"ok": self.ok, "error_count": len(self.errors), "by_file": self.by_file, "errors": self.errors}


def contracts_dir() -> Path:
    """随包契约资源目录；资源缺失时明确报错，不回退到源码树或当前目录。"""
    path = Path(str(resources.files(PACKAGE_NAME).joinpath(CONTRACTS_RESOURCE)))
    if not path.is_dir():
        raise SchemaConfigError(
            f"随包契约资源缺失：{PACKAGE_NAME}/{CONTRACTS_RESOURCE}（{path}）；"
            "请重新安装完整发行包，不要指向开发机器路径"
        )
    return path


def load_contract(name: str, *, directory: Optional[Path] = None) -> dict:
    """读取运行契约；directory 显式给出目录时用于测试与调用方自带契约。"""
    if name not in CONTRACT_FILES:
        raise SchemaConfigError(f"未知契约：{name!r}；可用：{sorted(CONTRACT_FILES)}")
    filename = CONTRACT_FILES[name]
    if directory is not None:
        path = Path(directory) / filename
        if not path.is_file():
            raise SchemaConfigError(f"契约文件不存在：{path}")
        text = path.read_text(encoding="utf-8")
        source = str(path)
    else:
        resource = resources.files(PACKAGE_NAME).joinpath(CONTRACTS_RESOURCE, filename)
        try:
            text = resource.read_text(encoding="utf-8")
        except (FileNotFoundError, IsADirectoryError, ModuleNotFoundError, NotADirectoryError) as exc:
            raise SchemaConfigError(
                f"随包契约文件缺失：{PACKAGE_NAME}/{CONTRACTS_RESOURCE}/{filename}"
            ) from exc
        source = f"{PACKAGE_NAME}/{CONTRACTS_RESOURCE}/{filename}"
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise SchemaConfigError(f"契约文件不是合法 JSON：{source}：{exc}") from exc


# ---------- JSON Schema 子集 ----------


def validate_instance(instance, schema: Mapping, path: str = "$") -> List[str]:
    """返回错误列表；空列表表示通过。"""
    errors: List[str] = []

    for sub in schema.get("allOf", []):
        errors.extend(validate_instance(instance, sub, path))

    if "anyOf" in schema:
        if not any(not validate_instance(instance, sub, path) for sub in schema["anyOf"]):
            errors.append(f"{path}: 不满足 anyOf 任一分支")

    if "if" in schema:
        branch = schema.get("then") if not validate_instance(instance, schema["if"], path) else schema.get("else")
        if branch:
            errors.extend(validate_instance(instance, branch, path))

    expected = schema.get("type")
    if expected is not None and not _matches_type(instance, expected):
        errors.append(f"{path}: 类型应为 {_type_label(expected)}，实际 {type(instance).__name__}")
        return errors

    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: 取值应为 {schema['const']!r}，实际 {instance!r}")
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: 取值必须是 {schema['enum']} 之一，实际 {instance!r}")

    if isinstance(instance, str):
        errors.extend(_validate_string(instance, schema, path))
    if isinstance(instance, bool):
        pass
    elif isinstance(instance, (int, float)):
        errors.extend(_validate_number(instance, schema, path))

    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append(f"{path}: 元素个数至少 {schema['minItems']}，实际 {len(instance)}")
        items = schema.get("items")
        if isinstance(items, Mapping):
            for index, item in enumerate(instance):
                errors.extend(validate_instance(item, items, f"{path}[{index}]"))

    if isinstance(instance, Mapping):
        errors.extend(_validate_object(instance, schema, path))

    return errors


def _validate_string(value: str, schema: Mapping, path: str) -> List[str]:
    errors = []
    if "minLength" in schema and len(value) < schema["minLength"]:
        errors.append(f"{path}: 长度至少 {schema['minLength']}，实际 {len(value)}")
    if "maxLength" in schema and len(value) > schema["maxLength"]:
        errors.append(f"{path}: 长度至多 {schema['maxLength']}，实际 {len(value)}")
    if "pattern" in schema and not re.search(schema["pattern"], value):
        errors.append(f"{path}: 不匹配 pattern {schema['pattern']!r}：{value!r}")
    fmt = schema.get("format")
    if fmt == "date" and not _is_date(value):
        errors.append(f"{path}: 不是合法日期：{value!r}")
    elif fmt == "date-time" and not _is_datetime(value):
        errors.append(f"{path}: 不是合法日期时间：{value!r}")
    elif fmt == "uri" and not _is_uri(value):
        errors.append(f"{path}: 不是合法 URI：{value!r}")
    return errors


def _validate_number(value, schema: Mapping, path: str) -> List[str]:
    errors = []
    if "minimum" in schema and value < schema["minimum"]:
        errors.append(f"{path}: 不能小于 {schema['minimum']}，实际 {value!r}")
    if "maximum" in schema and value > schema["maximum"]:
        errors.append(f"{path}: 不能大于 {schema['maximum']}，实际 {value!r}")
    if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
        errors.append(f"{path}: 必须大于 {schema['exclusiveMinimum']}，实际 {value!r}")
    return errors


def _validate_object(instance: Mapping, schema: Mapping, path: str) -> List[str]:
    errors = []
    for key in schema.get("required", []):
        if key not in instance:
            errors.append(f"{path}: 缺少必填字段 {key!r}")
    if "minProperties" in schema and len(instance) < schema["minProperties"]:
        errors.append(f"{path}: 属性个数至少 {schema['minProperties']}，实际 {len(instance)}")
    properties = schema.get("properties", {})
    for key, value in instance.items():
        if key in properties:
            errors.extend(validate_instance(value, properties[key], f"{path}.{key}"))
            continue
        additional = schema.get("additionalProperties", True)
        if additional is False:
            errors.append(f"{path}: 出现契约未声明的字段 {key!r}")
        elif isinstance(additional, Mapping):
            errors.extend(validate_instance(value, additional, f"{path}.{key}"))
    return errors


def _matches_type(value, expected) -> bool:
    types = expected if isinstance(expected, list) else [expected]
    return any(_matches_single_type(value, name) for name in types)


def _matches_single_type(value, name: str) -> bool:
    if name == "object":
        return isinstance(value, Mapping)
    if name == "array":
        return isinstance(value, list)
    if name == "string":
        return isinstance(value, str)
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if name == "boolean":
        return isinstance(value, bool)
    if name == "null":
        return value is None
    return False


def _type_label(expected) -> str:
    return "/".join(expected) if isinstance(expected, list) else str(expected)


def _is_date(value: str) -> bool:
    if not _DATE_PATTERN.match(value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _is_datetime(value: str) -> bool:
    try:
        datetime.fromisoformat(value)
    except ValueError:
        return False
    return True


def _is_uri(value: str) -> bool:
    parts = urlsplit(value)
    return bool(parts.scheme) and bool(parts.netloc or parts.path)


# ---------- 交付文件校验 ----------


def validate_rows(
    rows: Sequence[Mapping],
    schema: Mapping,
    *,
    label: str,
    first_line: int = 1,
) -> List[dict]:
    errors = []
    for offset, row in enumerate(rows):
        for message in validate_instance(row, schema):
            errors.append({"file": label, "line": first_line + offset, "message": message})
    return errors


def load_jsonl_rows(path: Path, label: str) -> tuple:
    """逐行读取 JSONL，返回 ([(行号, 行对象)], [错误])；语法错误定位到具体行。"""
    path = Path(path)
    if not path.is_file():
        return [], []
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        return [], [{"file": label, "line": 0, "message": f"文件不是合法 UTF-8：{exc}"}]
    rows = []
    errors = []
    for line_no, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append({"file": label, "line": line_no, "message": f"JSON 语法错误：{exc.msg}"})
            continue
        if not isinstance(payload, Mapping):
            errors.append({"file": label, "line": line_no, "message": "JSONL 每行必须是 JSON 对象"})
            continue
        rows.append((line_no, payload))
    return rows, errors


def validate_jsonl_file(path: Path, schema: Mapping, *, label: Optional[str] = None) -> List[dict]:
    path = Path(path)
    label = label or path.name
    rows, errors = load_jsonl_rows(path, label)
    for line_no, row in rows:
        for message in validate_instance(row, schema):
            errors.append({"file": label, "line": line_no, "message": message})
    return errors


def validate_delivery(data_dir: Path, *, directory: Optional[Path] = None) -> ValidationReport:
    """按契约校验交付 JSONL；附件逐条按 attachment 契约校验。"""
    layout = DeliveryLayout(data_dir)
    contracts = {
        name: load_contract(name, directory=directory)
        for name in ("manifest", "document", "block", "attachment", "failure")
    }
    errors: List[dict] = []
    errors.extend(validate_jsonl_file(layout.manifest_path, contracts["manifest"], label="crawl_manifest.jsonl"))
    errors.extend(
        validate_jsonl_file(layout.failures_path, contracts["failure"], label="failed_records.jsonl")
    )
    errors.extend(validate_jsonl_file(layout.blocks_path, contracts["block"], label="blocks.jsonl"))
    errors.extend(_validate_documents(layout.documents_path, contracts))
    report = ValidationReport(ok=not errors, errors=errors)
    for error in errors:
        report.by_file[error["file"]] = report.by_file.get(error["file"], 0) + 1
    logger.info("schema 校验 ok=%s errors=%d", report.ok, len(errors))
    return report


def _validate_documents(path: Path, contracts: Mapping[str, Mapping]) -> List[dict]:
    rows, errors = load_jsonl_rows(path, "documents.jsonl")
    for line_no, row in rows:
        for message in validate_instance(row, contracts["document"]):
            errors.append({"file": "documents.jsonl", "line": line_no, "message": message})
        for position, attachment in enumerate(row.get("attachments") or []):
            for message in validate_instance(attachment, contracts["attachment"]):
                errors.append(
                    {
                        "file": "documents.jsonl",
                        "line": line_no,
                        "message": f"attachments[{position}] {message}",
                    }
                )
    return errors
