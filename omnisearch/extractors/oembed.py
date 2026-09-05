"""
oEmbed discovery link detector and parser.
"""

from __future__ import annotations
from typing import Any, Dict, Optional
from bs4 import BeautifulSoup
from omnisearch.models.video import VideoMetadataSource, VideoRecord
from omnisearch.core.dedup import resolve_platform_and_id


class OEmbedExtractor:
    """Discovers and parses oEmbed endpoints and responses."""

    @classmethod
    def discover_endpoint(cls, html_content: str) -> Optional[str]:
        soup = BeautifulSoup(html_content, "html.parser")
        link = soup.find("link", type="application/json+oembed")
        if link and link.get("href"):
            return link.get("href")
        return None

    @classmethod
    def parse_oembed_json(cls, data: Dict[str, Any], page_url: str) -> Optional[VideoRecord]:
        if not data:
            return None

        oembed_type = data.get("type")
        if oembed_type not in ("video", "rich"):
            return None

        title = data.get("title") or ""
        author_name = data.get("author_name")
        author_url = data.get("author_url")
        provider = data.get("provider_name")
        thumbnail_url = data.get("thumbnail_url")
        html_code = data.get("html")

        # Extract iframe src if present
        embed_url = None
        if html_code and "src=" in html_code:
            soup = BeautifulSoup(html_code, "html.parser")
            iframe = soup.find("iframe")
            if iframe and iframe.get("src"):
                embed_url = iframe.get("src")

        platform, platform_id, canonical_url = resolve_platform_and_id(page_url)
        internal_id = f"{platform.lower()}:{platform_id}" if platform_id else f"oembed:{canonical_url}"

        return VideoRecord(
            id=internal_id,
            canonical_url=canonical_url,
            platform=provider or platform,
            platform_id=platform_id,
            title=title,
            uploader_name=author_name,
            uploader_url=author_url,
            thumbnail_url=thumbnail_url,
            embed_url=embed_url,
            metadata_sources=[VideoMetadataSource.OEMBED],
            raw_metadata={"oembed": data},
        )
