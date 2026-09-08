"""
Shared HTML parsing helpers.

Selects the fastest available BeautifulSoup parser (lxml when installed,
stdlib html.parser otherwise) so every module parses HTML exactly once,
through one canonical entry point.
"""

from __future__ import annotations
from bs4 import BeautifulSoup

try:
    import lxml  # noqa: F401
    HTML_PARSER = "lxml"
except ImportError:  # pragma: no cover - lxml is a declared dependency
    HTML_PARSER = "html.parser"


def make_soup(html: str) -> BeautifulSoup:
    """Parses HTML with the best available parser."""
    return BeautifulSoup(html, HTML_PARSER)
