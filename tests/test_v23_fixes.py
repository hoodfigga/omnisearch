"""
Regression tests for v2.3 fixes:
- meta: field directive expansion (previously dead — never matched)
- site: host-boundary anchoring (mediafire.com.evil.io spoof rejected)
- File-host domain resolution anchoring (debunkr.com is NOT Bunkr)
- Naive datetime filters (--after 2025-01-01 no longer raises TypeError)
- Deduplicated engine search terms (no phrase word repetition)
- Cache key includes timeout_seconds
- Deadline-truncated responses are not cached
- ConnectTimeout/WriteTimeout are retried (TransportError base)
- Open-web engine-domain skip keeps drive.google.com results
"""

import asyncio
from datetime import datetime, timezone

import pytest

from omnisearch.adapters.open_web import OpenWebDiscoveryAdapter
from omnisearch.core.cache import SearchCache
from omnisearch.core.http_client import ResilientHttpClient
from omnisearch.core.matcher import MatchEngine
from omnisearch.core.orchestrator import VideoDiscoveryOrchestrator, cls_filter_candidate
from omnisearch.core.query_parser import QueryParser
from omnisearch.extractors.file_hosts import resolve_file_host_key
from omnisearch.models.item import ItemRecord, ItemType
from omnisearch.models.query import SearchOptions


# ---------------------------------------------------------------- meta: directive

def test_meta_directive_matches_metadata_fields():
    item = ItemRecord(
        id="t:1",
        canonical_url="https://example.com/x.zip",
        platform="Web",
        title="Cool Tool",
        description="a neural network trainer",
        tags=["ai"],
        item_type=ItemType.SOFTWARE,
    )
    matched, prov = MatchEngine.evaluate(item, QueryParser.parse("cool meta:neural"))
    assert matched is True
    assert "description" in prov.matched_fields


def test_meta_directive_excludes_title():
    item = ItemRecord(
        id="t:2",
        canonical_url="https://example.com/x.zip",
        platform="Web",
        title="Cool Tool",
        description="nothing relevant here",
        item_type=ItemType.SOFTWARE,
    )
    # "cool" appears only in the title — meta: must not see it
    matched, _ = MatchEngine.evaluate(item, QueryParser.parse("meta:cool"))
    assert matched is False


def test_meta_directive_phrase():
    item = ItemRecord(
        id="t:3",
        canonical_url="https://example.com/x.zip",
        platform="Web",
        title="Tool",
        description="trains a neural network overnight",
        item_type=ItemType.SOFTWARE,
    )
    matched, prov = MatchEngine.evaluate(item, QueryParser.parse('meta:"neural network"'))
    assert matched is True
    assert prov.match_type.value == "EXACT_PHRASE"


# ---------------------------------------------------------------- site: anchoring

def _spoofed_item():
    return ItemRecord(
        id="t:evil",
        canonical_url="https://mediafire.com.evil.io/f/x",
        platform="evil.io",
        title="Cool Tool",
        item_type=ItemType.FILE,
    )


def _real_mediafire_item():
    return ItemRecord(
        id="t:mf",
        canonical_url="https://www.mediafire.com/file/abc123/x.zip",
        platform="MediaFire",
        title="x package",
        file_extension="zip",
    )


def test_site_directive_rejects_host_spoofing():
    matched, _ = MatchEngine.evaluate(_spoofed_item(), QueryParser.parse("site:mediafire.com"))
    assert matched is False


def test_site_directive_accepts_subdomain_of_target():
    sub = ItemRecord(
        id="t:sub",
        canonical_url="https://download.mediafire.com/xyz",
        platform="MediaFire",
        title="mirror file",
        item_type=ItemType.FILE,
    )
    matched, _ = MatchEngine.evaluate(sub, QueryParser.parse("site:mediafire.com"))
    assert matched is True


def test_site_directive_still_matches_real_domain_and_platform():
    q = QueryParser.parse("site:mediafire.com")
    assert MatchEngine.evaluate(_real_mediafire_item(), q)[0] is True
    assert MatchEngine.evaluate(_real_mediafire_item(), QueryParser.parse("site:MediaFire"))[0] is True


# ---------------------------------------------------------------- file-host anchoring

@pytest.mark.parametrize(
    "url,expected_key",
    [
        ("https://debunkr.com/f/abc", None),
        ("https://mymediafire.com/file/abc", None),
        ("https://mediafire.com.evil.io/x", None),
        ("https://evil-bunkr.example.com/f/x", None),
        ("https://www.mediafire.com/file/xyz/pkg.zip/file", "mediafire"),
        ("https://download1584.mediafire.com/xyz/file", "mediafire"),
        ("https://mega.nz/file/AbCdEf", "mega"),
        ("https://bunkrr.su/v/abc", "bunkr"),
        ("https://mega.bunkr.is/a/album1", "bunkr"),
        ("https://cyberdrop.me/f/abc", "cyberfile"),
        ("https://litterbox.catbox.moe/abc123.zip", "catbox"),
        ("https://files.catbox.moe/abc123.zip", "catbox"),
        ("https://drive.google.com/file/d/1AbC/view", "gdrive"),
    ],
)
def test_file_host_resolution_host_boundaries(url, expected_key):
    assert resolve_file_host_key(url) == expected_key


