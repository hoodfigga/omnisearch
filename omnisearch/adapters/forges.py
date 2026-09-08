"""
Git Forge Adapter: GitLab and Codeberg public repository search.

Mirrors the GitHub adapter pattern: repository records with clone URLs as
direct downloads, ranked by relevance/last-activity.
"""

from __future__ import annotations
import asyncio
import logging
from typing import List
from omnisearch.models.query import SearchQuery
from omnisearch.models.video import VideoMetadataSource, VideoRecord, ItemType
from omnisearch.adapters.base import BaseSourceAdapter
from omnisearch.extractors.json_ld import parse_iso_datetime

logger = logging.getLogger(__name__)


class GitLabAdapter(BaseSourceAdapter):
    """Discovers GitLab repositories (gitlab.com public projects)."""

    @property
    def source_id(self) -> str:
        return "gitlab"

    @property
    def source_name(self) -> str:
        return "GitLab (repos & source code)"

    async def search(self, query: SearchQuery, page: int = 1) -> List[VideoRecord]:
        search_terms = query.search_terms_string()
        if not search_terms.strip():
            return []

        records: List[VideoRecord] = []
        try:
            params = {
                "search": search_terms,
                "per_page": 15,
                "page": page,
                "order_by": "last_activity_at",
                "simple": "true",
            }
            resp = await self.http_client.get(
                "https://gitlab.com/api/v4/projects", params=params, timeout=8.0
            )
            if resp.status_code != 200:
                return records

            for item in resp.json():
                path = item.get("path_with_namespace", "")
                if not path:
                    continue
                tags = ["gitlab", "source-code"]
                if item.get("topics"):
                    tags.extend(str(t).lower() for t in item["topics"][:5])

                records.append(
                    VideoRecord(
                        id=f"gitlab:{path}",
                        canonical_url=item.get("web_url", f"https://gitlab.com/{path}"),
                        download_url=item.get("http_url_to_repo"),
                        platform="GitLab",
                        platform_id=path,
                        title=path,
                        description=(item.get("description") or "")[:500],
                        item_type=ItemType.SOFTWARE,
                        uploader_name=item.get("namespace", {}).get("path"),
                        publication_date=parse_iso_datetime(item.get("created_at")),
                        view_count=item.get("star_count"),
                        like_count=item.get("star_count"),
                        tags=tags,
                        metadata_sources=[VideoMetadataSource.OFFICIAL_API],
                        raw_metadata={
                            "gitlab_repo": {
                                k: item.get(k)
                                for k in ("path_with_namespace", "star_count", "forks_count", "language", "last_activity_at")
                            }
                        },
                    )
                )
        except Exception as exc:
            logger.debug("GitLab search error: %s", exc)

        return records


class CodebergAdapter(BaseSourceAdapter):
    """Discovers Codeberg (Gitea) repositories."""

    @property
    def source_id(self) -> str:
        return "codeberg"

    @property
    def source_name(self) -> str:
        return "Codeberg (repos & source code)"

    async def search(self, query: SearchQuery, page: int = 1) -> List[VideoRecord]:
        search_terms = query.search_terms_string()
        if not search_terms.strip():
            return []

        records: List[VideoRecord] = []
        try:
            params = {"q": search_terms, "limit": 15, "page": page}
            # Codeberg 403s browser-mimicking UAs; use a plain identifying one.
            resp = await self.http_client.get(
                "https://codeberg.org/api/v1/repos/search",
                params=params,
                headers={"User-Agent": "OmniSearch/2.3 (universal discovery engine)"},
                timeout=8.0,
            )
            if resp.status_code != 200:
                return records

            data = resp.json()
            for item in data.get("data", []):
                full_name = item.get("full_name", "")
                if not full_name:
                    continue
                tags = ["codeberg", "source-code"]
                if item.get("language"):
                    tags.append(str(item["language"]).lower())

                records.append(
                    VideoRecord(
                        id=f"codeberg:{full_name}",
                        canonical_url=item.get("html_url", f"https://codeberg.org/{full_name}"),
                        download_url=item.get("clone_url"),
                        platform="Codeberg",
                        platform_id=full_name,
                        title=full_name,
                        description=(item.get("description") or "")[:500],
                        item_type=ItemType.SOFTWARE,
                        uploader_name=item.get("owner", {}).get("username"),
                        publication_date=parse_iso_datetime(item.get("created_at")),
                        view_count=item.get("stars_count"),
                        tags=tags,
                        metadata_sources=[VideoMetadataSource.OFFICIAL_API],
                        raw_metadata={
                            "codeberg_repo": {
                                k: item.get(k)
                                for k in ("full_name", "stars_count", "forks_count", "language", "updated_at")
                            }
                        },
                    )
                )
        except Exception as exc:
            logger.debug("Codeberg search error: %s", exc)

        return records
