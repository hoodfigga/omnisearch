"""
Academic & Scientific Data Adapter: Zenodo, arXiv, EuropePMC, DOAJ, Crossref,
and Semantic Scholar.

Zenodo records expose direct-download file links; arXiv entries link straight
to PDFs; EuropePMC/DOAJ/Crossref/Semantic Scholar surface papers and datasets
across publishers with open-access full text where available.
"""

from __future__ import annotations
import asyncio
import logging
import re
from typing import List, Optional
from urllib.parse import quote_plus
from omnisearch.models.query import SearchQuery
from omnisearch.models.video import VideoMetadataSource, VideoRecord, ItemType
from omnisearch.adapters.base import BaseSourceAdapter
from omnisearch.extractors.file_hosts import detect_file_extension, infer_item_type, format_bytes
from omnisearch.extractors.json_ld import parse_iso_datetime

logger = logging.getLogger(__name__)


class ZenodoAdapter(BaseSourceAdapter):
    """Discovers research data, datasets, and papers on Zenodo with direct file downloads."""

    @property
    def source_id(self) -> str:
        return "zenodo"

    @property
    def source_name(self) -> str:
        return "Zenodo (research data & files)"

    async def search(self, query: SearchQuery, page: int = 1) -> List[VideoRecord]:
        search_terms = query.search_terms_string()
        if not search_terms.strip():
            return []

        records: List[VideoRecord] = []
        try:
            params = {"q": search_terms, "size": 15, "page": page, "sort": "bestmatch"}
            resp = await self.http_client.get(
                "https://zenodo.org/api/records", params=params, timeout=9.0
            )
            if resp.status_code == 200:
                hits = resp.json().get("hits", {}).get("hits", [])
                for hit in hits:
                    rec_id = hit.get("id")
                    if rec_id is None:
                        continue
                    meta = hit.get("metadata", {})
                    title = meta.get("title", "") or f"Zenodo record {rec_id}"
                    desc = (meta.get("description") or "")[:500]
                    # strip html from description
                    desc = re.sub(r"<[^>]+>", " ", desc)
                    files = hit.get("files", [])
                    pub_date = parse_iso_datetime(hit.get("created"))

                    if files:
                        # One record per downloadable file (first 6)
                        for f in files[:6]:
                            key = f.get("key", "file")
                            size = f.get("size")
                            links = f.get("links", {})
                            dl = links.get("self") or links.get("download")
                            ext = detect_file_extension(key)
                            records.append(
                                VideoRecord(
                                    id=f"zenodo:{rec_id}/{key}",
                                    canonical_url=f"https://zenodo.org/records/{rec_id}",
                                    download_url=dl,
                                    platform="Zenodo",
                                    platform_id=str(rec_id),
                                    title=f"{title} — {key}",
                                    description=desc or f"Zenodo research record {rec_id}",
                                    item_type=infer_item_type(ext),
                                    file_name=key,
                                    file_extension=ext,
                                    file_size_bytes=size,
                                    file_size_human=format_bytes(size) if size else None,
                                    publication_date=pub_date,
                                    tags=["zenodo", "research", "direct-download", ext] if ext else ["zenodo", "research", "direct-download"],
                                    metadata_sources=[VideoMetadataSource.OFFICIAL_API, VideoMetadataSource.DIRECT_LINK],
                                    raw_metadata={"zenodo_record": rec_id, "doi": hit.get("doi"), "file": key},
                                )
                            )
                    else:
                        records.append(
                            VideoRecord(
                                id=f"zenodo:{rec_id}",
                                canonical_url=f"https://zenodo.org/records/{rec_id}",
                                download_url=None,
                                platform="Zenodo",
                                platform_id=str(rec_id),
                                title=title,
                                description=desc or f"Zenodo research record {rec_id}",
                                item_type=ItemType.DOCUMENT,
                                publication_date=pub_date,
                                tags=["zenodo", "research"],
                                metadata_sources=[VideoMetadataSource.OFFICIAL_API],
                                raw_metadata={"zenodo_record": rec_id, "doi": hit.get("doi")},
                            )
                        )
        except Exception as exc:
            logger.debug("Zenodo search error: %s", exc)

        return records


