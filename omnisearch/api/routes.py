"""
FastAPI REST API routes for universal file, document, download, and web discovery.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from omnisearch.models.query import SearchOptions, SearchResponse, MatchMode
from omnisearch.models.video import ItemRecord, ItemType, VideoRecord
from omnisearch.core.orchestrator import VideoDiscoveryOrchestrator
from omnisearch.extractors.page_extractor import PageExtractor
from omnisearch.core.http_client import ResilientHttpClient, validate_safe_url

router = APIRouter(prefix="/api")

# Singleton orchestrator instance for API
orchestrator = VideoDiscoveryOrchestrator()
http_client = ResilientHttpClient()


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Search query keywords, phrases, filenames, or Boolean expressions")
    match_mode: MatchMode = Field(default=MatchMode.EXACT_MATCH, description="Match mode")
    title_only: bool = Field(default=False, description="Restrict matching to title/filename only")
    sources: Optional[List[str]] = Field(default=None, description="List of source IDs to query")
    item_types: Optional[List[ItemType]] = Field(default=None, description="Filter by item types (FILE, ARCHIVE, DOCUMENT, SOFTWARE, AUDIO, VIDEO, etc.)")
    file_extensions: Optional[List[str]] = Field(default=None, description="Filter by file extensions (e.g. ['zip', 'iso', 'pdf'])")
    max_results: int = Field(default=100, ge=1, le=500, description="Max results")
    max_pages_per_source: int = Field(default=3, ge=1, le=15, description="Max pages per source")
    min_score: float = Field(default=0.1, ge=0.0, description="Relevance cutoff score")
    allow_cache: bool = Field(default=True, description="Enable caching")


class ExtractRequest(BaseModel):
    url: str = Field(..., description="Target webpage URL to inspect and extract metadata/download links from")


@router.post("/search", response_model=SearchResponse)
async def search_items(req: SearchRequest):
    """Executes a multi-source universal discovery and direct download matching query."""
    opts = SearchOptions(
        match_mode=req.match_mode,
        title_only=req.title_only,
        sources=req.sources,
        item_types=req.item_types,
        file_extensions=req.file_extensions,
        max_results=req.max_results,
        max_pages_per_source=req.max_pages_per_source,
        min_score=req.min_score,
        allow_cache=req.allow_cache,
    )
    try:
        response = await orchestrator.search(req.query, options=opts)
        return response
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/extract", response_model=List[ItemRecord])
async def extract_url(req: ExtractRequest):
    """Directly extracts structured file/download metadata from any web URL with SSRF protection."""
    try:
        validate_safe_url(req.url)
        resp = await http_client.get(req.url, timeout=12.0, safe_only=True)
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=f"Target URL returned status {resp.status_code}")
        records = PageExtractor.extract_from_html(resp.text, str(resp.url))
        return records
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Extraction failed: {exc}")


@router.get("/sources")
async def get_sources():
    """Returns list of registered discovery adapters and their statuses."""
    return orchestrator.get_registered_sources()


@router.get("/health")
async def health_check():
    return {"status": "ok", "service": "omnisearch-discovery-engine"}


async def close_api_resources():
    """Cleanly releases all orchestrator adapters and HTTP client connections."""
    await orchestrator.close()
    await http_client.close()

