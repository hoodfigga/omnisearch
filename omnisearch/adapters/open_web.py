"""
Open Web Search & Universal File / Deep Metadata Discovery Adapter.
Searches the entire open web via public search engines (DuckDuckGo, Yahoo HTML,
Bing HTML, Mojeek, SearXNG uncensored instances, Qwant, and targeted file host dorks),
fetches candidate web pages from arbitrary domains across the internet, and automatically
extracts structured file, document, software, media metadata, and direct download links.
"""

from __future__ import annotations
import asyncio
import base64
import logging
import re
from urllib.parse import parse_qs, quote_plus, unquote, urlparse
from typing import List, Optional, Set
from bs4 import BeautifulSoup

from omnisearch.models.query import SearchQuery
from dataclasses import dataclass
from omnisearch.models.query import SearchQuery
from omnisearch.models.video import MetadataSource, ItemRecord, ItemType
from omnisearch.adapters.base import BaseSourceAdapter
from omnisearch.extractors.page_extractor import PageExtractor
from omnisearch.extractors.file_hosts import detect_file_extension, infer_item_type
from omnisearch.core.dedup import resolve_platform_and_id, DeduplicationEngine

logger = logging.getLogger(__name__)


@dataclass
class WebSearchResult:
    url: str
    title: str = ""
    snippet: str = ""


