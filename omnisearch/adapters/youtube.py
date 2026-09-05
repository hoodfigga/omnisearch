"""
YouTube Source Adapter supporting YouTube Data API v3 and public Invidious API fallback.
"""

from __future__ import annotations
import os
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from omnisearch.models.query import SearchQuery
from omnisearch.models.video import VideoMetadataSource, VideoRecord
from omnisearch.adapters.base import BaseSourceAdapter
from omnisearch.extractors.json_ld import parse_iso8601_duration, parse_iso_datetime

logger = logging.getLogger(__name__)


class YouTubeAdapter(BaseSourceAdapter):
    """Discovers YouTube videos via official Data API v3 or public Invidious mirrors."""

    INVIDIOUS_INSTANCES = [
        "https://inv.tux.pizza",
        "https://invidious.nerdvpn.de",
        "https://vid.priv.au",
        "https://invidious.no-logs.com",
    ]

    def __init__(self, api_key: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        self.api_key = api_key or os.getenv("YOUTUBE_API_KEY")

    @property
    def source_id(self) -> str:
        return "youtube"

    @property
    def source_name(self) -> str:
        return "YouTube"

    async def search(self, query: SearchQuery, page: int = 1) -> List[VideoRecord]:
        search_terms = " ".join(query.extracted_phrases + query.extracted_terms) or query.raw_query
        if not search_terms.strip():
            return []

        if self.api_key:
            return await self._search_official_api(search_terms, query, page)
        else:
            return await self._search_invidious(search_terms, query, page)

    async def _search_official_api(self, search_terms: str, query: SearchQuery, page: int) -> List[VideoRecord]:
        records: List[VideoRecord] = []
        try:
            url = "https://www.googleapis.com/youtube/v3/search"
            params = {
                "key": self.api_key,
                "q": search_terms,
                "part": "snippet",
                "type": "video",
                "maxResults": min(50, query.options.max_results),
            }
            resp = await self.http_client.get(url, params=params)
            if resp.status_code != 200:
                logger.warning("YouTube API returned status %d: %s", resp.status_code, resp.text)
                return await self._search_invidious(search_terms, query, page)

            data = resp.json()
            items = data.get("items", [])
            for item in items:
                snippet = item.get("snippet", {})
                vid_id = item.get("id", {}).get("videoId")
                if not vid_id:
                    continue

                title = snippet.get("title", "")
                desc = snippet.get("description", "")
                channel = snippet.get("channelTitle")
                published = parse_iso_datetime(snippet.get("publishedAt"))
                thumbs = snippet.get("thumbnails", {})
                thumb_url = thumbs.get("high", {}).get("url") or thumbs.get("default", {}).get("url")

                record = VideoRecord(
                    id=f"youtube:{vid_id}",
                    canonical_url=f"https://www.youtube.com/watch?v={vid_id}",
                    platform="YouTube",
                    platform_id=vid_id,
                    title=title,
                    description=desc,
                    uploader_name=channel,
                    publication_date=published,
                    thumbnail_url=thumb_url,
                    embed_url=f"https://www.youtube.com/embed/{vid_id}",
                    metadata_sources=[VideoMetadataSource.OFFICIAL_API],
                    raw_metadata={"youtube_snippet": snippet},
                )
                records.append(record)
        except Exception as exc:
            logger.warning("YouTube official API error: %s. Falling back to Invidious.", exc)
            return await self._search_invidious(search_terms, query, page)

        return records

    async def _search_invidious(self, search_terms: str, query: SearchQuery, page: int) -> List[VideoRecord]:
        records: List[VideoRecord] = []
        for instance in self.INVIDIOUS_INSTANCES:
            try:
                url = f"{instance}/api/v1/search"
                params = {
                    "q": search_terms,
                    "page": page,
                    "type": "video",
                }
                resp = await self.http_client.get(url, params=params, timeout=6.0)
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list):
                        for item in data:
                            if item.get("type") != "video":
                                continue
                            vid_id = item.get("videoId")
                            if not vid_id:
                                continue

                            title = item.get("title", "")
                            desc = item.get("description", "")
                            author = item.get("author")
                            published = None
                            if item.get("published"):
                                try:
                                    published = datetime.fromtimestamp(item["published"], timezone.utc)
                                except Exception:
                                    pass

                            duration = item.get("lengthSeconds")
                            view_count = item.get("viewCount")
                            thumbnails = item.get("videoThumbnails", [])
                            thumb_url = thumbnails[0].get("url") if thumbnails else None

                            record = VideoRecord(
                                id=f"youtube:{vid_id}",
                                canonical_url=f"https://www.youtube.com/watch?v={vid_id}",
                                platform="YouTube",
                                platform_id=vid_id,
                                title=title,
                                description=desc,
                                uploader_name=author,
                                publication_date=published,
                                duration_seconds=duration,
                                view_count=view_count,
                                thumbnail_url=thumb_url,
                                embed_url=f"https://www.youtube.com/embed/{vid_id}",
                                metadata_sources=[VideoMetadataSource.OFFICIAL_API],
                                raw_metadata={"invidious_item": item},
                            )
                            records.append(record)
                        return records
            except Exception:
                continue

        return records
