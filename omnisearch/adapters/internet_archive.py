"""
Internet Archive Video Adapter using Archive.org Advanced Search API.
"""

from __future__ import annotations
import json
import logging
import re
from datetime import datetime
from typing import List
from omnisearch.models.query import SearchQuery
from omnisearch.models.video import VideoMetadataSource, VideoRecord
from omnisearch.adapters.base import BaseSourceAdapter
from omnisearch.extractors.json_ld import parse_iso_datetime

logger = logging.getLogger(__name__)


class InternetArchiveAdapter(BaseSourceAdapter):
    """Discovers videos on Internet Archive (archive.org) collections."""

    @property
    def source_id(self) -> str:
        return "ia"

    @property
    def source_name(self) -> str:
        return "Internet Archive"

    async def search(self, query: SearchQuery, page: int = 1) -> List[VideoRecord]:
        search_terms = " ".join(query.extracted_phrases + query.extracted_terms) or query.raw_query
        if not search_terms.strip():
            return []

        records: List[VideoRecord] = []
        try:
            url = "https://archive.org/advancedsearch.php"
            ia_query = f"({search_terms}) AND mediatype:(movies)"
            params = {
                "q": ia_query,
                "fl[]": ["identifier", "title", "description", "creator", "date", "runtime", "subject", "downloads", "publicdate"],
                "rows": min(50, query.options.max_results),
                "page": page,
                "output": "json",
            }
            resp = await self.http_client.get(url, params=params)
            if resp.status_code == 200:
                data = None
                try:
                    data = json.loads(resp.text, strict=False)
                except Exception:
                    try:
                        # Clean unescaped control chars
                        cleaned_text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", resp.text)
                        data = json.loads(cleaned_text, strict=False)
                    except Exception:
                        pass

                if not data or not isinstance(data, dict):
                    return []

                docs = data.get("response", {}).get("docs", [])
                for doc in docs:
                    identifier = doc.get("identifier")
                    if not identifier:
                        continue

                    title = doc.get("title") or identifier
                    description = doc.get("description") or ""
                    creator = doc.get("creator")
                    if isinstance(creator, list):
                        creator = ", ".join(creator)

                    date_str = doc.get("publicdate") or doc.get("date")
                    published = parse_iso_datetime(date_str)

                    # Parse runtime (could be MM:SS, HH:MM:SS, or seconds)
                    duration_sec = None
                    runtime = doc.get("runtime")
                    if runtime:
                        if isinstance(runtime, (int, float)):
                            duration_sec = int(runtime)
                        elif isinstance(runtime, str) and ":" in runtime:
                            parts = runtime.split(":")
                            try:
                                if len(parts) == 2:
                                    duration_sec = int(parts[0]) * 60 + int(parts[1])
                                elif len(parts) == 3:
                                    duration_sec = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
                            except Exception:
                                pass

                    subjects = doc.get("subject", [])
                    if isinstance(subjects, str):
                        tags = [s.strip() for s in subjects.split(";") if s.strip()]
                    elif isinstance(subjects, list):
                        tags = [str(s).strip() for s in subjects if str(s).strip()]
                    else:
                        tags = []

                    downloads = doc.get("downloads")
                    view_count = int(downloads) if downloads and str(downloads).isdigit() else None

                    thumb_url = f"https://archive.org/services/img/{identifier}"
                    canonical_url = f"https://archive.org/details/{identifier}"
                    embed_url = f"https://archive.org/embed/{identifier}"

                    record = VideoRecord(
                        id=f"ia:{identifier}",
                        canonical_url=canonical_url,
                        platform="Internet Archive",
                        platform_id=identifier,
                        title=title,
                        description=description,
                        uploader_name=creator,
                        publication_date=published,
                        duration_seconds=duration_sec,
                        tags=tags,
                        thumbnail_url=thumb_url,
                        embed_url=embed_url,
                        view_count=view_count,
                        metadata_sources=[VideoMetadataSource.OFFICIAL_API],
                        raw_metadata={"ia_doc": doc},
                    )
                    records.append(record)
        except Exception as exc:
            logger.warning("Internet Archive search error: %s", exc)

        return records
