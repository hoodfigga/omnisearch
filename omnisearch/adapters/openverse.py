"""
Openverse Adapter: Creative Commons / public domain images and audio via the
Openverse API (aggregates Flickr, Wikimedia, Jamendo, Freesound, and more).
"""

from __future__ import annotations
import logging
from typing import List
from urllib.parse import quote_plus
from omnisearch.models.query import SearchQuery
from omnisearch.models.video import VideoMetadataSource, VideoRecord, ItemType
from omnisearch.adapters.base import BaseSourceAdapter
from omnisearch.extractors.json_ld import parse_iso_datetime

logger = logging.getLogger(__name__)


class OpenverseAdapter(BaseSourceAdapter):
    """Discovers CC-licensed and public-domain images and audio via Openverse."""

    @property
    def source_id(self) -> str:
        return "openverse"

    @property
    def source_name(self) -> str:
        return "Openverse (CC images & audio)"

    async def search(self, query: SearchQuery, page: int = 1) -> List[VideoRecord]:
        search_terms = " ".join(query.extracted_phrases + query.extracted_terms) or query.raw_query
        if not search_terms.strip():
            return []

        records: List[VideoRecord] = []
        try:
            params = {"q": search_terms, "page_size": 20, "page": page}
            resp = await self.http_client.get(
                "https://api.openverse.org/v1/images/", params=params, timeout=9.0
            )
            if resp.status_code == 200:
                for r in resp.json().get("results", []):
                    rec = self._build_record(r, kind="image")
                    if rec:
                        records.append(rec)
        except Exception as exc:
            logger.debug("Openverse images search error: %s", exc)

        # Audio search
        try:
            params = {"q": search_terms, "page_size": 15, "page": page}
            resp = await self.http_client.get(
                "https://api.openverse.org/v1/audio/", params=params, timeout=9.0
            )
            if resp.status_code == 200:
                for r in resp.json().get("results", []):
                    rec = self._build_record(r, kind="audio")
                    if rec:
                        records.append(rec)
        except Exception as exc:
            logger.debug("Openverse audio search error: %s", exc)

        return records

    @classmethod
    def _build_record(cls, r: dict, kind: str):
        item_id = r.get("id")
        url = r.get("url")
        if not item_id or not url:
            return None
        title = r.get("title") or f"Openverse {kind} {item_id}"
        creator = r.get("creator")
        provider = r.get("provider") or r.get("source") or "Openverse"
        license_ = r.get("license") or ""
        foreign = r.get("foreign_landing_url") or url
        duration = r.get("duration") if kind == "audio" else None

        return VideoRecord(
            id=f"openverse_{kind}:{item_id}",
            canonical_url=foreign,
            download_url=url,
            platform="Openverse",
            platform_id=str(item_id),
            title=title,
            description=f"CC-licensed {kind} by {creator or 'unknown'} on {provider} ({license_} license)",
            item_type=ItemType.IMAGE if kind == "image" else ItemType.AUDIO,
            file_extension="mp3" if kind == "audio" else None,
            uploader_name=creator,
            duration_seconds=duration,
            thumbnail_url=r.get("thumbnail") or (url if kind == "image" else None),
            tags=["openverse", "creative-commons", kind, license_.lower()] if license_ else ["openverse", "creative-commons", kind],
            metadata_sources=[VideoMetadataSource.OFFICIAL_API, VideoMetadataSource.DIRECT_LINK],
            raw_metadata={"openverse": {k: r.get(k) for k in ("id", "license", "provider", "source", "foreign_landing_url")}},
        )