class ArxivAdapter(BaseSourceAdapter):
    """Discovers academic papers on arXiv with direct PDF links."""

    @property
    def source_id(self) -> str:
        return "arxiv"

    @property
    def source_name(self) -> str:
        return "arXiv (papers & PDFs)"

    async def search(self, query: SearchQuery, page: int = 1) -> List[VideoRecord]:
        search_terms = query.search_terms_string()
        if not search_terms.strip():
            return []

        records: List[VideoRecord] = []
        try:
            # arXiv Atom API: relevance sorted
            api_query = f"all:{search_terms}"
            url = (
                "http://export.arxiv.org/api/query?"
                f"search_query={quote_plus(api_query)}"
                f"&start={max(0, (page - 1) * 15)}&max_results=15"
                "&sortBy=relevance"
            )
            resp = await self.http_client.get(url, timeout=9.0)
            if resp.status_code == 200:
                records = self._parse_atom(resp.text)
        except Exception as exc:
            logger.debug("arXiv search error: %s", exc)

        return records

    @classmethod
    def _parse_atom(cls, xml_text: str) -> List[VideoRecord]:
        records: List[VideoRecord] = []
        entries = re.findall(r"<entry>(.*?)</entry>", xml_text, re.S)
        for e in entries:
            id_m = re.search(r"<id>(.*?)</id>", e, re.S)
            title_m = re.search(r"<title>(.*?)</title>", e, re.S)
            summary_m = re.search(r"<summary>(.*?)</summary>", e, re.S)
            pub_m = re.search(r"<published>(.*?)</published>", e, re.S)
            author_m = re.findall(r"<name>(.*?)</name>", e, re.S)
            if not id_m or not title_m:
                continue

            entry_url = id_m.group(1).strip()
            pdf_url = entry_url.replace("/abs/", "/pdf/") if "/abs/" in entry_url else None
            title = re.sub(r"\s+", " ", title_m.group(1)).strip()
            summary = re.sub(r"\s+", " ", summary_m.group(1)).strip()[:500] if summary_m else ""

            records.append(
                VideoRecord(
                    id=f"arxiv:{entry_url.split('/abs/')[-1] if '/abs/' in entry_url else entry_url}",
                    canonical_url=entry_url,
                    download_url=pdf_url,
                    platform="arXiv",
                    platform_id=entry_url.split("/abs/")[-1] if "/abs/" in entry_url else entry_url,
                    title=title,
                    description=summary,
                    item_type=ItemType.DOCUMENT,
                    file_extension="pdf" if pdf_url else None,
                    uploader_name=", ".join(author_m[:3]) if author_m else None,
                    publication_date=parse_iso_datetime(pub_m.group(1)) if pub_m else None,
                    tags=["arxiv", "paper", "pdf", "direct-download"] if pdf_url else ["arxiv", "paper"],
                    metadata_sources=[VideoMetadataSource.OFFICIAL_API, VideoMetadataSource.DIRECT_LINK],
                    raw_metadata={"arxiv_url": entry_url},
                )
            )
        return records


class EuropePMCAdapter(BaseSourceAdapter):
    """Discovers biomedical literature via Europe PMC (open-access full text links where available)."""

    @property
    def source_id(self) -> str:
        return "europepmc"

    @property
    def source_name(self) -> str:
        return "Europe PMC (biomedical literature)"

    async def search(self, query: SearchQuery, page: int = 1) -> List[VideoRecord]:
        search_terms = query.search_terms_string()
        if not search_terms.strip():
            return []

        records: List[VideoRecord] = []
        try:
            params = {
                "query": search_terms,
                "format": "json",
                "pageSize": 15,
                "page": page,
            }
            resp = await self.http_client.get(
                "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
                params=params, timeout=9.0,
            )
            if resp.status_code != 200:
                return records
            results = resp.json().get("resultList", {}).get("result", [])
            for item in results:
                pmcid = item.get("id")
                source = item.get("source", "MED")
                if not pmcid:
                    continue
                # Full-text links: PMC open access, or DOI landing
                full_text = None
                if item.get("inPMC") == "Y" or item.get("isOpenAccess") == "Y":
                    if item.get("pmcid"):
                        full_text = f"https://europepmc.org/article/{source}/{item['pmcid']}"
                canonical = (
                    f"https://europepmc.org/article/{source}/{pmcid}"
                    if pmcid
                    else None
                )
                pub_date = None
                if item.get("firstPublicationDate"):
                    pub_date = parse_iso_datetime(item["firstPublicationDate"])

                records.append(
                    VideoRecord(
                        id=f"europepmc:{source}:{pmcid}",
                        canonical_url=canonical or f"https://europepmc.org/search?query={quote_plus(search_terms)}",
                        download_url=full_text,
                        platform="Europe PMC",
                        platform_id=str(pmcid),
                        title=item.get("title", "") or f"Europe PMC {pmcid}",
                        description=(item.get("abstractText") or "")[:500],
                        item_type=ItemType.DOCUMENT,
                        uploader_name=item.get("authorString"),
                        publication_date=pub_date,
                        tags=["paper", "biomedical", "europepmc"] + (["open-access"] if full_text else []),
                        metadata_sources=[VideoMetadataSource.OFFICIAL_API],
                        raw_metadata={"europepmc": {k: item.get(k) for k in ("id", "source", "doi", "pubYear", "citedByCount", "isOpenAccess")}},
                    )
                )
        except Exception as exc:
            logger.debug("EuropePMC search error: %s", exc)

        return records


