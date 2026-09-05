"""
PeerTube Federated Search Adapter.
"""

from __future__ import annotations
import logging
from typing import List
from omnisearch.models.query import SearchQuery
from omnisearch.models.video import VideoMetadataSource, VideoRecord
from omnisearch.adapters.base import BaseSourceAdapter
from omnisearch.extractors.json_ld import parse_iso_datetime

logger = logging.getLogger(__name__)


class PeerTubeAdapter(BaseSourceAdapter):
    """Discovers videos across decentralized PeerTube instances via SepiaSearch and federation."""

    SEARCH_INDEXES = [
        "https://sepiasearch.org",
        "https://peertube.tv",
        "https://framatube.org",
    ]

    @property
    def source_id(self) -> str:
        return "peertube"

    @property
    def source_name(self) -> str:
        return "PeerTube"

    async def search(self, query: SearchQuery, page: int = 1) -> List[VideoRecord]:
        search_terms = " ".join(query.extracted_phrases + query.extracted_terms) or query.raw_query
        if not search_terms.strip():
            return []

        records: List[VideoRecord] = []
        limit = min(50, query.options.max_results)
        start = (page - 1) * limit

        for index_url in self.SEARCH_INDEXES:
            try:
                url = f"{index_url}/api/v1/search/videos"
                params = {
                    "search": search_terms,
                    "start": start,
                    "count": limit,
                }
                resp = await self.http_client.get(url, params=params, timeout=7.0)
                if resp.status_code == 200:
                    data = resp.json()
                    items = data.get("data", [])
                    for item in items:
                        uuid = item.get("uuid") or item.get("shortUUID")
                        if not uuid:
                            continue

                        canonical_url = item.get("url") or f"{index_url}/w/{uuid}"
                        channel = item.get("channel", {}).get("displayName") or item.get("account", {}).get("displayName")
                        thumb_path = item.get("thumbnailPath")
                        thumb_url = f"{index_url}{thumb_path}" if (thumb_path and thumb_path.startswith("/")) else thumb_path
                        embed_path = item.get("embedPath")
                        embed_url = f"{index_url}{embed_path}" if (embed_path and embed_path.startswith("/")) else embed_path

                        record = VideoRecord(
                            id=f"peertube:{uuid}",
                            canonical_url=canonical_url,
                            platform="PeerTube",
                            platform_id=uuid,
                            title=item.get("name", ""),
                            description=item.get("description", "") or "",
                            uploader_name=channel,
                            publication_date=parse_iso_datetime(item.get("publishedAt")),
                            duration_seconds=item.get("duration"),
                            tags=item.get("tags") or [],
                            thumbnail_url=thumb_url,
                            embed_url=embed_url,
                            view_count=item.get("views"),
                            like_count=item.get("likes"),
                            metadata_sources=[VideoMetadataSource.OFFICIAL_API],
                            raw_metadata={"peertube_item": item},
                        )
                        records.append(record)
                    if records:
                        return records
            except Exception as exc:
                logger.debug("PeerTube index %s failed: %s", index_url, exc)
                continue

        return records
