"""
Gaming Adapter: Modrinth (Minecraft mods), Steam (store search), itch.io (indie games).

Modrinth is a JSON API with direct downloads; Steam and itch.io are HTML
search pages parsed with the shared single-parse soup pipeline.
"""

from __future__ import annotations
import logging
import re
from urllib.parse import quote_plus
from typing import List, Optional
from bs4 import BeautifulSoup

from omnisearch.models.query import SearchQuery
from omnisearch.models.video import VideoMetadataSource, VideoRecord, ItemType
from omnisearch.adapters.base import BaseSourceAdapter
from omnisearch.extractors.json_ld import parse_iso_datetime
from omnisearch.parsing import make_soup

logger = logging.getLogger(__name__)


class ModrinthAdapter(BaseSourceAdapter):
    """Discovers Minecraft mods, plugins, and resource packs on Modrinth."""

    @property
    def source_id(self) -> str:
        return "modrinth"

    @property
    def source_name(self) -> str:
        return "Modrinth (Minecraft mods & plugins)"

    async def search(self, query: SearchQuery, page: int = 1) -> List[VideoRecord]:
        search_terms = query.search_terms_string()
        if not search_terms.strip():
            return []

        records: List[VideoRecord] = []
        try:
            params = {"query": search_terms, "limit": 15, "offset": max(0, (page - 1) * 15)}
            resp = await self.http_client.get(
                "https://api.modrinth.com/v2/search", params=params, timeout=8.0
            )
            if resp.status_code != 200:
                return records
            for hit in resp.json().get("hits", []):
                slug = hit.get("slug") or hit.get("project_id")
                if not slug:
                    continue
                records.append(
                    VideoRecord(
                        id=f"modrinth:{slug}",
                        canonical_url=f"https://modrinth.com/{hit.get('project_type', 'mod')}/{slug}",
                        download_url=None,
                        platform="Modrinth",
                        platform_id=str(slug),
                        title=hit.get("title", "") or slug,
                        description=(hit.get("description") or "")[:300],
                        item_type=ItemType.SOFTWARE,
                        uploader_name=hit.get("author"),
                        publication_date=parse_iso_datetime(hit.get("date_created")),
                        view_count=hit.get("downloads"),
                        like_count=hit.get("follows"),
                        thumbnail_url=hit.get("icon_url"),
                        tags=["minecraft", str(hit.get("project_type", "mod"))]
                        + [str(c).lower() for c in (hit.get("categories") or [])[:5]],
                        metadata_sources=[VideoMetadataSource.OFFICIAL_API],
                        raw_metadata={"modrinth": {k: hit.get(k) for k in ("slug", "project_type", "downloads", "follows")}},
                    )
                )
        except Exception as exc:
            logger.debug("Modrinth search error: %s", exc)

        return records


