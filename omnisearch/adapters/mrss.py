"""
MediaRSS (MRSS) and Video Podcast XML Feed Adapter.
"""

from __future__ import annotations
import logging
from typing import List, Optional
from bs4 import BeautifulSoup
from omnisearch.models.query import SearchQuery
from omnisearch.models.video import VideoMetadataSource, VideoRecord
from omnisearch.adapters.base import BaseSourceAdapter
from omnisearch.core.dedup import resolve_platform_and_id
from omnisearch.extractors.json_ld import parse_iso_datetime

logger = logging.getLogger(__name__)


class MRSSAdapter(BaseSourceAdapter):
    """Parses and queries MediaRSS and video podcast feeds."""

    # Curated public high-quality MRSS / video feeds for discovery
    PUBLIC_FEEDS = [
        "https://feeds.feedburner.com/tedtalks_video",
        "https://www.nasa.gov/rss/dyn/lg_video_podcast.rss",
        "https://www.loc.gov/rss/podcasts/webcasts.xml",
    ]

    def __init__(self, custom_feeds: Optional[List[str]] = None, **kwargs):
        super().__init__(**kwargs)
        self.feeds = custom_feeds or self.PUBLIC_FEEDS

    @property
    def source_id(self) -> str:
        return "mrss"

    @property
    def source_name(self) -> str:
        return "MediaRSS Feeds"

    async def search(self, query: SearchQuery, page: int = 1) -> List[VideoRecord]:
        records: List[VideoRecord] = []
        for feed_url in self.feeds:
            try:
                resp = await self.http_client.get(feed_url, timeout=8.0)
                if resp.status_code == 200:
                    feed_records = self.parse_feed(resp.text, feed_url)
                    records.extend(feed_records)
            except Exception as exc:
                logger.debug("MRSS feed fetch failed for %s: %s", feed_url, exc)
                continue

        return records

    @classmethod
    def parse_feed(cls, xml_content: str, feed_url: str) -> List[VideoRecord]:
        records: List[VideoRecord] = []
        soup = BeautifulSoup(xml_content, "xml")
        items = soup.find_all("item")

        channel_title = soup.find("channel")
        channel_name = channel_title.find("title").get_text().strip() if (channel_title and channel_title.find("title")) else "MRSS Feed"

        for item in items:
            title_tag = item.find("title")
            title = title_tag.get_text().strip() if title_tag else ""

            link_tag = item.find("link")
            link = link_tag.get_text().strip() if link_tag else feed_url

            desc_tag = item.find("description") or item.find("itunes:summary") or item.find("media:description")
            description = desc_tag.get_text().strip() if desc_tag else ""

            pub_date_tag = item.find("pubDate")
            pub_date = parse_iso_datetime(pub_date_tag.get_text()) if pub_date_tag else None

            # Media thumbnail
            thumb_tag = item.find("media:thumbnail") or item.find("itunes:image")
            thumb_url = thumb_tag.get("url") or thumb_tag.get("href") if thumb_tag else None

            # Media content / enclosure
            media_content = item.find("media:content") or item.find("enclosure")
            content_url = media_content.get("url") if media_content else None
            duration_sec = None
            if media_content and media_content.get("duration"):
                try:
                    duration_sec = int(media_content.get("duration"))
                except Exception:
                    pass

            # Keywords / Tags
            keywords_tag = item.find("media:keywords") or item.find("itunes:keywords")
            tags = []
            if keywords_tag:
                tags = [k.strip() for k in keywords_tag.get_text().split(",") if k.strip()]

            final_url = link or content_url or feed_url
            platform, platform_id, canonical_url = resolve_platform_and_id(final_url)
            internal_id = f"mrss:{canonical_url}"

            record = VideoRecord(
                id=internal_id,
                canonical_url=canonical_url,
                platform=channel_name or platform,
                platform_id=platform_id,
                title=title,
                description=description,
                uploader_name=channel_name,
                publication_date=pub_date,
                duration_seconds=duration_sec,
                tags=tags,
                thumbnail_url=thumb_url,
                embed_url=content_url if content_url and "mp4" not in content_url else None,
                metadata_sources=[VideoMetadataSource.MRSS_FEED],
                raw_metadata={"feed_url": feed_url},
            )
            records.append(record)

        return records
