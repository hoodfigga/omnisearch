"""
Package Registry Adapter: npm and crates.io (Rust) via public registry APIs.

Each result carries the package page plus a direct-download archive link
(.tgz for npm, .crate for crates.io).
"""

from __future__ import annotations
import asyncio
import logging
from typing import List
from urllib.parse import quote_plus
from omnisearch.models.query import SearchQuery
from omnisearch.models.video import VideoMetadataSource, VideoRecord, ItemType
from omnisearch.adapters.base import BaseSourceAdapter
from omnisearch.extractors.file_hosts import format_bytes
from omnisearch.extractors.json_ld import parse_iso_datetime

logger = logging.getLogger(__name__)


class RegistryAdapter(BaseSourceAdapter):
    """Discovers software packages across npm, crates.io, RubyGems, Packagist, NuGet, AUR, and Docker Hub with direct downloads where available."""

    @property
    def source_id(self) -> str:
        return "registries"

    @property
    def source_name(self) -> str:
        return "Package Registries (npm, crates.io, RubyGems, Packagist, NuGet, AUR, Docker Hub)"

    async def search(self, query: SearchQuery, page: int = 1) -> List[VideoRecord]:
        search_terms = query.search_terms_string()
        if not search_terms.strip():
            return []

        tasks = [
            self._search_npm(search_terms),
            self._search_crates(search_terms),
            self._search_rubygems(search_terms),
            self._search_packagist(search_terms),
            self._search_nuget(search_terms),
            self._search_aur(search_terms),
            self._search_dockerhub(search_terms),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        records: List[VideoRecord] = []
        for res in results:
            if isinstance(res, list):
                records.extend(res)
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

    async def _search_rubygems(self, search_terms: str) -> List[VideoRecord]:
        """RubyGems: gems with direct .gem download links."""
        records: List[VideoRecord] = []
        try:
            resp = await self.http_client.get(
                "https://rubygems.org/api/v1/search.json",
                params={"query": search_terms, "page": 1},
                timeout=8.0,
            )
            if resp.status_code != 200:
                return records
            for gem in resp.json()[:15]:
                name = gem.get("name", "")
                if not name:
                    continue
                gem_uri = gem.get("gem_uri")  # direct .gem tarball
                version = gem.get("version", "")
                records.append(
                    VideoRecord(
                        id=f"rubygem:{name}",
                        canonical_url=gem.get("project_uri") or f"https://rubygems.org/gems/{name}",
                        download_url=gem_uri,
                        platform="RubyGems",
                        platform_id=name,
                        title=f"{name} ({version})" if version else name,
                        description=(gem.get("info") or "")[:300],
                        item_type=ItemType.SOFTWARE,
                        file_name=f"{name}-{version}.gem" if version and gem_uri else None,
                        file_extension="gem" if gem_uri else None,
                        uploader_name=gem.get("authors"),
                        view_count=gem.get("downloads"),
                        tags=["ruby", "gem", "package"] + ([ "direct-download"] if gem_uri else []),
                        metadata_sources=[VideoMetadataSource.OFFICIAL_API] + ([VideoMetadataSource.DIRECT_LINK] if gem_uri else []),
                        raw_metadata={"rubygem": {k: gem.get(k) for k in ("name", "version", "downloads")}},
                    )
                )
        except Exception as exc:
            logger.debug("RubyGems search error: %s", exc)
        return records

    async def _search_packagist(self, search_terms: str) -> List[VideoRecord]:
        """Packagist: PHP composer packages (page links, no direct tarball in search API)."""
        records: List[VideoRecord] = []
        try:
            resp = await self.http_client.get(
                "https://packagist.org/search.json",
                params={"q": search_terms, "per_page": 15},
                timeout=8.0,
            )
            if resp.status_code != 200:
                return records
            for pkg in resp.json().get("results", [])[:15]:
                name = pkg.get("name", "")
                if not name:
                    continue
                records.append(
                    VideoRecord(
                        id=f"packagist:{name}",
                        canonical_url=pkg.get("url") or f"https://packagist.org/packages/{name}",
                        download_url=None,
                        platform="Packagist",
                        platform_id=name,
                        title=name,
                        description=(pkg.get("description") or "")[:300],
                        item_type=ItemType.SOFTWARE,
                        view_count=pkg.get("downloads"),
                        like_count=pkg.get("favers"),
                        tags=["php", "composer", "package"],
                        metadata_sources=[VideoMetadataSource.OFFICIAL_API],
                        raw_metadata={"packagist_package": {k: pkg.get(k) for k in ("name", "downloads", "favers")}},
                    )
                )
        except Exception as exc:
            logger.debug("Packagist search error: %s", exc)
        return records

    async def _search_nuget(self, search_terms: str) -> List[VideoRecord]:
        """NuGet: .NET packages with direct .nupkg download links."""
        records: List[VideoRecord] = []
        try:
            resp = await self.http_client.get(
                "https://azuresearch-usnc.nuget.org/query",
                params={"q": search_terms, "take": 15},
                timeout=8.0,
            )
            if resp.status_code != 200:
                return records
            for pkg in resp.json().get("data", [])[:15]:
                pkg_id = pkg.get("id", "")
                if not pkg_id:
                    continue
                version = pkg.get("version", "")
                # Direct .nupkg download via the flat container
                dl = (
                    f"https://api.nuget.org/v3-flatcontainer/{pkg_id.lower()}/{version}/{pkg_id.lower()}.{version}.nupkg"
                    if version
                    else None
                )
                records.append(
                    VideoRecord(
                        id=f"nuget:{pkg_id}",
                        canonical_url=f"https://www.nuget.org/packages/{pkg_id}/",
                        download_url=dl,
                        platform="NuGet",
                        platform_id=pkg_id,
                        title=f"{pkg.get('title') or pkg_id} ({version})" if version else pkg_id,
                        description=(pkg.get("description") or "")[:300],
                        item_type=ItemType.SOFTWARE,
                        file_name=f"{pkg_id}.{version}.nupkg" if version else None,
                        file_extension="nupkg" if version else None,
                        uploader_name=", ".join(pkg.get("authors", [])[:3]) if isinstance(pkg.get("authors"), list) else pkg.get("authors"),
                        view_count=pkg.get("totalDownloads"),
                        tags=["dotnet", "nuget", "package"] + (["direct-download"] if dl else []),
                        metadata_sources=[VideoMetadataSource.OFFICIAL_API] + ([VideoMetadataSource.DIRECT_LINK] if dl else []),
                        raw_metadata={"nuget_package": {k: pkg.get(k) for k in ("id", "version", "totalDownloads", "verified")}},
                    )
                )
        except Exception as exc:
            logger.debug("NuGet search error: %s", exc)
        return records

    async def _search_aur(self, search_terms: str) -> List[VideoRecord]:
        """AUR: Arch Linux User Repository packages with source snapshots."""
        records: List[VideoRecord] = []
        try:
            resp = await self.http_client.get(
                "https://aur.archlinux.org/rpc/",
                params={"v": 5, "type": "search", "arg": search_terms},
                timeout=8.0,
            )
            if resp.status_code != 200:
                return records
            for pkg in resp.json().get("results", [])[:15]:
                name = pkg.get("Name", "")
                if not name:
                    continue
                snapshot = (
                    f"https://aur.archlinux.org{pkg['URLPath']}" if pkg.get("URLPath") else None
                )
                records.append(
                    VideoRecord(
                        id=f"aur:{name}",
                        canonical_url=f"https://aur.archlinux.org/packages/{name}",
                        download_url=snapshot,
                        platform="AUR",
                        platform_id=name,
                        title=f"{name} {pkg.get('Version', '')}".strip(),
                        description=(pkg.get("Description") or "")[:300],
                        item_type=ItemType.SOFTWARE,
                        file_name=f"{name}.tar.gz" if snapshot else None,
                        file_extension="tar.gz" if snapshot else None,
                        uploader_name=pkg.get("Maintainer"),
                        like_count=pkg.get("NumVotes"),
                        tags=["arch-linux", "aur", "package"] + (["direct-download"] if snapshot else []),
                        metadata_sources=[VideoMetadataSource.OFFICIAL_API] + ([VideoMetadataSource.DIRECT_LINK] if snapshot else []),
                        raw_metadata={"aur_package": {k: pkg.get(k) for k in ("Name", "Version", "NumVotes", "Popularity")}},
                    )
                )
        except Exception as exc:
            logger.debug("AUR search error: %s", exc)
        return records

    async def _search_dockerhub(self, search_terms: str) -> List[VideoRecord]:
        """Docker Hub: container images (page links; pulls require auth for most)."""
        records: List[VideoRecord] = []
        try:
            resp = await self.http_client.get(
                "https://hub.docker.com/v2/search/repositories/",
                params={"query": search_terms, "page_size": 15},
                timeout=8.0,
            )
            if resp.status_code != 200:
                return records
            for repo in resp.json().get("results", [])[:15]:
                name = repo.get("repo_name", "")
                if not name:
                    continue
                full_name = name if "/" in name else f"library/{name}"
                records.append(
                    VideoRecord(
                        id=f"dockerhub:{full_name}",
                        canonical_url=f"https://hub.docker.com/r/{full_name}",
                        download_url=None,
                        platform="Docker Hub",
                        platform_id=full_name,
                        title=name,
                        description=(repo.get("short_description") or "")[:300],
                        item_type=ItemType.SOFTWARE,
                        like_count=repo.get("star_count"),
                        view_count=repo.get("pull_count"),
                        tags=["docker", "container", "image"],
                        metadata_sources=[VideoMetadataSource.OFFICIAL_API],
                        raw_metadata={"dockerhub_repo": {k: repo.get(k) for k in ("repo_name", "star_count", "pull_count", "is_official")}},
                    )
                )
        except Exception as exc:
            logger.debug("Docker Hub search error: %s", exc)
        return records
