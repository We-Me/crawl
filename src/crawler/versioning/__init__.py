"""历史版本与现行状态。"""

from crawler.versioning.identity import document_identity, identity_key
from crawler.versioning.store import (
    OFFLINE_STATUSES,
    SUPERSEDED_STATUS,
    VersionStore,
    VersionStoreError,
)
from crawler.versioning.versions import (
    NEW,
    REVISION,
    UNCHANGED,
    VersionDecision,
    apply_decision,
    plan_version,
    version_number,
)

__all__ = [
    "NEW",
    "OFFLINE_STATUSES",
    "REVISION",
    "SUPERSEDED_STATUS",
    "UNCHANGED",
    "VersionDecision",
    "VersionStore",
    "VersionStoreError",
    "apply_decision",
    "document_identity",
    "identity_key",
    "plan_version",
    "version_number",
]
