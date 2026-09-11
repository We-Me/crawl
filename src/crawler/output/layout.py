"""交付目录布局（T018，FR-019）。

统一六项成果的落盘位置：raw/、manifests/、normalized/、logs/，所有组件都从同一份
布局取路径，不在各自模块里拼 data 目录。raw_path 始终是相对数据根的路径；读取时
经 resolve_raw_path 校验，拒绝绝对路径、``..`` 与符号链接越界。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Union

from crawler.util.paths import PathSafetyError, ensure_within, safe_segment

RAW_DIRNAME = "raw"
MANIFESTS_DIRNAME = "manifests"
NORMALIZED_DIRNAME = "normalized"
LOGS_DIRNAME = "logs"

MANIFEST_FILENAME = "crawl_manifest.jsonl"
FAILED_FILENAME = "failed_records.jsonl"
DOCUMENTS_FILENAME = "documents.jsonl"
BLOCKS_FILENAME = "blocks.jsonl"
CRAWLER_LOG_FILENAME = "crawler.log"
METRICS_FILENAME = "metrics.json"
METRICS_HISTORY_FILENAME = "metrics_history.jsonl"
INCREMENTAL_STATE_FILENAME = "incremental_state.json"

REQUIRED_DIRNAMES = (RAW_DIRNAME, MANIFESTS_DIRNAME, NORMALIZED_DIRNAME, LOGS_DIRNAME)


@dataclass(frozen=True)
class DeliveryLayout:
    """一个数据根的交付布局；路径解析基准只来自这里。"""

    data_dir: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "data_dir", Path(self.data_dir).resolve())

    # ---- 目录 ----
    @property
    def raw_dir(self) -> Path:
        return self.data_dir / RAW_DIRNAME

    @property
    def manifests_dir(self) -> Path:
        return self.data_dir / MANIFESTS_DIRNAME

    @property
    def normalized_dir(self) -> Path:
        return self.data_dir / NORMALIZED_DIRNAME

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / LOGS_DIRNAME

    def required_dirs(self):
        return {
            RAW_DIRNAME: self.raw_dir,
            MANIFESTS_DIRNAME: self.manifests_dir,
            NORMALIZED_DIRNAME: self.normalized_dir,
            LOGS_DIRNAME: self.logs_dir,
        }

    def ensure(self) -> "DeliveryLayout":
        """建齐四个交付目录；已存在内容不删除、不搬迁。"""
        for directory in self.required_dirs().values():
            directory.mkdir(parents=True, exist_ok=True)
        return self

    # ---- 文件 ----
    @property
    def manifest_path(self) -> Path:
        return self.manifests_dir / MANIFEST_FILENAME

    @property
    def failures_path(self) -> Path:
        return self.manifests_dir / FAILED_FILENAME

    @property
    def documents_path(self) -> Path:
        return self.normalized_dir / DOCUMENTS_FILENAME

    @property
    def blocks_path(self) -> Path:
        return self.normalized_dir / BLOCKS_FILENAME

    @property
    def crawler_log_path(self) -> Path:
        return self.logs_dir / CRAWLER_LOG_FILENAME

    @property
    def metrics_path(self) -> Path:
        return self.logs_dir / METRICS_FILENAME

    @property
    def metrics_history_path(self) -> Path:
        return self.logs_dir / METRICS_HISTORY_FILENAME

    @property
    def incremental_state_path(self) -> Path:
        return self.manifests_dir / INCREMENTAL_STATE_FILENAME

    # ---- 路径规则 ----
    def raw_dir_for(self, source_id: str, date_str: str, kind: str) -> Path:
        """原件目录 raw/<source_id>/<YYYY-MM-DD>/<kind>/。"""
        safe_source = safe_segment(source_id, field="source_id")
        safe_kind = safe_segment(kind, field="kind")
        return self.raw_dir / safe_source / date_str / safe_kind

    def resolve_raw_path(self, raw_path: Union[str, Path]) -> Path:
        """把记录的相对 raw_path 解析为数据根内路径；任何越界都拒绝。"""
        text = str(raw_path)
        if not text.strip():
            raise PathSafetyError("raw_path 不能为空")
        candidate = Path(text)
        if candidate.is_absolute() or text.startswith(("\\\\", "//")):
            raise PathSafetyError(f"raw_path 必须是相对路径：{text!r}")
        if ".." in candidate.parts:
            raise PathSafetyError(f"raw_path 不能包含 ..：{text!r}")
        return ensure_within(self.data_dir, self.data_dir / candidate)

    def relative_to_root(self, path: Union[str, Path]) -> str:
        """把数据根内路径转成相对路径（POSIX 分隔符），越界时报错。"""
        resolved = ensure_within(self.data_dir, Path(path))
        return resolved.relative_to(self.data_dir).as_posix()
