"""
Query lexer and recursive descent parser supporting quoted phrases, boolean logic,
field specifiers, and negative terms.
"""

from __future__ import annotations
import re
from typing import List, Optional, Tuple
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
from omnisearch.core.normalizer import normalize_unicode, tokenize


class TokenType:
    TERM = "TERM"
    PHRASE = "PHRASE"
    AND = "AND"
    OR = "OR"
    NOT = "NOT"
    LPAREN = "LPAREN"
    RPAREN = "RPAREN"
    FIELD_PREFIX = "FIELD_PREFIX"
    EOF = "EOF"


class Token:
    def __init__(self, type_: str, value: str, field: Optional[str] = None):
        self.type = type_
        self.value = value
        self.field = field

    def __repr__(self):
        if self.field:
            return f"Token({self.type}, {self.value!r}, field={self.field!r})"
        return f"Token({self.type}, {self.value!r})"


class QueryLexer:
    """Lexer that turns query strings into structured tokens."""

    FIELD_PATTERN = re.compile(
        r"^(title|meta|description|tags|uploader|ext|type|site|url|file_name):",
        re.IGNORECASE,
    )

    def __init__(self, query_str: str):
        self.text = normalize_unicode(query_str).strip()
        self.pos = 0
        self.length = len(self.text)

    def tokenize(self) -> List[Token]:
        tokens: List[Token] = []
        while self.pos < self.length:
            self._skip_whitespace()
            if self.pos >= self.length:
                break

            current_field: Optional[str] = None

            # Check for field specifier like "title:", "meta:", etc.
            remaining = self.text[self.pos :]
            field_match = self.FIELD_PATTERN.match(remaining)
            if field_match:
                current_field = field_match.group(1).lower()
                self.pos += field_match.end()
                self._skip_whitespace()
                if self.pos >= self.length:
                    break

            ch = self.text[self.pos]

            if ch == "(":
                tokens.append(Token(TokenType.LPAREN, "("))
                self.pos += 1
            elif ch == ")":
                tokens.append(Token(TokenType.RPAREN, ")"))
                self.pos += 1
            elif ch in ('"', "'", "“", "”", "‘", "’"):
                quote_char = ch
                closing_quote = '"' if ch in ('"', "“", "”") else "'"
                phrase = self._read_quoted(quote_char, closing_quote)
                tokens.append(Token(TokenType.PHRASE, phrase, field=current_field))
            elif ch == "-" and self.pos + 1 < self.length and not self.text[self.pos + 1].isspace():
                tokens.append(Token(TokenType.NOT, "NOT"))
                self.pos += 1
            else:
                word = self._read_word()
                if not word:
                    self.pos += 1
                    continue
                upper_word = word.upper()
                if upper_word == "AND":
                    tokens.append(Token(TokenType.AND, "AND"))
                elif upper_word == "OR":
                    tokens.append(Token(TokenType.OR, "OR"))
                elif upper_word == "NOT":
                    tokens.append(Token(TokenType.NOT, "NOT"))
                else:
                    tokens.append(Token(TokenType.TERM, word, field=current_field))

        tokens.append(Token(TokenType.EOF, ""))
        return tokens

    def _skip_whitespace(self):
        while self.pos < self.length and self.text[self.pos].isspace():
            self.pos += 1

    def _read_quoted(self, quote_char: str, closing_quote: str) -> str:
        self.pos += 1  # Skip start quote
        start = self.pos
        quote_set = {'"', "“", "”"} if quote_char in ('"', "“", "”") else {"'", "‘", "’"}
        while self.pos < self.length and self.text[self.pos] not in quote_set:
            self.pos += 1
        phrase = self.text[start : self.pos]
        if self.pos < self.length:
            self.pos += 1  # Skip closing quote
        return phrase.strip()

    def _read_word(self) -> str:
        start = self.pos
        while self.pos < self.length and not self.text[self.pos].isspace() and self.text[self.pos] not in "()\"'“”‘’":
            self.pos += 1
        return self.text[start : self.pos].strip()


