"""
Match Engine: Evaluates candidate video records against search queries, ASTs,
and matching modes with strict literal word-boundary checks and full provenance tracking.
Zero assumptions or alterations in EXACT_MATCH mode.
"""

from __future__ import annotations
import math
import re
from typing import Dict, List, Optional, Set, Tuple
from omnisearch.models.query import (
    ASTNode,
    AndNode,
    FieldNode,
    NotNode,
    OrNode,
    PhraseNode,
    SearchOptions,
    SearchQuery,
    TermNode,
)
from omnisearch.models.video import (
    MatchMode,
    MatchProvenance,
    MatchSpan,
    MatchType,
    VideoRecord,
    ItemRecord,
)
from omnisearch.core.normalizer import (
    build_word_boundary_regex,
    find_all_spans,
    normalize_for_matching,
    simple_stem,
    tokenize,
)


class MatchEvaluationResult:
    def __init__(self, is_match: bool, spans: List[MatchSpan]):
        self.is_match = is_match
        self.spans = spans


class MatchEngine:
    """Evaluates candidate videos against search queries with strict provenance recording."""

    @classmethod
    def evaluate(cls, item: ItemRecord, query: SearchQuery) -> Tuple[bool, Optional[MatchProvenance]]:
        options = query.options

        # Filter by item_types if specified
        if options.item_types and item.item_type not in options.item_types:
            return False, None

        # Filter by file_extensions if specified
        if options.file_extensions:
            allowed_exts = {e.lower().lstrip(".") for e in options.file_extensions}
            item_ext = (item.file_extension or "").lower().lstrip(".")
            if not item_ext or item_ext not in allowed_exts:
                return False, None

        text_map = item.get_searchable_text_map()

        # If title_only or MatchMode.TITLE_ONLY, restrict searchable fields to title and file_name
        is_title_only = options.title_only or options.match_mode == MatchMode.TITLE_ONLY
        if is_title_only:
            target_fields = {
                "title": text_map.get("title", ""),
                "file_name": text_map.get("file_name", ""),
            }
        else:
            target_fields = text_map

        # Evaluate AST if present, otherwise evaluate extracted terms/phrases
        ast = query.parsed_ast
        all_spans: List[MatchSpan] = []

        if ast:
            eval_result = cls._evaluate_node(ast, target_fields, options, default_field=None)
            if eval_result.is_match:
                all_spans = eval_result.spans
            elif options.match_mode == MatchMode.FLEXIBLE_MATCH and query.extracted_terms:
                # FLEXIBLE_MATCH relaxation: strict AND/OR failed — accept items
                # matching at least half of the positive query terms.
                salvage_spans: List[MatchSpan] = []
                for term in query.extracted_terms:
                    salvage_spans.extend(cls._match_term(term, target_fields, options))
                for phrase in query.extracted_phrases:
                    salvage_spans.extend(cls._match_phrase(phrase, target_fields, options))
                matched_terms = {s.term for s in salvage_spans}
                required = max(1, math.ceil(len(set(query.extracted_terms)) * 0.5))
                if len(matched_terms) >= required:
                    all_spans = salvage_spans
                else:
                    return False, None
            else:
                return False, None
        else:
            # Fallback if no AST
            matched = False
            for term in query.extracted_terms:
                spans = cls._match_term(term, target_fields, options)
                if spans:
                    matched = True
                    all_spans.extend(spans)
            for phrase in query.extracted_phrases:
                spans = cls._match_phrase(phrase, target_fields, options)
                if spans:
                    matched = True
                    all_spans.extend(spans)
            if not matched:
                return False, None

        # Build provenance
        matched_fields = list(dict.fromkeys(s.field for s in all_spans))
        matched_terms = list(dict.fromkeys(s.term for s in all_spans))

        has_title = "title" in matched_fields or "file_name" in matched_fields
        has_meta = any(f not in ("title", "file_name") for f in matched_fields)
        has_exact_phrase = any(s.is_exact_phrase for s in all_spans)
        has_stemmed = any(s.is_stemmed for s in all_spans)

        if has_stemmed:
            match_type = MatchType.STEMMED_OR_EXPANDED
        elif has_exact_phrase:
            match_type = MatchType.EXACT_PHRASE
        elif has_title and has_meta:
            match_type = MatchType.TITLE_AND_METADATA
        elif has_title:
            match_type = MatchType.WORD_BOUNDARY
        else:
            match_type = MatchType.METADATA_ONLY

        provenance = MatchProvenance(
            discovery_source=item.platform,
            matched_terms=matched_terms,
            matched_fields=matched_fields,
            match_type=match_type,
            match_spans=all_spans,
            query_variation_used=None,
            all_discovery_sources=[item.platform],
        )

        return True, provenance

    @classmethod
    def _evaluate_node(
        cls,
        node: ASTNode,
        target_fields: Dict[str, str],
        options: SearchOptions,
        default_field: Optional[str] = None,
    ) -> MatchEvaluationResult:
        if isinstance(node, TermNode):
            spans = cls._match_term(node.value, target_fields, options, specific_field=default_field)
            return MatchEvaluationResult(is_match=len(spans) > 0, spans=spans)

        elif isinstance(node, PhraseNode):
            spans = cls._match_phrase(node.phrase, target_fields, options, specific_field=default_field)
            return MatchEvaluationResult(is_match=len(spans) > 0, spans=spans)

        elif isinstance(node, FieldNode):
            # Restrict matching to specified field
            return cls._evaluate_node(node.child, target_fields, options, default_field=node.field_name)

        elif isinstance(node, NotNode):
            child_res = cls._evaluate_node(node.child, target_fields, options, default_field)
            # If child matched, NOT fails (is_match = False)
            return MatchEvaluationResult(is_match=not child_res.is_match, spans=[])

        elif isinstance(node, AndNode):
            left_res = cls._evaluate_node(node.left, target_fields, options, default_field)
            right_res = cls._evaluate_node(node.right, target_fields, options, default_field)

            # In strict mode: both left and right must be satisfied
            if left_res.is_match and right_res.is_match:
                combined_spans = left_res.spans + right_res.spans
                return MatchEvaluationResult(is_match=True, spans=combined_spans)
            else:
                return MatchEvaluationResult(is_match=False, spans=[])

        elif isinstance(node, OrNode):
            left_res = cls._evaluate_node(node.left, target_fields, options, default_field)
            right_res = cls._evaluate_node(node.right, target_fields, options, default_field)
            if left_res.is_match or right_res.is_match:
                combined_spans = left_res.spans + right_res.spans
                return MatchEvaluationResult(is_match=True, spans=combined_spans)
            else:
                return MatchEvaluationResult(is_match=False, spans=[])

        return MatchEvaluationResult(is_match=False, spans=[])

    @classmethod
    def _match_term(
        cls,
        term: str,
        target_fields: Dict[str, str],
        options: SearchOptions,
        specific_field: Optional[str] = None,
    ) -> List[MatchSpan]:
        spans: List[MatchSpan] = []
        if not term:
            return spans

        # Domain-like terms (site:mediafire.com) must match as contiguous
        # phrases, not word-by-word tokens ("mediafire", "com").
        is_domainish = specific_field == "site" or (
            specific_field is None and re.match(r"^[a-z0-9.-]+\.[a-z]{2,}$", term, re.I)
        )
        regex = (
            build_word_boundary_regex(term, exact_phrase=True, case_insensitive=True)
            if is_domainish
            else build_word_boundary_regex(term, exact_phrase=False, case_insensitive=True)
        )
        allow_stemming = options.match_mode == MatchMode.SEMANTIC_EXPANSION

        fields_to_check = {specific_field: target_fields.get(specific_field, "")} if specific_field else target_fields

        for field_name, content in fields_to_check.items():
            if not content:
                continue

            found_spans = find_all_spans(content, regex)
            for start, end, matched_text in found_spans:
                spans.append(
                    MatchSpan(
                        field=field_name,
                        term=term,
                        start=start,
                        end=end,
                        matched_text=matched_text,
                        is_exact_phrase=False,
                        is_stemmed=False,
                    )
                )

            # If no direct match and semantic expansion mode is explicitly enabled, test stemmed tokens
            if not found_spans and allow_stemming:
                term_stem = simple_stem(term)
                content_tokens = tokenize(content, fold_case=True, strip_punct=True)
                for t in content_tokens:
                    t_stem = simple_stem(t)
                    if t_stem == term_stem and t != term.lower():
                        t_regex = build_word_boundary_regex(t, exact_phrase=False, case_insensitive=True)
                        stem_spans = find_all_spans(content, t_regex)
                        for start, end, matched_text in stem_spans:
                            spans.append(
                                MatchSpan(
                                    field=field_name,
                                    term=term,
                                    start=start,
                                    end=end,
                                    matched_text=matched_text,
                                    is_exact_phrase=False,
                                    is_stemmed=True,
                                )
                            )

        return spans

    @classmethod
    def _match_phrase(
        cls,
        phrase: str,
        target_fields: Dict[str, str],
        options: SearchOptions,
        specific_field: Optional[str] = None,
    ) -> List[MatchSpan]:
        spans: List[MatchSpan] = []
        if not phrase:
            return spans

        regex = build_word_boundary_regex(phrase, exact_phrase=True, case_insensitive=True)
        fields_to_check = {specific_field: target_fields.get(specific_field, "")} if specific_field else target_fields

        for field_name, content in fields_to_check.items():
            if not content:
                continue

            found_spans = find_all_spans(content, regex)
            for start, end, matched_text in found_spans:
                spans.append(
                    MatchSpan(
                        field=field_name,
                        term=phrase,
                        start=start,
                        end=end,
                        matched_text=matched_text,
                        is_exact_phrase=True,
                        is_stemmed=False,
                    )
                )

        return spans
