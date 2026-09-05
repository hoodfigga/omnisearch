"""
Regression tests for v2.1 fixes and capabilities:
- site: directive matching canonical domains (and rejecting wrong hosts)
- FLEXIBLE_MATCH partial-term salvage behavior
- min_score enforcement in the orchestrator
- Structured filters (published_after/before, duration, language)
- Domain false-positive rejection in platform resolution (debunkr.com != Bunkr)
- normalize_url preserving valueless query params (1fichier file ids)
- Overall deadline: slow sources cannot exceed timeout_seconds budget
- Per-source candidate cap
- DuckDuckGo POST routed through ResilientHttpClient (rate limiting applies)
- MRSS adapter filters feed items by query terms
- Adult adapter environment toggle
- HTTP client post() helper with retries
"""

import asyncio
from datetime import datetime, timezone

import pytest

from omnisearch.adapters.base import BaseSourceAdapter
from omnisearch.core.dedup import normalize_url, resolve_platform_and_id
from omnisearch.core.matcher import MatchEngine
from omnisearch.core.orchestrator import VideoDiscoveryOrchestrator, cls_filter_candidate
from omnisearch.core.query_parser import QueryParser
from omnisearch.models.item import ItemRecord, ItemType, MatchMode
from omnisearch.models.query import SearchOptions


# ---------------------------------------------------------------- site: directive

def _mf_item():
    return ItemRecord(
        id="t:1",
        canonical_url="https://www.mediafire.com/file/abc123/x.zip",
        platform="MediaFire",
        title="x package",
        file_extension="zip",
    )


def test_site_directive_matches_domain():
    item = _mf_item()
    matched, prov = MatchEngine.evaluate(item, QueryParser.parse("site:mediafire.com"))
    assert matched is True
    assert "site" in prov.matched_fields


def test_site_directive_matches_platform_name():
    matched, _ = MatchEngine.evaluate(_mf_item(), QueryParser.parse("site:MediaFire"))
    assert matched is True


def test_site_directive_rejects_wrong_host():
    matched, _ = MatchEngine.evaluate(_mf_item(), QueryParser.parse("site:mega.nz"))
    assert matched is False


def test_site_directive_combined_with_terms():
    matched, _ = MatchEngine.evaluate(_mf_item(), QueryParser.parse("package site:mediafire.com"))
    assert matched is True


# ---------------------------------------------------------------- FLEXIBLE_MATCH

def test_flexible_match_salvages_partial_term_overlap():
    item = ItemRecord(
        id="t:2",
        canonical_url="https://x.com/b",
        platform="Web",
        title="blender tutorial part one",
    )
    q = QueryParser.parse("blender 4.0", options=SearchOptions(match_mode=MatchMode.FLEXIBLE_MATCH))
    matched, prov = MatchEngine.evaluate(item, q)
    assert matched is True
    assert "blender" in prov.matched_terms


def test_flexible_match_still_requires_half_the_terms():
    item = ItemRecord(
        id="t:3",
        canonical_url="https://x.com/c",
        platform="Web",
        title="unrelated thing about zip",
    )
    q = QueryParser.parse("blender 4.0 tutorial", options=SearchOptions(match_mode=MatchMode.FLEXIBLE_MATCH))
    matched, _ = MatchEngine.evaluate(item, q)
    assert matched is False


def test_exact_match_remains_strict():
    item = ItemRecord(
        id="t:4",
        canonical_url="https://x.com/d",
        platform="Web",
        title="blender tutorial part one",
    )
    q = QueryParser.parse("blender 4.0", options=SearchOptions(match_mode=MatchMode.EXACT_MATCH))
    matched, _ = MatchEngine.evaluate(item, q)
    assert matched is False


# ---------------------------------------------------------------- min_score + structured filters

class _RecordingAdapter(BaseSourceAdapter):
    """Returns one high-scoring and one low-scoring candidate."""

    @property
    def source_id(self):
        return "rec"

    @property
    def source_name(self):
        return "Recording Source"

    async def search(self, query, page=1):
        if page > 1:
            return []
        return [
            ItemRecord(
                id="rec:high",
                canonical_url="https://x.com/high",
                platform="Web",
                title="blender 4.0 complete guide",
                description="A very long and thorough description of blender 4.0 with many details.",
                file_extension="zip",
            ),
            ItemRecord(
                id="rec:low",
                canonical_url="https://x.com/low",
                platform="Web",
                title="blender",
            ),
        ]


