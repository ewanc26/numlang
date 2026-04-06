from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List


class LexError(Exception):
    pass


@dataclass(slots=True)
class Token:
    kind: str
    value: Any
    line: int
    col: int


class Lexer:
    def __init__(self, source: str):
        self.source = source
        self.length = len(source)
        self.i = 0
        self.line = 1
        self.col = 1

    def tokenize(self) -> List[Token]:
        tokens: List[Token] = []
        while not self._eof():
            ch = self._peek()
            if ch in " \t\r":
                self._advance()
                continue
            if ch == "\n":
                self._advance_line()
                continue

            start_line, start_col = self.line, self.col

            if ch in "0123456789^&*+-/.|;":
                tokens.append(Token(ch, ch, start_line, start_col))
                self._advance()
                continue

            raise LexError(f"Unexpected character {ch!r} at {start_line}:{start_col}")

        tokens.append(Token("EOF", None, self.line, self.col))
        return tokens

    def _eof(self) -> bool:
        return self.i >= self.length

    def _peek(self, offset: int = 0) -> str:
        pos = self.i + offset
        if pos >= self.length:
            return "\0"
        return self.source[pos]

    def _advance(self) -> str:
        ch = self.source[self.i]
        self.i += 1
        self.col += 1
        return ch

    def _advance_line(self) -> None:
        self.i += 1
        self.line += 1
        self.col = 1