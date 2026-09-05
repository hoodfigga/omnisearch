"""
Dailymotion Source Adapter using Dailymotion Public Graph API.
"""

from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import List
from omnisearch.models.query import SearchQuery
from omnisearch.models.video import VideoMetadataSource, VideoRecord
from omnisearch.adapters.base import BaseSourceAdapter

logger = logging.getLogger(__name__)


class DailymotionAdapter(BaseSourceAdapter):
    """Discovers videos on Dailymotion via their public API."""

    @property
    def source_id(self) -> str:
        return "dailymotion"

    @property
    def source_name(self) -> str:
        return "Dailymotion"

    async def search(self, query: SearchQuery, page: int = 1) -> List[VideoRecord]:
        search_terms = " ".join(query.extracted_phrases + query.extracted_terms) or query.raw_query
        if not search_terms.strip():
            return []

        records: List[VideoRecord] = []
        try:
            url = "https://api.dailymotion.com/videos"
            params = {
                "search": search_terms,
                "page": page,
                "limit": min(50, query.options.max_results),
                "fields": "id,title,description,tags,duration,owner.screenname,owner.url,created_time,thumbnail_720_url,views_total,likes_total",
            }
            resp = await self.http_client.get(url, params=params)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("list", []):
                    vid_id = item.get("id")
                    if not vid_id:
                        continue

                    published = None
                    if item.get("created_time"):
                        try:
                            published = datetime.fromtimestamp(item["created_time"], timezone.utc)
                        except Exception:
                            pass

                    record = VideoRecord(
                        id=f"dailymotion:{vid_id}",
                        canonical_url=f"https://www.dailymotion.com/video/{vid_id}",
                        platform="Dailymotion",
                        platform_id=vid_id,
                        title=item.get("title") or "",
                        description=item.get("description") or "",
                        uploader_name=item.get("owner.screenname"),
                        uploader_url=item.get("owner.url"),
                        publication_date=published,
                        duration_seconds=item.get("duration"),
                        tags=item.get("tags") or [],
                        thumbnail_url=item.get("thumbnail_720_url"),
                        embed_url=f"https://www.dailymotion.com/embed/video/{vid_id}",
                        view_count=item.get("views_total"),
                        like_count=item.get("likes_total"),
                        metadata_sources=[VideoMetadataSource.OFFICIAL_API],
                        raw_metadata={"dailymotion_item": item},
                    )
                    records.append(record)
        except Exception as exc:
            logger.warning("Dailymotion search error: %s", exc)

        return records
