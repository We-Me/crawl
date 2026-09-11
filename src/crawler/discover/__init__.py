"""发现策略：栏目分页、搜索、sitemap、API 与附件。"""

from crawler.discover.discoverer import (
    ATTACHMENT_EXTENSIONS,
    DiscoveredTarget,
    Discoverer,
    SkippedTarget,
)

__all__ = [
    "ATTACHMENT_EXTENSIONS",
    "DiscoveredTarget",
    "Discoverer",
    "SkippedTarget",
]
