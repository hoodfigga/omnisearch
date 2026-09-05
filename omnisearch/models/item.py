"""
Domain models for universal discovery, files, metadata, provenance, and search queries.
"""

from __future__ import annotations
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ItemType(str, Enum):
    FILE = "FILE"
    ARCHIVE = "ARCHIVE"
    DOCUMENT = "DOCUMENT"
    SOFTWARE = "SOFTWARE"
    AUDIO = "AUDIO"
    VIDEO = "VIDEO"
    IMAGE = "IMAGE"
    DATASET = "DATASET"
    WEB_PAGE = "WEB_PAGE"


class MatchType(str, Enum):
    EXACT_PHRASE = "EXACT_PHRASE"
    WORD_BOUNDARY = "WORD_BOUNDARY"
    METADATA_ONLY = "METADATA_ONLY"
    TITLE_AND_METADATA = "TITLE_AND_METADATA"
    STEMMED_OR_EXPANDED = "STEMMED_OR_EXPANDED"
    FLEXIBLE = "FLEXIBLE"


class MatchMode(str, Enum):
    TITLE_ONLY = "TITLE_ONLY"
    TITLE_AND_METADATA = "TITLE_AND_METADATA"
    EXACT_MATCH = "EXACT_MATCH"
    FLEXIBLE_MATCH = "FLEXIBLE_MATCH"
    SEMANTIC_EXPANSION = "SEMANTIC_EXPANSION"


class MatchSpan(BaseModel):
    field: str
    term: str
    start: int
    end: int
    matched_text: str
    is_exact_phrase: bool = False
    is_stemmed: bool = False


class MatchProvenance(BaseModel):
    discovery_source: str
    discovered_at: datetime = Field(default_factory=utc_now)
    matched_terms: List[str] = Field(default_factory=list)
    matched_fields: List[str] = Field(default_factory=list)
    match_type: MatchType = MatchType.WORD_BOUNDARY
    match_spans: List[MatchSpan] = Field(default_factory=list)
    query_variation_used: Optional[str] = None
    fetch_latency_ms: Optional[float] = None
    raw_source_record_id: Optional[str] = None
    all_discovery_sources: List[str] = Field(default_factory=list)

    def model_post_init(self, __context: Any) -> None:
        if self.discovery_source and self.discovery_source not in self.all_discovery_sources:
            self.all_discovery_sources.append(self.discovery_source)


class MetadataSource(str, Enum):
    OFFICIAL_API = "OFFICIAL_API"
    JSON_LD = "JSON_LD"
    OPEN_GRAPH = "OPEN_GRAPH"
    OEMBED = "OEMBED"
    HTML_META = "HTML_META"
    MRSS_FEED = "MRSS_FEED"
    OPEN_DIRECTORY = "OPEN_DIRECTORY"
    FILE_HOST_PAGE = "FILE_HOST_PAGE"
    DIRECT_LINK = "DIRECT_LINK"
    INFERRED = "INFERRED"


# Backwards compatibility alias
VideoMetadataSource = MetadataSource


class ItemRecord(BaseModel):
    id: str = Field(description="Unique internal canonical identifier (hash or platform:id)")
    canonical_url: str = Field(description="Canonical URL of the file landing or download page")
    download_url: Optional[str] = Field(default=None, description="Direct 1-click download link if extractable")
    platform: str = Field(description="Origin platform (e.g. MediaFire, MEGA, Rapidgator, Google Drive, Bunkr, Pixeldrain, GitHub, Open Directory, Web)")
    platform_id: Optional[str] = Field(default=None, description="Platform-native identifier if available")

    title: str = Field(default="", description="Item title or clean filename")
    description: str = Field(default="", description="File description, context, or snippet")
    item_type: ItemType = Field(default=ItemType.FILE, description="Category of item (FILE, ARCHIVE, DOCUMENT, SOFTWARE, AUDIO, VIDEO, etc.)")

    file_name: Optional[str] = Field(default=None, description="Normalized filename (e.g. 'archive.zip')")
    file_extension: Optional[str] = Field(default=None, description="File extension without dot (e.g. 'zip', 'iso', 'pdf')")
    file_size_bytes: Optional[int] = Field(default=None, description="File size in bytes if detected")
    file_size_human: Optional[str] = Field(default=None, description="Human readable size string (e.g. '1.4 GB', '25 MB')")

    uploader_name: Optional[str] = Field(default=None, description="Creator, channel, or uploader name")
    uploader_url: Optional[str] = Field(default=None, description="Creator profile URL")

    publication_date: Optional[datetime] = Field(default=None, description="Publication or upload timestamp")
    duration_seconds: Optional[int] = Field(default=None, description="Duration in seconds for media files")

    tags: List[str] = Field(default_factory=list, description="Tags or keywords associated with the item")
    categories: List[str] = Field(default_factory=list, description="Category or genre labels")
    language: Optional[str] = Field(default=None, description="Language code (e.g. 'en', 'es')")

    thumbnail_url: Optional[str] = Field(default=None, description="Primary preview image URL")
    embed_url: Optional[str] = Field(default=None, description="Stream player or preview URL if permitted")

    view_count: Optional[int] = Field(default=None, description="View or download count if exposed")
    like_count: Optional[int] = Field(default=None, description="Like count if exposed")

    metadata_sources: List[MetadataSource] = Field(default_factory=list, description="List of metadata sources that populated this record")
    raw_metadata: Dict[str, Any] = Field(default_factory=dict, description="Raw structured data preserved for inspection")

    provenance: Optional[MatchProvenance] = Field(default=None, description="Provenance of match and discovery")
    relevance_score: float = Field(default=0.0, description="Relevance score assigned by ranking engine")
    rank: Optional[int] = Field(default=None, description="Final rank position in result set")

    def get_searchable_text_map(self) -> Dict[str, str]:
        """Returns map of field_name -> text content for matching."""
        try:
            domain = urlparse(self.canonical_url or "").netloc.lower()
            if domain.startswith("www."):
                domain = domain[4:]
        except Exception:
            domain = ""
        fields = {
            "title": self.title or "",
            "file_name": self.file_name or "",
            "description": self.description or "",
            "tags": " ".join(self.tags) if self.tags else "",
            "categories": " ".join(self.categories) if self.categories else "",
            "uploader": self.uploader_name or "",
            "url": self.canonical_url or "",
            "ext": self.file_extension or "",
            "type": (self.item_type.value if hasattr(self.item_type, "value") else str(self.item_type)).lower(),
            "site": f"{self.platform or ''} {domain}".strip(),
        }
        return fields



# Backwards compatibility alias
VideoRecord = ItemRecord
