from __future__ import annotations

from typing import List, Any, Tuple, Optional

from .ast import Program, Function, Op
from .lexer import Lexer, Token, LexError


class ParseError(Exception):
    pass


# -----------------------------------------------------------------------
# Numeric opcode tables
# All keys are plain integers — float literals bypass this table entirely.
# -----------------------------------------------------------------------

_COMPARE_OPS: dict[int, str] = {
    10: "LT",
    11: "GT",
    12: "EQ",
    13: "NE",
    14: "LE",
    15: "GE",
}

_STACK_OPS: dict[int, str] = {
    16: "DUP",
    17: "SWAP",
    18: "DROP",
}

_LOGICAL_OPS: dict[int, str] = {
    19: "LOGICAL_OR",
    39: "LOGICAL_AND",
}

# Math / numeric built-ins
_MATH_OPS: dict[int, str] = {
    21: "ABS",    # |x|
    22: "SQRT",   # √x
    23: "FLOOR",  # ⌊x⌋
    24: "CEIL",   # ⌈x⌉
    25: "NEG",    # −x
    26: "MIN2",   # min(a, b)
    27: "MAX2",   # max(a, b)
    29: "POW",    # a ^ b
    31: "LOG",    # ln(x)
    32: "LOG10",  # log₁₀(x)
    33: "SIN",    # sin(x) — radians
    34: "COS",    # cos(x) — radians
    35: "TAN",    # tan(x) — radians
    36: "ROUND",  # round to nearest integer
    37: "TRUNC",  # truncate toward zero
    38: "IMOD",   # integer remainder (a % b, both cast to int)
}

# Bitwise operations — values are truncated to int before the operation
_BITWISE_OPS: dict[int, str] = {
    40: "BAND",   # a & b
    41: "BOR",    # a | b
    42: "BXOR",   # a ^ b
    43: "BNOT",   # ~a  (unary)
    44: "BSHL",   # a << b
    45: "BSHR",   # a >> b (arithmetic)
}

# Misc
_MISC_OPS: dict[int, str] = {
    60: "RAND",   # push random double in [0, 1)
    61: "TIME",   # push current Unix timestamp as double
    62: "EXIT",   # pop exit code and terminate program
}

# All opcodes that consume their numeric token and produce a non-NUM op
_SPECIAL_NUMS: dict[int, str] = {
    **_COMPARE_OPS,
    **_STACK_OPS,
    **_LOGICAL_OPS,
    **_MATH_OPS,
    **_BITWISE_OPS,
    **_MISC_OPS,
    # Control flow — handled specially in _parse_single_op
    20: "IF_BLOCK",    # 20 <then_body> [28 <else_body>] ;
    30: "WHILE",       # 30 <body> ;
    50: "REPEAT",      # 50 <body> ;
    # 28 is NOT in this table: inside an IF_BLOCK body it is the else-separator;
    # outside of that context it is treated as a plain numeric push.
}


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
                if not isinstance(num, int):
                    raise ParseError(
                        f"Function number must be an integer, got {num!r} "
                        f"at {self._current().line}:{self._current().col}"
                    )
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
        """Parse a sequence of ops until ';' (consumed) or EOF.

        Used for WHILE bodies, REPEAT bodies, function bodies, and the
        outer terminator of IF_BLOCK.  Does NOT consume the else-separator
        (28) — that is handled inside _parse_if_body only.
        """
        ops: List[Op] = []
        while not self._at_end() and self._current().kind != ";":
            op = self._parse_single_op()
            if op is not None:
                ops.append(op)
        # Consume the closing ";"
        if not self._at_end() and self._current().kind == ";":
            self._advance()
        return ops

    def _parse_if_body(self) -> tuple[List[Op], Optional[List[Op]]]:
        """Parse the body of an IF_BLOCK construct.

        Grammar (after the leading '20' has been consumed):
            <then_ops> [ 28 <else_ops> ] ;

        The integer literal 28 is the else-separator and is ONLY treated as
        such when it appears at the top level of an if body (not nested).
        Outside of if bodies it pushes the value 28 normally.
        """
        then_ops: List[Op] = []
        else_ops: Optional[List[Op]] = None

        while not self._at_end() and self._current().kind != ";":
            tok = self._current()
            # Integer 28 (not float 28.0) is the else-separator
            if (tok.kind == "NUM"
                    and isinstance(tok.value, int)
                    and tok.value == 28):
                self._advance()  # consume 28
                # Parse else body until ";"
                else_ops = []
                while not self._at_end() and self._current().kind != ";":
                    op = self._parse_single_op()
                    if op is not None:
                        else_ops.append(op)
                break  # ';' consumed below

            op = self._parse_single_op()
            if op is not None:
                then_ops.append(op)

        # Consume the closing ";"
        if not self._at_end() and self._current().kind == ";":
            self._advance()
        return then_ops, else_ops

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
            if not isinstance(num, int):
                raise ParseError(
                    f"Function number must be an integer, got {num!r} "
                    f"at {tok.line}:{tok.col}"
                )
            self._advance()
            return ("CALL", num)

        if tok.kind == "!":
            self._advance()
            return ("NOT", None)

        if tok.kind == "NUM":
            value = tok.value
            self._advance()

            # Float literals always push — they never map to opcodes
            if isinstance(value, float):
                return ("NUM", value)

            # Integer opcode dispatch
            if value in _COMPARE_OPS:
                return (_COMPARE_OPS[value], None)
            if value in _STACK_OPS:
                return (_STACK_OPS[value], None)
            if value in _LOGICAL_OPS:
                return (_LOGICAL_OPS[value], None)
            if value in _MATH_OPS:
                return (_MATH_OPS[value], None)
            if value in _BITWISE_OPS:
                return (_BITWISE_OPS[value], None)
            if value in _MISC_OPS:
                return (_MISC_OPS[value], None)

            if value == 20:
                # IF_BLOCK: 20 <then_body> [28 <else_body>] ;
                then_body, else_body = self._parse_if_body()
                return ("IF_BLOCK", (then_body, else_body))

            if value == 30:
                # WHILE: 30 <body> ;
                body = self._parse_block()
                return ("WHILE", body)

            if value == 50:
                # REPEAT: pop N, execute body N times pushing iteration index
                body = self._parse_block()
                return ("REPEAT", body)

            # Plain number push (includes 28 when outside an IF body)
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
