"""
Torrent Index Adapter: Nyaa (nyaa.si) and Sukebei (sukebei.nyaa.si) via RSS.

Nyaa covers software/anime/data torrents; Sukebei covers adult torrents and is
disabled together with the adult content toggle (OMNISEARCH_ADULT_ENABLED).
Each item exposes a direct .torrent download link, seeders, size, and infoHash.
"""

from __future__ import annotations
import logging
import os
import re
from datetime import datetime, timezone
from typing import List, Optional
from urllib.parse import quote_plus
from xml.etree import ElementTree
from omnisearch.models.query import SearchQuery
from omnisearch.models.video import VideoMetadataSource, VideoRecord, ItemType
from omnisearch.adapters.base import BaseSourceAdapter
from omnisearch.extractors.file_hosts import parse_size_str, format_bytes

logger = logging.getLogger(__name__)

NYAA_NS = {"nyaa": "https://nyaa.si/xmlns/nyaa"}


def _parse_rfc822(date_str: Optional[str]) -> Optional[datetime]:
    if not date_str:
        return None
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


class NyaaAdapter(BaseSourceAdapter):
    """Discovers torrents on Nyaa (and Sukebei for adult content) via RSS."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Sukebei (adult torrents) follows the same toggle as the adult adapter.
        self._sukebei_enabled = os.getenv("OMNISEARCH_ADULT_ENABLED", "1").strip().lower() not in ("0", "false", "no", "off")

    @property
    def source_id(self) -> str:
        return "nyaa"

    @property
    def source_name(self) -> str:
        return "Nyaa Torrents (software, anime, data)"

    async def search(self, query: SearchQuery, page: int = 1) -> List[VideoRecord]:
        search_terms = " ".join(query.extracted_phrases + query.extracted_terms) or query.raw_query
        if not search_terms.strip():
            return []

        records: List[VideoRecord] = []
        feeds = [("https://nyaa.si/?page=rss", "Nyaa")]
        if self._sukebei_enabled:
            feeds.append(("https://sukebei.nyaa.si/?page=rss", "Sukebei"))

        for base, platform in feeds:
            url = f"{base}&q={quote_plus(search_terms)}"
            try:
                resp = await self.http_client.get(url, timeout=8.0)
                if resp.status_code == 200:
                    recs = self._parse_feed(resp.text, platform)
                    records.extend(recs)
            except Exception as exc:
                logger.debug("%s RSS search failed: %s", platform, exc)

        return records

    @classmethod
    def _parse_feed(cls, xml_text: str, platform: str) -> List[VideoRecord]:
        records: List[VideoRecord] = []
        try:
            root = ElementTree.fromstring(xml_text)
        except Exception:
            return records

        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            if not title or not link:
                continue
            guid = (item.findtext("guid") or "").strip()
            pub_date = _parse_rfc822(item.findtext("pubDate"))

            size_str = (item.findtext("nyaa:size", namespaces=NYAA_NS) or "").strip()
            seeders = item.findtext("nyaa:seeders", namespaces=NYAA_NS)
            leechers = item.findtext("nyaa:leechers", namespaces=NYAA_NS)
            downloads = item.findtext("nyaa:downloads", namespaces=NYAA_NS)
            info_hash = (item.findtext("nyaa:infoHash", namespaces=NYAA_NS) or "").strip()
            category = (item.findtext("nyaa:category", namespaces=NYAA_NS) or "").strip()

            size_bytes = parse_size_str(size_str)
            torrent_id = guid.rstrip("/").split("/")[-1] if guid else link.rstrip(".torrent").split("/")[-1]

            records.append(
                VideoRecord(
                    id=f"nyaa:{torrent_id}",
                    canonical_url=guid or link,
                    download_url=link,  # direct .torrent file
                    platform=platform,
                    platform_id=torrent_id,
                    title=title,
                    description=f"Torrent ({category}) — {seeders or 0} seeders, {leechers or 0} leechers"
                                f" | infoHash {info_hash[:12] if info_hash else 'n/a'}",
                    item_type=ItemType.FILE,
                    file_name=f"{title}.torrent",
                    file_extension="torrent",
                    file_size_bytes=size_bytes,
                    file_size_human=format_bytes(size_bytes) if size_bytes else size_str,
                    publication_date=pub_date,
                    view_count=int(downloads) if downloads and downloads.isdigit() else None,
                    like_count=int(seeders) if seeders and seeders.isdigit() else None,
                    tags=["torrent", "nyaa", "direct-download", "magnet"] + ([category.lower()] if category else []),
                    metadata_sources=[VideoMetadataSource.OFFICIAL_API, VideoMetadataSource.DIRECT_LINK],
                    raw_metadata={
                        "torrent": {
                            "info_hash": info_hash,
                            "seeders": seeders,
                            "leechers": leechers,
                            "category": category,
                            "size": size_str,
                        }
                    },
                )
            )
        return records