def test_file_host_extractor_not_triggered_for_spoofed_host():
    from omnisearch.extractors.file_hosts import FileHostExtractor

    assert FileHostExtractor.is_file_host_url("https://debunkr.com/f/abc") is False
    assert FileHostExtractor.is_file_host_url("https://mediafire.com.evil.io/x") is False
    assert FileHostExtractor.is_file_host_url("https://www.mediafire.com/file/x/y") is True


# ---------------------------------------------------------------- naive datetime filters

def test_naive_date_filters_do_not_crash():
    rec = ItemRecord(
        id="t:5",
        canonical_url="https://example.com/x.mp4",
        platform="Test",
        title="Test Video",
        item_type=ItemType.VIDEO,
        publication_date=datetime.fromisoformat("2025-06-01T00:00:00+00:00"),
    )
    # CLI --after 2025-01-01 produces a naive datetime; must not raise
    assert cls_filter_candidate(rec, SearchOptions(published_after=datetime(2025, 1, 1))) is True
    assert cls_filter_candidate(rec, SearchOptions(published_after=datetime(2026, 1, 1))) is False
    assert cls_filter_candidate(rec, SearchOptions(published_before=datetime(2025, 1, 1))) is False
    assert cls_filter_candidate(rec, SearchOptions(published_before=datetime(2026, 1, 1))) is True


# ---------------------------------------------------------------- engine search terms

def test_search_terms_string_deduplicates_phrase_words():
    q = QueryParser.parse('"blender 4.0" installer')
    assert q.search_terms_string() == "blender 4.0 installer"


def test_search_terms_string_plain_terms_unchanged():
    q = QueryParser.parse("blender 4.0")
    assert q.search_terms_string() == "blender 4.0"


def test_search_terms_string_falls_back_to_raw_query():
    q = QueryParser.parse("python NOT golang")
    assert q.search_terms_string() == "python"


# ---------------------------------------------------------------- cache

def test_cache_key_includes_timeout():
    q1 = QueryParser.parse("linux", SearchOptions(timeout_seconds=5))
    q2 = QueryParser.parse("linux", SearchOptions(timeout_seconds=120))
    assert SearchCache.generate_query_key(q1) != SearchCache.generate_query_key(q2)


def test_deadline_truncated_response_not_cached():
    from omnisearch.adapters.base import BaseSourceAdapter

    class _SlowAdapter(BaseSourceAdapter):
        @property
        def source_id(self):
            return "slow"

        @property
        def source_name(self):
            return "Slow Source"

        async def search(self, query, page=1):
            await asyncio.sleep(2.0)
            return [
                ItemRecord(
                    id="slow:1",
                    canonical_url="https://slow.com/1",
                    platform="Slow",
                    title="blender guide",
                )
            ]

    orch = VideoDiscoveryOrchestrator(adapters=[_SlowAdapter()])
    opts = SearchOptions(sources=["slow"], allow_cache=True, timeout_seconds=1.0)
    resp = asyncio.run(orch.search("blender", options=opts))
    assert resp.metrics.stopping_reason == "deadline_reached"
    assert len(orch.cache) == 0, "deadline-truncated response must not be cached"


# ---------------------------------------------------------------- retry coverage

@pytest.mark.asyncio
async def test_connect_timeout_is_retried():
    """ConnectTimeout (a TimeoutException, not in the old tuple) must retry."""
    import httpx

    client = ResilientHttpClient(max_retries=2)
    attempts = {"n": 0}

    class _FakeAsyncClient:
        is_closed = False

        async def request(self, method, url, **kwargs):
            attempts["n"] += 1
            if attempts["n"] <= 2:
                raise httpx.ConnectTimeout("connect timed out")
            resp = httpx.Response(200, request=httpx.Request("GET", url))
            return resp

        async def aclose(self):
            pass

    async def fake_get_client():
        return _FakeAsyncClient()

    client.get_client = fake_get_client
    client.rate_limiter.acquire = _noop_acquire
    resp = await client.get("https://example.com/x")
    assert resp.status_code == 200
    assert attempts["n"] == 3  # initial + 2 retries


async def _noop_acquire():
    return None


# ---------------------------------------------------------------- open-web domain skip

def test_engine_domain_skip_keeps_google_drive():
    a = OpenWebDiscoveryAdapter()
    assert a._is_engine_domain("https://www.google.com/search?q=x") is True
    assert a._is_engine_domain("https://search.yahoo.com/search?p=x") is True
    # Dork targets must survive the filter
    assert a._is_engine_domain("https://drive.google.com/file/d/x") is False
    assert a._is_engine_domain("https://docs.google.com/document/d/x") is False
    assert a._is_engine_domain("https://example.com/file.zip") is False
