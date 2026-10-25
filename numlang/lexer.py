"""Tokeniser for Numlang source files.

Produces a flat stream of Token values consumed by the parser.
Supports integers, floats (which bypass opcode dispatch), string literals
with full C-style escapes, and the |n variable-shorthand syntax.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, List


class LexError(Exception):
    """Raised on invalid tokens, unterminated strings, or bad escape sequences."""


_IDENT_START = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_"
_IDENT_CHARS = _IDENT_START + "0123456789"

# Integer suffixes accepted by C: u/U, l/L/ll/LL, and the combinations of the two.
_INT_SUFFIX_RE = re.compile(r"(?:[uU]|[uU](?:l|L|ll|LL)|(?:l|L|ll|LL)[uU]?)?")


# Maps single-character escape letters to their byte values (mirrors C).
_SIMPLE_ESCAPES: dict[str, int] = {
    "n": 10,  # newline
    "t": 9,  # horizontal tab
    "r": 13,  # carriage return
    "\\": 92,  # backslash
    '"': 34,  # double quote
    "'": 39,  # single quote
    "a": 7,  # alert / bell
    "b": 8,  # backspace
    "f": 12,  # form feed
    "v": 11,  # vertical tab
    "?": 63,  # question mark (trigraph-free spelling)
}


@dataclass(slots=True)
class Token:
    """A single token from the source: kind, value, and source location."""

    kind: str
    value: Any
    line: int
    col: int


class Lexer:
    """Recursive-descent lexical analyser for Numlang.

    The Numlang character set is: 0-9 ^ & * + - / . | ; % # ~ " ! @ $.
    Tokens are context-free — the parser handles structural disambiguation
    (e.g. integer 28 as an else-separator vs. a plain push).
    """

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

            # Capture position now — used by all remaining branches.
            start_line, start_col = self.line, self.col

            # String literal "..."
            if ch == '"':
                self._advance()  # consume opening "
                codes: List[int] = []
                while not self._eof() and self._peek() != '"':
                    c = self._peek()
                    if c == "\n":
                        raise LexError(
                            f"Unterminated string literal at {start_line}:{start_col}"
                        )
                    if c == "\\":
                        self._advance()  # consume backslash
                        if self._eof():
                            raise LexError(
                                f"Unterminated escape sequence in string at "
                                f"{start_line}:{start_col}"
                            )
                        esc = self._peek()
                        self._advance()
                        if esc in "uU":
                            codes.extend(
                                self._universal_name_bytes(esc, start_line, start_col)
                            )
                        else:
                            codes.append(self._escape_char(esc, start_line, start_col))
                    else:
                        codes.append(ord(c))
                        self._advance()
                if self._eof():
                    raise LexError(
                        f"Unterminated string literal at {start_line}:{start_col}"
                    )
                self._advance()  # consume closing "
                tokens.append(Token("STRING", codes, start_line, start_col))
                continue

            # Skip line comments
            if ch == "#":
                while not self._eof() and self._peek() != "\n":
                    self._advance()
                continue

            # |nn → push variable nn (0–99); bare | → print
            if ch == "|":
                if self._peek(1) in "0123456789":
                    self._advance()  # consume |
                    d1 = self._advance()  # first digit (guaranteed)
                    var_str = d1
                    # Optionally consume a second digit for indices 10-99
                    if not self._eof() and self._peek() in "0123456789":
                        var_str += self._advance()
                    var_idx = int(var_str)
                    if var_idx > 99:
                        raise LexError(
                            f"Variable index {var_idx} out of range (0–99) "
                            f"at {start_line}:{start_col}"
                        )
                    tokens.append(Token("PUSH_VAR", var_idx, start_line, start_col))
                else:
                    tokens.append(Token("|", "|", start_line, start_col))
                    self._advance()
                continue

            # Character constant 'c' (C int value of one character or escape)
            if ch == "'":
                self._advance()  # consume opening '
                if self._eof() or self._peek() in "'\n":
                    raise LexError(
                        f"Empty or unterminated character constant at {start_line}:{start_col}"
                    )
                c = self._peek()
                self._advance()
                if c == "\\":
                    if self._eof():
                        raise LexError(
                            f"Unterminated character constant at {start_line}:{start_col}"
                        )
                    esc = self._peek()
                    self._advance()
                    code = self._escape_char(esc, start_line, start_col)
                else:
                    code = ord(c)
                if self._peek() != "'":
                    raise LexError(
                        f"Character constant must hold one character at {start_line}:{start_col}"
                    )
                self._advance()  # consume closing '
                # Plain char is signed on the reference platform (gcc/clang)
                if code > 127:
                    code -= 256
                tokens.append(Token("LIT", code, start_line, start_col))
                continue

            # Numbers: decimal, octal (leading 0), hex (0x), binary (0b), suffixed
            if ch.isdigit():
                tokens.append(self._lex_number(start_line, start_col))
                continue

            # Identifiers and keywords (keywords are ID tokens; the parser decides)
            if ch in _IDENT_START:
                buf = []
                while not self._eof() and self._peek() in _IDENT_CHARS:
                    buf.append(self._advance())
                tokens.append(Token("ID", "".join(buf), start_line, start_col))
                continue

            # Arrow operator -> (member access through a pointer)
            if ch == "-" and self._peek(1) == ">":
                self._advance()
                self._advance()
                tokens.append(Token("->", "->", start_line, start_col))
                continue

            # Single-character operators and structural markers
            if ch in "^&*+-/.|;%~!@$:<>()=[]{},\\":
                tokens.append(Token(ch, ch, start_line, start_col))
                self._advance()
                continue

            raise LexError(f"Unexpected character {ch!r} at {start_line}:{start_col}")

        tokens.append(Token("EOF", None, self.line, self.col))
        return tokens

    def _lex_number(self, start_line: int, start_col: int) -> Token:
        """Lex a numeric constant starting at a digit.

        Plain decimal integers stay NUM tokens (dispatched as opcodes by the
        parser). Floats, hex (0x), binary (0b), octal (leading 0) and any
        suffixed integer are LIT tokens, which always push their value.
        """
        if self._peek() == "0" and self._peek(1) in "xX":
            self._advance()
            self._advance()
            digits = self._take_while("0123456789abcdefABCDEF")
            if not digits:
                raise LexError(
                    f"Hex constant has no digits at {start_line}:{start_col}"
                )
            value: Any = int(digits, 16)
            return self._finish_int(value, start_line, start_col, lit=True)

        if self._peek() == "0" and self._peek(1) in "bB":
            self._advance()
            self._advance()
            digits = self._take_while("01")
            if not digits:
                raise LexError(
                    f"Binary constant has no digits at {start_line}:{start_col}"
                )
            return self._finish_int(int(digits, 2), start_line, start_col, lit=True)

        digits = self._take_while("0123456789")
        if self._peek() == "." and self._peek(1) in "0123456789":
            self._advance()  # consume '.'
            fraction = self._take_while("0123456789")
            return Token("NUM", float(f"{digits}.{fraction}"), start_line, start_col)

        if len(digits) > 1 and digits[0] == "0":
            if any(d in "89" for d in digits):
                raise LexError(
                    f"Invalid digit in octal constant {digits} at {start_line}:{start_col}"
                )
            return self._finish_int(int(digits, 8), start_line, start_col, lit=True)

        return self._finish_int(int(digits), start_line, start_col, lit=False)

    def _finish_int(
        self, value: int, start_line: int, start_col: int, lit: bool
    ) -> Token:
        """Consume an optional integer suffix and build the integer token."""
        suffix = self._take_while("uUlL")
        if not _INT_SUFFIX_RE.fullmatch(suffix):
            raise LexError(
                f"Invalid integer suffix {suffix!r} at {start_line}:{start_col}"
            )
        if suffix:
            lit = True  # a suffixed constant is a literal, never an opcode
        if self._peek().isalnum() or self._peek() == "_":
            raise LexError(f"Invalid numeric constant at {start_line}:{start_col}")
        return Token("LIT" if lit else "NUM", value, start_line, start_col)

    def _take_while(self, allowed: str) -> str:
        buf = []
        while not self._eof() and self._peek() in allowed:
            buf.append(self._advance())
        return "".join(buf)

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

    def _universal_name_bytes(self, esc: str, err_line: int, err_col: int) -> List[int]:
        """Resolve \\uXXXX or \\UXXXXXXXX into the UTF-8 bytes C stores for it."""
        width = 4 if esc == "u" else 8
        digits = self._take_while("0123456789abcdefABCDEF")
        if len(digits) != width:
            raise LexError(
                f"Universal character name needs {width} hex digits at {err_line}:{err_col}"
            )
        cp = int(digits, 16)
        basic = cp in (0x24, 0x40, 0x60)  # $ @ ` may be spelled as UCNs
        if (cp < 0xA0 and not basic) or 0xD800 <= cp <= 0xDFFF or cp > 0x10FFFF:
            raise LexError(
                f"Invalid universal character \\{esc}{digits} at {err_line}:{err_col}"
            )
        return list(chr(cp).encode("utf-8"))

    def _escape_char(self, esc: str, err_line: int, err_col: int) -> int:
        """Resolve a single escape character (the char *after* the backslash).

        Supports the full C escape syntax set:
          Named:  \\n \\t \\r \\\\ \\" \\' \\a \\b \\f \\v
          Hex:    \\xHH   (1–2 hex digits)
          Octal:  \\NNN   (1–3 octal digits, first digit 0–7)
        """
        if esc in _SIMPLE_ESCAPES:
            return _SIMPLE_ESCAPES[esc]

        # Hex escape: \xH... (any number of hex digits, as in C)
        if esc == "x":
            h = self._take_while("0123456789abcdefABCDEF")
            if not h:
                raise LexError(f"Empty hex escape \\x at {err_line}:{err_col}")
            value = int(h, 16)
            if value > 255:
                raise LexError(
                    f"Hex escape \\x{h} out of byte range at {err_line}:{err_col}"
                )
            return value

        # Octal escape: \0–\7 (up to 3 octal digits)
        if esc in "01234567":
            oct_str = esc
            for _ in range(2):
                if not self._eof() and self._peek() in "01234567":
                    oct_str += self._advance()
                else:
                    break
            value = int(oct_str, 8)
            if value > 255:
                raise LexError(
                    f"Octal escape \\{oct_str} out of byte range at {err_line}:{err_col}"
                )
            return value

        raise LexError(f"Unknown escape sequence \\{esc} at {err_line}:{err_col}")
