"""R3 反向灵敏度核对（一次性脚本，仅用于证据）：临时移除归档锁，验证两真实进程交错时
会出现 crawl_id 复用或同名原件覆盖。正常测试不修改 file_lock；本脚本只为证明
tests/test_archive_processes.py 约束的是锁语义。

用法（仓库根目录）：uv run python specs/001-public-knowledge-collection/evidence/logs/stage-six-r3-unlocked-sensitivity.py
只写 /tmp 临时数据根，不触碰开发 data/。
"""

import collections
import json
import multiprocessing
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "src"))

import crawler.output.archive as archive_module
from crawler.output.archive import ResponseArchiver


@contextmanager
def _no_lock(_path):
    yield None


archive_module.file_lock = _no_lock  # 仅本脚本：去掉跨进程归档锁

FIXED = datetime(2026, 9, 14, 10, 0, 0, tzinfo=timezone.utc)
ROUNDS = 8


def worker(data_dir, name, mode, barrier):
    archiver = ResponseArchiver(Path(data_dir), now=lambda: FIXED)
    payload = b"shared-identical-bytes" if mode == "identical" else None
    barrier.wait(timeout=60)
    for index in range(ROUNDS):
        content = payload if payload is not None else f"unique-{name}-{index}".encode()
        url = f"https://example.invalid/{name}/{index}.html"
        archiver.archive_bytes(
            content,
            source_id="SENS",
            kind="html",
            filename="same-name.html",
            discovery_method="list",
            requested_url=url,
            final_url=url,
            status_code=200,
            content_type="text/html",
        )


def attempt(mode):
    with tempfile.TemporaryDirectory() as tmp:
        ResponseArchiver(Path(tmp), now=lambda: FIXED)
        ctx = multiprocessing.get_context("fork")
        barrier = ctx.Barrier(2)
        procs = [
            ctx.Process(target=worker, args=(tmp, name, mode, barrier))
            for name in ("A", "B")
        ]
        for process in procs:
            process.start()
        for process in procs:
            process.join(timeout=120)
        exits = [process.exitcode for process in procs]
        manifest = Path(tmp) / "manifests" / "crawl_manifest.jsonl"
        rows = [
            json.loads(line)["crawl_id"]
            for line in manifest.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        duplicate = {key: value for key, value in collections.Counter(rows).items() if value > 1}
        return exits, len(rows), len(duplicate), sorted(duplicate.items())[:3]


def main():
    print("模式 A：同名不同字节（无锁）")
    exits, rows, duplicates, sample = attempt("different")
    print(f"  exits={exits} rows={rows} duplicated_ids={duplicates} sample={sample}")

    print("模式 B：同名相同字节（无锁，5 次）")
    hits = 0
    for index in range(5):
        exits, rows, duplicates, sample = attempt("identical")
        hits += 1 if duplicates else 0
        print(
            f"  attempt {index + 1}: exits={exits} rows={rows} "
            f"duplicated_ids={duplicates} sample={sample}"
        )
    print(f"  出现重复 crawl_id 的次数={hits}/5")


if __name__ == "__main__":
    main()
