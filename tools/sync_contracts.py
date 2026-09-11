#!/usr/bin/env python3
"""同步/校验随包运行契约（NEXT-08）。

规格目录 `specs/001-public-knowledge-collection/contracts/` 是契约的权威来源；
运行命令 (`crawl sources`、`crawl check`) 读取随包资源 `src/crawler/contracts/`，
两者必须逐字节一致，避免维护两套会漂移的 schema。

用法：
  uv run --locked --no-python-downloads python tools/sync_contracts.py          # 写入随包副本
  uv run --locked --no-python-downloads python tools/sync_contracts.py --check  # 只校验一致性，漂移时退出码 1
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC_CONTRACTS = (
    REPO_ROOT / "specs" / "001-public-knowledge-collection" / "contracts"
)
PACKAGED_CONTRACTS = REPO_ROOT / "src" / "crawler" / "contracts"
CONTRACT_SUFFIX = ".schema.json"


def contract_files(directory: Path) -> list:
    return sorted(path.name for path in directory.glob(f"*{CONTRACT_SUFFIX}"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check() -> int:
    if not SPEC_CONTRACTS.is_dir():
        print(f"规格契约目录不存在：{SPEC_CONTRACTS}", file=sys.stderr)
        return 1
    problems = []
    for name in contract_files(SPEC_CONTRACTS):
        source = SPEC_CONTRACTS / name
        target = PACKAGED_CONTRACTS / name
        if not target.is_file():
            problems.append(f"随包契约缺失：{name}")
            continue
        if digest(source) != digest(target):
            problems.append(f"随包契约与规格不一致：{name}")
    for name in contract_files(PACKAGED_CONTRACTS):
        if not (SPEC_CONTRACTS / name).is_file():
            problems.append(f"随包契约在规格目录没有对应来源：{name}")
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        print("运行 tools/sync_contracts.py 重新同步后重试", file=sys.stderr)
        return 1
    print(f"契约一致：{len(contract_files(SPEC_CONTRACTS))} 个文件（{PACKAGED_CONTRACTS}）")
    return 0


def sync() -> int:
    if not SPEC_CONTRACTS.is_dir():
        print(f"规格契约目录不存在：{SPEC_CONTRACTS}", file=sys.stderr)
        return 1
    PACKAGED_CONTRACTS.mkdir(parents=True, exist_ok=True)
    names = contract_files(SPEC_CONTRACTS)
    for name in names:
        shutil.copyfile(SPEC_CONTRACTS / name, PACKAGED_CONTRACTS / name)
    print(f"已同步 {len(names)} 个契约到 {PACKAGED_CONTRACTS}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="同步或校验随包运行契约")
    parser.add_argument("--check", action="store_true", help="只校验一致性，不写入")
    args = parser.parse_args(argv)
    return check() if args.check else sync()


if __name__ == "__main__":
    raise SystemExit(main())
