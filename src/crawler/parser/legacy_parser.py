"""旧式 DOC/XLS 支持路线（T012）。

旧式 .doc/.xls 是 OLE2 复合文档，python-docx 与 openpyxl 均不支持，本项目不
自行解析二进制格式。已验证的路线是：按 OLE2 魔数识别 → 用系统 LibreOffice
（soffice/libreoffice 命令）headless 转换为 docx/xlsx → 复用现有解析器；转换器
不可用或转换失败时抛出带路线说明的 LegacyFormatError，由调用方记入失败记录，
不得静默返回空文档。转换器可注入，便于测试与后续替换。
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Optional, Tuple

from crawler.parser.docx_parser import parse_docx
from crawler.parser.parsed_page import ParsedPage
from crawler.parser.xlsx_parser import parse_xlsx

logger = logging.getLogger(__name__)

OLE2_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
LEGACY_EXTENSIONS = (".doc", ".xls")
TARGET_EXTENSIONS = {".doc": ".docx", ".xls": ".xlsx"}
CONVERT_TIMEOUT_SECONDS = 120

Converter = Callable[[bytes, str], Tuple[bytes, str]]


class LegacyFormatError(ValueError):
    """旧式 DOC/XLS 需要转换器，或转换失败。"""


def is_legacy_office(content: bytes) -> bool:
    return content.startswith(OLE2_MAGIC)


def find_soffice() -> Optional[str]:
    for name in ("soffice", "libreoffice"):
        path = shutil.which(name)
        if path:
            return path
    return None


def parse_legacy(
    content: bytes,
    filename: str,
    page_url: str = "",
    *,
    converter: Optional[Converter] = None,
) -> ParsedPage:
    extension = Path(filename).suffix.lower()
    if not is_legacy_office(content):
        raise LegacyFormatError(f"不是旧式 OLE2 Office 文件：{filename}")
    if extension not in LEGACY_EXTENSIONS:
        raise LegacyFormatError(f"不支持的旧式格式：{extension or filename}")
    converter = converter or soffice_converter
    converted, target_extension = converter(content, extension)
    if target_extension == ".docx":
        return parse_docx(converted, page_url)
    if target_extension == ".xlsx":
        return parse_xlsx(converted, page_url)
    raise LegacyFormatError(f"转换器返回未知目标格式：{target_extension}")


def soffice_converter(content: bytes, extension: str) -> Tuple[bytes, str]:
    """用系统 LibreOffice headless 转换；任一失败都抛 LegacyFormatError。

    实测 LibreOffice 24.2 在源文件无法加载时会以 0 退出且不产出文件，因此不能只
    看退出码：退出码非 0 与“未生成目标文件”分别报错，都不会当作空成功放行。
    """
    soffice = find_soffice()
    if soffice is None:
        raise LegacyFormatError(
            "本机未安装 LibreOffice（soffice/libreoffice），无法转换旧式 "
            f"{extension}；请安装 LibreOffice 后重试或提供转换器"
        )
    target_extension = TARGET_EXTENSIONS[extension]
    with tempfile.TemporaryDirectory() as workdir:
        source = Path(workdir) / f"source{extension}"
        source.write_bytes(content)
        command = [
            soffice,
            "--headless",
            "--convert-to",
            target_extension.lstrip("."),
            "--outdir",
            workdir,
            str(source),
        ]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                timeout=CONVERT_TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise LegacyFormatError(f"LibreOffice 转换失败：{exc}") from exc
        output = Path(workdir) / f"source{target_extension}"
        message = result.stderr.decode("utf-8", errors="replace").strip()
        if result.returncode != 0:
            raise LegacyFormatError(f"LibreOffice 转换失败（code={result.returncode}）：{message}")
        if not output.is_file():
            raise LegacyFormatError(
                f"LibreOffice 未生成转换结果 {target_extension}（源文件无法转换）：{message}"
            )
        logger.info("旧式 %s 已转换为 %s", extension, target_extension)
        return output.read_bytes(), target_extension