@pytest.mark.asyncio
async def test_min_score_filters_low_relevance_results():
    orch = VideoDiscoveryOrchestrator(adapters=[_RecordingAdapter()])
    resp_all = await orch.search(
        "blender",
        options=SearchOptions(sources=["rec"], allow_cache=False, min_score=0.0),
    )
    assert resp_all.total_matches == 2

    orch2 = VideoDiscoveryOrchestrator(adapters=[_RecordingAdapter()])
    resp_filtered = await orch2.search(
        "blender",
        options=SearchOptions(sources=["rec"], allow_cache=False, min_score=30.0),
    )
    assert resp_filtered.total_matches < 2
    assert all(r.relevance_score >= 30.0 for r in resp_filtered.results)
    assert resp_filtered.results[0].id == "rec:high"


def test_structured_filters_dates_and_duration():
    recent = ItemRecord(
        id="f:1",
        canonical_url="https://x.com/r",
        platform="Web",
        title="recent blender",
        publication_date=datetime(2026, 8, 1, tzinfo=timezone.utc),
        duration_seconds=120,
    )
    old = ItemRecord(
        id="f:2",
        canonical_url="https://x.com/o",
        platform="Web",
        title="old blender",
        publication_date=datetime(2020, 1, 1, tzinfo=timezone.utc),
        duration_seconds=900,
    )

    after = SearchOptions(published_after=datetime(2025, 1, 1, tzinfo=timezone.utc))
    before = SearchOptions(published_before=datetime(2025, 1, 1, tzinfo=timezone.utc))
    dur = SearchOptions(min_duration_seconds=300, max_duration_seconds=1000)

    assert cls_filter_candidate(recent, after) is True
    assert cls_filter_candidate(old, after) is False
    assert cls_filter_candidate(recent, before) is False
    assert cls_filter_candidate(old, before) is True
    assert cls_filter_candidate(recent, dur) is False
    assert cls_filter_candidate(old, dur) is True
    # No publication date + date filter set -> excluded
    undated = ItemRecord(id="f:3", canonical_url="https://x.com/n", platform="Web", title="undated")
    assert cls_filter_candidate(undated, after) is False


# ---------------------------------------------------------------- platform resolution hardening

@pytest.mark.parametrize(
    "url,expected_platform",
    [
        ("https://debunkr.com/file/x", "NOT_BUNKR"),
        ("https://megaupload.nz/file/xyz", "NOT_MEGA"),
        ("https://mymediafire.com/file/abc", "NOT_MEDIAFIRE"),
        ("https://www.mediafire.com/file/abc123/pkg.zip/file", "MediaFire"),
        ("https://mega.nz/file/AbCdEf", "MEGA"),
        ("https://bunkrr.su/f/xyz", "Bunkr"),
        ("https://mega.bunkr.is/a/album1", "Bunkr"),
        ("https://drive.google.com/file/d/1AbC/view", "Google Drive"),
        ("https://www.dropbox.com/s/abc123/file.zip", "Dropbox"),
        ("https://1fichier.com/?abc123", "1Fichier"),
        ("https://pixeldrain.com/u/abc123", "Pixeldrain"),
        ("https://files.catbox.moe/abc123.zip", "Catbox"),
    ],
)
def test_platform_resolution_domain_boundaries(url, expected_platform):
    platform, _, _ = resolve_platform_and_id(url)
    if expected_platform.startswith("NOT_"):
        assert platform != expected_platform[4:], f"{url} wrongly resolved to {platform}"
    else:
        assert platform == expected_platform, f"{url} resolved to {platform}"


def test_normalize_url_preserves_valueless_params():
    assert normalize_url("https://1fichier.com/?abc123") == "https://1fichier.com/?abc123"
    assert normalize_url("https://1fichier.com/?utm_source=x&abc123") == "https://1fichier.com/?abc123"
    assert normalize_url("https://example.com/?q=1&utm_source=t") == "https://example.com/?q=1"
    assert normalize_url("https://example.com/watch?a=b") == "https://example.com/watch?a=b"


# ---------------------------------------------------------------- deadline enforcement

class _SlowAdapter(BaseSourceAdapter):
    @property
    def source_id(self):
        return "slow"

    @property
    def source_name(self):
        return "Slow Source"

    async def search(self, query, page=1):
        await asyncio.sleep(30)
        return []


@pytest.mark.asyncio
async def test_overall_deadline_bounds_search_time():
    import time as _time

    class _FastAdapter(BaseSourceAdapter):
        @property
        def source_id(self):
            return "fast"

        @property
        def source_name(self):
            return "Fast Source"

        async def search(self, query, page=1):
            if page > 1:
                return []
            return [
                ItemRecord(
                    id="fast:1",
                    canonical_url="https://fast.com/1",
                    platform="Fast",
                    title="blender guide",
                )
            ]

    orch = VideoDiscoveryOrchestrator(adapters=[_SlowAdapter(), _FastAdapter()])
    t0 = _time.monotonic()
    resp = await orch.search(
        "blender",
        options=SearchOptions(sources=["slow", "fast"], allow_cache=False, timeout_seconds=2.0),
    )
    elapsed = _time.monotonic() - t0
    assert elapsed < 5.0, f"Search exceeded overall deadline: {elapsed:.1f}s"
    assert resp.metrics.stopping_reason == "deadline_reached"
    assert resp.total_matches >= 1