class SteamAdapter(BaseSourceAdapter):
    """Discovers games on the Steam store via HTML search results."""

    BROWSER_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    @property
    def source_id(self) -> str:
        return "steam"

    @property
    def source_name(self) -> str:
        return "Steam (game store)"

    async def search(self, query: SearchQuery, page: int = 1) -> List[VideoRecord]:
        search_terms = query.search_terms_string()
        if not search_terms.strip():
            return []

        records: List[VideoRecord] = []
        try:
            resp = await self.http_client.get(
                "https://store.steampowered.com/search/",
                params={"term": search_terms, "page": page},
                headers=self.BROWSER_HEADERS,
                timeout=8.0,
            )
            if resp.status_code != 200:
                return records
            soup = make_soup(resp.text)
            for row in soup.select("a.search_result_row"):
                href = row.get("href", "")
                app_id = (row.get("data-ds-appid") or "").split(",")[0]
                if not href or not app_id:
                    continue

                title_el = row.select_one(".search_name .title") or row.select_one(".title")
                title = title_el.get_text().strip() if title_el else ""
                img = row.select_one(".search_capsule img")
                thumb = img.get("src") if img else None
                released_el = row.select_one(".search_released")
                released = released_el.get_text().strip() if released_el else ""
                pub_date = None
                if released:
                    for fmt in ("%d %b, %Y", "%b %d, %Y", "%d %B, %Y"):
                        try:
                            from datetime import datetime as _dt
                            pub_date = _dt.strptime(released, fmt)
                            break
                        except ValueError:
                            continue
                price_el = row.select_one(".discount_final_price, .discount_original_price")
                price = price_el.get_text().strip() if price_el else ""

                records.append(
                    VideoRecord(
                        id=f"steam:{app_id}",
                        canonical_url=href.split("?")[0],
                        download_url=None,
                        platform="Steam",
                        platform_id=str(app_id),
                        title=title or f"Steam app {app_id}",
                        description=f"Steam game — released {released}" + (f", {price}" if price else ""),
                        item_type=ItemType.SOFTWARE,
                        thumbnail_url=thumb,
                        publication_date=pub_date,
                        tags=["game", "steam"],
                        metadata_sources=[VideoMetadataSource.HTML_META],
                        raw_metadata={"steam_appid": app_id, "released": released, "price": price},
                    )
                )
        except Exception as exc:
            logger.debug("Steam search error: %s", exc)

        return records


class ItchIoAdapter(BaseSourceAdapter):
    """Discovers indie games and assets on itch.io via HTML search results."""

    BROWSER_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    @property
    def source_id(self) -> str:
        return "itchio"

    @property
    def source_name(self) -> str:
        return "itch.io (indie games & assets)"

    async def search(self, query: SearchQuery, page: int = 1) -> List[VideoRecord]:
        search_terms = query.search_terms_string()
        if not search_terms.strip():
            return []

        records: List[VideoRecord] = []
        try:
            resp = await self.http_client.get(
                "https://itch.io/search",
                params={"q": search_terms, "page": page},
                headers=self.BROWSER_HEADERS,
                timeout=8.0,
            )
            if resp.status_code != 200:
                return records
            soup = make_soup(resp.text)
            for cell in soup.select("div.game_cell"):
                link = cell.select_one("a.game_link, a.thumb_link, a[href*='.itch.io']")
                if not link:
                    continue
                href = link.get("href", "")
                if not href:
                    continue

                title_el = cell.select_one(".game_title, .title") or link
                title = title_el.get_text().strip() if title_el else ""
                img = cell.select_one("img")
                thumb = img.get("data-lazy_src") or img.get("src") if img else None
                genre_el = cell.select_one(".game_genre, .genre")
                genre = genre_el.get_text().strip() if genre_el else ""
                text_el = cell.select_one(".game_text, .description")
                desc = text_el.get_text().strip()[:300] if text_el else ""
                price_el = cell.select_one(".price_value, .sale_tag")
                price = price_el.get_text().strip() if price_el else ""

                # itch.io URLs embed the author: author.itch.io/game
                try:
                    author = href.split("//", 1)[-1].split(".itch.io")[0] if ".itch.io" in href else None
                except Exception:
                    author = None

                records.append(
                    VideoRecord(
                        id=f"itchio:{href}",
                        canonical_url=href,
                        download_url=None,
                        platform="itch.io",
                        platform_id=href.rstrip("/").split("/")[-1],
                        title=title or href.rstrip("/").split("/")[-1],
                        description=desc or f"Indie game on itch.io" + (f" ({genre})" if genre else ""),
                        item_type=ItemType.SOFTWARE,
                        uploader_name=author,
                        thumbnail_url=thumb,
                        tags=["game", "indie", "itchio"] + ([genre.lower()] if genre else []),
                        metadata_sources=[VideoMetadataSource.HTML_META],
                        raw_metadata={"itchio_url": href, "price": price},
                    )
                )
        except Exception as exc:
            logger.debug("itch.io search error: %s", exc)

        return records
