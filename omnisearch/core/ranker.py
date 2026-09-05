"""
Multi-factor relevance ranking engine.
Prioritizes exact textual matches in title/filename and exact phrase matches over popularity,
while rewarding direct download availability, file metadata completeness, and query term coverage.
"""

from __future__ import annotations
import math
from datetime import datetime, timezone
from typing import List, Optional
from omnisearch.models.query import SearchQuery
from omnisearch.models.video import MatchType, ItemRecord, VideoRecord


class RelevanceRanker:
    """
    Ranks candidate records based on textual match strength, field weighting,
    direct download availability, term coverage, and metadata completeness.
    """

    # Field weights for term occurrences
    FIELD_WEIGHTS = {
        "title": 10.0,
        "file_name": 10.0,
        "tags": 4.0,
        "categories": 3.0,
        "uploader": 2.5,
        "description": 1.5,
        "url": 1.0,
    }

    # Match type bonus
    MATCH_TYPE_BONUS = {
        MatchType.EXACT_PHRASE: 8.0,
        MatchType.TITLE_AND_METADATA: 6.0,
        MatchType.WORD_BOUNDARY: 5.0,
        MatchType.METADATA_ONLY: 3.0,
        MatchType.STEMMED_OR_EXPANDED: 2.0,
        MatchType.FLEXIBLE: 1.5,
    }

    @classmethod
    def score_record(cls, record: ItemRecord, query: SearchQuery) -> float:
        """Calculates a normalized relevance score for a single record."""
        prov = record.provenance
        if not prov:
            return 0.0

        score = 0.0

        # 1. Match Type Base Bonus
        score += cls.MATCH_TYPE_BONUS.get(prov.match_type, 1.0)

        # 2. Term Coverage (percentage of query terms found in record)
        all_query_terms = set(query.extracted_terms + query.extracted_phrases)
        if all_query_terms:
            matched_terms = set(prov.matched_terms)
            coverage = len(matched_terms.intersection(all_query_terms)) / len(all_query_terms)
            score += coverage * 10.0

        # 3. Field Occurrence Weights from Spans
        field_hit_count = {k: 0 for k in cls.FIELD_WEIGHTS}
        for span in prov.match_spans:
            weight = cls.FIELD_WEIGHTS.get(span.field, 1.0)
            # Exact phrase span bonus
            if span.is_exact_phrase:
                weight *= 2.0
            # Diminishing returns for multiple hits in same field
            field_hit_count[span.field] = field_hit_count.get(span.field, 0) + 1
            diminishing = 1.0 / math.sqrt(field_hit_count[span.field])
            score += weight * diminishing

        # 4. Multi-field Bonus (matching across multiple fields)
        unique_matched_fields = set(prov.matched_fields)
        if len(unique_matched_fields) >= 2:
            score += len(unique_matched_fields) * 2.0

        # 5. Direct Download Availability & File Metadata Bonus
        if record.download_url:
            score += 3.0
        if record.file_extension:
            score += 1.0
        if record.file_size_bytes or record.file_size_human:
            score += 1.5

        # 6. Metadata Completeness Bonus
        completeness = 0.0
        if record.description and len(record.description) > 20:
            completeness += 1.0
        if record.uploader_name:
            completeness += 0.5
        if record.thumbnail_url:
            completeness += 0.5
        if record.publication_date:
            completeness += 0.5
        if record.tags:
            completeness += 0.5
        score += completeness

        # 7. Recency Signal (minor tiebreaker, logarithmic decay)
        if record.publication_date:
            try:
                now = datetime.now(timezone.utc)
                pub = record.publication_date
                if pub.tzinfo is None:
                    pub = pub.replace(tzinfo=timezone.utc)
                age_days = max(1.0, (now - pub).total_seconds() / 86400.0)
                recency_bonus = max(0.0, 1.5 - math.log10(age_days) * 0.5)
                score += recency_bonus
            except Exception:
                pass

        return round(score, 2)

    @classmethod
    def rank_records(cls, records: List[ItemRecord], query: SearchQuery) -> List[ItemRecord]:
        """Calculates relevance scores, sorts records descending by score, and assigns 1-based ranks."""
        for rec in records:
            rec.relevance_score = cls.score_record(rec, query)

        # Sort descending by score, then tiebreak by title length / direct download
        sorted_records = sorted(
            records,
            key=lambda r: (
                r.relevance_score,
                bool(r.download_url),
                -len(r.title),
            ),
            reverse=True,
        )

        # Assign ranks
        for idx, rec in enumerate(sorted_records, start=1):
            rec.rank = idx

        return sorted_records
