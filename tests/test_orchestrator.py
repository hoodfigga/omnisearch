"""
Tests for VideoDiscoveryOrchestrator, mock adapter isolation, and resilience.
"""

import pytest
from typing import List
from omnisearch.adapters.base import BaseSourceAdapter
from omnisearch.core.orchestrator import VideoDiscoveryOrchestrator
from omnisearch.models.query import SearchOptions, SearchQuery
from omnisearch.models.video import VideoMetadataSource, VideoRecord


class MockSuccessAdapter(BaseSourceAdapter):
    @property
    def source_id(self) -> str:
        return "mock_ok"

    @property
    def source_name(self) -> str:
        return "Mock OK Source"

    async def search(self, query: SearchQuery, page: int = 1) -> List[VideoRecord]:
        if page > 1:
            return []  # Exhaust after 1 page
        return [
            VideoRecord(
                id="mock:1",
                canonical_url="https://mock.com/video/1",
                platform="MockPlatform",
                title="Python Fast Discovery Tutorial",
                description="Learn how to discover videos quickly.",
                metadata_sources=[VideoMetadataSource.OFFICIAL_API],
            )
        ]


class MockFailingAdapter(BaseSourceAdapter):
    @property
    def source_id(self) -> str:
        return "mock_fail"

    @property
    def source_name(self) -> str:
        return "Mock Failing Source"

    async def search(self, query: SearchQuery, page: int = 1) -> List[VideoRecord]:
        raise RuntimeError("Simulated upstream network outage")


@pytest.mark.asyncio
async def test_orchestrator_resilience_with_failing_source():
    # Failing source should NOT prevent successful results from working source
    orchestrator = VideoDiscoveryOrchestrator(
        adapters=[MockSuccessAdapter(), MockFailingAdapter()]
    )

    response = await orchestrator.search("python", options=SearchOptions(sources=["mock_ok", "mock_fail"]))

    assert response.total_matches == 1
    assert response.results[0].title == "Python Fast Discovery Tutorial"
    assert "Mock Failing Source" in response.metrics.errors
    assert "Simulated upstream network outage" in response.metrics.errors["Mock Failing Source"]


@pytest.mark.asyncio
async def test_orchestrator_cache_hit():
    orchestrator = VideoDiscoveryOrchestrator(
        adapters=[MockSuccessAdapter()]
    )

    opts = SearchOptions(allow_cache=True, sources=["mock_ok"])
    resp1 = await orchestrator.search("python", options=opts)
    resp2 = await orchestrator.search("python", options=opts)

    assert resp1.total_matches == 1
    assert resp2.total_matches == 1
    assert resp1.results[0].id == resp2.results[0].id
