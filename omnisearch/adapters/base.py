"""
Base abstract class for source adapters.
"""

from __future__ import annotations
import abc
import logging
from typing import List, Optional
from omnisearch.models.query import SearchQuery
from omnisearch.models.video import VideoRecord
from omnisearch.core.http_client import ResilientHttpClient

logger = logging.getLogger(__name__)


class BaseSourceAdapter(abc.ABC):
    """Abstract interface for all video discovery source adapters."""

    def __init__(
        self,
        http_client: Optional[ResilientHttpClient] = None,
        rate_limit_per_sec: float = 5.0,
    ):
        self.rate_limit_per_sec = rate_limit_per_sec
        self.http_client = http_client or ResilientHttpClient(rate_limit_per_sec=rate_limit_per_sec)

    @property
    @abc.abstractmethod
    def source_id(self) -> str:
        """Unique identifier (e.g. 'youtube', 'vimeo', 'dailymotion', 'ia', 'peertube')."""
        pass

    @property
    @abc.abstractmethod
    def source_name(self) -> str:
        """Human-readable name."""
        pass

    @property
    def is_enabled(self) -> bool:
        """Whether this adapter is configured and active."""
        return True

    @abc.abstractmethod
    async def search(self, query: SearchQuery, page: int = 1) -> List[VideoRecord]:
        """Searches the source for candidate video records matching the query."""
        pass

    async def health_check(self) -> bool:
        """Performs a lightweight liveness check for this adapter."""
        return True

    async def close(self):
        """Releases underlying HTTP client network connections."""
        if self.http_client:
            await self.http_client.close()

