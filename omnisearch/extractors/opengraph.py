"""
OpenGraph video metadata extractor (<meta property="og:*"> and <meta property="video:*">).
"""

from __future__ import annotations
from typing import Dict, List, Optional
from bs4 import BeautifulSoup
from omnisearch.models.video import MetadataSource, ItemRecord, ItemType
from omnisearch.core.dedup import resolve_platform_and_id
from omnisearch.extractors.json_ld import parse_iso_datetime
from omnisearch.extractors.file_hosts import detect_file_extension, infer_item_type


class OpenGraphExtractor:
    """Extracts OpenGraph metadata from HTML."""

    @classmethod
    def extract_from_html(cls, html_content: str, page_url: str) -> Optional[ItemRecord]:
        soup = BeautifulSoup(html_content, "html.parser")
        meta_tags = soup.find_all("meta")

        og_data: Dict[str, str] = {}
        video_tags: List[str] = []

        for meta in meta_tags:
            prop = meta.get("property") or meta.get("name")
            content = meta.get("content")
            if not prop or not content:
                continue

            prop_lower = prop.lower()
            if prop_lower.startswith("og:") or prop_lower.startswith("video:"):
                og_data[prop_lower] = content.strip()
                if prop_lower == "video:tag":
                    video_tags.append(content.strip())

        title = og_data.get("og:title") or ""
        if not title:
            return None

        # Verify if page actually contains video
        is_video_type = og_data.get("og:type") in ("video.other", "video.movie", "video.episode", "video")
        has_video_url = any(k in og_data for k in ("og:video", "og:video:url", "og:video:secure_url"))
        is_video = is_video_type or has_video_url

        description = og_data.get("og:description") or ""
        video_url = og_data.get("og:video:secure_url") or og_data.get("og:video:url") or og_data.get("og:video") or page_url
        thumbnail_url = og_data.get("og:image:secure_url") or og_data.get("og:image")
        site_name = og_data.get("og:site_name")

        # Duration
        duration_sec = None
        duration_str = og_data.get("og:video:duration") or og_data.get("video:duration")
        if duration_str and duration_str.isdigit():
            duration_sec = int(duration_str)

        # Release date
        pub_date = parse_iso_datetime(og_data.get("video:release_date"))

        ext = detect_file_extension(page_url)
        item_type = ItemType.VIDEO if is_video else (infer_item_type(ext) if ext else ItemType.WEB_PAGE)

        platform, platform_id, canonical_url = resolve_platform_and_id(page_url)
        internal_id = f"{platform.lower()}:{platform_id}" if platform_id else f"og:{canonical_url}"

        return ItemRecord(
            id=internal_id,
            canonical_url=canonical_url,
            platform=site_name or platform,
            platform_id=platform_id,
            title=title,
            description=description,
            uploader_name=site_name,
            publication_date=pub_date,
            duration_seconds=duration_sec,
            tags=video_tags,
            thumbnail_url=thumbnail_url,
            embed_url=video_url if is_video and ("embed" in video_url or "player" in video_url) else None,
            item_type=item_type,
            file_extension=ext,
            metadata_sources=[MetadataSource.OPEN_GRAPH],
            raw_metadata={"opengraph": og_data},
        )
