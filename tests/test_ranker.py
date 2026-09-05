"""
Tests for Multi-Factor Relevance Ranker.
"""

from omnisearch.core.matcher import MatchEngine
from omnisearch.core.query_parser import QueryParser
from omnisearch.core.ranker import RelevanceRanker
from omnisearch.models.video import VideoMetadataSource, VideoRecord


def test_title_match_ranks_above_description_match():
    query = QueryParser.parse("neural networks")

    video_title_match = VideoRecord(
        id="v1",
        canonical_url="https://example.com/1",
        platform="PlatformA",
        title="Deep Dive into Neural Networks",
        description="Comprehensive tutorial on modern deep learning architectures.",
        tags=["ai", "deep-learning"],
        uploader_name="Dr. AI",
        duration_seconds=1200,
        thumbnail_url="https://example.com/1.jpg",
        metadata_sources=[VideoMetadataSource.OFFICIAL_API],
    )

    video_desc_match = VideoRecord(
        id="v2",
        canonical_url="https://example.com/2",
        platform="PlatformB",
        title="Modern Machine Learning Systems",
        description="This lecture covers decision trees, svm, and briefly neural networks.",
        tags=["ml"],
        uploader_name="ML Academy",
        metadata_sources=[VideoMetadataSource.OFFICIAL_API],
    )

    # Evaluate matches
    _, prov1 = MatchEngine.evaluate(video_title_match, query)
    video_title_match.provenance = prov1

    _, prov2 = MatchEngine.evaluate(video_desc_match, query)
    video_desc_match.provenance = prov2

    ranked = RelevanceRanker.rank_records([video_desc_match, video_title_match], query)

    assert len(ranked) == 2
    # video_title_match should be ranked 1st
    assert ranked[0].id == "v1"
    assert ranked[0].relevance_score > ranked[1].relevance_score


def test_exact_phrase_bonus():
    query = QueryParser.parse('"computer vision"')

    v_exact = VideoRecord(
        id="v1",
        canonical_url="https://example.com/1",
        platform="PlatformA",
        title="Computer Vision Masterclass",
        description="Learn image classification and segmentation.",
        metadata_sources=[VideoMetadataSource.OFFICIAL_API],
    )

    v_scattered = VideoRecord(
        id="v2",
        canonical_url="https://example.com/2",
        platform="PlatformB",
        title="Vision and Graphic Systems for the Modern Computer",
        description="Exploring displays and visual computing.",
        metadata_sources=[VideoMetadataSource.OFFICIAL_API],
    )

    _, prov1 = MatchEngine.evaluate(v_exact, query)
    v_exact.provenance = prov1

    _, prov2 = MatchEngine.evaluate(v_scattered, query)
    v_scattered.provenance = prov2

    assert prov1.match_type.value == "EXACT_PHRASE"
    # scattered video should either not match exact phrase or rank lower
    if prov2:
        score1 = RelevanceRanker.score_record(v_exact, query)
        score2 = RelevanceRanker.score_record(v_scattered, query)
        assert score1 > score2
