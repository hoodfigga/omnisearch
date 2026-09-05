"""
Tests for Source Adapters and Open Web Discovery.
"""

import pytest
from omnisearch.adapters.open_web import OpenWebDiscoveryAdapter
from omnisearch.adapters.mrss import MRSSAdapter
from omnisearch.models.query import SearchOptions, SearchQuery
from omnisearch.core.query_parser import QueryParser


def test_open_web_adapter_properties():
    adapter = OpenWebDiscoveryAdapter()
    assert adapter.source_id == "open_web"
    assert "Open Web" in adapter.source_name
    assert adapter.is_enabled is True


@pytest.mark.asyncio
async def test_open_web_discovery_integration():
    adapter = OpenWebDiscoveryAdapter(max_crawl_pages=3)
    query = QueryParser.parse('"James Webb Space Telescope"')
    # Test that open web adapter can search without throwing unhandled exceptions
    try:
        records = await adapter.search(query, page=1)
        assert isinstance(records, list)
    except Exception as exc:
        pytest.fail(f"Open web discovery raised unexpected exception: {exc}")