class QueryParser:
    """Parses token stream into an AST."""

    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.pos = 0

    @classmethod
    def parse(cls, query_str: str, options: Optional[SearchOptions] = None) -> SearchQuery:
        opts = options or SearchOptions()
        lexer = QueryLexer(query_str)
        tokens = lexer.tokenize()
        parser = cls(tokens)
        ast = parser.parse_expression()

        # Extract all positive terms and phrases
        terms: List[str] = []
        phrases: List[str] = []
        if ast:
            cls._extract_positive_terms(ast, terms, phrases)
            cls._extract_options_from_ast(ast, opts)

        return SearchQuery(
            raw_query=query_str,
            options=opts,
            parsed_ast=ast,
            extracted_terms=list(dict.fromkeys(terms)),
            extracted_phrases=list(dict.fromkeys(phrases)),
        )

    def _peek(self) -> Token:
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return Token(TokenType.EOF, "")

    def _consume(self, expected_type: Optional[str] = None) -> Token:
        tok = self._peek()
        self.pos += 1
        return tok

    def parse_expression(self) -> Optional[ASTNode]:
        return self.parse_or()

    def parse_or(self) -> Optional[ASTNode]:
        node = self.parse_and()
        while self._peek().type == TokenType.OR:
            self._consume(TokenType.OR)
            right = self.parse_and()
            if node and right:
                node = OrNode(left=node, right=right)
            elif right:
                node = right
        return node

    def parse_and(self) -> Optional[ASTNode]:
        node = self.parse_not()
        while self._peek().type not in (TokenType.OR, TokenType.RPAREN, TokenType.EOF):
            if self._peek().type == TokenType.AND:
                self._consume(TokenType.AND)
            right = self.parse_not()
            if node and right:
                node = AndNode(left=node, right=right)
            elif right:
                node = right
        return node

    def parse_not(self) -> Optional[ASTNode]:
        if self._peek().type == TokenType.NOT:
            self._consume(TokenType.NOT)
            child = self.parse_primary()
            if child:
                return NotNode(child=child)
            return None
        return self.parse_primary()

    def parse_primary(self) -> Optional[ASTNode]:
        tok = self._peek()
        if tok.type == TokenType.LPAREN:
            self._consume(TokenType.LPAREN)
            node = self.parse_expression()
            if self._peek().type == TokenType.RPAREN:
                self._consume(TokenType.RPAREN)
            return node

        if tok.type == TokenType.PHRASE:
            self._consume()
            clean_phrase = tok.value.strip()
            if not clean_phrase:
                return None
            words = tokenize(clean_phrase)
            node: ASTNode = PhraseNode(phrase=clean_phrase, words=words)
            if tok.field:
                node = FieldNode(field_name=tok.field, child=node)
            return node

        if tok.type == TokenType.TERM:
            self._consume()
            clean_term = tok.value.strip()
            if not clean_term:
                return None
            node: ASTNode = TermNode(value=clean_term)
            if tok.field:
                node = FieldNode(field_name=tok.field, child=node)
            return node

        if tok.type != TokenType.EOF:
            self._consume()
        return None

    @classmethod
    def _extract_positive_terms(cls, node: ASTNode, terms: List[str], phrases: List[str]):
        if isinstance(node, TermNode):
            terms.append(node.value)
        elif isinstance(node, PhraseNode):
            phrases.append(node.phrase)
            terms.extend(node.words)
        elif isinstance(node, FieldNode):
            cls._extract_positive_terms(node.child, terms, phrases)
        elif isinstance(node, AndNode) or isinstance(node, OrNode):
            cls._extract_positive_terms(node.left, terms, phrases)
            cls._extract_positive_terms(node.right, terms, phrases)
        elif isinstance(node, NotNode):
            pass

    @classmethod
    def _extract_options_from_ast(cls, node: ASTNode, opts: SearchOptions):
        from omnisearch.models.video import ItemType
        if isinstance(node, FieldNode):
            val = None
            if isinstance(node.child, TermNode):
                val = node.child.value
            elif isinstance(node.child, PhraseNode):
                val = node.child.phrase

            if val:
                f_name = node.field_name.lower()
                if f_name == "ext":
                    ext_clean = val.lower().lstrip(".")
                    if opts.file_extensions is None:
                        opts.file_extensions = [ext_clean]
                    elif ext_clean not in opts.file_extensions:
                        opts.file_extensions.append(ext_clean)
                elif f_name == "type":
                    val_norm = val.strip().upper()
                    if val_norm in ItemType.__members__:
                        itype = ItemType[val_norm]
                        if opts.item_types is None:
                            opts.item_types = [itype]
                        elif itype not in opts.item_types:
                            opts.item_types.append(itype)
        elif isinstance(node, (AndNode, OrNode)):
            cls._extract_options_from_ast(node.left, opts)
            cls._extract_options_from_ast(node.right, opts)

