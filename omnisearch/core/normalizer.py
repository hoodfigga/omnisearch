"""
Unicode normalization, accent stripping, stemming, word-boundary,
and phonetic/spelling variation utilities.
"""

from __future__ import annotations
import functools
import re
import unicodedata
from typing import List, Pattern, Set, Tuple

COMMON_PHONETIC_PAIRS = [
    ("ph", "f"),
    ("f", "ph"),
    ("ck", "k"),
    ("k", "ck"),
    ("z", "s"),
    ("s", "z"),
    ("v", "b"),
]

SUFFIX_RULES = [
    ("ies", "y"),
    ("ing", ""),
    ("ed", ""),
    ("es", ""),
    ("er", ""),
    ("s", ""),
    ("tion", ""),
    ("able", ""),
]


def strip_accents(text: str) -> str:
    """Strips diacritics / accent marks from Unicode characters."""
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join([c for c in nfkd if not unicodedata.combining(c)])


def normalize_unicode(text: str) -> str:
    """Normalizes Unicode text to NFKC standard."""
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKC", text)
    # Normalize common smart quotes and typographic apostrophes
    normalized = (
        normalized.replace("“", '"')
        .replace("”", '"')
        .replace("‘", "'")
        .replace("’", "'")
        .replace("`", "'")
        .replace("«", '"')
        .replace("»", '"')
    )
    return normalized


def normalize_for_matching(text: str) -> str:
    """Complete normalization pipeline: NFKC, lowercase, strip accents."""
    return strip_accents(normalize_unicode(text)).lower()


def tokenize(text: str, fold_case: bool = True, strip_punct: bool = True) -> List[str]:
    """Tokenizes text into words preserving alphanumeric characters."""
    if fold_case:
        normalized = normalize_for_matching(text)
    else:
        normalized = normalize_unicode(text)
    return re.findall(r"[a-zA-Z0-9_]+", normalized)


def simple_stem(word: str) -> str:
    """Applies rule-based suffix stemming for semantic expansion."""
    w = word.lower()
    if len(w) <= 3:
        return w

    for suffix, replacement in SUFFIX_RULES:
        if w.endswith(suffix):
            stemmed = w[: -len(suffix)] + replacement
            # Handle doubled consonants before suffix (e.g. running -> runn -> run, runner -> runn -> run)
            if len(stemmed) >= 4 and stemmed[-1] == stemmed[-2]:
                stemmed = stemmed[:-1]
            if len(stemmed) >= 3:
                return stemmed
    return w


stem_word = simple_stem


@functools.lru_cache(maxsize=2048)
def build_word_boundary_regex(
    text: str,
    exact_phrase: bool = False,
    case_insensitive: bool = True,
) -> Pattern:
    """
    Builds strict word-boundary regex pattern that avoids false substring positives
    (e.g. searching 'cat' will NOT match 'category' or 'bobcat'), while properly
    respecting delimiters such as '_', '-', '.', '/', '@' commonly found in filenames,
    handles, and URLs.
    """
    flags = re.IGNORECASE if case_insensitive else 0
    clean_text = normalize_unicode(text).strip()
    if not clean_text:
        return re.compile(r"$^")  # Matches nothing

    if exact_phrase or " " in clean_text:
        tokens = tokenize(clean_text)
        if not tokens:
            return re.compile(re.escape(clean_text), flags)
        escaped_tokens = [re.escape(t) for t in tokens]
        pattern = r"[\s\-_./]+".join(escaped_tokens)
        return re.compile(rf"(?<![a-zA-Z0-9]){pattern}(?![a-zA-Z0-9])", flags)

    escaped = re.escape(clean_text)
    return re.compile(rf"(?<![a-zA-Z0-9]){escaped}(?![a-zA-Z0-9])", flags)



def build_exact_phrase_regex(phrase: str) -> Pattern:
    """Builds regex for exact multi-word phrase matching with flexible internal whitespace/delimiters."""
    return build_word_boundary_regex(phrase, exact_phrase=True, case_insensitive=True)


def find_all_spans(text: str, pattern: Pattern) -> List[Tuple[int, int, str]]:
    """Finds all (start, end, matched_text) spans for pattern in text."""
    if not text:
        return []
    return [(m.start(), m.end(), m.group(0)) for m in pattern.finditer(text)]


def generate_spelling_and_phonetic_variations(query_str: str) -> List[str]:
    """
    Generates intelligent phonetic and typo variations for queries with rare or misspelled words.
    e.g. 'phish' -> ['fish']
    """
    q = normalize_unicode(query_str).lower().strip()
    if not q:
        return []

    variations: Set[str] = set()

    for pattern_src, pattern_dst in COMMON_PHONETIC_PAIRS:
        if pattern_src in q:
            variations.add(q.replace(pattern_src, pattern_dst))

    # Also generate single character deletion/doubling variants
    for i in range(len(q) - 1):
        if q[i] == q[i + 1]:
            # deduplicate repeated letters (e.g. 'running' -> 'runing')
            variations.add(q[:i] + q[i + 1 :])

    return list(variations)
