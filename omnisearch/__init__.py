"""
OmniVideo Discovery Package.
"""

from omnisearch.models.video import VideoRecord, MatchProvenance, MatchType, MatchMode
from omnisearch.models.query import SearchQuery, SearchOptions, SearchResponse
from omnisearch.core.orchestrator import VideoDiscoveryOrchestrator

__version__ = "1.0.0"

__all__ = [
    "VideoRecord",
    "MatchProvenance",
    "MatchType",
    "MatchMode",
    "SearchQuery",
    "SearchOptions",
    "SearchResponse",
    "VideoDiscoveryOrchestrator",
]
