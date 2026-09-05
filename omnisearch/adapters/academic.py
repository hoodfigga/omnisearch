"""
Academic & Scientific Data Adapter: Zenodo (research data/files) and arXiv (papers/PDFs).

Zenodo records expose direct-download file links; arXiv entries link straight to PDFs.
"""

from __future__ import annotations
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
        search_terms = " ".join(query.extracted_phrases + query.extracted_terms) or query.raw_query
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
        search_terms = " ".join(query.extracted_phrases + query.extracted_terms) or query.raw_query
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
