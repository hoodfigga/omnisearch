"""
Package Registry Adapter: npm and crates.io (Rust) via public registry APIs.

Each result carries the package page plus a direct-download archive link
(.tgz for npm, .crate for crates.io).
"""

from __future__ import annotations
import logging
from typing import List
from urllib.parse import quote_plus
from omnisearch.models.query import SearchQuery
from omnisearch.models.video import VideoMetadataSource, VideoRecord, ItemType
from omnisearch.adapters.base import BaseSourceAdapter
from omnisearch.extractors.file_hosts import format_bytes

logger = logging.getLogger(__name__)


class RegistryAdapter(BaseSourceAdapter):
    """Discovers software packages on npm and crates.io with direct tarball downloads."""

    @property
    def source_id(self) -> str:
        return "registries"

    @property
    def source_name(self) -> str:
        return "Package Registries (npm & crates.io)"

    async def search(self, query: SearchQuery, page: int = 1) -> List[VideoRecord]:
        search_terms = " ".join(query.extracted_phrases + query.extracted_terms) or query.raw_query
        if not search_terms.strip():
            return []

        records: List[VideoRecord] = []
        try:
            npm_records = await self._search_npm(search_terms)
            records.extend(npm_records)
        except Exception as exc:
            logger.debug("npm search error: %s", exc)

        try:
            crate_records = await self._search_crates(search_terms)
            records.extend(crate_records)
        except Exception as exc:
            logger.debug("crates.io search error: %s", exc)

        return records

    async def _search_npm(self, search_terms: str) -> List[VideoRecord]:
        records: List[VideoRecord] = []
        params = {"text": search_terms, "size": 15}
        resp = await self.http_client.get(
            "https://registry.npmjs.org/-/v1/search", params=params, timeout=8.0
        )
        if resp.status_code != 200:
            return records

        for obj in resp.json().get("objects", []):
            pkg = obj.get("package", {})
            name = pkg.get("name", "")
            if not name:
                continue
            version = pkg.get("version", "")
            links = pkg.get("links", {})

            # Direct tarball download
            tarball = f"https://registry.npmjs.org/{name}/-/{name.split('/')[-1]}-{version}.tgz"

            records.append(
                VideoRecord(
                    id=f"npm:{name}",
                    canonical_url=links.get("npm") or f"https://www.npmjs.com/package/{name}",
                    download_url=tarball,
                    platform="npm",
                    platform_id=name,
                    title=f"{name} ({version})",
                    description=(pkg.get("description") or "")[:300],
                    item_type=ItemType.SOFTWARE,
                    file_name=f"{name}-{version}.tgz",
                    file_extension="tgz",
                    uploader_name=pkg.get("publisher", {}).get("username") if isinstance(pkg.get("publisher"), dict) else pkg.get("author", {}).get("name"),
                    publication_date=None,
                    tags=["npm", "package", "javascript", "direct-download"],
                    metadata_sources=[VideoMetadataSource.OFFICIAL_API, VideoMetadataSource.DIRECT_LINK],
                    raw_metadata={"npm_package": {k: pkg.get(k) for k in ("name", "version", "keywords")}},
                )
            )
        return records

    async def _search_crates(self, search_terms: str) -> List[VideoRecord]:
        records: List[VideoRecord] = []
        params = {"q": search_terms, "per_page": 15}
        # crates.io requires a descriptive User-Agent
        headers = {"User-Agent": "OmniSearch/2.1 (universal discovery engine)"}
        resp = await self.http_client.get(
            "https://crates.io/api/v1/crates", params=params, headers=headers, timeout=8.0
        )
        if resp.status_code != 200:
            return records

        for c in resp.json().get("crates", []):
            name = c.get("name", "")
            if not name:
                continue
            version = c.get("max_stable_version") or c.get("newest_version") or ""
            dl_url = f"https://crates.io/api/v1/crates/{name}/{version}/download"

            records.append(
                VideoRecord(
                    id=f"crate:{name}",
                    canonical_url=f"https://crates.io/crates/{name}",
                    download_url=dl_url if version else None,
                    platform="crates.io",
                    platform_id=name,
                    title=f"{name} ({version})" if version else name,
                    description=(c.get("description") or "")[:300],
                    item_type=ItemType.SOFTWARE,
                    file_name=f"{name}-{version}.crate" if version else None,
                    file_extension="crate" if version else None,
                    view_count=c.get("downloads"),
                    like_count=c.get("recent_downloads"),
                    tags=["crate", "rust", "package", "direct-download"] if version else ["crate", "rust", "package"],
                    metadata_sources=[VideoMetadataSource.OFFICIAL_API] + ([VideoMetadataSource.DIRECT_LINK] if version else []),
                    raw_metadata={"crate": {k: c.get(k) for k in ("name", "max_stable_version", "downloads", "updated_at")}},
                )
            )
        return records