class DoajAdapter(BaseSourceAdapter):
    """Discovers open-access journal articles via the DOAJ API (full-text links)."""

    @property
    def source_id(self) -> str:
        return "doaj"

    @property
    def source_name(self) -> str:
        return "DOAJ (open-access journals)"

    async def search(self, query: SearchQuery, page: int = 1) -> List[VideoRecord]:
        search_terms = query.search_terms_string()
        if not search_terms.strip():
            return []

        records: List[VideoRecord] = []
        try:
            url = f"https://doaj.org/api/search/articles/{quote_plus(search_terms)}"
            # DOAJ's Cloudflare 403s browser-mimicking UAs; plain UA passes.
            resp = await self.http_client.get(
                url,
                params={"pageSize": 15, "page": page},
                headers={"User-Agent": "OmniSearch/2.3 (universal discovery engine)"},
                timeout=9.0,
            )
            if resp.status_code != 200:
                return records
            results = resp.json().get("results", [])
            for item in results:
                bib = item.get("bibjson", {})
                rec_id = item.get("id")
                if not rec_id:
                    continue

                title = bib.get("title", "") or f"DOAJ article {rec_id}"
                # First full-text link
                full_text = None
                for link in bib.get("link", []):
                    if link.get("type") == "fulltext" and link.get("url"):
                        full_text = link["url"]
                        break

                year = bib.get("year")
                month = bib.get("month")
                pub_date = None
                if year:
                    try:
                        pub_date = parse_iso_datetime(f"{int(year)}-{int(month or 1):02d}-01")
                    except Exception:
                        pub_date = None

                authors = [a.get("name") for a in bib.get("author", []) if a.get("name")]
                journal = bib.get("journal", {}).get("title", "")
                keywords = bib.get("keywords", [])[:8]
                doi = None
                for ident in bib.get("identifier", []):
                    if ident.get("type") == "doi":
                        doi = ident.get("id")
                        break

                records.append(
                    VideoRecord(
                        id=f"doaj:{rec_id}",
                        canonical_url=full_text or f"https://doaj.org/article/{rec_id}",
                        download_url=full_text,
                        platform="DOAJ",
                        platform_id=str(rec_id),
                        title=title,
                        description=(bib.get("abstract") or "")[:500],
                        item_type=ItemType.DOCUMENT,
                        uploader_name=", ".join(authors[:3]) if authors else journal,
                        publication_date=pub_date,
                        tags=["paper", "open-access", "journal"] + [k.lower() for k in keywords if isinstance(k, str)],
                        metadata_sources=[VideoMetadataSource.OFFICIAL_API] + ([VideoMetadataSource.DIRECT_LINK] if full_text else []),
                        raw_metadata={"doaj": {"id": rec_id, "doi": doi, "journal": journal, "year": year}},
                    )
                )
        except Exception as exc:
            logger.debug("DOAJ search error: %s", exc)

        return records


