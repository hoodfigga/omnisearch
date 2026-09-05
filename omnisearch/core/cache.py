"""
TTL-based cache for query results, metadata lookups, and page extractions.
"""

from __future__ import annotations
import collections
import hashlib
import json
import time
from typing import Any, Dict, Optional, Tuple
from omnisearch.models.query import SearchQuery, SearchResponse


class CacheEntry:
    def __init__(self, data: Any, expires_at: float):
        self.data = data
        self.expires_at = expires_at

    def is_expired(self) -> bool:
        return time.time() > self.expires_at


class SearchCache:
    """In-memory LRU cache with TTL support for query responses and page metadata."""

    def __init__(self, default_ttl_seconds: int = 3600, max_entries: int = 1000):
        self.default_ttl = default_ttl_seconds
        self.max_entries = max_entries
        self._store: collections.OrderedDict[str, CacheEntry] = collections.OrderedDict()

    @staticmethod
    def generate_query_key(query: SearchQuery) -> str:
        """Generates a stable deterministic hash key for a search query and its options."""
        opts = query.options
        key_dict = {
            "q": query.raw_query.strip().lower(),
            "mode": opts.match_mode.value,
            "title_only": opts.title_only,
            "sources": sorted(opts.sources) if opts.sources else "all",
            "max": opts.max_results,
            "pages": opts.max_pages_per_source,
            "min_score": opts.min_score,
            "lang": opts.language,
            "item_types": (
                sorted([t.value if hasattr(t, "value") else str(t) for t in opts.item_types])
                if opts.item_types
                else None
            ),
            "exts": (
                sorted([e.lower().lstrip(".") for e in opts.file_extensions])
                if opts.file_extensions
                else None
            ),
            "min_dur": opts.min_duration_seconds,
            "max_dur": opts.max_duration_seconds,
            "pub_after": opts.published_after.isoformat() if opts.published_after else None,
            "pub_before": opts.published_before.isoformat() if opts.published_before else None,
        }
        serialized = json.dumps(key_dict, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def get(self, key: str) -> Optional[Any]:
        """Retrieves entry if present and not expired, marking it recently used."""
        entry = self._store.get(key)
        if not entry:
            return None
        if entry.is_expired():
            del self._store[key]
            return None
        self._store.move_to_end(key)
        return entry.data

    def set(self, key: str, data: Any, ttl_seconds: Optional[int] = None):
        """Sets an entry with TTL, evicting LRU items if capacity exceeded."""
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl
        if key in self._store:
            self._store.move_to_end(key)
        else:
            while len(self._store) >= self.max_entries:
                self._store.popitem(last=False)

        self._store[key] = CacheEntry(data=data, expires_at=time.time() + ttl)

    def invalidate(self, key: str):
        """Removes a key from the cache."""
        self._store.pop(key, None)

    def clear(self):
        """Clears all cached entries."""
        self._store.clear()

    def __len__(self) -> int:
        return len(self._store)

