from __future__ import annotations

from typing import List, Any, Tuple

from .ast import Program, Function, Op
from .lexer import Lexer, Token, LexError


class ParseError(Exception):
    pass


# Numbers with special meaning
_COMPARE_OPS = {
    10: "LT",
    11: "GT",
    12: "EQ",
    13: "NE",
    14: "LE",
    15: "GE",
}

_STACK_OPS = {
    16: "DUP",
    17: "SWAP",
    18: "DROP",
}

_SPECIAL_NUMS = {**_COMPARE_OPS, **_STACK_OPS, 20: "IF", 30: "WHILE"}


class Parser:
    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.i = 0

    @classmethod
    def from_source(cls, source: str) -> "Parser":
        lexer = Lexer(source)
        tokens = lexer.tokenize()
        return cls(tokens)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def parse(self) -> Program:
        functions: List[Function] = []
        main_code: List[Op] = []

        while not self._at_end():
            tok = self._current()

            if tok.kind == "/" and self._peek_next_kind() == "NUM":
                # Function definition:  /N <body> ;
                self._advance()
                num = self._current().value
                self._advance()
                body = self._parse_block()   # consumes up to and including ";"
                functions.append(Function(num, body))

            else:
                op = self._parse_single_op()
                if op is not None:
                    main_code.append(op)

        return Program(functions, main_code)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_block(self) -> List[Op]:
        """Parse a sequence of ops until ';' (consumed) or EOF."""
        ops: List[Op] = []
        while not self._at_end() and self._current().kind != ";":
            op = self._parse_single_op()
            if op is not None:
                ops.append(op)
        # Consume the closing ";"
        if not self._at_end() and self._current().kind == ";":
            self._advance()
        return ops

    def _parse_single_op(self) -> Op | None:
        tok = self._current()

        if tok.kind == ";":
            # Bare semicolons outside a block are ignored (legacy tolerance)
            self._advance()
            return None

        if tok.kind == "STRING":
            self._advance()
            return ("STRING", tok.value)

        if tok.kind == ".":
            # Function call: .N
            self._advance()
            if self._current().kind != "NUM":
                raise ParseError(
                    f"Expected function number after '.' at {tok.line}:{tok.col}"
                )
            num = self._current().value
            self._advance()
            return ("CALL", num)

        if tok.kind == "NUM":
            value = tok.value
            self._advance()

            if value in _COMPARE_OPS:
                return (_COMPARE_OPS[value], None)
            if value in _STACK_OPS:
                return (_STACK_OPS[value], None)
            if value == 20:
                return ("IF", None)
            if value == 30:
                # While loop:  30 <body> ;
                body = self._parse_block()
                return ("WHILE", body)

            return ("NUM", value)

        # Everything else: single-character tokens
        kind = tok.kind
        value = tok.value
        self._advance()
        return (kind, value)

    # ------------------------------------------------------------------
    # Token stream helpers
    # ------------------------------------------------------------------

    def _peek_next_kind(self) -> str | None:
        """Return the kind of the token after the current one, or None at EOF."""
        pos = self.i + 1
        if pos >= len(self.tokens):
            return None
        return self.tokens[pos].kind

    def _at_end(self) -> bool:
        return self.tokens[self.i].kind == "EOF"

    def _current(self) -> Token:
        return self.tokens[self.i]

    def _advance(self) -> Token:
        if not self._at_end():
            self.i += 1
        return self.tokens[self.i - 1]
