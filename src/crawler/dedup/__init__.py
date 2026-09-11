"""去重与来源关系。"""

from crawler.dedup.duplicates import (
    DuplicateConfigError,
    DuplicateGroup,
    EXACT_BYTES,
    EXACT_TEXT,
    NEAR_TEXT,
    find_exact_duplicates,
    find_near_duplicates,
    group_row_counts,
)
from crawler.dedup.fingerprint import document_fingerprint, text_hash, text_similarity
from crawler.dedup.relations import (
    RELATION_TYPES,
    RelationError,
    attach_relations,
    build_relation,
    relation_index,
)

__all__ = [
    "DuplicateConfigError",
    "DuplicateGroup",
    "EXACT_BYTES",
    "EXACT_TEXT",
    "NEAR_TEXT",
    "RELATION_TYPES",
    "RelationError",
    "attach_relations",
    "build_relation",
    "document_fingerprint",
    "find_exact_duplicates",
    "find_near_duplicates",
    "group_row_counts",
    "relation_index",
    "text_hash",
    "text_similarity",
]
