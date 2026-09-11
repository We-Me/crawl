"""运行日志（T017，FR-018）。

日志写入数据根的 logs/crawler.log；同一进程对同一数据根只挂一个文件处理器，
重复调用不会重复写行。日志只记录运行上下文、计数和异常摘要，不打印环境变量或
.env 内容（project-startup.md 的日志约束）。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from crawler.output.layout import CRAWLER_LOG_FILENAME, DeliveryLayout

LOG_DIRNAME = "logs"
LOG_FILENAME = CRAWLER_LOG_FILENAME
LOGGER_NAME = "crawler"
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
DATE_FORMAT = "%Y-%m-%dT%H:%M:%S%z"
_HANDLER_FLAG = "_crawler_run_handler"


def log_path(data_dir: Path) -> Path:
    """本次运行日志文件：<数据根>/logs/crawler.log。"""
    return DeliveryLayout(data_dir).crawler_log_path


def configure_run_logging(
    data_dir: Path,
    *,
    level: int = logging.INFO,
) -> Path:
    """给 crawler 日志树挂上数据根内的文件处理器，返回日志文件路径。

    幂等：同一数据根重复调用复用已有处理器；切换数据根时移除本模块此前挂的处理器。
    只管理本模块创建的处理器，不影响调用方自行配置的 handler。
    """
    path = log_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(LOGGER_NAME)
    resolved = path.resolve()
    for handler in list(logger.handlers):
        if not getattr(handler, _HANDLER_FLAG, False):
            continue
        if Path(getattr(handler, "baseFilename", resolved)).resolve() == resolved:
            handler.setLevel(level)
            _ensure_level(logger, level)
            return path
        logger.removeHandler(handler)
        handler.close()
    handler = logging.FileHandler(path, mode="a", encoding="utf-8")
    handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
    handler.setLevel(level)
    setattr(handler, _HANDLER_FLAG, True)
    logger.addHandler(handler)
    _ensure_level(logger, level)
    return path


def close_run_logging(data_dir: Optional[Path] = None) -> None:
    """关闭本模块挂的运行日志处理器；测试与嵌入式调用释放文件句柄用。"""
    logger = logging.getLogger(LOGGER_NAME)
    target = None if data_dir is None else log_path(data_dir).resolve()
    for handler in list(logger.handlers):
        if not getattr(handler, _HANDLER_FLAG, False):
            continue
        if target is not None and Path(getattr(handler, "baseFilename", target)).resolve() != target:
            continue
        logger.removeHandler(handler)
        handler.close()


def log_run_context(logger: logging.Logger, settings) -> None:
    """记录运行模式、解析后的数据根以及是否为默认值；不打印任何环境变量内容。"""
    logger.info(
        "运行配置 mode=%s data_dir=%s data_dir_default=%s",
        settings.mode,
        settings.data_dir,
        settings.data_dir_from_default,
    )


def _ensure_level(logger: logging.Logger, level: int) -> None:
    if logger.level == logging.NOTSET or logger.level > level:
        logger.setLevel(level)
