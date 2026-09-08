"""
Community & Discussion Adapter: Hacker News (Algolia API) and StackExchange (Stack Overflow et al.).

Both are keyless public JSON APIs surfacing discussions, answers, and links.
"""

from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import List
from urllib.parse import quote_plus
from omnisearch.models.query import SearchQuery
from omnisearch.models.video import VideoMetadataSource, VideoRecord, ItemType
from omnisearch.adapters.base import BaseSourceAdapter
from omnisearch.extractors.json_ld import parse_iso_datetime

logger = logging.getLogger(__name__)


class HackerNewsAdapter(BaseSourceAdapter):
    """Discovers Hacker News stories and discussions via the Algolia search API."""

    @property
    def source_id(self) -> str:
        return "hackernews"

    @property
    def source_name(self) -> str:
        return "Hacker News (tech stories & discussions)"

    async def search(self, query: SearchQuery, page: int = 1) -> List[VideoRecord]:
        search_terms = query.search_terms_string()
        if not search_terms.strip():
            return []

        records: List[VideoRecord] = []
        try:
            # Stories only (not comments) for relevance
            params = {
                "query": search_terms,
                "tags": "(story,ask_hn,show_hn)",
                "hitsPerPage": 15,
                "page": max(0, page - 1),
            }
            resp = await self.http_client.get(
                "https://hn.algolia.com/api/v1/search", params=params, timeout=8.0
            )
            if resp.status_code != 200:
                return records
            for hit in resp.json().get("hits", []):
                object_id = hit.get("objectID")
                if not object_id:
                    continue

                story_url = hit.get("url")  # external link if present
                hn_url = f"https://news.ycombinator.com/item?id={object_id}"
                title = hit.get("title") or hit.get("story_title") or f"HN item {object_id}"

                records.append(
                    VideoRecord(
                        id=f"hn:{object_id}",
                        canonical_url=hn_url,
                        download_url=None,
                        platform="Hacker News",
                        platform_id=str(object_id),
                        title=title,
                        description=f"HN discussion ({hit.get('points', 0)} points, {hit.get('num_comments', 0)} comments)"
                        + (f" — links to {story_url}" if story_url else ""),
                        item_type=ItemType.WEB_PAGE,
                        uploader_name=hit.get("author"),
                        publication_date=parse_iso_datetime(hit.get("created_at")),
                        view_count=hit.get("points"),
                        like_count=hit.get("num_comments"),
                        embed_url=story_url,
                        tags=["discussion", "hackernews", "tech"],
                        metadata_sources=[VideoMetadataSource.OFFICIAL_API],
                        raw_metadata={
                            "hn": {
                                "objectID": object_id,
                                "points": hit.get("points"),
                                "num_comments": hit.get("num_comments"),
                                "url": story_url,
                            }
                        },
                    )
                )
        except Exception as exc:
            logger.debug("Hacker News search error: %s", exc)

        return records


class StackExchangeAdapter(BaseSourceAdapter):
    """Discovers Stack Overflow / StackExchange Q&A via the public API (quota-limited without key)."""

    # Sites worth searching beyond stackoverflow
    SITES = ["stackoverflow", "superuser", "unix", "askubuntu"]

    @property
    def source_id(self) -> str:
        return "stackexchange"

    @property
    def source_name(self) -> str:
        return "StackExchange (Stack Overflow Q&A)"

    async def search(self, query: SearchQuery, page: int = 1) -> List[VideoRecord]:
        search_terms = query.search_terms_string()
        if not search_terms.strip():
            return []

        import asyncio

        tasks = [self._search_site(self.http_client, search_terms, site, page) for site in self.SITES]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        records: List[VideoRecord] = []
        for res in results:
            if isinstance(res, list):
                records.extend(res)
        return records

    @classmethod
    async def _search_site(cls, http_client, search_terms: str, site: str, page: int) -> List[VideoRecord]:
        records: List[VideoRecord] = []
        try:
            params = {
                "q": search_terms,
                "site": site,
                "pagesize": 8,
                "page": page,
                "order": "desc",
                "sort": "relevance",
                "filter": "!nNPvSNVZJS",  # include body snippet
            }
            resp = await http_client.get(
                "https://api.stackexchange.com/2.3/search/advanced", params=params, timeout=8.0
            )
            if resp.status_code != 200:
                return records
            for item in resp.json().get("items", []):
                qid = item.get("question_id")
                if not qid:
                    continue

                owner = item.get("owner", {}) or {}
                tags = [t.lower() for t in item.get("tags", [])[:6]]

                records.append(
                    VideoRecord(
                        id=f"stackex:{site}:{qid}",
                        canonical_url=item.get("link") or f"https://{site}.com/questions/{qid}",
                        download_url=None,
                        platform=f"StackExchange ({site})",
                        platform_id=str(qid),
                        title=item.get("title", "") or f"Question {qid}",
                        description=f"{item.get('answer_count', 0)} answers · {item.get('score', 0)} score · "
                        f"{'answered ✓' if item.get('is_answered') else 'unanswered'}",
                        item_type=ItemType.WEB_PAGE,
                        uploader_name=owner.get("display_name"),
                        uploader_url=owner.get("link"),
                        publication_date=(
                            datetime.fromtimestamp(item["creation_date"], tz=timezone.utc)
                            if item.get("creation_date")
                            else None
                        ),
                        view_count=item.get("view_count"),
                        like_count=item.get("score"),
                        tags=["question", "qa", site] + tags,
                        metadata_sources=[VideoMetadataSource.OFFICIAL_API],
                        raw_metadata={"stackex": {k: item.get(k) for k in ("question_id", "score", "answer_count", "is_answered")}},
                    )
                )
        except Exception as exc:
            logger.debug("StackExchange %s search error: %s", site, exc)
        return records
