"""
Schema.org JSON-LD VideoObject and MediaObject extractor.
"""

from __future__ import annotations
import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from bs4 import BeautifulSoup
from omnisearch.models.video import VideoMetadataSource, VideoRecord
from omnisearch.core.dedup import resolve_platform_and_id


ISO8601_DURATION_RE = re.compile(
    r"^P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+(?:\.\d+)?)S)?)?$"
)


def parse_iso8601_duration(duration_str: str) -> Optional[int]:
    """Parses ISO 8601 duration string like 'PT1H2M30S' or 'PT45M' into seconds."""
    if not duration_str:
        return None
    try:
        match = ISO8601_DURATION_RE.match(duration_str.strip())
        if not match:
            # Check for pure integer seconds
            if duration_str.isdigit():
                return int(duration_str)
            return None
        parts = match.groupdict()
        days = int(parts.get("days") or 0)
        hours = int(parts.get("hours") or 0)
        minutes = int(parts.get("minutes") or 0)
        seconds = float(parts.get("seconds") or 0)
        total = days * 86400 + hours * 3600 + minutes * 60 + int(seconds)
        return total if total > 0 else None
    except Exception:
        return None


def parse_iso_datetime(date_str: str) -> Optional[datetime]:
    """Parses ISO 8601 datetime strings."""
    if not date_str:
        return None
    try:
        # Replace trailing Z with +00:00 for fromisoformat compatibility
        cleaned = date_str.strip()
        if cleaned.endswith("Z"):
            cleaned = cleaned[:-1] + "+00:00"
        return datetime.fromisoformat(cleaned)
    except Exception:
        return None


class JsonLdExtractor:
    """Extracts VideoObject structures from HTML <script type="application/ld+json">."""

    @classmethod
    def extract_from_html(cls, html_content: str, page_url: str) -> List[VideoRecord]:
        records: List[VideoRecord] = []
        soup = BeautifulSoup(html_content, "html.parser")
        scripts = soup.find_all("script", type="application/ld+json")

        for script in scripts:
            if not script.string:
                continue
            try:
                data = json.loads(script.string)
                cls._extract_video_objects(data, page_url, records)
            except Exception:
                continue

        return records

    @classmethod
    def _extract_video_objects(cls, data: Any, page_url: str, records: List[VideoRecord]):
        if isinstance(data, list):
            for item in data:
                cls._extract_video_objects(item, page_url, records)
        elif isinstance(data, dict):
            # Check @graph
            if "@graph" in data and isinstance(data["@graph"], list):
                for item in data["@graph"]:
                    cls._extract_video_objects(item, page_url, records)
                return

            type_field = data.get("@type", "")
            if isinstance(type_field, list):
                is_video = "VideoObject" in type_field or "MediaObject" in type_field
            else:
                is_video = type_field in ("VideoObject", "MediaObject")

            if is_video:
                record = cls._build_record(data, page_url)
                if record:
                    records.append(record)

    @classmethod
    def _build_record(cls, data: Dict[str, Any], page_url: str) -> Optional[VideoRecord]:
        title = data.get("name") or data.get("headline") or ""
        description = data.get("description") or ""
        url = data.get("url") or data.get("contentUrl") or page_url

        platform, platform_id, canonical_url = resolve_platform_and_id(url)
        internal_id = f"{platform.lower()}:{platform_id}" if platform_id else f"jsonld:{canonical_url}"

        # Uploader / Author
        uploader_name = None
        uploader_url = None
        author_data = data.get("author") or data.get("creator") or data.get("publisher")
        if isinstance(author_data, dict):
            uploader_name = author_data.get("name")
            uploader_url = author_data.get("url")
        elif isinstance(author_data, str):
            uploader_name = author_data
        elif isinstance(author_data, list) and author_data:
            first = author_data[0]
            if isinstance(first, dict):
                uploader_name = first.get("name")
                uploader_url = first.get("url")
            elif isinstance(first, str):
                uploader_name = first

        # Publication date
        pub_date = parse_iso_datetime(data.get("uploadDate") or data.get("datePublished") or data.get("dateCreated"))

        # Duration
        duration = parse_iso8601_duration(data.get("duration") or "")

        # Thumbnail
        thumbnail_url = None
        thumb_data = data.get("thumbnailUrl") or data.get("thumbnail")
        if isinstance(thumb_data, list) and thumb_data:
            thumbnail_url = thumb_data[0]
        elif isinstance(thumb_data, str):
            thumbnail_url = thumb_data
        elif isinstance(thumb_data, dict):
            thumbnail_url = thumb_data.get("url")

        # Embed URL
        embed_url = data.get("embedUrl")

        # Tags / Keywords
        tags: List[str] = []
        keywords = data.get("keywords")
        if isinstance(keywords, str):
            tags = [k.strip() for k in keywords.split(",") if k.strip()]
        elif isinstance(keywords, list):
            tags = [str(k).strip() for k in keywords if str(k).strip()]

        # Interaction statistics (views, likes)
        view_count = None
        like_count = None
        interaction = data.get("interactionStatistic")
        if isinstance(interaction, list):
            for stat in interaction:
                if isinstance(stat, dict):
                    stat_type = stat.get("interactionType", {})
                    stat_name = stat_type.get("@type") if isinstance(stat_type, dict) else str(stat_type)
                    count = stat.get("userInteractionCount")
                    if "WatchAction" in str(stat_name) and count is not None:
                        try:
                            view_count = int(count)
                        except Exception:
                            pass
                    elif "LikeAction" in str(stat_name) and count is not None:
                        try:
                            like_count = int(count)
                        except Exception:
                            pass

        return VideoRecord(
            id=internal_id,
            canonical_url=canonical_url,
            platform=platform,
            platform_id=platform_id,
            title=title,
            description=description,
            uploader_name=uploader_name,
            uploader_url=uploader_url,
            publication_date=pub_date,
            duration_seconds=duration,
            tags=tags,
            thumbnail_url=thumbnail_url,
            embed_url=embed_url,
            view_count=view_count,
            like_count=like_count,
            metadata_sources=[VideoMetadataSource.JSON_LD],
            raw_metadata={"json_ld": data},
        )
