"""
Tests for Query Lexer, Parser, AST generation, and token extraction.
"""

import pytest
from omnisearch.core.query_parser import QueryLexer, QueryParser
from omnisearch.models.query import AndNode, FieldNode, NotNode, OrNode, PhraseNode, TermNode


def test_simple_term_query():
    query = QueryParser.parse("python")
    assert isinstance(query.parsed_ast, TermNode)
    assert query.parsed_ast.value == "python"
    assert query.extracted_terms == ["python"]
    assert query.extracted_phrases == []


def test_quoted_phrase_query():
    query = QueryParser.parse('"deep learning tutorial"')
    assert isinstance(query.parsed_ast, PhraseNode)
    assert query.parsed_ast.phrase == "deep learning tutorial"
    assert query.extracted_phrases == ["deep learning tutorial"]
    assert set(query.extracted_terms) == {"deep", "learning", "tutorial"}


def test_smart_quotes_handling():
    query = QueryParser.parse('“machine learning”')
    assert isinstance(query.parsed_ast, PhraseNode)
    assert query.parsed_ast.phrase == "machine learning"


def test_boolean_and_query():
    query = QueryParser.parse("python AND rust")
    assert isinstance(query.parsed_ast, AndNode)
    assert isinstance(query.parsed_ast.left, TermNode)
    assert isinstance(query.parsed_ast.right, TermNode)
    assert query.parsed_ast.left.value == "python"
    assert query.parsed_ast.right.value == "rust"
    assert "python" in query.extracted_terms
    assert "rust" in query.extracted_terms


def test_boolean_or_query():
    query = QueryParser.parse("react OR vue")
    assert isinstance(query.parsed_ast, OrNode)
    assert query.parsed_ast.left.value == "react"
    assert query.parsed_ast.right.value == "vue"


def test_negation_and_minus_syntax():
    query1 = QueryParser.parse("python NOT beginner")
    assert isinstance(query1.parsed_ast, AndNode)
    assert isinstance(query1.parsed_ast.right, NotNode)
    assert query1.extracted_terms == ["python"]  # Negated terms excluded from positive list

    query2 = QueryParser.parse("python -beginner")
    assert isinstance(query2.parsed_ast, AndNode)
    assert isinstance(query2.parsed_ast.right, NotNode)


def test_field_directives():
    query = QueryParser.parse('title:"fastapi tutorial" meta:async')
    assert isinstance(query.parsed_ast, AndNode)
    assert isinstance(query.parsed_ast.left, FieldNode)
    assert query.parsed_ast.left.field_name == "title"
    assert isinstance(query.parsed_ast.left.child, PhraseNode)
    assert query.parsed_ast.left.child.phrase == "fastapi tutorial"

    assert isinstance(query.parsed_ast.right, FieldNode)
    assert query.parsed_ast.right.field_name == "meta"
    assert query.parsed_ast.right.child.value == "async"


def test_complex_parentheses_query():
    query = QueryParser.parse('(python OR rust) AND "system programming"')
    assert isinstance(query.parsed_ast, AndNode)
    assert isinstance(query.parsed_ast.left, OrNode)
    assert isinstance(query.parsed_ast.right, PhraseNode)
    assert query.parsed_ast.right.phrase == "system programming"
