"""
Discovery Orchestrator: Coordinates multi-source retrieval, pagination,
matching, deduplication, ranking, caching, and observability metrics.
"""

from __future__ import annotations
import asyncio
import logging
import time
from datetime import timezone
from typing import Any, Dict, List, Optional, Tuple
from omnisearch.models.query import (
    MatchMode,
    SearchMetrics,
    SearchOptions,
    SearchQuery,
    SearchResponse,
)
from omnisearch.models.video import VideoRecord, ItemRecord
from omnisearch.core.query_parser import QueryParser
from omnisearch.core.matcher import MatchEngine
from omnisearch.core.dedup import DeduplicationEngine
from omnisearch.core.ranker import RelevanceRanker
from omnisearch.core.cache import SearchCache
from omnisearch.adapters.base import BaseSourceAdapter
from omnisearch.adapters.youtube import YouTubeAdapter
from omnisearch.adapters.vimeo import VimeoAdapter
from omnisearch.adapters.dailymotion import DailymotionAdapter
from omnisearch.adapters.internet_archive import InternetArchiveAdapter
from omnisearch.adapters.peertube import PeerTubeAdapter
from omnisearch.adapters.mrss import MRSSAdapter
from omnisearch.adapters.generic_web import GenericWebAdapter
from omnisearch.adapters.open_web import OpenWebDiscoveryAdapter
from omnisearch.adapters.adult_web import AdultVideoNetworkAdapter
from omnisearch.adapters.file_hosts import FileHostingAdapter

logger = logging.getLogger(__name__)


def cls_filter_candidate(record: VideoRecord, opts: SearchOptions) -> bool:
    """Applies structured filters (dates, duration, language) before text matching."""
    if opts.published_after or opts.published_before:
        pub = record.publication_date
        if pub is None:
            return False
        if pub.tzinfo is None:
            pub = pub.replace(tzinfo=timezone.utc)
        if opts.published_after and pub < opts.published_after:
            return False
        if opts.published_before and pub > opts.published_before:
            return False
    if opts.min_duration_seconds is not None:
        if record.duration_seconds is None or record.duration_seconds < opts.min_duration_seconds:
            return False
    if opts.max_duration_seconds is not None:
        if record.duration_seconds is None or record.duration_seconds > opts.max_duration_seconds:
            return False
    if opts.language and record.language and record.language.lower() != opts.language.lower():
        return False
    return True


