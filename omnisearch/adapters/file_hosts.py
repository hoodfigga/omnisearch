"""
Universal File Hosting, Cyberlocker & Cloud Storage Source Adapter.
Discovers and extracts files, downloads, and archives across:
- MediaFire, MEGA, Rapidgator, 1Fichier, Turbobit, Nitroflare, DDownload, Katfile
- Pixeldrain, Gofile, Krakenfiles, Catbox, Tmpfiles, Cyberfile, Bunkr (all domains)
- Google Drive, Dropbox, Workupload
"""

from __future__ import annotations
import asyncio
import base64
import logging
import re
from typing import List, Optional, Set
from urllib.parse import parse_qs, quote_plus, unquote, urlparse
from bs4 import BeautifulSoup

from omnisearch.models.query import SearchQuery
from omnisearch.models.video import ItemRecord, MetadataSource
from omnisearch.adapters.base import BaseSourceAdapter
from omnisearch.extractors.page_extractor import PageExtractor

logger = logging.getLogger(__name__)


class FileHostingAdapter(BaseSourceAdapter):
    """Discovers file uploads, downloads, and archives across major cyberlockers and cloud storage platforms."""

    TARGET_DOMAINS = [
        "mediafire.com",
        "mega.nz",
        "mega.io",
        "rapidgator.net",
        "1fichier.com",
        "turbobit.net",
        "nitroflare.com",
        "ddownload.com",
        "katfile.com",
        "pixeldrain.com",
        "gofile.io",
        "krakenfiles.com",
        "catbox.moe",
        "tmpfiles.org",
        "cyberfile.me",
        "cyberdrop.me",
        "saint2.su",
        "bunkr.cr",
        "bunkr.is",
        "bunkr.si",
        "bunkrr.su",
        "bunkr.site",
        "bunkr.black",
        "bunkr.ws",
        "bunkr.ps",
        "bunkr.ph",
        "drive.google.com",
        "dropbox.com",
        "workupload.com",
    ]

    @property
    def source_id(self) -> str:
        return "file_hosts"

    @property
    def source_name(self) -> str:
        return "File Hosts & Cyberlockers (MediaFire, MEGA, Rapidgator, 1Fichier, Pixeldrain, Bunkr, GDrive, etc.)"

    async def search(self, query: SearchQuery, page: int = 1) -> List[ItemRecord]:
        search_terms = " ".join(query.extracted_phrases + query.extracted_terms) or query.raw_query
        if not search_terms.strip():
            return []

        records: List[ItemRecord] = []

        # 1. Query Bunkr Album Indexer (balbums.st) for Bunkr albums
        bunkr_records = await self._search_balbums(search_terms)
        records.extend(bunkr_records)

        # 2. Discover direct file links across target hosts via search engine dorks
        candidate_urls = await self._discover_file_host_urls(search_terms, page)
        if candidate_urls:
            tasks = [self._extract_page(url) for url in candidate_urls[:35]]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for res in results:
                if isinstance(res, list):
                    records.extend(res)
                elif isinstance(res, ItemRecord):
                    records.append(res)

        return records

    async def _search_balbums(self, search_terms: str) -> List[ItemRecord]:
        """Searches Bunkr Album archive (balbums.st) and extracts individual album items with real titles."""
        records: List[ItemRecord] = []
        try:
            clean_q = search_terms.replace("_", " ").strip()
            url = f"https://balbums.st/?search={quote_plus(clean_q)}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            }
            resp = await self.http_client.get(url, headers=headers, timeout=7.0)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                album_links: List[tuple[str, str]] = []

                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if "/a/" in href:
                        raw_title = a.get_text().strip()
                        album_links.append((href, raw_title))

                album_tasks = [self._extract_bunkr_album(a_url, title) for a_url, title in album_links[:6]]
                album_results = await asyncio.gather(*album_tasks, return_exceptions=True)
                for a_res in album_results:
                    if isinstance(a_res, list):
                        records.extend(a_res)
        except Exception as exc:
            logger.debug("balbums.st search failed: %s", exc)

        return records

    async def _extract_bunkr_album(self, album_url: str, album_title: str) -> List[ItemRecord]:
        """Parses individual items from a Bunkr album page."""
        records: List[ItemRecord] = []
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            resp = await self.http_client.get(album_url, headers=headers, timeout=8.0)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                for div in soup.find_all("div", class_=re.compile("grid-images_box|the_box", re.I)):
                    a_file = div.find("a", href=re.compile(r"/f/|/d/|/v/|/file/", re.I))
                    if not a_file:
                        continue
                    file_href = a_file.get("href", "")
                    if not file_href.startswith("http"):
                        file_href = f"https://bunkr.cr{file_href}"

                    p_name = div.find("p") or div.find("span", class_="name")
                    item_name = p_name.get_text().strip() if p_name else ""

                    img = div.find("img")
                    thumb = img.get("src") if img else None

                    rec = ItemRecord(
                        id=f"bunkr:{file_href}",
                        canonical_url=file_href,
                        download_url=file_href,
                        platform="Bunkr",
                        title=item_name or album_title or "Bunkr File",
                        description=f"Album file: {item_name or album_title}",
                        thumbnail_url=thumb,
                        tags=["bunkr", "file-host"],
                        metadata_sources=[MetadataSource.FILE_HOST_PAGE],
                        raw_metadata={"album_url": album_url, "file_url": file_href},
                    )
                    records.append(rec)
        except Exception as exc:
            logger.debug("Failed to extract Bunkr album %s: %s", album_url, exc)

        return records

    async def _discover_file_host_urls(self, search_terms: str, page: int) -> List[str]:
        """Discovers direct links to target file hosts using multi-engine search dorks."""
        discovered: Set[str] = set()

        # Dork queries targeting major cyberlockers
        dorks = [
            f'"{search_terms}" (site:mediafire.com OR site:mega.nz OR site:rapidgator.net OR site:1fichier.com)',
            f'"{search_terms}" (site:pixeldrain.com OR site:gofile.io OR site:krakenfiles.com OR site:catbox.moe)',
            f'"{search_terms}" (site:drive.google.com OR site:dropbox.com OR site:workupload.com)',
            f'"{search_terms}" (site:bunkr.cr OR site:bunkr.is OR site:bunkr.si OR site:cyberfile.me)',
        ]

        tasks = []
        for dork in dorks:
            tasks.append(self._search_yahoo(dork))
            tasks.append(self._search_bing(dork))
            tasks.append(self._search_duckduckgo(dork))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for res in results:
            if isinstance(res, list):
                discovered.update(res)

        clean_urls: List[str] = []
        for u in discovered:
            if not u.startswith("http"):
                continue
            parsed = urlparse(u)
            domain = parsed.netloc.lower()
            if any(target in domain for target in self.TARGET_DOMAINS):
                clean_urls.append(u)

        return clean_urls

    async def _search_yahoo(self, query_str: str) -> List[str]:
        discovered: List[str] = []
        try:
            url = f"https://search.yahoo.com/search?p={quote_plus(query_str)}"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            resp = await self.http_client.get(url, headers=headers, timeout=6.0)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                for a in soup.select('div.compText a, h3 a, a[href*="r.search.yahoo.com"]'):
                    href = a.get("href", "")
                    if "RU=" in href:
                        ru = href.split("RU=")[1].split("/RK=")[0]
                        decoded = unquote(ru)
                        if decoded.startswith("http"):
                            discovered.append(decoded)
                    elif href.startswith("http") and "yahoo.com" not in href:
                        discovered.append(href)
        except Exception as exc:
            logger.debug("Yahoo file host search error: %s", exc)
        return list(dict.fromkeys(discovered))

    async def _search_bing(self, query_str: str) -> List[str]:
        discovered: List[str] = []
        try:
            url = f"https://www.bing.com/search?q={quote_plus(query_str)}"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            resp = await self.http_client.get(url, headers=headers, timeout=6.0)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                for a in soup.select("li.b_algo h2 a, h2 a"):
                    href = a.get("href", "")
                    if "/ck/a?" in href and "&u=" in href:
                        u_part = href.split("&u=")[1].split("&")[0]
                        if u_part.startswith("a1"):
                            raw_b64 = u_part[2:]
                            raw_b64 += "=" * (-len(raw_b64) % 4)
                            try:
                                decoded = base64.b64decode(raw_b64).decode("utf-8", errors="ignore")
                                if decoded.startswith("http"):
                                    discovered.append(decoded)
                            except Exception:
                                pass
                    elif href.startswith("http"):
                        discovered.append(href)
        except Exception as exc:
            logger.debug("Bing file host search error: %s", exc)
        return list(dict.fromkeys(discovered))

    async def _search_duckduckgo(self, query_str: str) -> List[str]:
        discovered: List[str] = []
        try:
            url = "https://html.duckduckgo.com/html/"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": "https://html.duckduckgo.com/",
            }
            client = await self.http_client.get_client()
            resp = await client.post(url, data={"q": query_str, "kp": "-2"}, headers=headers, timeout=6.0)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                for link in soup.find_all("a", href=True):
                    href = link.get("href", "")
                    if "uddg=" in href:
                        parsed = urlparse(href)
                        qs = parse_qs(parsed.query)
                        target = qs.get("uddg", [None])[0]
                        if target:
                            discovered.append(unquote(target))
                    elif href.startswith("http") and "duckduckgo.com" not in href:
                        discovered.append(href)
        except Exception as exc:
            logger.debug("DuckDuckGo file host search error: %s", exc)
        return list(dict.fromkeys(discovered))

    async def _extract_page(self, page_url: str) -> List[ItemRecord]:
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            resp = await self.http_client.get(page_url, headers=headers, timeout=8.0)
            if resp.status_code == 200:
                final_url = str(resp.url)
                return PageExtractor.extract_from_html(resp.text, final_url)
        except Exception as exc:
            logger.debug("Failed to extract file host page %s: %s", page_url, exc)

        return []
