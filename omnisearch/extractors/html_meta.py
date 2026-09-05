"""
HTML Standard Meta tags, Twitter Player cards, and HTML5 video tag extractor.
"""

from __future__ import annotations
from typing import Dict, List, Optional
from bs4 import BeautifulSoup
from omnisearch.models.video import MetadataSource, ItemRecord, ItemType
from omnisearch.core.dedup import resolve_platform_and_id
from omnisearch.extractors.file_hosts import detect_file_extension, infer_item_type


class HtmlMetaExtractor:
    """Extracts standard meta tags, canonical link, twitter cards, and HTML5 video elements."""

    @classmethod
    def extract_from_html(cls, html_content: str, page_url: str) -> Optional[ItemRecord]:
        soup = BeautifulSoup(html_content, "html.parser")

        # Check canonical URL
        canonical_tag = soup.find("link", rel="canonical")
        canonical_href = canonical_tag.get("href") if canonical_tag else page_url

        # Check title
        title_tag = soup.find("title")
        title = title_tag.get_text().strip() if title_tag else ""

        # Collect meta tags
        meta_dict: Dict[str, str] = {}
        for meta in soup.find_all("meta"):
            name = meta.get("name") or meta.get("property") or meta.get("itemprop")
            content = meta.get("content")
            if name and content:
                meta_dict[name.lower()] = content.strip()

        doc_title = meta_dict.get("twitter:title") or meta_dict.get("og:title") or title
        if not doc_title:
            return None

        # Check for Video indicators
        has_twitter_player = "twitter:player" in meta_dict
        has_video_tag = soup.find("video") is not None
        is_video = (has_twitter_player or has_video_tag or "video" in meta_dict.get("keywords", "").lower())

        # Build fields
        description = meta_dict.get("description") or meta_dict.get("twitter:description") or meta_dict.get("og:description") or ""
        author = meta_dict.get("author") or meta_dict.get("twitter:creator")
        keywords_str = meta_dict.get("keywords") or ""
        tags = [k.strip() for k in keywords_str.split(",") if k.strip()]
        thumbnail = meta_dict.get("twitter:image") or meta_dict.get("og:image")
        embed_url = meta_dict.get("twitter:player")

        ext = detect_file_extension(canonical_href or page_url)
        item_type = ItemType.VIDEO if is_video else (infer_item_type(ext) if ext else ItemType.WEB_PAGE)

        platform, platform_id, canonical_url = resolve_platform_and_id(canonical_href or page_url)
        internal_id = f"{platform.lower()}:{platform_id}" if platform_id else f"html:{canonical_url}"

        return ItemRecord(
            id=internal_id,
            canonical_url=canonical_url,
            platform=platform,
            platform_id=platform_id,
            title=doc_title,
            description=description,
            uploader_name=author,
            tags=tags,
            thumbnail_url=thumbnail,
            embed_url=embed_url,
            item_type=item_type,
            file_extension=ext,
            metadata_sources=[MetadataSource.HTML_META],
            raw_metadata={"html_meta": meta_dict},
        )
