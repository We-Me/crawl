"""原子写入与跨进程锁（并发运行安全，S5-06）。

多个 collect 进程可能共用一个数据根，同时写待处理项、发现游标、增量状态与运行指标。
固定临时名 ``<file>.tmp`` 会在并发 ``os.replace`` 时互相覆盖（先替换者移走临时文件，
后替换者拿到 FileNotFoundError）；“读-改-写”不加锁则会整段丢失其他进程的更新。

这里提供两个基础原语：

- :func:`atomic_writer` / :func:`atomic_write_text` / :func:`atomic_write_json`：
  写入本进程唯一的临时文件（uuid 后缀），完成后 ``os.replace`` 目标；异常时清理临时文件，
  读取者只会看到完整内容；
- :func:`file_lock`：以 ``<file>.lock`` 为载体的建议锁，覆盖单个文件的一次“读-改-写”，
  进程间用 flock，进程内用线程锁。同一路径的嵌套加锁不会死锁：阻塞模式会等自己
  （调用方不得嵌套），非阻塞模式抛 :class:`LockUnavailable`。
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Iterator, Optional, TextIO

try:  # POSIX 平台用 flock 覆盖跨进程
    import fcntl
except ImportError:  # pragma: no cover - 非 POSIX 平台退回进程内线程锁
    fcntl = None  # type: ignore[assignment]

_THREAD_LOCKS: Dict[str, threading.Lock] = {}
_THREAD_LOCKS_GUARD = threading.Lock()


class LockUnavailable(RuntimeError):
    """锁已被其它进程或线程占用（非阻塞获取失败）；调用方据此放弃本次操作。"""


def _thread_lock(path: Path) -> threading.Lock:
    key = str(path)
    with _THREAD_LOCKS_GUARD:
        lock = _THREAD_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _THREAD_LOCKS[key] = lock
        return lock


@contextmanager
def file_lock(path: Path, *, blocking: bool = True) -> Iterator[None]:
    """保护 ``path`` 的一次读-改-写：``<path>.lock`` 上 flock，同进程线程先互斥。

    ``blocking=False`` 时锁被占用立即抛 :class:`LockUnavailable`，不等待。
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + ".lock")
    thread_lock = _thread_lock(lock_path)
    if not thread_lock.acquire(blocking=blocking):
        raise LockUnavailable(f"锁已被占用：{lock_path}")
    try:
        if fcntl is None:  # pragma: no cover - 非 POSIX 平台没有跨进程锁
            yield
            return
        with lock_path.open("a+", encoding="utf-8") as handle:
            flags = fcntl.LOCK_EX if blocking else fcntl.LOCK_EX | fcntl.LOCK_NB
            try:
                fcntl.flock(handle.fileno(), flags)
            except BlockingIOError as exc:
                raise LockUnavailable(f"锁已被其它进程占用：{lock_path}") from exc
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        thread_lock.release()


@contextmanager
def atomic_writer(path: Path) -> Iterator[TextIO]:
    """写唯一临时文件，正常退出时替换目标；异常时删除临时文件并保留旧内容。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp-{uuid.uuid4().hex}")
    handle = tmp.open("w", encoding="utf-8")
    try:
        yield handle
        handle.flush()
        os.fsync(handle.fileno())
        handle.close()
        os.replace(tmp, path)
    except BaseException:
        handle.close()
        if tmp.exists():
            try:
                tmp.unlink()
            except FileNotFoundError:  # pragma: no cover - 临时文件已被移除
                pass
        raise


def atomic_write_text(path: Path, text: str) -> None:
    """整文件原子写入文本。"""
    with atomic_writer(path) as handle:
        handle.write(text)


def atomic_write_json(path: Path, payload: dict, *, indent: Optional[int] = None) -> None:
    """整文件原子写入 JSON 对象，末尾换行，UTF-8 不转义非 ASCII。"""
    text = json.dumps(payload, ensure_ascii=False, indent=indent) + "\n"
    atomic_write_text(path, text)