class OpenWebDiscoveryAdapter(BaseSourceAdapter):
    """
    Discovers websites, files, downloads, and web resources across the open internet by querying
    multiple search engines, encyclopedias, and dork patterns, retrieving arbitrary web pages,
    and inspecting them for downloads, mirrors, open directories, and structured metadata.
    """

    SEARXNG_INSTANCES = [
        "https://search.ononoki.org",
        "https://searx.be",
        "https://priv.au",
        "https://search.sapti.me",
        "https://search.mdosch.de",
    ]

    def __init__(self, max_crawl_pages: int = 30, **kwargs):
        super().__init__(**kwargs)
        self.max_crawl_pages = max_crawl_pages

    @property
    def source_id(self) -> str:
        return "open_web"

    @property
    def source_name(self) -> str:
        return "Open Web Crawler (Entire Internet - SafeSearch Off)"

    async def search(self, query: SearchQuery, page: int = 1) -> List[ItemRecord]:
        search_terms = " ".join(query.extracted_phrases + query.extracted_terms) or query.raw_query
        if not search_terms.strip():
            return []

        # 1. Discover matching websites, web pages, and candidate URLs
        web_results = await self._discover_web_items(search_terms, page)
        if not web_results:
            return []

        all_candidates: List[ItemRecord] = []

        # 2. Turn discovered web search hits into first-class Web Page ItemRecords
        for hit in web_results:
            ext = detect_file_extension(hit.url) or detect_file_extension(hit.title)
            item_type = infer_item_type(ext) if ext else ItemType.WEB_PAGE
            platform, platform_id, canonical = resolve_platform_and_id(hit.url)
            clean_domain = urlparse(hit.url).netloc.replace("www.", "")

            web_rec = ItemRecord(
                id=f"web:{canonical}",
                canonical_url=canonical,
                download_url=canonical if (ext and ext != "html") else None,
                platform=platform if platform != "Web" else clean_domain,
                platform_id=platform_id,
                title=hit.title or f"Page on {clean_domain}",
                description=hit.snippet or f"Discovered web page matching '{search_terms}' on {clean_domain}",
                item_type=item_type,
                file_name=hit.title if ext else None,
                file_extension=ext,
                metadata_sources=[MetadataSource.HTML_META],
                raw_metadata={"search_engine": "web_search", "snippet": hit.snippet, "url": canonical},
            )
            all_candidates.append(web_rec)

        # 3. Concurrently crawl candidate pages to extract direct download links, files, and cyberlockers
        crawl_urls = [hit.url for hit in web_results[: self.max_crawl_pages]]
        tasks = [self._extract_from_page_url(url) for url in crawl_urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for res in results:
            if isinstance(res, list):
                all_candidates.extend(res)
            elif isinstance(res, ItemRecord):
                all_candidates.append(res)

        # 4. Merge records sharing the same canonical URL (e.g. combining web snippet with direct download URL)
        deduped, _ = DeduplicationEngine.deduplicate(all_candidates)
        return deduped

    async def _discover_web_items(self, search_terms: str, page: int) -> List[WebSearchResult]:
        """Discovers web items (URL, title, snippet) matching search terms across multiple search engines and dorks."""
        dork_cyberlockers = f'"{search_terms}" (site:mediafire.com OR site:mega.nz OR site:rapidgator.net OR site:1fichier.com OR site:pixeldrain.com)'
        dork_cloud_fast = f'"{search_terms}" (site:gofile.io OR site:krakenfiles.com OR site:drive.google.com OR site:dropbox.com OR site:catbox.moe)'
        dork_opendir = f'"{search_terms}" ("index of/" OR "parent directory")'

        tasks = [
            # Direct search engine queries
            self._search_wikipedia(search_terms),
            self._search_bing(search_terms),
            self._search_brave(search_terms),
            self._search_duckduckgo(search_terms),
            self._search_searxng(search_terms, page),
            self._search_yahoo(search_terms),
            # Targeted cyberlocker & open directory dork queries
            self._search_bing(dork_cyberlockers),
            self._search_bing(dork_cloud_fast),
            self._search_bing(dork_opendir),
            self._search_yahoo(dork_cyberlockers),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        seen_urls: Set[str] = set()
        clean_results: List[WebSearchResult] = []

        for res in results:
            if not isinstance(res, list):
                continue
            for item in res:
                if not isinstance(item, WebSearchResult) or not item.url.startswith("http"):
                    continue
                parsed = urlparse(item.url)
                domain = parsed.netloc.lower()
                if any(skip in domain for skip in ("duckduckgo.com", "google.com", "bing.com", "yandex.com", "yahoo.com", "qwant.com", "msn.com")):
                    continue
                norm_url = item.url.split("#")[0].rstrip("/")
                if norm_url not in seen_urls:
                    seen_urls.add(norm_url)
                    clean_results.append(item)

        return clean_results

    async def _search_wikipedia(self, search_terms: str) -> List[WebSearchResult]:
        """Queries Wikipedia OpenSearch API for relevant encyclopedia articles and portals."""
        discovered: List[WebSearchResult] = []
        try:
            url = "https://en.wikipedia.org/w/api.php"
            params = {
                "action": "opensearch",
                "search": search_terms,
                "limit": 10,
                "namespace": 0,
                "format": "json",
            }
            headers = {"User-Agent": "OmniSearch/2.0 (OpenWeb Discovery Bot)"}
            resp = await self.http_client.get(url, params=params, headers=headers, timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                if len(data) >= 4:
                    for t, d, u in zip(data[1], data[2], data[3]):
                        if u.startswith("http"):
                            discovered.append(WebSearchResult(url=u, title=t, snippet=d))
        except Exception as exc:
            logger.debug("Wikipedia search error: %s", exc)
        return discovered

    async def _search_bing(self, search_terms: str) -> List[WebSearchResult]:
        """Queries Bing search, parses titles, snippets, and decodes base64 redirection links."""
        discovered: List[WebSearchResult] = []
        try:
            url = f"https://www.bing.com/search?q={quote_plus(search_terms)}"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            resp = await self.http_client.get(url, headers=headers, timeout=6.0)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                for item in soup.select("li.b_algo"):
                    a = item.select_one("h2 a")
                    if not a:
                        continue
                    title = a.get_text().strip()
                    href = a.get("href", "")
                    if "/ck/a?" in href and "&u=" in href:
                        u_part = href.split("&u=")[1].split("&")[0]
                        if u_part.startswith("a1"):
                            raw_b64 = u_part[2:]
                            raw_b64 += "=" * (-len(raw_b64) % 4)
                            try:
                                href = base64.b64decode(raw_b64).decode("utf-8", errors="ignore")
                            except Exception:
                                pass
                    p = item.select_one("p, div.b_caption p")
                    snippet = p.get_text().strip() if p else ""
                    if href.startswith("http"):
                        discovered.append(WebSearchResult(url=href, title=title, snippet=snippet))
        except Exception as exc:
            logger.debug("Bing search error: %s", exc)
        return discovered

    async def _search_brave(self, search_terms: str) -> List[WebSearchResult]:
        """Queries Brave search HTML and extracts titles, URLs, and snippets."""
        discovered: List[WebSearchResult] = []
        try:
            url = f"https://search.brave.com/search?q={quote_plus(search_terms)}"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            resp = await self.http_client.get(url, headers=headers, timeout=6.0)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                for res in soup.select("div[data-type='web'], div.snippet, div.search-result"):
                    a = res.select_one("a[href^='http']")
                    if not a:
                        continue
                    title = a.get_text().strip()
                    href = a.get("href", "")
                    snip = res.select_one("div.snippet-description, p")
                    snippet = snip.get_text().strip() if snip else ""
                    if href.startswith("http"):
                        discovered.append(WebSearchResult(url=href, title=title, snippet=snippet))
        except Exception as exc:
            logger.debug("Brave search error: %s", exc)
        return discovered

    async def _search_duckduckgo(self, search_terms: str) -> List[WebSearchResult]:
        """Queries DuckDuckGo HTML endpoint with SafeSearch OFF (kp=-2)."""
        discovered: List[WebSearchResult] = []
        try:
            url = "https://html.duckduckgo.com/html/"
            client_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": "https://html.duckduckgo.com/",
            }
            resp = await self.http_client.post(url, data={"q": search_terms, "kp": "-2"}, headers=client_headers, timeout=6.0)

            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                for r in soup.select("div.result"):
                    a = r.select_one("a.result__a")
                    if not a:
                        continue
                    title = a.get_text().strip()
                    href = a.get("href", "")
                    if "uddg=" in href:
                        qs = parse_qs(urlparse(href).query)
                        href = unquote(qs.get("uddg", [None])[0])
                    snip = r.select_one(".result__snippet")
                    snippet = snip.get_text().strip() if snip else ""
                    if href.startswith("http") and "duckduckgo.com" not in href:
                        discovered.append(WebSearchResult(url=href, title=title, snippet=snippet))
        except Exception as exc:
            logger.debug("DuckDuckGo HTML search failed: %s", exc)

        return discovered

    async def _search_searxng(self, search_terms: str, page: int) -> List[WebSearchResult]:
        """Queries public SearXNG meta-search engines with safesearch=0 (disabled)."""
        discovered: List[WebSearchResult] = []
        for instance in self.SEARXNG_INSTANCES:
            try:
                url = f"{instance}/search"
                params = {
                    "q": search_terms,
                    "format": "json",
                    "pageno": page,
                    "safesearch": 0,
                    "categories": "general,files",
                }
                resp = await self.http_client.get(url, params=params, timeout=5.0)
                if resp.status_code == 200:
                    data = resp.json()
                    for item in data.get("results", []):
                        item_url = item.get("url")
                        title = item.get("title", "")
                        content = item.get("content", "")
                        if item_url and item_url.startswith("http"):
                            discovered.append(WebSearchResult(url=item_url, title=title, snippet=content))
                    if discovered:
                        break
            except Exception as exc:
                logger.debug("SearXNG instance %s error: %s", instance, exc)
                continue

        return discovered

    async def _search_yahoo(self, search_terms: str) -> List[WebSearchResult]:
        """Queries Yahoo search and decodes redirect URLs."""
        discovered: List[WebSearchResult] = []
        try:
            url = f"https://search.yahoo.com/search?p={quote_plus(search_terms)}"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            resp = await self.http_client.get(url, headers=headers, timeout=6.0)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                for a in soup.select('div.compText a, h3 a, a[href*="r.search.yahoo.com"]'):
                    href = a.get("href", "")
                    title = a.get_text().strip()
                    if "RU=" in href:
                        ru = href.split("RU=")[1].split("/RK=")[0]
                        decoded = unquote(ru)
                        if decoded.startswith("http"):
                            discovered.append(WebSearchResult(url=decoded, title=title, snippet=""))
                    elif href.startswith("http") and "yahoo.com" not in href:
                        discovered.append(WebSearchResult(url=href, title=title, snippet=""))
        except Exception as exc:
            logger.debug("Yahoo search error: %s", exc)
        return discovered

    async def _extract_from_page_url(self, page_url: str) -> List[ItemRecord]:
        """Fetches an arbitrary webpage and extracts structured ItemRecords."""
        try:
            resp = await self.http_client.get(page_url, timeout=8.0)
            if resp.status_code == 200:
                content_type = resp.headers.get("Content-Type", "")
                if "text/html" not in content_type and "application/xhtml" not in content_type:
                    # Direct binary file response!
                    ext = detect_file_extension(page_url)
                    filename = page_url.rstrip("/").split("/")[-1]
                    item_type = infer_item_type(ext)
                    platform, platform_id, canonical = resolve_platform_and_id(page_url)
                    return [
                        ItemRecord(
                            id=f"direct:{canonical}",
                            canonical_url=canonical,
                            download_url=canonical,
                            platform=platform,
                            platform_id=platform_id,
                            title=filename or "Direct File Download",
                            description=f"Direct downloadable {ext or 'file'} from {platform}",
                            item_type=item_type,
                            file_name=filename,
                            file_extension=ext,
                            tags=["direct-download", ext] if ext else ["direct-download"],
                            metadata_sources=[MetadataSource.DIRECT_LINK],
                            raw_metadata={"direct_url": canonical, "content_type": content_type},
                        )
                    ]

                final_url = str(resp.url)
                records = PageExtractor.extract_from_html(resp.text, final_url)
                if records:
                    return records

                soup = BeautifulSoup(resp.text, "html.parser")
                title_tag = soup.find("title") or soup.find("h1")
                title = title_tag.get_text().strip() if title_tag else ""
                desc_tag = soup.find("meta", attrs={"name": "description"})
                desc = desc_tag.get("content", "").strip() if desc_tag else ""
                platform, platform_id, canonical_url = resolve_platform_and_id(final_url)
                ext = detect_file_extension(final_url) or detect_file_extension(title)

                record = ItemRecord(
                    id=f"web:{canonical_url}",
                    canonical_url=canonical_url,
                    download_url=None,
                    platform=platform,
                    platform_id=platform_id,
                    title=title or f"Page on {platform}",
                    description=desc or f"Discovered web page on {platform}",
                    item_type=infer_item_type(ext) if ext else ItemType.WEB_PAGE,
                    file_name=title if ext else None,
                    file_extension=ext,
                    metadata_sources=[MetadataSource.HTML_META],
                    raw_metadata={"crawled_url": final_url},
                )
                return [record]
        except Exception as exc:
            logger.debug("Failed to extract from open web page %s: %s", page_url, exc)

        return []
