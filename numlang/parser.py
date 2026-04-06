from __future__ import annotations

from typing import List

from .ast import Program, Function
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
        functions = []
        main_code = []
        while not self._at_end():
            if self._current().kind == "/":
                self._advance()
                if self._current().kind == "NUM":
                    num = self._current().value
                    self._advance()
                    code = self._parse_code()
                    if not self._at_end() and self._current().kind == ";":
                        self._advance()
                    functions.append(Function(num, code))
                else:
                    raise ParseError("Expected NUM after /")
            else:
                if self._current().kind == ".":
                    self._advance()
                    if self._current().kind == "NUM":
                        main_code.append(("CALL", self._current().value))
                        self._advance()
                    else:
                        raise ParseError("Expected NUM after .")
                else:
                    kind = self._current().kind
                    value = self._current().value
                    if kind == "NUM" and value in [10,11,12,13,14,15]:
                        kind = {10: "LT", 11: "GT", 12: "EQ", 13: "NE", 14: "LE", 15: "GE"}[value]
                        value = None
                    main_code.append((kind, value))
                    self._advance()
        return Program(functions, main_code)

    def _parse_code(self) -> List[tuple[str, Any]]:
        code = []
        while not self._at_end() and self._current().kind != ";":
            if self._current().kind == ".":
                self._advance()
                if self._current().kind == "NUM":
                    code.append(("CALL", self._current().value))
                    self._advance()
                else:
                    raise ParseError("Expected NUM after .")
            else:
                kind = self._current().kind
                value = self._current().value
                if kind == "NUM" and value in [10,11,12,13,14,15]:
                    kind = {10: "LT", 11: "GT", 12: "EQ", 13: "NE", 14: "LE", 15: "GE"}[value]
                    value = None
                code.append((kind, value))
                self._advance()
        return code

    def _at_end(self) -> bool:
        return self.tokens[self.i].kind == "EOF"

    def _current(self) -> Token:
        return self.tokens[self.i]

    def _advance(self) -> Token:
        if not self._at_end():
            self.i += 1
        return self.tokens[self.i - 1]