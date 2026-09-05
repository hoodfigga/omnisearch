"""
Generic Web Search & Structured Data Adapter.
Inspects arbitrary web URLs or search candidate pages using PageExtractor (JSON-LD, OpenGraph, etc.).
"""

from __future__ import annotations
import logging
from typing import List, Optional
from omnisearch.models.query import SearchQuery
from omnisearch.models.video import VideoRecord
from omnisearch.adapters.base import BaseSourceAdapter
from omnisearch.extractors.page_extractor import PageExtractor

logger = logging.getLogger(__name__)


class GenericWebAdapter(BaseSourceAdapter):
    """Discovers video records across generic web pages using structured schema extraction."""

    @property
    def source_id(self) -> str:
        return "web"

    @property
    def source_name(self) -> str:
        return "Generic Web (JSON-LD/OG)"

    async def search(self, query: SearchQuery, page: int = 1) -> List[VideoRecord]:
        # If the query itself is a direct URL, extract metadata directly
        if query.raw_query.startswith("http://") or query.raw_query.startswith("https://"):
            record = await self.extract_from_url(query.raw_query)
            return [record] if record else []
        return []

    async def extract_from_url(self, url: str) -> Optional[VideoRecord]:
        """Fetches a web page and extracts structured video records."""
        try:
            resp = await self.http_client.get(url, timeout=10.0)
            if resp.status_code == 200:
                records = PageExtractor.extract_from_html(resp.text, str(resp.url))
                if records:
                    return records[0]
        except Exception as exc:
            logger.warning("Failed to extract video from URL %s: %s", url, exc)
        return None
