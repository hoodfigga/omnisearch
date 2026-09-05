"""
GitHub Source Adapter: repositories + release binaries via the public REST API.

Discovers:
- Repositories matching the query (clone/source access, WEB_PAGE/SOFTWARE records)
- Latest release assets (direct-download binaries) for the top matches
"""

from __future__ import annotations
import asyncio
import logging
import os
from typing import List, Optional
from omnisearch.models.query import SearchQuery
from omnisearch.models.video import VideoMetadataSource, VideoRecord, ItemRecord, ItemType
from omnisearch.adapters.base import BaseSourceAdapter
from omnisearch.extractors.file_hosts import detect_file_extension, infer_item_type, format_bytes
from omnisearch.extractors.json_ld import parse_iso_datetime

logger = logging.getLogger(__name__)


class GitHubAdapter(BaseSourceAdapter):
    """Discovers GitHub repositories and their release binaries (direct downloads)."""

    def __init__(self, api_token: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        self.api_token = api_token or os.getenv("GITHUB_TOKEN")

    @property
    def source_id(self) -> str:
        return "github"

    @property
    def source_name(self) -> str:
        return "GitHub (repos & release binaries)"

    def _headers(self) -> dict:
        headers = {"Accept": "application/vnd.github+json"}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        return headers

    async def search(self, query: SearchQuery, page: int = 1) -> List[VideoRecord]:
        search_terms = " ".join(query.extracted_phrases + query.extracted_terms) or query.raw_query
        if not search_terms.strip():
            return []

        records: List[VideoRecord] = []
        try:
            # 1. Repository search
            params = {
                "q": search_terms,
                "sort": "stars",
                "order": "desc",
                "per_page": 15,
                "page": page,
            }
            resp = await self.http_client.get(
                "https://api.github.com/search/repositories",
                params=params,
                headers=self._headers(),
                timeout=8.0,
            )
            if resp.status_code == 200:
                for item in resp.json().get("items", []):
                    repo_full = item.get("full_name", "")
                    if not repo_full:
                        continue
                    tags = ["github", "source-code"]
                    for lang in [item.get("language")] if item.get("language") else []:
                        tags.append(lang.lower())
                    records.append(
                        VideoRecord(
                            id=f"github:{repo_full}",
                            canonical_url=item.get("html_url", f"https://github.com/{repo_full}"),
                            download_url=item.get("clone_url"),
                            platform="GitHub",
                            platform_id=repo_full,
                            title=repo_full,
                            description=(item.get("description") or "")[:500],
                            item_type=ItemType.SOFTWARE,
                            file_extension=None,
                            uploader_name=item.get("owner", {}).get("login"),
                            uploader_url=item.get("owner", {}).get("html_url"),
                            publication_date=parse_iso_datetime(item.get("created_at")),
                            view_count=item.get("stargazers_count"),
                            like_count=item.get("stargazers_count"),
                            tags=tags,
                            embed_url=None,
                            metadata_sources=[VideoMetadataSource.OFFICIAL_API],
                            raw_metadata={"github_repo": {k: item.get(k) for k in ("full_name", "stargazers_count", "language", "license", "topics")}},
                        )
                    )

                # 2. Release binaries for the top repos (concurrent, capped)
                top_repos = [r.platform_id for r in records if r.platform_id][:3]
                release_tasks = [self._fetch_latest_release(rp) for rp in top_repos]
                release_results = await asyncio.gather(*release_tasks, return_exceptions=True)
                for res in release_results:
                    if isinstance(res, list):
                        records.extend(res)
            else:
                logger.debug("GitHub search returned %d", resp.status_code)
        except Exception as exc:
            logger.debug("GitHub search error: %s", exc)

        return records

    async def _fetch_latest_release(self, repo_full: str) -> List[VideoRecord]:
        """Fetches the latest release of a repo and returns one record per downloadable asset."""
        out: List[VideoRecord] = []
        try:
            resp = await self.http_client.get(
                f"https://api.github.com/repos/{repo_full}/releases/latest",
                headers=self._headers(),
                timeout=6.0,
            )
            if resp.status_code != 200:
                return out
            rel = resp.json()
            assets = rel.get("assets", [])
            pub_date = parse_iso_datetime(rel.get("published_at"))
            for asset in assets[:8]:
                name = asset.get("name", "")
                url = asset.get("browser_download_url")
                if not name or not url:
                    continue
                size = asset.get("size")
                ext = detect_file_extension(name)
                out.append(
                    VideoRecord(
                        id=f"github_release:{repo_full}/{name}",
                        canonical_url=rel.get("html_url") or f"https://github.com/{repo_full}/releases",
                        download_url=url,
                        platform="GitHub",
                        platform_id=f"{repo_full}@{rel.get('tag_name', 'latest')}",
                        title=f"{repo_full} — {name}",
                        description=f"Release {rel.get('tag_name', '')} asset: {name} ({format_bytes(size) if size else 'unknown size'})",
                        item_type=infer_item_type(ext),
                        file_name=name,
                        file_extension=ext,
                        file_size_bytes=size,
                        file_size_human=format_bytes(size) if size else None,
                        uploader_name=rel.get("author", {}).get("login") if isinstance(rel.get("author"), dict) else None,
                        publication_date=pub_date,
                        tags=["github", "release", "direct-download", ext] if ext else ["github", "release", "direct-download"],
                        metadata_sources=[VideoMetadataSource.OFFICIAL_API, VideoMetadataSource.DIRECT_LINK],
                        raw_metadata={"repo": repo_full, "tag": rel.get("tag_name"), "asset": name, "downloads": asset.get("download_count")},
                    )
                )
        except Exception as exc:
            logger.debug("GitHub release fetch failed for %s: %s", repo_full, exc)
        return out
