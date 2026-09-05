"""
Tests for security hardening (SSRF protection), cache resilience & LRU eviction,
query parser directives, and resource lifecycle management.
"""

import pytest
from omnisearch.core.cache import SearchCache
from omnisearch.core.http_client import is_safe_public_url, validate_safe_url, ResilientHttpClient
from omnisearch.core.query_parser import QueryParser
from omnisearch.core.matcher import MatchEngine
from omnisearch.models.item import ItemRecord, ItemType, MatchMode
from omnisearch.models.query import SearchOptions, SearchQuery
from omnisearch.api.routes import close_api_resources


def test_cache_collision_avoidance_on_filters():
    q1 = QueryParser.parse("linux", SearchOptions(item_types=[ItemType.SOFTWARE]))
    q2 = QueryParser.parse("linux", SearchOptions(item_types=[ItemType.DOCUMENT]))
    key1 = SearchCache.generate_query_key(q1)
    key2 = SearchCache.generate_query_key(q2)
    assert key1 != key2, "Cache keys must differ when item_types differ"

    q3 = QueryParser.parse("dataset", SearchOptions(file_extensions=["zip"]))
    q4 = QueryParser.parse("dataset", SearchOptions(file_extensions=["tar.gz"]))
    key3 = SearchCache.generate_query_key(q3)
    key4 = SearchCache.generate_query_key(q4)
    assert key3 != key4, "Cache keys must differ when file_extensions differ"


def test_cache_lru_eviction():
    cache = SearchCache(default_ttl_seconds=300, max_entries=3)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)

    # Access 'a', making 'b' the least recently used
    assert cache.get("a") == 1

    # Insert 'd', which should evict 'b'
    cache.set("d", 4)

    assert cache.get("b") is None
    assert cache.get("a") == 1
    assert cache.get("c") == 3
    assert cache.get("d") == 4
    assert len(cache) == 3


def test_ssrf_protection_blocks_internal_and_reserved_ips():
    # Loopback
    assert is_safe_public_url("http://127.0.0.1:8000/secret") is False
    assert is_safe_public_url("http://localhost:5000/") is False
    assert is_safe_public_url("http://[::1]/") is False

    # Cloud metadata
    assert is_safe_public_url("http://169.254.169.254/latest/meta-data/") is False

    # Private subnets
    assert is_safe_public_url("http://10.0.0.1/admin") is False
    assert is_safe_public_url("http://192.168.1.1/gateway") is False
    assert is_safe_public_url("http://172.16.0.10:9000/") is False

    # Non-HTTP schemes
    assert is_safe_public_url("ftp://example.com/file.zip") is False
    assert is_safe_public_url("file:///etc/passwd") is False
    assert is_safe_public_url("gopher://example.com") is False

    # Public domain
    assert is_safe_public_url("https://archive.org/details/test") is True

    # validate_safe_url raises ValueError
    with pytest.raises(ValueError, match="SSRF Protection"):
        validate_safe_url("http://127.0.0.1:8000/api")


def test_query_parser_inline_directives():
    query = QueryParser.parse("kernel ext:iso type:software")
    assert "kernel" in query.extracted_terms
    assert query.options.file_extensions == ["iso"]
    assert query.options.item_types == [ItemType.SOFTWARE]


def test_item_record_searchable_map_includes_ext_type_site():
    item = ItemRecord(
        id="test:1",
        canonical_url="https://example.com/file.zip",
        platform="MediaFire",
        title="Linux Kernel Source",
        item_type=ItemType.ARCHIVE,
        file_extension="zip",
    )
    s_map = item.get_searchable_text_map()
    assert s_map["ext"] == "zip"
    assert s_map["type"] == "archive"
    # site field now includes BOTH the platform label and the canonical domain,
    # so `site:mediafire.com` and `site:MediaFire` both match.
    assert "MediaFire" in s_map["site"]
    assert "example.com" in s_map["site"]


def test_match_engine_with_directives():
    item = ItemRecord(
        id="test:2",
        canonical_url="https://mediafire.com/file/debian.iso",
        platform="MediaFire",
        title="Debian GNU Linux Minimal",
        item_type=ItemType.SOFTWARE,
        file_extension="iso",
    )
    # Query with ext and site directives
    query = QueryParser.parse("Debian ext:iso site:MediaFire")
    is_match, prov = MatchEngine.evaluate(item, query)
    assert is_match is True
    assert prov is not None

    # Mismatch extension should not match
    query_mismatch = QueryParser.parse("Debian ext:zip")
    is_match_bad, _ = MatchEngine.evaluate(item, query_mismatch)
    assert is_match_bad is False



@pytest.mark.asyncio
async def test_api_resource_teardown():
    # Verify that close_api_resources can execute cleanly without unhandled exceptions
    try:
        await close_api_resources()
    except Exception as exc:
        pytest.fail(f"close_api_resources raised unexpected exception: {exc}")
