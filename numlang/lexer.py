from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List


class LexError(Exception):
    pass


# Maps single-character escape letters to their byte values (mirrors C).
_SIMPLE_ESCAPES: dict[str, int] = {
    'n':  10,   # newline
    't':  9,    # horizontal tab
    'r':  13,   # carriage return
    '\\': 92,  # backslash
    '"':  34,   # double quote
    "'":  39,   # single quote
    'a':  7,    # alert / bell
    'b':  8,    # backspace
    'f':  12,   # form feed
    'v':  11,   # vertical tab
}


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
                        codes.append(
                            self._escape_char(esc, start_line, start_col)
                        )
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
                    self._advance()              # consume |
                    d1 = self._advance()         # first digit (guaranteed)
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

            # Numbers (integer or float)
            if ch.isdigit():
                buf = [ch]
                self._advance()
                while not self._eof() and self._peek().isdigit():
                    buf.append(self._advance())

                # Check for decimal point → float literal
                is_float = False
                if (not self._eof()
                        and self._peek() == '.'
                        and self._peek(1) in "0123456789"):
                    is_float = True
                    buf.append(self._advance())  # consume '.'
                    while not self._eof() and self._peek().isdigit():
                        buf.append(self._advance())

                text = "".join(buf)
                if is_float:
                    tokens.append(Token("NUM", float(text), start_line, start_col))
                else:
                    tokens.append(Token("NUM", int(text), start_line, start_col))
                continue

            # Single-character operators
            if ch in "^&*+-/.|;%~!":
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

    def _escape_char(self, esc: str, err_line: int, err_col: int) -> int:
        """Resolve a single escape character (the char *after* the backslash).

        Supports the full C escape syntax set:
          Named:  \\n \\t \\r \\\\ \\" \\' \\a \\b \\f \\v
          Hex:    \\xHH   (1–2 hex digits)
          Octal:  \\NNN   (1–3 octal digits, first digit 0–7)
        """
        if esc in _SIMPLE_ESCAPES:
            return _SIMPLE_ESCAPES[esc]

        # Hex escape: \xHH
        if esc == 'x':
            h = ''
            for _ in range(2):
                if not self._eof() and self._peek() in '0123456789abcdefABCDEF':
                    h += self._advance()
                else:
                    break
            if not h:
                raise LexError(
                    f"Empty hex escape \\x at {err_line}:{err_col}"
                )
            value = int(h, 16)
            if value > 255:
                raise LexError(
                    f"Hex escape \\x{h} out of byte range at {err_line}:{err_col}"
                )
            return value

        # Octal escape: \0–\7 (up to 3 octal digits)
        if esc in '01234567':
            oct_str = esc
            for _ in range(2):
                if not self._eof() and self._peek() in '01234567':
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
