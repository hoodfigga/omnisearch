"""
Tests for Canonical identity resolution, URL normalization, and deduplication.
"""

from omnisearch.core.dedup import DeduplicationEngine, normalize_url, resolve_platform_and_id
from omnisearch.models.video import MatchProvenance, MatchType, VideoMetadataSource, VideoRecord


def test_url_normalization():
    raw_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&utm_source=twitter&utm_medium=social&si=abc12345"
    norm = normalize_url(raw_url)
    assert "utm_source" not in norm
    assert "si=" not in norm
    assert "v=dQw4w9WgXcQ" in norm


def test_platform_id_resolution_youtube():
    urls = [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtu.be/dQw4w9WgXcQ?t=10",
        "https://m.youtube.com/watch?v=dQw4w9WgXcQ&feature=share",
        "https://www.youtube.com/embed/dQw4w9WgXcQ",
    ]
    for url in urls:
        platform, pid, canonical = resolve_platform_and_id(url)
        assert platform == "YouTube"
        assert pid == "dQw4w9WgXcQ"
        assert canonical == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def test_platform_id_resolution_vimeo_and_ia():
    vimeo_url = "https://vimeo.com/76979871?utm_campaign=xyz"
    platform, pid, canonical = resolve_platform_and_id(vimeo_url)
    assert platform == "Vimeo"
    assert pid == "76979871"
    assert canonical == "https://vimeo.com/76979871"

    ia_url = "https://archive.org/details/night_of_the_living_dead"
    platform, pid, canonical = resolve_platform_and_id(ia_url)
    assert platform == "Internet Archive"
    assert pid == "night_of_the_living_dead"
    assert canonical == "https://archive.org/details/night_of_the_living_dead"


def test_deduplication_and_metadata_merging():
    rec1 = VideoRecord(
        id="youtube:dQw4w9WgXcQ",
        canonical_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        platform="YouTube",
        platform_id="dQw4w9WgXcQ",
        title="Rick Astley - Never Gonna Give You Up",
        description="Official Music Video",
        tags=["music", "80s"],
        metadata_sources=[VideoMetadataSource.OFFICIAL_API],
        provenance=MatchProvenance(
            discovery_source="YouTube",
            matched_terms=["rick"],
            matched_fields=["title"],
            match_type=MatchType.WORD_BOUNDARY,
        ),
    )

    rec2 = VideoRecord(
        id="youtube:dQw4w9WgXcQ",
        canonical_url="https://youtu.be/dQw4w9WgXcQ",
        platform="YouTube",
        platform_id="dQw4w9WgXcQ",
        title="Rick Astley - Never Gonna Give You Up (4K Remaster)",
        description="Official Music Video with full lyrics and remaster details.",
        tags=["pop", "classic"],
        metadata_sources=[VideoMetadataSource.OPEN_GRAPH],
        provenance=MatchProvenance(
            discovery_source="Web",
            matched_terms=["astley"],
            matched_fields=["description"],
            match_type=MatchType.METADATA_ONLY,
        ),
    )

    deduped, dup_count = DeduplicationEngine.deduplicate([rec1, rec2])

    assert len(deduped) == 1
    assert dup_count == 1
    merged = deduped[0]

    # Description should be the richer/longer one
    assert "remaster details" in merged.description
    # Tags should be merged
    assert set(merged.tags) == {"music", "80s", "pop", "classic"}
    # Metadata sources should be merged
    assert VideoMetadataSource.OFFICIAL_API in merged.metadata_sources
    assert VideoMetadataSource.OPEN_GRAPH in merged.metadata_sources
    # Provenance terms should be merged
    assert "rick" in merged.provenance.matched_terms
    assert "astley" in merged.provenance.matched_terms
    assert set(merged.provenance.all_discovery_sources) == {"YouTube", "Web"}