class CrossrefAdapter(BaseSourceAdapter):
    """Discovers scholarly works across all publishers via Crossref (DOI landing pages)."""

    @property
    def source_id(self) -> str:
        return "crossref"

    @property
    def source_name(self) -> str:
        return "Crossref (scholarly works & DOIs)"

    async def search(self, query: SearchQuery, page: int = 1) -> List[VideoRecord]:
        search_terms = query.search_terms_string()
        if not search_terms.strip():
            return []

        records: List[VideoRecord] = []
        try:
            params = {
                "query": search_terms,
                "rows": 15,
                "offset": max(0, (page - 1) * 15),
                "mailto": "omnisearch@example.com",  # polite pool
            }
            resp = await self.http_client.get(
                "https://api.crossref.org/works", params=params, timeout=9.0
            )
            if resp.status_code != 200:
                return records
            items = resp.json().get("message", {}).get("items", [])
            for item in items:
                doi = item.get("DOI")
                if not doi:
                    continue

                titles = item.get("title") or []
                title = titles[0] if titles else f"Crossref {doi}"
                authors = [
                    f"{a.get('given', '')} {a.get('family', '')}".strip()
                    for a in item.get("author", [])[:3]
                    if a.get("family") or a.get("given")
                ]
                container = item.get("container-title") or []
                journal = container[0] if container else ""

                pub_date = None
                issued = item.get("issued", {}).get("date-parts") or []
                if issued and issued[0]:
                    parts = issued[0]
                    try:
                        date_str = f"{parts[0]:04d}"
                        if len(parts) > 1:
                            date_str += f"-{parts[1]:02d}"
                            if len(parts) > 2:
                                date_str += f"-{parts[2]:02d}"
                        if len(date_str) == 4:
                            date_str += "-01-01"
                        elif len(date_str) == 7:
                            date_str += "-01"
                        pub_date = parse_iso_datetime(date_str)
                    except Exception:
                        pub_date = None

                records.append(
                    VideoRecord(
                        id=f"crossref:{doi}",
                        canonical_url=item.get("resource", {}).get("primary", {}).get("URL")
                        or f"https://doi.org/{doi}",
                        download_url=None,
                        platform="Crossref",
                        platform_id=doi,
                        title=title,
                        description=(item.get("abstract") or journal or "")[:500],
                        item_type=ItemType.DOCUMENT,
                        uploader_name=", ".join(authors) if authors else journal,
                        publication_date=pub_date,
                        like_count=item.get("is-referenced-by-count"),
                        tags=["paper", "doi", "scholarly"],
                        metadata_sources=[VideoMetadataSource.OFFICIAL_API],
                        raw_metadata={"crossref": {k: item.get(k) for k in ("DOI", "type", "publisher", "is-referenced-by-count")}},
                    )
                )
        except Exception as exc:
            logger.debug("Crossref search error: %s", exc)

        return records


class SemanticScholarAdapter(BaseSourceAdapter):
    """Discovers papers via Semantic Scholar Graph API (may rate-limit; results degrade gracefully)."""

    @property
    def source_id(self) -> str:
        return "semanticscholar"

    @property
    def source_name(self) -> str:
        return "Semantic Scholar (AI-powered paper search)"

    async def search(self, query: SearchQuery, page: int = 1) -> List[VideoRecord]:
        search_terms = query.search_terms_string()
        if not search_terms.strip():
            return []

        records: List[VideoRecord] = []
        try:
            params = {
                "query": search_terms,
                "limit": 15,
                "offset": max(0, (page - 1) * 15),
                "fields": "title,year,authors,abstract,externalIds,openAccessPdf,citationCount,url",
            }
            resp = await self.http_client.get(
                "https://api.semanticscholar.org/graph/v1/paper/search",
                params=params, timeout=9.0,
            )
            if resp.status_code != 200:
                # 429 rate-limits are expected without an API key
                logger.debug("Semantic Scholar returned %d", resp.status_code)
                return records
            for item in resp.json().get("data", []):
                paper_id = item.get("paperId") or (item.get("externalIds") or {}).get("DOI")
                if not paper_id:
                    continue

                open_pdf = (item.get("openAccessPdf") or {}).get("url")
                authors = [a.get("name") for a in item.get("authors", [])[:3] if a.get("name")]

                records.append(
                    VideoRecord(
                        id=f"semanticscholar:{paper_id}",
                        canonical_url=item.get("url") or f"https://www.semanticscholar.org/paper/{paper_id}",
                        download_url=open_pdf,
                        platform="Semantic Scholar",
                        platform_id=paper_id,
                        title=item.get("title", "") or f"Paper {paper_id}",
                        description=(item.get("abstract") or "")[:500],
                        item_type=ItemType.DOCUMENT,
                        uploader_name=", ".join(authors) if authors else None,
                        publication_date=parse_iso_datetime(f"{item['year']}-01-01") if item.get("year") else None,
                        like_count=item.get("citationCount"),
                        tags=["paper", "ai-research"] + (["open-access", "pdf", "direct-download"] if open_pdf else []),
                        metadata_sources=[VideoMetadataSource.OFFICIAL_API] + ([VideoMetadataSource.DIRECT_LINK] if open_pdf else []),
                        raw_metadata={"semanticscholar": {k: item.get(k) for k in ("paperId", "year", "citationCount")}},
                    )
                )
        except Exception as exc:
            logger.debug("Semantic Scholar search error: %s", exc)

        return records
