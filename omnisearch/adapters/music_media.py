"""
Music & Audio Media Adapter: iTunes Search API (music/movies) and Mixcloud (DJ mixes).

Both are keyless public JSON APIs with preview/stream URLs.
"""

from __future__ import annotations
import logging
from typing import List
from omnisearch.models.query import SearchQuery
from omnisearch.models.video import VideoMetadataSource, VideoRecord, ItemType
from omnisearch.adapters.base import BaseSourceAdapter
from omnisearch.extractors.json_ld import parse_iso_datetime

logger = logging.getLogger(__name__)


class ITunesAdapter(BaseSourceAdapter):
    """Discovers music tracks, albums, movies, and podcasts via the iTunes Search API (30s previews)."""

    @property
    def source_id(self) -> str:
        return "itunes"

    @property
    def source_name(self) -> str:
        return "Apple iTunes (music, movies & podcasts)"

    async def search(self, query: SearchQuery, page: int = 1) -> List[VideoRecord]:
        search_terms = query.search_terms_string()
        if not search_terms.strip():
            return []

        records: List[VideoRecord] = []
        try:
            # Music first; podcasts reach a different audience
            tasks = [
                self._search_media(self.http_client, search_terms, "music", "song"),
                self._search_media(self.http_client, search_terms, "podcast", "podcast"),
            ]
            import asyncio
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for res in results:
                if isinstance(res, list):
                    records.extend(res)
        except Exception as exc:
            logger.debug("iTunes search error: %s", exc)

        return records

    @classmethod
    async def _search_media(cls, http_client, search_terms: str, media: str, entity: str) -> List[VideoRecord]:
        records: List[VideoRecord] = []
        try:
            params = {"term": search_terms, "limit": 12, "media": media, "entity": entity}
            resp = await http_client.get("https://itunes.apple.com/search", params=params, timeout=8.0)
            if resp.status_code != 200:
                return records
            for item in resp.json().get("results", []):
                track_id = item.get("trackId") or item.get("collectionId")
                if not track_id:
                    continue

                kind = item.get("kind", "")
                if "song" in kind or media == "music":
                    item_type = ItemType.AUDIO
                elif "movie" in kind or "podcast" in kind:
                    item_type = ItemType.VIDEO if "movie" in kind else ItemType.AUDIO
                else:
                    item_type = ItemType.AUDIO

                artwork = item.get("artworkUrl100") or item.get("artworkUrl60")
                if artwork and "100x100" in artwork:
                    artwork = artwork.replace("100x100", "300x300")

                records.append(
                    VideoRecord(
                        id=f"itunes:{track_id}",
                        canonical_url=item.get("trackViewUrl") or item.get("collectionViewUrl") or f"https://music.apple.com",
                        download_url=item.get("previewUrl"),  # 30s m4a preview
                        platform="iTunes",
                        platform_id=str(track_id),
                        title=item.get("trackName") or item.get("collectionName") or f"iTunes {track_id}",
                        description=(f"{item.get('artistName', '')} — {item.get('collectionName', '')}").strip(" —"),
                        item_type=item_type,
                        uploader_name=item.get("artistName"),
                        publication_date=parse_iso_datetime(item.get("releaseDate")),
                        duration_seconds=(item.get("trackTimeMillis", 0) or 0) // 1000 or None,
                        thumbnail_url=artwork,
                        embed_url=item.get("previewUrl"),
                        tags=["music" if media == "music" else "podcast", "itunes", "apple"],
                        metadata_sources=[VideoMetadataSource.OFFICIAL_API],
                        raw_metadata={"itunes": {k: item.get(k) for k in ("trackId", "artistName", "collectionName", "primaryGenreName")}},
                    )
                )
        except Exception as exc:
            logger.debug("iTunes %s search error: %s", media, exc)
        return records


class MixcloudAdapter(BaseSourceAdapter):
    """Discovers DJ mixes and radio shows on Mixcloud with stream URLs."""

    @property
    def source_id(self) -> str:
        return "mixcloud"

    @property
    def source_name(self) -> str:
        return "Mixcloud (DJ mixes & radio shows)"

    async def search(self, query: SearchQuery, page: int = 1) -> List[VideoRecord]:
        search_terms = query.search_terms_string()
        if not search_terms.strip():
            return []

        records: List[VideoRecord] = []
        try:
            resp = await self.http_client.get(
                "https://api.mixcloud.com/search/",
                params={"q": search_terms, "type": "cloudcast", "limit": 15, "offset": max(0, (page - 1) * 15)},
                timeout=8.0,
            )
            if resp.status_code != 200:
                return records
            # Mixcloud returns {"data": [...], "paging": {...}}
            payload = resp.json()
            items = payload.get("data", []) if isinstance(payload, dict) else payload
            for item in items:
                key = item.get("key", "").strip("/")
                if not key:
                    continue

                tags = [t.get("name") for t in item.get("tags", [])[:6] if t.get("name")]
                pictures = item.get("pictures", {}) or {}
                audio_length = item.get("audio_length")

                records.append(
                    VideoRecord(
                        id=f"mixcloud:{key}",
                        canonical_url=item.get("url") or f"https://www.mixcloud.com/{key}",
                        download_url=None,  # streams are m4a/HLS via player, not direct files
                        platform="Mixcloud",
                        platform_id=key,
                        title=item.get("name", "") or key.split("/")[-1],
                        description=f"DJ mix / radio show by {item.get('user', {}).get('name', 'unknown')}",
                        item_type=ItemType.AUDIO,
                        uploader_name=item.get("user", {}).get("name"),
                        uploader_url=item.get("user", {}).get("url"),
                        publication_date=parse_iso_datetime(item.get("created_time")),
                        duration_seconds=audio_length,
                        view_count=item.get("play_count"),
                        like_count=item.get("favorite_count"),
                        thumbnail_url=pictures.get("medium") or pictures.get("thumbnail"),
                        embed_url=f"https://www.mixcloud.com/widget/iframe/?feed={key}",
                        tags=["mix", "dj", "mixcloud"] + [t.lower() for t in tags],
                        metadata_sources=[VideoMetadataSource.OFFICIAL_API],
                        raw_metadata={"mixcloud": {k: item.get(k) for k in ("key", "play_count", "favorite_count", "listener_count")}},
                    )
                )
        except Exception as exc:
            logger.debug("Mixcloud search error: %s", exc)

        return records
