"""逻辑文档身份（T014）。

同一来源下以规范化 URL 作为版本链身份：每个 URL 保留独立抓取身份（Q05 候选），
版本链只表达同一地址的内容演进，不因相似度合并不同地址或不同立场。
"""

from __future__ import annotations

from typing import Mapping, Optional

from crawler.normalize.metadata_normalizer import normalize_url


def identity_key(source_id: str, url: Optional[str], canonical_url: Optional[str] = None) -> Optional[str]:
    normalized = normalize_url(canonical_url or url)
    if not normalized:
        return None
    return f"{source_id}|{normalized}"


def document_identity(document: Mapping) -> Optional[str]:
    return identity_key(
        str(document.get("source_id") or ""),
        document.get("source_url"),
        document.get("canonical_url"),
    )
