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

            # Skip whitespace
            if ch in " \t\r":
                self._advance()
                continue
            if ch == "\n":
                self._advance_line()
                continue

            # Skip line comments
            if ch == "#":
                while not self._eof() and self._peek() != "\n":
                    self._advance()
                continue

            start_line, start_col = self.line, self.col

            # |n → push variable n, bare | → print
            if ch == "|":
                if self._peek(1) in "0123456789":
                    var = self._peek(1)
                    tokens.append(Token("PUSH_VAR", int(var), start_line, start_col))
                    self._advance()
                    self._advance()
                else:
                    tokens.append(Token("|", "|", start_line, start_col))
                    self._advance()
                continue

            # Numbers
            if ch.isdigit():
                buf = [ch]
                self._advance()
                while not self._eof() and self._peek().isdigit():
                    buf.append(self._advance())
                text = "".join(buf)
                tokens.append(Token("NUM", int(text), start_line, start_col))
                continue

            # Single-character operators (including new % for modulo)
            if ch in "^&*+-/.|;%":
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
