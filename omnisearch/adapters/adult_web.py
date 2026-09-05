"""
Uncensored & Adult Video Network Adapter.
Searches major public adult video platforms (EroMe albums, Eporner API, RedTube API, SpankBang,
YouPorn, Tube8, Motherless, and uncensored video networks) without content filtering or censorship.
"""

from __future__ import annotations
import asyncio
import logging
import os
import re
from typing import List, Optional, Set
from urllib.parse import quote_plus
from bs4 import BeautifulSoup

from omnisearch.models.query import SearchQuery
from omnisearch.models.video import VideoMetadataSource, VideoRecord
from omnisearch.adapters.base import BaseSourceAdapter
from omnisearch.extractors.json_ld import parse_iso_datetime
from omnisearch.extractors.page_extractor import PageExtractor

logger = logging.getLogger(__name__)


class AdultVideoNetworkAdapter(BaseSourceAdapter):
    """Discovers videos across adult and uncensored video networks via public search endpoints and album extractors."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Toggleable: enabled by default; set OMNISEARCH_ADULT_ENABLED=0 to disable.
        self._enabled = os.getenv("OMNISEARCH_ADULT_ENABLED", "1").strip().lower() not in ("0", "false", "no", "off")

    @property
    def source_id(self) -> str:
        return "adult_web"

    @property
    def source_name(self) -> str:
        return "Explicit Content"

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    async def search(self, query: SearchQuery, page: int = 1) -> List[VideoRecord]:
        search_terms = " ".join(query.extracted_phrases + query.extracted_terms) or query.raw_query
        if not search_terms.strip():
            return []

        records: List[VideoRecord] = []

        # Run multi-platform search tasks concurrently
        tasks = [
            self._search_erome(search_terms),
            self._search_eporner(search_terms, page),
            self._search_redtube(search_terms, page),
            self._search_spankbang(search_terms, page),
            self._search_youporn(search_terms, page),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for res in results:
            if isinstance(res, list):
                records.extend(res)

        return records

    async def _search_erome(self, search_terms: str) -> List[VideoRecord]:
        """Searches EroMe albums and extracts individual video files with real page metadata only."""
        records: List[VideoRecord] = []
        try:
            url = f"https://www.erome.com/search?q={quote_plus(search_terms)}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            }
            resp = await self.http_client.get(url, headers=headers, timeout=8.0)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                album_links: Set[str] = set()

                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if "/a/" in href and "erome.com" in href:
                        album_links.add(href)
                    elif "/a/" in href and href.startswith("/"):
                        album_links.add(f"https://www.erome.com{href}")

                album_tasks = [self._extract_erome_album(a_url) for a_url in list(album_links)[:6]]
                album_results = await asyncio.gather(*album_tasks, return_exceptions=True)
                for a_res in album_results:
                    if isinstance(a_res, list):
                        records.extend(a_res)
        except Exception as exc:
            logger.debug("EroMe search error: %s", exc)

        return records

    async def _extract_erome_album(self, album_url: str) -> List[VideoRecord]:
        """Fetches an EroMe album and extracts only actual video objects and real metadata."""
        records: List[VideoRecord] = []
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            resp = await self.http_client.get(album_url, headers=headers, timeout=8.0)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                h1 = soup.find("h1")
                album_title = h1.get_text().strip() if h1 else ""

                user_tag = soup.find("a", class_="username") or soup.find("span", class_="username")
                uploader = user_tag.get_text().strip() if user_tag else "EroMe Creator"

                real_tags: List[str] = []
                for tag_a in soup.select("a.tag, a[href*='/tag/']"):
                    t_text = tag_a.get_text().strip()
                    if t_text:
                        real_tags.append(t_text)

                videos = soup.find_all("video")
                album_id = album_url.rstrip("/").split("/")[-1]

                for idx, v in enumerate(videos, start=1):
                    v_src = v.get("src")
                    if not v_src:
                        source = v.find("source")
                        if source:
                            v_src = source.get("src")
                    if not v_src:
                        continue

                    poster = v.get("poster")
                    vid_title = f"{album_title} - Video #{idx}" if len(videos) > 1 and album_title else (album_title or f"EroMe Video #{idx}")

                    record = VideoRecord(
                        id=f"erome:{album_id}_{idx}",
                        canonical_url=album_url,
                        platform="EroMe",
                        platform_id=f"{album_id}_{idx}",
                        title=vid_title,
                        description=f"Album: {album_title} by {uploader}",
                        uploader_name=uploader,
                        thumbnail_url=poster,
                        embed_url=v_src,
                        tags=real_tags,
                        metadata_sources=[VideoMetadataSource.HTML_META],
                        raw_metadata={"album_url": album_url, "video_src": v_src},
                    )
                    records.append(record)
        except Exception as exc:
            logger.debug("Failed to extract EroMe album %s: %s", album_url, exc)

        return records

    async def _search_eporner(self, search_terms: str, page: int) -> List[VideoRecord]:
        records: List[VideoRecord] = []
        try:
            url = "https://www.eporner.com/api/v2/web/search/"
            params = {
                "query": search_terms,
                "page": page,
                "per_page": 25,
                "thumbsize": "big",
                "order": "top-weekly",
            }
            resp = await self.http_client.get(url, params=params, timeout=7.0)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("videos", []):
                    vid_id = item.get("id")
                    if not vid_id:
                        continue

                    title = item.get("title", "")
                    url_val = item.get("url", f"https://www.eporner.com/video-{vid_id}/")
                    embed_url = item.get("embed")
                    duration_sec = item.get("length_sec")
                    views = item.get("views")
                    keywords_str = item.get("keywords", "")
                    tags = [k.strip() for k in keywords_str.split(",") if k.strip()]
                    thumb = item.get("default_thumb", {}).get("src")

                    published = parse_iso_datetime(item.get("added"))

                    record = VideoRecord(
                        id=f"eporner:{vid_id}",
                        canonical_url=url_val,
                        platform="Eporner",
                        platform_id=str(vid_id),
                        title=title,
                        description=f"Keywords: {keywords_str}",
                        tags=tags,
                        duration_seconds=duration_sec,
                        view_count=views,
                        thumbnail_url=thumb,
                        embed_url=embed_url,
                        publication_date=published,
                        metadata_sources=[VideoMetadataSource.OFFICIAL_API],
                        raw_metadata={"eporner_item": item},
                    )
                    records.append(record)
        except Exception as exc:
            logger.debug("Eporner API search failed: %s", exc)

        return records

    async def _search_redtube(self, search_terms: str, page: int) -> List[VideoRecord]:
        records: List[VideoRecord] = []
        try:
            url = "https://api.redtube.com/"
            params = {
                "data": "redtube.Videos.searchVideos",
                "output": "json",
                "search": search_terms,
                "page": page,
                "thumbsize": "big",
            }
            resp = await self.http_client.get(url, params=params, timeout=7.0)
            if resp.status_code == 200:
                data = resp.json()
                videos = data.get("videos", [])
                for v_wrap in videos:
                    v = v_wrap.get("video", {})
                    vid_id = v.get("video_id")
                    if not vid_id:
                        continue

                    title = v.get("title", "")
                    url_val = v.get("url", f"https://www.redtube.com/{vid_id}")
                    thumb = v.get("default_thumb")
                    duration_str = v.get("duration")
                    duration_sec = None
                    if duration_str and ":" in duration_str:
                        parts = duration_str.split(":")
                        try:
                            if len(parts) == 2:
                                duration_sec = int(parts[0]) * 60 + int(parts[1])
                            elif len(parts) == 3:
                                duration_sec = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
                        except Exception:
                            pass

                    views = int(v.get("views")) if v.get("views") else None
                    tags = [t.get("tag_name") for t in v.get("tags", []) if t.get("tag_name")]

                    record = VideoRecord(
                        id=f"redtube:{vid_id}",
                        canonical_url=url_val,
                        platform="RedTube",
                        platform_id=str(vid_id),
                        title=title,
                        description=" ".join(tags),
                        tags=tags,
                        duration_seconds=duration_sec,
                        view_count=views,
                        thumbnail_url=thumb,
                        embed_url=f"https://embed.redtube.com/?id={vid_id}",
                        metadata_sources=[VideoMetadataSource.OFFICIAL_API],
                        raw_metadata={"redtube_item": v},
                    )
                    records.append(record)
        except Exception as exc:
            logger.debug("RedTube API search failed: %s", exc)

        return records

    async def _search_spankbang(self, search_terms: str, page: int) -> List[VideoRecord]:
        records: List[VideoRecord] = []
        try:
            url = f"https://spankbang.com/s/{quote_plus(search_terms)}/{page}/"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            resp = await self.http_client.get(url, headers=headers, timeout=6.0)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                for item in soup.select("div.video-item, div.video_item"):
                    a = item.find("a", class_="thumb") or item.find("a", href=True)
                    if not a:
                        continue
                    href = a["href"]
                    if not href.startswith("http"):
                        href = f"https://spankbang.com{href}"
                    img = item.find("img")
                    thumb = img.get("data-src") or img.get("src") if img else None
                    title_elem = item.find("span", class_="title") or item.find("a", class_="n") or a
                    title = title_elem.get_text().strip() if title_elem else ""
                    if title and href:
                        vid_id = href.rstrip("/").split("/")[-2] if len(href.rstrip("/").split("/")) > 2 else "video"
                        records.append(
                            VideoRecord(
                                id=f"spankbang:{vid_id}",
                                canonical_url=href,
                                platform="SpankBang",
                                platform_id=vid_id,
                                title=title,
                                thumbnail_url=thumb,
                                embed_url=href,
                                metadata_sources=[VideoMetadataSource.HTML_META],
                                raw_metadata={"source": "spankbang"},
                            )
                        )
        except Exception as exc:
            logger.debug("SpankBang search failed: %s", exc)
        return records

    async def _search_youporn(self, search_terms: str, page: int) -> List[VideoRecord]:
        records: List[VideoRecord] = []
        try:
            url = f"https://www.youporn.com/search/?query={quote_plus(search_terms)}&page={page}"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            resp = await self.http_client.get(url, headers=headers, timeout=6.0)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                for div in soup.select("div.video-box, div.js_video-wrapper"):
                    a = div.find("a", href=re.compile(r"/watch/"))
                    if not a:
                        continue
                    href = a["href"]
                    if not href.startswith("http"):
                        href = f"https://www.youporn.com{href}"
                    img = div.find("img")
                    thumb = img.get("data-src") or img.get("src") if img else None
                    title = a.get("title") or a.get_text().strip()
                    if title and href:
                        vid_id = href.rstrip("/").split("/")[-2] if "/watch/" in href else "yp"
                        records.append(
                            VideoRecord(
                                id=f"youporn:{vid_id}",
                                canonical_url=href,
                                platform="YouPorn",
                                platform_id=vid_id,
                                title=title,
                                thumbnail_url=thumb,
                                embed_url=href,
                                metadata_sources=[VideoMetadataSource.HTML_META],
                                raw_metadata={"source": "youporn"},
                            )
                        )
        except Exception as exc:
            logger.debug("YouPorn search failed: %s", exc)
        return records
