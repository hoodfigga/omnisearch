"""
Tests for Match Engine, word boundary checks, exact phrase matching, and provenance classification.
"""

import pytest
from omnisearch.core.matcher import MatchEngine
from omnisearch.core.query_parser import QueryParser
from omnisearch.models.query import MatchMode, SearchOptions
from omnisearch.models.video import MatchType, VideoMetadataSource, VideoRecord


def create_sample_video(
    title: str = "Test Video",
    description: str = "Test description",
    tags: list = None,
    uploader: str = "Test Creator",
) -> VideoRecord:
    return VideoRecord(
        id="sample:123",
        canonical_url="https://example.com/video/123",
        platform="TestPlatform",
        title=title,
        description=description,
        tags=tags or [],
        uploader_name=uploader,
        metadata_sources=[VideoMetadataSource.OFFICIAL_API],
    )


def test_word_boundary_no_false_substring_match():
    # Searching for "art" should NEVER match "partial" or "starting"
    video = create_sample_video(
        title="A Partial Guide to Starting Projects",
        description="This contains the word chart and smart.",
    )
    query = QueryParser.parse("art")
    is_match, prov = MatchEngine.evaluate(video, query)
    assert not is_match
    assert prov is None


def test_word_boundary_true_match():
    video = create_sample_video(
        title="Modern Art in the 21st Century",
        description="Exploring contemporary art movements.",
    )
    query = QueryParser.parse("art")
    is_match, prov = MatchEngine.evaluate(video, query)
    assert is_match
    assert prov is not None
    assert "art" in prov.matched_terms
    assert "title" in prov.matched_fields


def test_exact_phrase_matching():
    video1 = create_sample_video(
        title="Deep Learning with PyTorch",
        description="A complete guide to neural networks.",
    )
    video2 = create_sample_video(
        title="Learning Deep Concepts in Programming",
        description="General introductory computer science topics.",
    )

    query = QueryParser.parse('"deep learning"')

    # video1 has exact phrase "Deep Learning"
    match1, prov1 = MatchEngine.evaluate(video1, query)
    assert match1
    assert prov1.match_type == MatchType.EXACT_PHRASE

    # video2 has "Learning Deep" (reversed order), should not match exact phrase
    match2, prov2 = MatchEngine.evaluate(video2, query)
    assert not match2


def test_metadata_only_vs_title_match():
    # Video has term in description and tags, but NOT in title
    video = create_sample_video(
        title="Advanced Robotics Engineering",
        description="Comprehensive tutorial on reinforcement learning and neural dynamics.",
        tags=["ai", "robotics", "reinforcement learning"],
    )

    query = QueryParser.parse("reinforcement")

    match, prov = MatchEngine.evaluate(video, query)
    assert match
    assert prov.match_type == MatchType.METADATA_ONLY
    assert "title" not in prov.matched_fields
    assert "description" in prov.matched_fields or "tags" in prov.matched_fields


def test_title_only_mode_restriction():
    video = create_sample_video(
        title="Cooking Italian Pasta",
        description="Secret recipe for tomato sauce and basil.",
    )
    opts = SearchOptions(match_mode=MatchMode.TITLE_ONLY)
    query = QueryParser.parse("tomato", options=opts)

    match, _ = MatchEngine.evaluate(video, query)
    assert not match  # "tomato" is in description but title_only was requested


def test_boolean_and_evaluation():
    video = create_sample_video(
        title="Python and Rust Performance Comparison",
        description="Benchmarking high concurrency microservices.",
    )

    query_pass = QueryParser.parse("python AND rust")
    match_pass, _ = MatchEngine.evaluate(video, query_pass)
    assert match_pass

    query_fail = QueryParser.parse("python AND golang")
    match_fail, _ = MatchEngine.evaluate(video, query_fail)
    assert not match_fail


def test_boolean_not_evaluation():
    video = create_sample_video(
        title="Python Web Development for Beginners",
        description="Getting started with basic web concepts.",
    )

    query_not = QueryParser.parse("python NOT beginners")
    # "beginners" matches title, so NOT should fail
    match, _ = MatchEngine.evaluate(video, query_not)
    assert not match


def test_semantic_expansion_stemming():
    video = create_sample_video(
        title="Running Distributed Systems",
        description="System operations and scalability.",
    )

    # In EXACT_MATCH mode, "runner" does not match "Running"
    query_exact = QueryParser.parse("runner", options=SearchOptions(match_mode=MatchMode.EXACT_MATCH))
    match_exact, _ = MatchEngine.evaluate(video, query_exact)
    assert not match_exact

    # In SEMANTIC_EXPANSION mode, stemming permits matching
    query_sem = QueryParser.parse("runner", options=SearchOptions(match_mode=MatchMode.SEMANTIC_EXPANSION))
    match_sem, prov_sem = MatchEngine.evaluate(video, query_sem)
    assert match_sem
    assert prov_sem.match_type == MatchType.STEMMED_OR_EXPANDED