class VideoDiscoveryOrchestrator:
    """Central search engine orchestrating discovery across multiple video platforms, file hosts, and the open web."""

    def __init__(
        self,
        adapters: Optional[List[BaseSourceAdapter]] = None,
        cache: Optional[SearchCache] = None,
        max_concurrent_sources: int = 12,
    ):
        self.cache = cache or SearchCache()
        self.semaphore = asyncio.Semaphore(max_concurrent_sources)
        self.adapters: Dict[str, BaseSourceAdapter] = {}

        default_adapters = adapters or [
            OpenWebDiscoveryAdapter(),
            FileHostingAdapter(),
            AdultVideoNetworkAdapter(),
            YouTubeAdapter(),
            VimeoAdapter(),
            DailymotionAdapter(),
            InternetArchiveAdapter(),
            PeerTubeAdapter(),
            MRSSAdapter(),
            GenericWebAdapter(),
        ]
        for adapter in default_adapters:
            self.register_adapter(adapter)

    def register_adapter(self, adapter: BaseSourceAdapter):
        self.adapters[adapter.source_id] = adapter

    def get_registered_sources(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": a.source_id,
                "name": a.source_name,
                "enabled": a.is_enabled,
                "rate_limit": a.rate_limit_per_sec,
            }
            for a in self.adapters.values()
        ]

    async def search(
        self,
        query_str: str,
        options: Optional[SearchOptions] = None,
    ) -> SearchResponse:
        """Executes full search, open web discovery, file host crawl, and ranking pipeline."""
        start_time = time.monotonic()
        opts = options or SearchOptions()

        # Parse query string into AST and tokens
        query = QueryParser.parse(query_str, options=opts)

        # Check Cache
        cache_key = self.cache.generate_query_key(query)
        if opts.allow_cache:
            cached_resp = self.cache.get(cache_key)
            if cached_resp:
                logger.info("Serving query %r from cache", query_str)
                return cached_resp

        # Select target adapters
        target_adapter_ids = opts.sources if opts.sources else list(self.adapters.keys())
        unknown_ids = [sid for sid in target_adapter_ids if sid not in self.adapters]
        if unknown_ids:
            logger.warning("Unknown source ids in request (ignored): %s", ", ".join(unknown_ids))
        active_adapters = [self.adapters[sid] for sid in target_adapter_ids if sid in self.adapters and self.adapters[sid].is_enabled]

        sources_contacted: List[str] = []
        all_candidates: List[VideoRecord] = []
        errors: Dict[str, str] = {}

        # Overall deadline: timeout_seconds bounds the ENTIRE multi-source
        # search, not each individual page fetch.
        deadline = start_time + opts.timeout_seconds
        stopping_reason = "completed"

        # Bounded concurrency fetch across all sources
        tasks = [
            self._fetch_source_with_pagination(
                adapter, query, opts.max_pages_per_source, opts.timeout_seconds, deadline
            )
            for adapter in active_adapters
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Per-source result cap: keep the pipeline tractable for sources that
        # return hundreds of records (open directories, album extractors).
        per_source_cap = max(50, opts.max_results * 3)

        for adapter, result in zip(active_adapters, results):
            sources_contacted.append(adapter.source_name)
            if isinstance(result, Exception):
                logger.warning("Source %s failed with exception: %s", adapter.source_name, result)
                errors[adapter.source_name] = str(result)
            elif isinstance(result, tuple):
                records, err = result
                if len(records) > per_source_cap:
                    records = records[:per_source_cap]
                all_candidates.extend(records)
                if err:
                    errors[adapter.source_name] = err

        # Match Evaluation and Provenance Enrichment
        matched_records: List[VideoRecord] = []
        for candidate in all_candidates:
            if not cls_filter_candidate(candidate, opts):
                continue
            is_match, provenance = MatchEngine.evaluate(candidate, query)
            if is_match and provenance:
                candidate.provenance = provenance
                matched_records.append(candidate)

        # Deduplication
        deduped_records, duplicates_count = DeduplicationEngine.deduplicate(matched_records)

        # Multi-factor Ranking
        ranked_records = RelevanceRanker.rank_records(deduped_records, query)

        # Apply minimum relevance score threshold
        if opts.min_score and opts.min_score > 0:
            ranked_records = [r for r in ranked_records if r.relevance_score >= opts.min_score]

        final_results = ranked_records[: opts.max_results] if (opts.max_results and len(ranked_records) > opts.max_results) else ranked_records

        # Duration & Metrics
        duration_ms = (time.monotonic() - start_time) * 1000.0
        if time.monotonic() > deadline:
            stopping_reason = "deadline_reached"
        metrics = SearchMetrics(
            query=query_str,
            duration_ms=round(duration_ms, 2),
            sources_contacted=sources_contacted,
            candidates_retrieved=len(all_candidates),
            matches_found=len(matched_records),
            duplicates_filtered=duplicates_count,
            errors=errors,
            stopping_reason=stopping_reason,
        )

        response = SearchResponse(
            query=query_str,
            match_mode=opts.match_mode,
            total_matches=len(ranked_records),
            results=final_results,
            metrics=metrics,
        )

        # Cache response
        if opts.allow_cache:
            self.cache.set(cache_key, response, ttl_seconds=opts.cache_ttl_seconds)

        return response

    async def _fetch_source_with_pagination(
        self,
        adapter: BaseSourceAdapter,
        query: SearchQuery,
        max_pages: int,
        timeout: float,
        deadline: Optional[float] = None,
    ) -> Tuple[List[VideoRecord], Optional[str]]:
        """Fetches multiple pages for a single source adapter up to max_pages."""
        candidates: List[VideoRecord] = []
        err_msg: Optional[str] = None

        async with self.semaphore:
            for page in range(1, max_pages + 1):
                if deadline is not None and time.monotonic() >= deadline:
                    err_msg = err_msg or f"Skipped page {page}: overall deadline reached"
                    break
                # Remaining time budget for this page
                page_timeout = timeout
                if deadline is not None:
                    page_timeout = max(0.5, min(timeout, deadline - time.monotonic()))
                try:
                    records = await asyncio.wait_for(adapter.search(query, page=page), timeout=page_timeout)
                    if not records:
                        break
                    candidates.extend(records)
                except asyncio.TimeoutError:
                    err_msg = f"Timed out after {page_timeout:.1f}s on page {page}"
                    break
                except Exception as exc:
                    err_msg = str(exc)
                    break

        return candidates, err_msg

    async def close(self):
        """Concurrently closes all adapter network connections."""
        tasks = [adapter.close() for adapter in self.adapters.values()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

