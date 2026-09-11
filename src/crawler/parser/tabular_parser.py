"""CSV 解析（T012）。

按原文行列保留表头、数据行与原始行号；分隔符与编码由实际解析结果记录，
不靠猜测改写内容。首行按布局约定作为表头（header_row=1）。不使用
pandas 等大依赖：csv 标准库即可满足当前范围。
"""

from __future__ import annotations

import csv
import codecs
import io
import logging
from typing import List, Optional, Tuple

from crawler.parser.parsed_page import ParsedBlock, ParsedPage

logger = logging.getLogger(__name__)

EXTRACTION_METHOD = "csv_stdlib"
ENCODING_CANDIDATES = ("utf-8", "gbk", "gb18030")


class CsvParseError(ValueError):
    """CSV 无法解码或解析。"""


def parse_csv(content: bytes, page_url: str = "") -> ParsedPage:
    text, encoding = decode_csv_bytes(content)
    delimiter = _detect_delimiter(text)
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows_with_numbers: List[Tuple[int, List[str]]] = []
    try:
        for row_number, row in enumerate(reader, start=1):
            values = [value.strip() for value in row]
            if any(values):
                rows_with_numbers.append((row_number, values))
    except csv.Error as exc:
        raise CsvParseError(f"CSV 无法解析：{exc}") from exc
    if not rows_with_numbers:
        raise CsvParseError("CSV 没有可解析的行")

    headers = rows_with_numbers[0][1]
    data_rows = [values for _, values in rows_with_numbers[1:]]
    block = ParsedBlock(
        block_type="table",
        text="\n".join("\t".join(values) for _, values in rows_with_numbers),
        structured_data={
            "encoding": encoding,
            "delimiter": delimiter,
            "header_row": rows_with_numbers[0][0],
            "headers": headers,
            "rows": data_rows,
            "row_numbers": [number for number, _ in rows_with_numbers[1:]],
            "caption": None,
        },
    )
    logger.debug("CSV 解析完成 url=%s rows=%d", page_url, len(rows_with_numbers))
    return ParsedPage(
        title=headers[0] if headers and headers[0] else "",
        full_text=block.text,
        blocks=(block,),
        extraction_method=EXTRACTION_METHOD,
        metadata_missing=("publication_date",) if headers else ("title", "publication_date"),
        canonical_url=page_url or None,
    )


def decode_csv_bytes(content: bytes) -> Tuple[str, str]:
    if content.startswith(codecs.BOM_UTF8):
        return content.decode("utf-8-sig"), "utf-8-sig"
    for encoding in ENCODING_CANDIDATES:
        try:
            return content.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace"), "utf-8(replace)"


def _detect_delimiter(text: str) -> str:
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        return dialect.delimiter
    except csv.Error:
        return ","
