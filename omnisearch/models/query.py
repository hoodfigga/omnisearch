"""
Search query models, AST nodes for Boolean expressions, and search options.
"""

from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field
from omnisearch.models.video import MatchMode, VideoRecord


class NodeType(str, Enum):
    TERM = "TERM"
    PHRASE = "PHRASE"
    AND = "AND"
    OR = "OR"
    NOT = "NOT"
    FIELD = "FIELD"


class ASTNode(BaseModel):
    type: NodeType


class TermNode(ASTNode):
    type: NodeType = NodeType.TERM
    value: str
    is_stemmed: bool = False


class PhraseNode(ASTNode):
    type: NodeType = NodeType.PHRASE
    phrase: str
    words: List[str] = Field(default_factory=list)


class AndNode(ASTNode):
    type: NodeType = NodeType.AND
    left: ASTNode
    right: ASTNode


class OrNode(ASTNode):
    type: NodeType = NodeType.OR
    left: ASTNode
    right: ASTNode


class NotNode(ASTNode):
    type: NodeType = NodeType.NOT
    child: ASTNode


class FieldNode(ASTNode):
    type: NodeType = NodeType.FIELD
    field_name: str  # e.g., 'title', 'meta', 'description', 'tags', 'uploader'
    child: ASTNode


from omnisearch.models.video import MatchMode, VideoRecord, ItemRecord, ItemType


# Re-resolve forward references for recursive AST models
AndNode.model_rebuild()
OrNode.model_rebuild()
NotNode.model_rebuild()
FieldNode.model_rebuild()


class SearchOptions(BaseModel):
    match_mode: MatchMode = Field(
        default=MatchMode.EXACT_MATCH,
        description="Matching mode: EXACT_MATCH, FLEXIBLE_MATCH, TITLE_ONLY, TITLE_AND_METADATA, SEMANTIC_EXPANSION"
    )
    title_only: bool = Field(
        default=False,
        description="Explicit flag to restrict matching to title only"
    )
    sources: Optional[List[str]] = Field(
        default=None,
        description="List of source adapters to query (e.g. ['open_web', 'file_hosts', 'youtube', 'vimeo', 'dailymotion', 'ia', 'peertube', 'mrss', 'web'])"
    )
    item_types: Optional[List[ItemType]] = Field(
        default=None,
        description="Optional filter by item types (FILE, ARCHIVE, DOCUMENT, SOFTWARE, AUDIO, VIDEO, etc.)"
    )
    file_extensions: Optional[List[str]] = Field(
        default=None,
        description="Optional list of file extensions to filter by (e.g. ['zip', 'iso', 'pdf'])"
    )
    max_results: int = Field(
        default=30,
        ge=1,
        le=500,
        description="Target maximum number of matched & ranked results"
    )
    max_pages_per_source: int = Field(
        default=3,
        ge=1,
        le=20,
        description="Maximum pagination depth per source"
    )
    timeout_seconds: float = Field(
        default=35.0,
        ge=1.0,
        le=120.0,
        description="Overall timeout for multi-source search"
    )
    min_score: float = Field(
        default=0.1,
        ge=0.0,
        description="Minimum relevance score threshold for returning a match"
    )
    min_duration_seconds: Optional[int] = None
    max_duration_seconds: Optional[int] = None
    published_after: Optional[datetime] = None
    published_before: Optional[datetime] = None
    language: Optional[str] = None
    allow_cache: bool = True
    cache_ttl_seconds: int = 3600


class SearchQuery(BaseModel):
    raw_query: str
    options: SearchOptions = Field(default_factory=SearchOptions)
    parsed_ast: Optional[ASTNode] = None
    extracted_terms: List[str] = Field(default_factory=list)
    extracted_phrases: List[str] = Field(default_factory=list)


class SearchMetrics(BaseModel):
    query: str
    duration_ms: float
    sources_contacted: List[str] = Field(default_factory=list)
    candidates_retrieved: int = 0
    matches_found: int = 0
    duplicates_filtered: int = 0
    errors: Dict[str, str] = Field(default_factory=dict)
    stopping_reason: str = "completed"


class SearchResponse(BaseModel):
    query: str
    match_mode: MatchMode
    total_matches: int
    results: List[ItemRecord]
    metrics: SearchMetrics