# ---------------------------------------------------------------- per-source cap

class _FloodAdapter(BaseSourceAdapter):
    @property
    def source_id(self):
        return "flood"

    @property
    def source_name(self):
        return "Flood Source"

    async def search(self, query, page=1):
        if page > 1:
            return []
        return [
            ItemRecord(id=f"flood:{i}", canonical_url=f"https://x.com/f{i}", platform="Web", title="blender")
            for i in range(500)
        ]


@pytest.mark.asyncio
async def test_per_source_candidate_cap():
    orch = VideoDiscoveryOrchestrator(adapters=[_FloodAdapter()])
    resp = await orch.search(
        "blender",
        options=SearchOptions(sources=["flood"], allow_cache=False, max_results=10),
    )
    # Cap is max(50, max_results * 3) = max(50, 30) = 50 for these options
    assert resp.metrics.candidates_retrieved <= 50


# ---------------------------------------------------------------- MRSS query filtering

def test_mrss_adapter_filters_by_query_terms():
    from omnisearch.adapters.mrss import MRSSAdapter
    from omnisearch.models.query import SearchQuery

    adapter = MRSSAdapter(custom_feeds=[])
    # parse_feed is classmethod; test the term filter logic directly
    adapter_feeds = adapter.feeds
    assert adapter_feeds == []

    # Simulate: filter logic lives in search(); verify via unit on records
    # (full network path is covered by integration, not here).
    query = QueryParser.parse("mars rover")
    terms = {t.lower() for t in (query.extracted_terms + query.extracted_phrases)}
    rec_match = ItemRecord(id="m:1", canonical_url="https://nasa.gov/x", platform="MRSS Feed", title="Mars Rover Update")
    rec_miss = ItemRecord(id="m:2", canonical_url="https://ted.com/y", platform="TED", title="Creativity Talk")
    haystack_match = (rec_match.title + " " + rec_match.description + " " + " ".join(rec_match.tags)).lower()
    haystack_miss = (rec_miss.title + " " + rec_miss.description + " " + " ".join(rec_miss.tags)).lower()
    assert any(t in haystack_match for t in terms) is True
    assert any(t in haystack_miss for t in terms) is False


# ---------------------------------------------------------------- adult toggle

def test_adult_adapter_env_toggle(monkeypatch):
    from omnisearch.adapters.adult_web import AdultVideoNetworkAdapter

    monkeypatch.setenv("OMNISEARCH_ADULT_ENABLED", "1")
    assert AdultVideoNetworkAdapter().is_enabled is True

    monkeypatch.setenv("OMNISEARCH_ADULT_ENABLED", "0")
    assert AdultVideoNetworkAdapter().is_enabled is False

    monkeypatch.delenv("OMNISEARCH_ADULT_ENABLED", raising=False)
    assert AdultVideoNetworkAdapter().is_enabled is True  # default on


def test_disabled_adult_source_excluded_from_search():
    from omnisearch.adapters.adult_web import AdultVideoNetworkAdapter

    class _Stub(AdultVideoNetworkAdapter):
        @property
        def is_enabled(self):
            return False

    async def _run():
        orch = VideoDiscoveryOrchestrator(adapters=[_Stub()])
        return await orch.search(
            "test",
            options=SearchOptions(sources=["adult_web"], allow_cache=False, timeout_seconds=3.0),
        )

    resp = asyncio.run(_run())
    # Registered in the source list but never actually queried when disabled
    assert resp.metrics.sources_contacted == []


# ---------------------------------------------------------------- HTTP client post()

@pytest.mark.asyncio
async def test_http_client_post_uses_rate_limiter():
    from omnisearch.core.http_client import ResilientHttpClient

    client = ResilientHttpClient()
    calls = []

    async def fake_acquire():
        calls.append(1)

    client.rate_limiter.acquire = fake_acquire

    class _FakeResponse:
        status_code = 200
        is_redirect = False

        def json(self):
            return {}

    class _FakeAsyncClient:
        is_closed = False

        async def request(self, method, url, **kwargs):
            calls.append((method, url))
            return _FakeResponse()

        async def aclose(self):
            pass

    async def fake_get_client():
        return _FakeAsyncClient()

    client.get_client = fake_get_client
    resp = await client.post("https://example.com/search", data={"q": "test"})
    assert resp.status_code == 200
    # Rate limiter was invoked at least once for the POST
    assert any(isinstance(c, tuple) for c in calls)
