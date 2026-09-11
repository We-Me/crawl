"""统一应用配置入口。

实现 project-startup.md 的配置契约：进程已有环境变量优先于 uv 显式加载的
.env，开发未设置数据根时使用工程根下 data/，生产必须显式给出绝对路径。
路径解析只发生在这里；其他模块接收 Settings 或由它派生的目录，不各自读取
环境变量，也不硬编码 data/。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional

logger = logging.getLogger(__name__)

ENV_MODE = "CRAWL_ENV"
ENV_DATA_DIR = "CRAWL_DATA_DIR"

MODE_DEVELOPMENT = "development"
MODE_PRODUCTION = "production"
VALID_MODES = (MODE_DEVELOPMENT, MODE_PRODUCTION)

DEFAULT_DATA_DIR_NAME = "data"
_WRITE_PROBE_NAME = ".crawl-write-probe"


class ConfigurationError(ValueError):
    """配置缺失、非法或数据根不可用时抛出；调用方不得静默回退。"""


@dataclass(frozen=True)
class Settings:
    """一次构建、处处复用的运行配置。"""

    mode: str
    data_dir: Path
    project_root: Optional[Path]
    data_dir_from_default: bool

    @property
    def is_production(self) -> bool:
        return self.mode == MODE_PRODUCTION


def detect_project_root(start: Optional[Path] = None) -> Optional[Path]:
    """从源码位置向上寻找同时含 pyproject.toml 和 src/crawler/ 的工程根。

    打包安装后通常找不到该结构，此时返回 None；调用方对未配置或相对路径
    必须报配置错误，不能猜测工程根。
    """
    current = (start or Path(__file__)).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").is_file() and (candidate / "src" / "crawler").is_dir():
            return candidate
    return None


def load_settings(
    environ: Optional[Mapping[str, str]] = None,
    project_root: Optional[Path] = None,
) -> Settings:
    """读取并校验运行配置，返回解析后的绝对数据根。

    environ 缺省时读取 os.environ；测试可注入映射及工程根。
    """
    env: Mapping[str, str] = os.environ if environ is None else environ

    mode = _resolve_mode(env)
    root = project_root if project_root is not None else detect_project_root()
    raw_dir = env[ENV_DATA_DIR] if ENV_DATA_DIR in env else None

    if raw_dir == "":
        raise ConfigurationError(
            "CRAWL_DATA_DIR 显式为空；请删除该变量以使用开发默认值，或给出有效路径"
        )

    if mode == MODE_PRODUCTION:
        if raw_dir is None:
            raise ConfigurationError("生产模式必须显式配置 CRAWL_DATA_DIR 绝对路径")
        candidate = Path(raw_dir)
        if not candidate.is_absolute():
            raise ConfigurationError(
                f"生产模式 CRAWL_DATA_DIR 必须是绝对路径，当前为 {raw_dir!r}"
            )
        data_dir = candidate
        from_default = False
    elif raw_dir is None:
        if root is None:
            raise ConfigurationError(
                "未配置 CRAWL_DATA_DIR，且当前安装中无法识别源码工程根；请显式配置数据根"
            )
        data_dir = root / DEFAULT_DATA_DIR_NAME
        from_default = True
    else:
        candidate = Path(raw_dir)
        if candidate.is_absolute():
            data_dir = candidate
        else:
            if root is None:
                raise ConfigurationError(
                    "CRAWL_DATA_DIR 为相对路径，但当前安装中无法识别源码工程根；"
                    "请改用绝对路径或从源码工程运行"
                )
            data_dir = root / candidate
        from_default = False

    resolved = _ensure_usable_directory(data_dir)
    logger.info(
        "配置载入 mode=%s data_dir=%s default=%s", mode, resolved, from_default
    )
    return Settings(
        mode=mode,
        data_dir=resolved,
        project_root=root,
        data_dir_from_default=from_default,
    )


def _resolve_mode(env: Mapping[str, str]) -> str:
    raw_mode = env[ENV_MODE] if ENV_MODE in env else None
    if raw_mode is None:
        return MODE_DEVELOPMENT
    if raw_mode == "":
        raise ConfigurationError(
            "CRAWL_ENV 显式为空；应为 development 或 production 之一"
        )
    if raw_mode not in VALID_MODES:
        raise ConfigurationError(
            f"CRAWL_ENV 取值非法：{raw_mode!r}；应为 development 或 production 之一"
        )
    return raw_mode


def _ensure_usable_directory(path: Path) -> Path:
    """校验目标不是文件、可创建且可写；失败时抛出明确错误。"""
    resolved = path.expanduser().resolve()
    if resolved.exists() and not resolved.is_dir():
        raise ConfigurationError(f"数据根已存在但不是目录：{resolved}")
    try:
        resolved.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ConfigurationError(f"无法创建数据根 {resolved}：{exc}") from exc
    if not resolved.is_dir():
        raise ConfigurationError(f"数据根不是目录：{resolved}")
    if not os.access(resolved, os.W_OK | os.X_OK):
        raise ConfigurationError(f"数据根不可写：{resolved}")
    _probe_writable(resolved)
    return resolved


def _probe_writable(directory: Path) -> None:
    probe = directory / _WRITE_PROBE_NAME
    try:
        fd = os.open(probe, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return
    except OSError as exc:
        raise ConfigurationError(f"数据根不可写 {directory}：{exc}") from exc
    try:
        os.close(fd)
    finally:
        try:
            os.unlink(probe)
        except OSError:
            pass
