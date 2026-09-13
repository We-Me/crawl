"""分块抽象与最小 dummy 实现（本轮新增；T010/T013）。

分块接口 `BlockSegmenter` 用标准库 abc 定义，供不同解析路径复用同一块模型
（ParsedBlock）与既有 ID/顺序规则（normalize/block_schema.py），不改变块契约。

最小实现 `StructuralBlankLineSegmenter` 只做确定性结构分块，规则如下：

1. 标题（h1—h6）、段落（p）、列表项（li）、表格（table）仍各自保留为独立结构块，
   表格不被压平为普通文本，列表项不合并；
2. 对 div（以及语义相近的 section/article）中**尚未被上述结构节点覆盖**的直接正文
   文本，按空行拆块；空行来自 DOM 文本与显式换行（br → 换行），不是对 HTML 源码
   做 split；
3. 只消费容器的直接文本与内联元素文本：嵌套容器各自处理，结构节点只输出一次，
   父子 div 与嵌套 div 不重复消费；
4. 元素之间仅由源码缩进产生的空白文本节点不算空行；单个换行不是空行，连续 br 或
   文本中的空白行才是分隔信号（空白归一化在拆块之后，不提前抹掉分隔信息）；
5. 不做 token 截断、语义合并、重叠窗口或模型调用，不返回空结果伪造成功。

`extraction_method` 记录“基础抽取方式+分块实现+版本”（例如
`bs4_lxml_dom+structural_blank_line_v1`），以便运行记录区分分块实现。
未实现的后续处理（语义合并、OCR 后质量提升等）仍是 deferred，不在本模块伪造。
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

from crawler.normalize.text_utils import collapse_whitespace
from crawler.parser.parsed_page import ParsedBlock

logger = logging.getLogger(__name__)

HEADING_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6")
STRUCTURAL_TAGS = HEADING_TAGS + ("p", "li", "table")
# 允许承载“尚未被结构节点覆盖的正文”的容器；其余元素只按内联文本处理。
RESIDUAL_CONTAINER_TAGS = ("div", "section", "article")
# 已知内联元素：只并入当前文本流；其余标签按块级容器递归，避免吞掉内部结构块。
INLINE_TAGS = frozenset(
    {
        "a", "abbr", "b", "bdi", "bdo", "big", "cite", "code", "data", "del", "dfn",
        "em", "font", "i", "img", "ins", "kbd", "label", "mark", "math", "meter",
        "output", "progress", "q", "ruby", "s", "samp", "small", "span", "strike",
        "strong", "sub", "sup", "time", "tt", "u", "var", "wbr",
    }
)
# 空行分隔：至少两个换行（中间可含空格/制表符）即视为一个或多个空白行。
BLANK_LINE = re.compile(r"\n(?:[ \t]*\n)+")


class SegmenterInputError(ValueError):
    """分块实现收到的输入类型不受支持；显式报错，不返回空块冒充成功。"""


@dataclass(frozen=True)
class SegmentRequest:
    """分块输入：HTML 路径给 DOM 范围，已解析格式给结构块；两者不混用。"""

    dom: Optional[Any] = None
    blocks: Tuple[ParsedBlock, ...] = ()
    page_url: Optional[str] = None
    next_page_anchor: Optional[Any] = None


class BlockSegmenter(ABC):
    """分块接口：把解析输入转成原始结构块序列（顺序与原件一致）。"""

    name: str = ""
    version: str = ""
    status: str = "implemented"

    @property
    def method(self) -> str:
        return f"{self.name}_{self.version}"

    def as_row(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "status": self.status,
            "method": self.method,
        }

    @abstractmethod
    def segment(self, request: SegmentRequest) -> List[ParsedBlock]:
        """返回按原件顺序排列的块；不得吞掉输入错误或伪造空结果。"""


class StructuralBlankLineSegmenter(BlockSegmenter):
    """最小 dummy：独立结构块 + div 空行拆块（本轮选定实现）。"""

    name = "structural_blank_line"
    version = "v1"

    def __init__(self, containers: Sequence[str] = RESIDUAL_CONTAINER_TAGS) -> None:
        self.containers = tuple(containers)

    def segment(self, request: SegmentRequest) -> List[ParsedBlock]:
        if request.dom is None:
            raise SegmenterInputError(
                "StructuralBlankLineSegmenter 需要 DOM 范围（request.dom）"
            )
        scope = request.dom
        blocks: List[ParsedBlock] = []
        self._walk(
            scope,
            scope,
            request.next_page_anchor,
            blocks,
            # 根范围本身是 div/section/article 时，其未覆盖的直接正文也按空行拆块；
            # body/main 等页面级范围只收集结构节点，避免把范围外文本算作正文。
            collect_residual=scope.name in self.containers,
        )
        return blocks

    # ---- DOM 遍历：按文档顺序输出结构块与容器剩余正文 ----

    def _walk(
        self,
        element: Any,
        scope: Any,
        next_anchor: Optional[Any],
        blocks: List[ParsedBlock],
        *,
        collect_residual: bool = True,
    ) -> None:
        buffer: List[str] = []

        def flush() -> None:
            if not buffer:
                return
            text = "".join(buffer)
            buffer.clear()
            for index, chunk in enumerate(_split_blank_lines(text)):
                blocks.append(
                    ParsedBlock(
                        block_type="paragraph",
                        text=chunk,
                        source_anchor=_anchor_with_chunk(element, scope, index),
                    )
                )

        for child in element.children:
            if isinstance(child, Comment):
                continue
            if isinstance(child, NavigableString):
                # 元素之间只有缩进的空白文本节点不算正文空行。
                text = str(child)
                if text.strip():
                    buffer.append(text)
                elif buffer and not buffer[-1][-1:].isspace():
                    buffer.append(" ")
                continue
            if not isinstance(child, Tag):
                continue
            if child.name == "br":
                buffer.append("\n")
                continue
            if child.name in HEADING_TAGS:
                flush()
                text = _clean_text(child)
                if text:
                    blocks.append(
                        ParsedBlock(
                            block_type="heading",
                            text=text,
                            heading_level=int(child.name[1]),
                            source_anchor=_anchor(child, scope),
                        )
                    )
                continue
            if child.name == "p":
                flush()
                if _is_pagination_control(child, next_anchor):
                    continue
                text = _clean_text(child)
                if text:
                    blocks.append(
                        ParsedBlock(
                            block_type="paragraph",
                            text=text,
                            source_anchor=_anchor(child, scope),
                        )
                    )
                continue
            if child.name == "li":
                flush()
                if _is_pagination_control(child, next_anchor):
                    continue
                text = _clean_text(child)
                if text:
                    blocks.append(
                        ParsedBlock(
                            block_type="list_item",
                            text=text,
                            source_anchor=_anchor(child, scope),
                        )
                    )
                # 嵌套列表/表格仍按结构节点输出（与既有行为一致）。
                self._walk(child, scope, next_anchor, blocks, collect_residual=False)
                continue
            if child.name == "table":
                flush()
                rows, headers = _table_rows(child)
                if rows:
                    blocks.append(
                        ParsedBlock(
                            block_type="table",
                            text="\n".join("\t".join(row) for row in rows),
                            structured_data={
                                "headers": headers,
                                "rows": rows[1:] if headers else rows,
                                "caption": _clean_text(child.caption) if child.caption else None,
                            },
                            source_anchor=_anchor(child, scope),
                        )
                    )
                continue
            if child.name not in INLINE_TAGS:
                flush()
                self._walk(
                    child,
                    scope,
                    next_anchor,
                    blocks,
                    collect_residual=child.name in self.containers,
                )
                continue
            # 其余元素按内联内容并入当前文本流。
            buffer.append(_inline_text(child))

        if collect_residual:
            flush()


class PreParsedSegmenter(BlockSegmenter):
    """已解析格式的直通实现：块由各自解析器产出，本实现只做顺序与类型校验。"""

    name = "preparsed_passthrough"
    version = "v1"

    def segment(self, request: SegmentRequest) -> List[ParsedBlock]:
        blocks = list(request.blocks)
        for block in blocks:
            if not isinstance(block, ParsedBlock):
                raise SegmenterInputError(
                    f"PreParsedSegmenter 只接受 ParsedBlock：{type(block).__name__}"
                )
            if block.block_type != "table" and not block.text.strip():
                raise SegmenterInputError(
                    f"非表格块缺少文本，不能作为直通块：{block.block_type}"
                )
        return blocks


DEFAULT_HTML_SEGMENTER = StructuralBlankLineSegmenter()
PREPARSED_SEGMENTER = PreParsedSegmenter()

SEGMENTERS: Dict[str, BlockSegmenter] = {
    "html": DEFAULT_HTML_SEGMENTER,
    "preparsed": PREPARSED_SEGMENTER,
}


def segmenter_for(fmt: str) -> BlockSegmenter:
    """按格式取分块实现；未知格式明确报错，不静默换实现。"""
    try:
        return SEGMENTERS[fmt]
    except KeyError as exc:
        raise SegmenterInputError(
            f"未登记的格式分块实现：{fmt!r}；已知 {sorted(SEGMENTERS)}"
        ) from exc


def extraction_method_for(base: str, segmenter: BlockSegmenter) -> str:
    """基础抽取方式 + 分块实现与版本；只扩展字符串，不新增字段。"""
    return f"{base}+{segmenter.name}_{segmenter.version}"


def segment_parsed_blocks(blocks: Sequence[ParsedBlock], *, fmt: str = "preparsed") -> List[ParsedBlock]:
    """把已有解析器的块经同一接口返回，保持既有能力不变。"""
    return segmenter_for(fmt).segment(SegmentRequest(blocks=tuple(blocks)))


def _split_blank_lines(text: str) -> List[str]:
    """按一个或多个空白行拆块；单个换行保留在同一块内。"""
    chunks: List[str] = []
    for raw in BLANK_LINE.split(text.replace("\r\n", "\n").replace("\r", "\n")):
        cleaned = collapse_whitespace(raw)
        if cleaned:
            chunks.append(cleaned)
    return chunks


def _inline_text(element: Tag) -> str:
    """内联元素的文本：br 记为换行，其他标签保留其文本内容。"""
    pieces: List[str] = []
    for node in element.descendants:
        if isinstance(node, Comment):
            continue
        if isinstance(node, NavigableString):
            pieces.append(str(node))
        elif isinstance(node, Tag) and node.name == "br":
            pieces.append("\n")
    return "".join(pieces)


def _clean_text(element: Tag) -> str:
    return collapse_whitespace(element.get_text(" ", strip=True))


def _table_rows(table: Tag) -> Tuple[list, list]:
    rows = []
    headers: list = []
    for row_index, tr in enumerate(table.find_all("tr")):
        cells = tr.find_all(["th", "td"])
        values = [_clean_text(cell) for cell in cells]
        if not values:
            continue
        rows.append(values)
        if row_index == 0 and any(cell.name == "th" for cell in cells):
            headers = values
    return rows, headers


def _is_pagination_control(element: Tag, next_anchor: Optional[Any]) -> bool:
    """纯翻页控件不进入正文：段落/列表项文本与下一页链接文本一致时跳过。"""
    if next_anchor is None or element.name not in ("p", "li"):
        return False
    anchors = element.find_all("a", href=True)
    if anchors != [next_anchor]:
        return False
    return _clean_text(element) == _clean_text(next_anchor)


def _anchor(element: Tag, scope: Tag) -> dict:
    parts = []
    current: Optional[Tag] = element
    while isinstance(current, Tag) and current is not scope:
        same_tag = [sib for sib in current.parent.find_all(current.name, recursive=False)]
        position = same_tag.index(current) + 1
        parts.append(f"{current.name}:nth-of-type({position})")
        current = current.parent if isinstance(current.parent, Tag) else None
    parts.append(scope.name)
    return {"selector": " > ".join(reversed(parts))}


def _anchor_with_chunk(element: Tag, scope: Tag, chunk_index: int) -> dict:
    """容器剩余正文的定位：容器选择器 + 容器内块序（0 起），不指向其他节点。"""
    anchor = _anchor(element, scope)
    anchor["chunk"] = chunk_index
    return anchor
