"""
Library & Books Adapter: OpenLibrary (books + public ebook access) and
Wikimedia Commons (freely licensed media files with direct URLs).
"""

from __future__ import annotations
import logging
import re
from typing import List
from urllib.parse import quote_plus, unquote
from omnisearch.models.query import SearchQuery
from omnisearch.models.video import VideoMetadataSource, VideoRecord, ItemType
from omnisearch.adapters.base import BaseSourceAdapter
from omnisearch.extractors.file_hosts import detect_file_extension, infer_item_type, format_bytes

logger = logging.getLogger(__name__)


class OpenLibraryAdapter(BaseSourceAdapter):
    """Discovers books on OpenLibrary, flagging public-domain readable ebooks."""

    @property
    def source_id(self) -> str:
        return "openlibrary"

    @property
    def source_name(self) -> str:
        return "OpenLibrary (books & ebooks)"

    async def search(self, query: SearchQuery, page: int = 1) -> List[VideoRecord]:
        search_terms = " ".join(query.extracted_phrases + query.extracted_terms) or query.raw_query
        if not search_terms.strip():
            return []

        records: List[VideoRecord] = []
        try:
            fields = "title,author_name,key,ia,ebook_access,first_publish_year,cover_i,edition_count,language"
            params = {"q": search_terms, "limit": 20, "page": page, "fields": fields}
            resp = await self.http_client.get(
                "https://openlibrary.org/search.json", params=params, timeout=9.0
            )
            if resp.status_code == 200:
                for doc in resp.json().get("docs", []):
                    key = doc.get("key", "")
                    if not key:
                        continue
                    title = doc.get("title", "Untitled")
                    authors = doc.get("author_name") or []
                    ia = doc.get("ia") or []
                    ebook_access = doc.get("ebook_access", "no_ebook")
                    has_readable = ebook_access == "public"

                    # Direct download: the Internet Archive full-text PDF when public
                    download_url = None
                    if has_readable and ia:
                        download_url = f"https://archive.org/download/{ia[0]}/{ia[0]}.pdf"

                    cover = f"https://covers.openlibrary.org/b/id/{doc['cover_i']}-M.jpg" if doc.get("cover_i") else None

                    records.append(
                        VideoRecord(
                            id=f"ol:{key}",
                            canonical_url=f"https://openlibrary.org{key}",
                            download_url=download_url,
                            platform="OpenLibrary",
                            platform_id=key,
                            title=title,
                            description=f"Book by {', '.join(authors[:3]) if authors else 'unknown'}"
                                        f" ({doc.get('first_publish_year', '?')})"
                                        f"{' — public ebook available' if has_readable else ''}",
                            item_type=ItemType.DOCUMENT,
                            file_extension="pdf" if download_url else None,
                            uploader_name=", ".join(authors[:3]) if authors else None,
                            publication_date=None,
                            thumbnail_url=cover,
                            tags=["book", "openlibrary"] + (["ebook", "direct-download"] if download_url else []),
                            metadata_sources=[VideoMetadataSource.OFFICIAL_API] + ([VideoMetadataSource.DIRECT_LINK] if download_url else []),
                            raw_metadata={"ol_doc": {k: doc.get(k) for k in ("key", "ebook_access", "ia", "edition_count", "language")}},
                        )
                    )
        except Exception as exc:
            logger.debug("OpenLibrary search error: %s", exc)

        return records


class WikimediaCommonsAdapter(BaseSourceAdapter):
    """Discovers freely licensed media files on Wikimedia Commons with direct file URLs."""

    @property
    def source_id(self) -> str:
        return "commons"

    @property
    def source_name(self) -> str:
        return "Wikimedia Commons (free media files)"

    async def search(self, query: SearchQuery, page: int = 1) -> List[VideoRecord]:
        search_terms = " ".join(query.extracted_phrases + query.extracted_terms) or query.raw_query
        if not search_terms.strip():
            return []

        records: List[VideoRecord] = []
        try:
            params = {
                "action": "query",
                "format": "json",
                "generator": "search",
                "gsrsearch": search_terms,
                "gsrnamespace": "6",  # File: namespace
                "gsrlimit": "20",
                "gsroffset": str((page - 1) * 20),
                "prop": "imageinfo",
                "iiprop": "url|size|mime",
            }
            resp = await self.http_client.get(
                "https://commons.wikimedia.org/w/api.php", params=params, timeout=9.0
            )
            if resp.status_code == 200:
                pages = resp.json().get("query", {}).get("pages", {})
                for _, p in pages.items():
                    infos = p.get("imageinfo") or []
                    if not infos:
                        continue
                    ii = infos[0]
                    file_url = ii.get("url", "")
                    if not file_url:
                        continue
                    # Strip utm params Commons appends
                    file_url = file_url.split("?")[0]
                    title = p.get("title", "").replace("File:", "")
                    mime = ii.get("mime", "")
                    size = ii.get("size")

                    if mime.startswith("audio/"):
                        item_type = ItemType.AUDIO
                    elif mime.startswith("video/"):
                        item_type = ItemType.VIDEO
                    elif mime.startswith("image/"):
                        item_type = ItemType.IMAGE
                    elif "pdf" in mime:
                        item_type = ItemType.DOCUMENT
                    else:
                        item_type = ItemType.FILE

                    ext = detect_file_extension(title) or detect_file_extension(file_url)

                    records.append(
                        VideoRecord(
                            id=f"commons:{p.get('pageid', title)}",
                            canonical_url=ii.get("descriptionurl") or file_url,
                            download_url=file_url,
                            platform="Wikimedia Commons",
                            platform_id=str(p.get("pageid", "")),
                            title=unquote(title),
                            description=f"Freely licensed media file ({mime}, {format_bytes(size) if size else 'unknown size'})",
                            item_type=item_type,
                            file_name=unquote(title),
                            file_extension=ext,
                            file_size_bytes=size,
                            file_size_human=format_bytes(size) if size else None,
                            thumbnail_url=ii.get("thumburl") or (file_url if mime.startswith("image/") else None),
                            tags=["commons", "wikimedia", "free-license", "direct-download"],
                            metadata_sources=[VideoMetadataSource.OFFICIAL_API, VideoMetadataSource.DIRECT_LINK],
                            raw_metadata={"commons_file": {"mime": mime, "width": ii.get("width"), "height": ii.get("height")}},
                        )
                    )
        except Exception as exc:
            logger.debug("Wikimedia Commons search error: %s", exc)

        return records
