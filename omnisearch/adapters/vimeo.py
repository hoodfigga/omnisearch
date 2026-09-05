"""
Vimeo Source Adapter.
"""

from __future__ import annotations
import logging
import os
from typing import List, Optional
from omnisearch.models.query import SearchQuery
from omnisearch.models.video import VideoMetadataSource, VideoRecord
from omnisearch.adapters.base import BaseSourceAdapter
from omnisearch.extractors.json_ld import parse_iso_datetime

logger = logging.getLogger(__name__)


class VimeoAdapter(BaseSourceAdapter):
    """Discovers Vimeo videos using public API or search endpoints."""

    def __init__(self, access_token: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        self.access_token = access_token or os.getenv("VIMEO_ACCESS_TOKEN")

    @property
    def source_id(self) -> str:
        return "vimeo"

    @property
    def source_name(self) -> str:
        return "Vimeo"

    async def search(self, query: SearchQuery, page: int = 1) -> List[VideoRecord]:
        search_terms = " ".join(query.extracted_phrases + query.extracted_terms) or query.raw_query
        if not search_terms.strip():
            return []

        records: List[VideoRecord] = []
        try:
            if self.access_token:
                # Official API
                url = "https://api.vimeo.com/videos"
                params = {
                    "query": search_terms,
                    "page": page,
                    "per_page": min(50, query.options.max_results),
                }
                headers = {"Authorization": f"Bearer {self.access_token}"}
                resp = await self.http_client.get(url, params=params, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    for item in data.get("data", []):
                        uri = item.get("uri", "")
                        vid_id = uri.split("/")[-1] if "/" in uri else ""
                        if not vid_id:
                            continue
                        record = VideoRecord(
                            id=f"vimeo:{vid_id}",
                            canonical_url=f"https://vimeo.com/{vid_id}",
                            platform="Vimeo",
                            platform_id=vid_id,
                            title=item.get("name", ""),
                            description=item.get("description", "") or "",
                            uploader_name=item.get("user", {}).get("name"),
                            uploader_url=item.get("user", {}).get("link"),
                            publication_date=parse_iso_datetime(item.get("created_time")),
                            duration_seconds=item.get("duration"),
                            tags=[t.get("name") for t in item.get("tags", []) if t.get("name")],
                            thumbnail_url=item.get("pictures", {}).get("sizes", [{}])[-1].get("link"),
                            embed_url=f"https://player.vimeo.com/video/{vid_id}",
                            metadata_sources=[VideoMetadataSource.OFFICIAL_API],
                            raw_metadata={"vimeo_item": item},
                        )
                        records.append(record)
                    return records
        except Exception as exc:
            logger.warning("Vimeo search failed: %s", exc)

        return records
