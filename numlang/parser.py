"""Recursive-descent parser that converts a token stream into an AST.

Dispatches integer tokens to opcode tables, floats always push, and
control-flow constructs (IF_BLOCK, WHILE, REPEAT, SWITCH) are parsed
recursively. Declarations are resolved to C types here, so the code
generator only lays out storage and emits code.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .ast import Decl, Expr, Foreign, Function, InitList, LVal, Op, Program
from .ctypes_model import (
    CType,
    TypeLayoutError,
    arithmetic_from_words,
    array_of,
    complete_struct,
    function_type,
    new_struct,
    pointer_to,
    scalar,
)
from .lexer import Lexer, LexError, Token

MAX_FOREIGN_ARITY = 3


class ParseError(Exception):
    """Raised on malformed syntax — unexpected tokens or structural errors."""


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
    21: "ABS",  # |x|
    22: "SQRT",  # √x
    23: "FLOOR",  # ⌊x⌋
    24: "CEIL",  # ⌈x⌉
    25: "NEG",  # −x
    26: "MIN2",  # min(a, b)
    27: "MAX2",  # max(a, b)
    29: "POW",  # a ^ b
    31: "LOG",  # ln(x)
    32: "LOG10",  # log₁₀(x)
    33: "SIN",  # sin(x) — radians
    34: "COS",  # cos(x) — radians
    35: "TAN",  # tan(x) — radians
    36: "ROUND",  # round to nearest integer
    37: "TRUNC",  # truncate toward zero
    38: "IMOD",  # integer remainder (a % b, both cast to int)
    46: "ASIN",  # arcsin(x) — result in radians
    47: "ACOS",  # arccos(x) — result in radians
    48: "ATAN",  # arctan(x) — result in radians
    49: "ATAN2",  # atan2(y, x) — two-argument arctangent
}

# Bitwise operations — values are truncated to int before the operation
_BITWISE_OPS: dict[int, str] = {
    40: "BAND",  # a & b
    41: "BOR",  # a | b
    42: "BXOR",  # a ^ b
    43: "BNOT",  # ~a  (unary)
    44: "BSHL",  # a << b
    45: "BSHR",  # a >> b (arithmetic)
}

# Misc
_MISC_OPS: dict[int, str] = {
    60: "RAND",  # push random double in [0, 1)
    61: "TIME",  # push current Unix timestamp as double
    62: "EXIT",  # pop exit code and terminate program
    63: "DEPTH",  # push current stack depth as a double
    64: "PICK",  # pop n; push copy of element n positions below the new top (0 = top)
}

# Integer operations and fixed-size arrays.
# ARR_NEW: [id, size] -> allocate array id with size zeroed elements
# ARR_SET: [id, index, value] -> store
# ARR_GET: [id, index] -> push element
# IDIV:    [a, b] -> a / b truncated toward zero, C int semantics
_INTEGER_ARRAY_OPS: dict[int, str] = {
    51: "ARR_NEW",
    52: "ARR_SET",
    53: "ARR_GET",
    55: "IDIV",
}

# All opcodes that consume their numeric token and produce a non-NUM op
_SPECIAL_NUMS: dict[int, str] = {
    **_COMPARE_OPS,
    **_STACK_OPS,
    **_LOGICAL_OPS,
    **_MATH_OPS,
    **_BITWISE_OPS,
    **_MISC_OPS,
    **_INTEGER_ARRAY_OPS,
    # Control flow — handled specially in _parse_single_op
    20: "IF_BLOCK",  # 20 <then_body> [28 <else_body>] ;
    30: "WHILE",  # 30 <body> ;
    50: "REPEAT",  # 50 <body> ;
    # 28 is NOT in this table: inside an IF_BLOCK body it is the else-separator;
    # outside of that context it is treated as a plain numeric push.
}

# -----------------------------------------------------------------------
# Keywords of the memory model. They are ID tokens; the parser decides.
# -----------------------------------------------------------------------

_TYPE_WORDS = frozenset(
    {"int", "char", "short", "long", "unsigned", "signed", "float", "double", "_Bool"}
)
_QUALIFIERS = frozenset({"const", "volatile", "restrict"})
_STORAGE = frozenset({"static", "typedef"})
_KEYWORDS = (
    _TYPE_WORDS
    | _QUALIFIERS
    | _STORAGE
    | frozenset(
        {
            "struct",
            "union",
            "enum",
            "sizeof",
            "switch",
            "case",
            "default",
            "goto",
            "label",
            "void",
        }
    )
)


class Parser:
    """Recursive-descent parser producing a Program AST.

    Integer tokens are checked against the opcode dispatch tables first.
    Floats, strings, and unrecognised integers become NUM pushes.
    Control flow (20=IF, 30=WHILE, 50=REPEAT) captures bodies recursively.
    """

    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.i = 0
        self.typedefs: Dict[str, CType] = {}
        self.tags: Dict[Tuple[str, str], CType] = {}
        self.enum_consts: Dict[str, int] = {}

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
        foreign: List[Foreign] = []

        try:
            while not self._at_end():
                tok = self._current()

                if tok.kind == "@":
                    foreign.append(self._parse_foreign())

                elif tok.kind == "/" and self._peek_next_kind() == "NUM":
                    # Function definition:  /N <body> ;
                    self._advance()
                    num = self._current().value
                    if not isinstance(num, int):
                        raise ParseError(
                            f"Function number must be an integer, got {num!r} "
                            f"at {self._current().line}:{self._current().col}"
                        )
                    self._advance()
                    position = len(main_code)
                    body = self._parse_block()  # consumes up to and including ";"
                    functions.append(Function(num, body, position))

                else:
                    op = self._parse_single_op()
                    if op is not None:
                        main_code.append(op)
        except TypeLayoutError as exc:
            raise ParseError(str(exc)) from exc

        return Program(functions, main_code, foreign)

    # ------------------------------------------------------------------
    # Foreign declarations and shared helpers
    # ------------------------------------------------------------------

    def _parse_foreign(self) -> Foreign:
        """Parse a foreign declaration:  @N "header.h" "symbol" arity ;"""
        at = self._advance()
        num = self._expect_int("Foreign function number", at)
        header = self._expect_string("Header name", at)
        symbol = self._expect_string("C symbol name", at)
        arity = self._expect_int("Foreign function arity", at)
        if not 0 <= arity <= MAX_FOREIGN_ARITY:
            raise ParseError(
                f"Foreign arity must be 0-{MAX_FOREIGN_ARITY}, got {arity} "
                f"at {at.line}:{at.col}"
            )
        if self._current().kind != ";":
            raise ParseError(
                f"Expected ';' after foreign declaration at {at.line}:{at.col}"
            )
        self._advance()
        return Foreign(num, header, symbol, arity)

    def _expect_int(self, what: str, at: Token) -> int:
        tok = self._current()
        if tok.kind not in ("NUM", "LIT") or not isinstance(tok.value, int):
            raise ParseError(f"{what} must be an integer at {at.line}:{at.col}")
        self._advance()
        return tok.value

    def _expect_string(self, what: str, at: Token) -> str:
        tok = self._current()
        if tok.kind != "STRING":
            raise ParseError(f"{what} must be a string at {at.line}:{at.col}")
        self._advance()
        return "".join(chr(code) for code in tok.value)

    def _expect(self, kind: str) -> Token:
        tok = self._current()
        if tok.kind != kind:
            raise ParseError(
                f"Expected '{kind}' but found {tok.value!r} at {tok.line}:{tok.col}"
            )
        return self._advance()

    def _expect_name(self, what: str = "identifier") -> str:
        tok = self._current()
        if tok.kind != "ID" or tok.value in _KEYWORDS:
            raise ParseError(f"Expected {what} at {tok.line}:{tok.col}")
        self._advance()
        return tok.value

    def _const_int(self) -> int:
        """An integer constant: a number, a char constant or an enum constant."""
        tok = self._current()
        if tok.kind in ("NUM", "LIT") and isinstance(tok.value, int):
            self._advance()
            return tok.value
        if tok.kind == "ID" and tok.value in self.enum_consts:
            self._advance()
            return self.enum_consts[tok.value]
        raise ParseError(f"Expected an integer constant at {tok.line}:{tok.col}")

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

    def _parse_until(self, closer: str, what: str, at: Token) -> List[Op]:
        """Parse ops up to a closing token (consumed); EOF before it is an error."""
        ops: List[Op] = []
        while not self._at_end() and self._current().kind != closer:
            op = self._parse_single_op()
            if op is not None:
                ops.append(op)
        if self._at_end():
            raise ParseError(f"Unterminated {what} starting at {at.line}:{at.col}")
        self._advance()
        return ops

    def _parse_ops_until(
        self, stops: tuple[str, ...], what: str = "expression"
    ) -> List[Op]:
        """Parse ops up to (not including) one of the stop token kinds."""
        ops: List[Op] = []
        while self._current().kind not in stops:
            if self._at_end():
                tok = self._current()
                raise ParseError(f"Unterminated {what} at {tok.line}:{tok.col}")
            op = self._parse_single_op()
            if op is not None:
                ops.append(op)
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
            if tok.kind == "NUM" and isinstance(tok.value, int) and tok.value == 28:
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

    # ------------------------------------------------------------------
    # Single operations
    # ------------------------------------------------------------------

    def _parse_single_op(self) -> Op | None:
        tok = self._current()

        if tok.kind == ";":
            # Bare semicolons outside a block are ignored (legacy tolerance)
            self._advance()
            return None

        if tok.kind == "ID":
            return self._parse_identifier_op(tok)

        if tok.kind == "\\":
            # Address-of: \lval, or \.N for the handle of function N
            self._advance()
            if self._current().kind == ".":
                self._advance()
                return ("FUNC_REF", self._expect_int("Function number", tok))
            return ("ADDR", self._parse_lval())

        if tok.kind in ("=", "[", "]", "{", "}", ",", "->"):
            raise ParseError(f"Unexpected {tok.kind!r} at {tok.line}:{tok.col}")

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

        if tok.kind == "$":
            # Foreign call: $N, where N was declared with @N
            self._advance()
            num = self._expect_int("Foreign function number", tok)
            return ("FFI_CALL", num)

        if tok.kind == ":":
            # Explicit conversion: :N converts the top of stack to C type N
            self._advance()
            code = self._expect_int("Cast type code", tok)
            return ("CAST", code)

        if tok.kind == "<":
            # BREAK: leave the innermost loop or switch
            self._advance()
            return ("BREAK", None)

        if tok.kind == ">":
            # CONTINUE: jump to the next iteration of the innermost loop
            self._advance()
            return ("CONTINUE", None)

        if tok.kind == "(":
            # DO-WHILE: ( <body> )  runs the body, then pops the flag it left
            self._advance()
            body = self._parse_until(")", "do-while body", tok)
            return ("DO_WHILE", body)

        if tok.kind == ")":
            raise ParseError(f"Unexpected ')' at {tok.line}:{tok.col}")

        if tok.kind == "LIT":
            # Literal constants (hex, octal, binary, char, suffixed) always push.
            self._advance()
            return ("NUM", tok.value)

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
            if value in _INTEGER_ARRAY_OPS:
                return (_INTEGER_ARRAY_OPS[value], None)

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

        # Everything else: single-character tokens (|, ^, &, *, ...)
        kind = tok.kind
        value = tok.value
        self._advance()
        return (kind, value)

    def _parse_identifier_op(self, tok: Token) -> Op | None:
        word = tok.value
        if self._starts_decl(tok):
            return self._parse_declaration()
        if word in self.enum_consts:
            self._advance()
            return ("NUM", self.enum_consts[word])
        if word == "sizeof":
            return self._parse_sizeof()
        if word == "switch":
            return self._parse_switch()
        if word == "goto":
            self._advance()
            name = self._expect_name("label name")
            self._expect(";")
            return ("GOTO", name)
        if word == "label":
            self._advance()
            name = self._expect_name("label name")
            self._expect(";")
            return ("LABEL", name)
        if word in ("case", "default"):
            raise ParseError(f"'{word}' outside a switch at {tok.line}:{tok.col}")
        if word in _KEYWORDS:
            raise ParseError(f"Unexpected keyword '{word}' at {tok.line}:{tok.col}")

        # An object name: assignment, call through a pointer, or a load.
        lval = self._parse_lval()
        if self._current().kind == "=":
            self._advance()
            rhs = self._parse_ops_until((";",), "assignment")
            if not rhs:
                raise ParseError(f"Missing value in assignment at {tok.line}:{tok.col}")
            self._expect(";")
            return ("ASSIGN", (lval, rhs))
        if self._current().kind == "(":
            self._advance()
            self._expect(")")
            return ("CALL_PTR", lval)
        return ("LOAD", lval)

    def _parse_lval(self) -> LVal:
        """Parse an object name followed by [index], .member and ->member steps."""
        tok = self._current()
        root = self._expect_name("object name")
        if root in self.enum_consts:
            raise ParseError(f"enumeration constant '{root}' is not an object")
        path: List[Tuple[str, Any]] = []
        while True:
            kind = self._current().kind
            if kind == "[":
                self._advance()
                ops = self._parse_ops_until(("]",), "subscript")
                if not ops:
                    raise ParseError(f"Empty subscript at {tok.line}:{tok.col}")
                self._expect("]")
                path.append(("index", ops))
            elif kind == "." and self._peek_next_kind() == "ID":
                self._advance()
                path.append(("dot", self._expect_name("member name")))
            elif kind == "->":
                self._advance()
                path.append(("arrow", self._expect_name("member name")))
            else:
                break
        return LVal(root, path)

    def _parse_sizeof(self) -> Op:
        self._advance()  # sizeof
        if self._current().kind == "(":
            nxt = self.tokens[self.i + 1]
            if self._starts_decl(nxt):
                self._advance()  # (
                ctype = self._parse_type_name()
                self._expect(")")
                return ("NUM", self._layout(lambda: ctype.bytes()))
            self._advance()  # (
            lval = self._parse_lval()
            self._expect(")")
            return ("SIZEOF_EXPR", lval)
        return ("SIZEOF_EXPR", self._parse_lval())

    def _parse_switch(self) -> Op:
        at = self._advance()  # switch
        scrutinee = self._parse_ops_until(("{",), "switch expression")
        if not scrutinee:
            raise ParseError(f"Missing switch expression at {at.line}:{at.col}")
        self._expect("{")
        groups: List[Tuple[Optional[int], List[Op]]] = []
        seen_default = False
        while True:
            tok = self._current()
            if tok.kind == "}":
                self._advance()
                break
            if self._at_end():
                raise ParseError(f"Unterminated switch at {at.line}:{at.col}")
            if tok.kind == "ID" and tok.value == "case":
                self._advance()
                label = self._const_int()
                self._expect(":")
                groups.append((label, []))
            elif tok.kind == "ID" and tok.value == "default":
                if seen_default:
                    raise ParseError(f"Duplicate default at {tok.line}:{tok.col}")
                seen_default = True
                self._advance()
                self._expect(":")
                groups.append((None, []))
            else:
                if not groups:
                    raise ParseError(
                        f"Statement before the first case label at {tok.line}:{tok.col}"
                    )
                op = self._parse_single_op()
                if op is not None:
                    groups[-1][1].append(op)
        return ("SWITCH", (scrutinee, groups))

    # ------------------------------------------------------------------
    # Declarations
    # ------------------------------------------------------------------

    def _starts_decl(self, tok: Token) -> bool:
        if tok.kind != "ID":
            return False
        word = tok.value
        return (
            word in _TYPE_WORDS
            or word in _QUALIFIERS
            or word in _STORAGE
            or word in ("struct", "union", "enum")
            or word in self.typedefs
        )

    def _parse_declaration(self) -> Op | None:
        """Parse a declaration statement, a typedef, or a bare tag definition."""
        at = self._current()
        base, storage, quals = self._parse_spec()
        if "restrict" in quals:
            raise ParseError(
                f"'restrict' must qualify a pointer declarator at {at.line}:{at.col}"
            )
        is_typedef = "typedef" in storage
        is_static = "static" in storage
        if self._current().kind == ";":
            self._advance()
            if is_typedef:
                raise ParseError(f"typedef without a name at {at.line}:{at.col}")
            return None

        decls: List[Decl] = []
        while True:
            name_tok = self._current()
            name, ctype = self._parse_declarator(base.with_quals(quals))
            if name is None:
                raise ParseError(
                    f"Declaration without a name at {name_tok.line}:{name_tok.col}"
                )
            if is_typedef:
                if name in self.typedefs or name in self.enum_consts:
                    raise ParseError(f"Redefinition of '{name}'")
                self.typedefs[name] = ctype
            else:
                if name in self.typedefs or name in self.enum_consts:
                    raise ParseError(
                        f"'{name}' is already a typedef name or enumeration constant"
                    )
                init: Any = None
                if self._current().kind == "=":
                    self._advance()
                    if self._current().kind == "{":
                        init = self._parse_init_list()
                    else:
                        ops = self._parse_ops_until((",", ";"), "initialiser")
                        if not ops:
                            raise ParseError(f"Missing initialiser for '{name}'")
                        init = Expr(ops)
                if ctype.kind == "array" and ctype.count is None:
                    if not isinstance(init, InitList):
                        raise ParseError(
                            f"Array '{name}' needs a size or an initialiser list"
                        )
                    ctype = array_of(ctype.target, _init_list_count(init))
                self._layout(lambda: ctype.cells())
                decls.append(Decl(name, ctype, init, is_static))
            if self._current().kind == ",":
                self._advance()
                continue
            self._expect(";")
            break

        if is_typedef:
            return None
        return ("DECL", decls)

    def _parse_spec(self) -> tuple[CType, list[str], list[str]]:
        """Parse declaration specifiers: returns (base type, storage, qualifiers)."""
        quals: list[str] = []
        storage: list[str] = []
        words: list[str] = []
        base: Optional[CType] = None
        while self._current().kind == "ID":
            tok = self._current()
            word = tok.value
            if word in _QUALIFIERS:
                quals.append(word)
                self._advance()
            elif word in _STORAGE:
                storage.append(word)
                self._advance()
            elif word in _TYPE_WORDS:
                if base is not None:
                    raise ParseError(
                        f"Conflicting type specifiers at {tok.line}:{tok.col}"
                    )
                words.append(word)
                self._advance()
            elif word == "void":
                raise ParseError(
                    "'void' objects are not supported; use a typed declaration"
                )
            elif word in ("struct", "union"):
                if base is not None or words:
                    raise ParseError(
                        f"Conflicting type specifiers at {tok.line}:{tok.col}"
                    )
                base = self._parse_struct()
            elif word == "enum":
                if base is not None or words:
                    raise ParseError(
                        f"Conflicting type specifiers at {tok.line}:{tok.col}"
                    )
                base = self._parse_enum()
            elif word in self.typedefs and base is None and not words:
                base = self.typedefs[word]
                self._advance()
            else:
                break
        if base is None:
            if not words:
                tok = self._current()
                raise ParseError(f"Expected a type at {tok.line}:{tok.col}")
            base = self._layout(lambda: arithmetic_from_words(words))
        return base, storage, quals

    def _parse_type_name(self) -> CType:
        """A type name as used in sizeof: specifiers plus an abstract declarator."""
        base, storage, quals = self._parse_spec()
        if storage:
            raise ParseError("storage class not allowed in a type name")
        if "restrict" in quals:
            raise ParseError("'restrict' must qualify a pointer declarator")
        _name, ctype = self._parse_declarator(base.with_quals(quals), abstract_ok=True)
        return ctype

    def _parse_declarator(
        self, base: CType, abstract_ok: bool = False
    ) -> tuple[Optional[str], CType]:
        """Parse a declarator and return (name, type).

        Supported forms: pointers (``*`` with qualifiers), a name, array
        dimensions, the function-pointer form ``(*name)()``, and arrays of
        function pointers ``(*name[N])()``.
        """
        t = base
        while self._current().kind == "*":
            self._advance()
            quals: list[str] = []
            while self._current().kind == "ID" and self._current().value in _QUALIFIERS:
                quals.append(self._advance().value)
            if "restrict" in quals:
                pass  # restrict on a pointer is allowed; codegen does not use it
            t = pointer_to(t, quals)

        if self._current().kind == "(" and self._peek_next_kind() == "*":
            self._advance()  # (
            self._advance()  # *
            name = self._expect_name("function pointer name")
            dims = self._parse_dims()
            self._expect(")")
            self._expect("(")
            if self._current().kind == "ID" and self._current().value == "void":
                self._advance()
            self._expect(")")
            return name, _apply_dims(pointer_to(function_type()), dims)

        name: Optional[str] = None
        if self._current().kind == "ID" and self._current().value not in _KEYWORDS:
            name = self._advance().value
        elif not abstract_ok:
            tok = self._current()
            raise ParseError(f"Expected a declarator name at {tok.line}:{tok.col}")

        return name, _apply_dims(t, self._parse_dims())

    def _parse_dims(self) -> list[Optional[int]]:
        """Parse zero or more ``[N]`` suffixes; an omitted size gives None."""
        dims: list[Optional[int]] = []
        while self._current().kind == "[":
            self._advance()
            if self._current().kind == "]":
                dims.append(None)
            else:
                dims.append(self._const_int())
            self._expect("]")
        for index, dim in enumerate(dims):
            if dim is None and index != 0:
                raise ParseError("Only the outermost array dimension may be omitted")
            if dim is not None and dim < 0:
                raise ParseError("Array size must not be negative")
        return dims

    def _parse_struct(self) -> CType:
        kw = self._advance().value  # struct | union
        is_union = kw == "union"
        tag: Optional[str] = None
        if self._current().kind == "ID" and self._current().value not in _KEYWORDS:
            tag = self._advance().value
        if self._current().kind != "{":
            if tag is None:
                tok = self._current()
                raise ParseError(
                    f"Expected a tag or member list at {tok.line}:{tok.col}"
                )
            key = (kw, tag)
            if key not in self.tags:
                self.tags[key] = new_struct(tag, is_union)
            return self.tags[key]

        if tag is not None and (kw, tag) in self.tags:
            st = self.tags[(kw, tag)]
            if st.complete:
                raise ParseError(f"Redefinition of {kw} '{tag}'")
        else:
            st = new_struct(tag, is_union)
            if tag is not None:
                self.tags[(kw, tag)] = st
        self._advance()  # {
        fields: list[tuple[str, CType]] = []
        while self._current().kind != "}":
            if self._at_end():
                raise ParseError(f"Unterminated {kw} body")
            base, storage, quals = self._parse_spec()
            if storage:
                raise ParseError("storage class not allowed in a member declaration")
            if "restrict" in quals:
                raise ParseError("'restrict' must qualify a pointer declarator")
            while True:
                name, ctype = self._parse_declarator(base.with_quals(quals))
                if name is None:
                    raise ParseError("Member without a name")
                fields.append((name, ctype))
                if self._current().kind == ",":
                    self._advance()
                    continue
                self._expect(";")
                break
        self._advance()  # }
        self._layout(lambda: complete_struct(st, fields))
        return st

    def _parse_enum(self) -> CType:
        self._advance()  # enum
        tag: Optional[str] = None
        if self._current().kind == "ID" and self._current().value not in _KEYWORDS:
            tag = self._advance().value
        if self._current().kind != "{":
            if tag is None:
                tok = self._current()
                raise ParseError(
                    f"Expected a tag or enumerator list at {tok.line}:{tok.col}"
                )
            if ("enum", tag) not in self.tags:
                raise ParseError(f"Use of undeclared enum '{tag}'")
            return scalar("enum")
        self._advance()  # {
        value = 0
        while self._current().kind != "}":
            name = self._expect_name("enumeration constant")
            if name in self.enum_consts or name in self.typedefs:
                raise ParseError(f"Redefinition of '{name}'")
            if self._current().kind == "=":
                self._advance()
                value = self._const_int()
            self.enum_consts[name] = value
            value += 1
            if self._current().kind == ",":
                self._advance()
                continue
            break
        self._expect("}")
        if tag is not None:
            self.tags[("enum", tag)] = scalar("enum")
        return scalar("enum")

    def _parse_init_list(self) -> InitList:
        self._expect("{")
        items: list = []
        while self._current().kind != "}":
            if self._at_end():
                raise ParseError("Unterminated initialiser list")
            designator = None
            tok = self._current()
            if tok.kind == "." and self._peek_next_kind() == "ID":
                self._advance()
                designator = ("field", self._advance().value)
                self._expect("=")
            elif tok.kind == "[":
                self._advance()
                designator = ("index", self._const_int())
                self._expect("]")
                self._expect("=")
            if self._current().kind == "{":
                value: Any = self._parse_init_list()
            else:
                ops = self._parse_ops_until((",", "}"), "initialiser")
                if not ops:
                    raise ParseError("Missing initialiser value")
                value = Expr(ops)
            items.append((designator, value))
            if self._current().kind == ",":
                self._advance()
                continue
            break
        self._expect("}")
        return InitList(items)

    def _layout(self, action):
        """Run a type-layout action, reporting failures as parse errors."""
        try:
            return action()
        except TypeLayoutError as exc:
            tok = self.tokens[max(self.i - 1, 0)]
            raise ParseError(f"{exc} at {tok.line}:{tok.col}") from exc

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


def _apply_dims(t: CType, dims: list[Optional[int]]) -> CType:
    """Wrap t in array types, the first dimension outermost as in C."""
    for dim in reversed(dims):
        t = array_of(t, dim)
    return t


def _init_list_count(init: InitList) -> int:
    """Number of elements an unsized array takes from its initialiser list."""
    pos = 0
    high = 0
    for designator, _value in init.items:
        if designator is not None:
            if designator[0] != "index":
                raise ParseError("Field designator used for an array element")
            pos = designator[1]
        pos += 1
        high = max(high, pos)
    return high
