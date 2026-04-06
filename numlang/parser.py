from __future__ import annotations

from typing import List

from .ast import Program
from .lexer import Lexer, Token, LexError


class ParseError(Exception):
    pass


class Parser:
    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.i = 0

    @classmethod
    def from_source(cls, source: str) -> "Parser":
        lexer = Lexer(source)
        tokens = lexer.tokenize()
        return cls(tokens)

    def parse(self) -> Program:
        operations = []
        while not self._at_end():
            token = self._advance()
            operations.append((token.kind, token.value))
        return Program(operations)

    def _at_end(self) -> bool:
        return self.tokens[self.i].kind == "EOF"

    def _advance(self) -> Token:
        if not self._at_end():
            self.i += 1
        return self.tokens[self.i - 1]