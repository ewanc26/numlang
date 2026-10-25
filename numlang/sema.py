"""Semantic analysis pass for Numlang programs.

Checks for undefined function calls, empty loop bodies, and out-of-range
variable indices before code generation.
"""

from __future__ import annotations

from typing import List, Set

from .ast import Op, Program

# Type codes accepted by the :N conversion operator (see the num_cast helper in codegen_c).
MAX_CAST_CODE = 12


class SemanticError(Exception):
    """Raised when a program violates Numlang's semantic rules."""


class SemanticAnalyzer:
    """Walks the AST to catch errors the parser can't detect.

    Currently checks:
      - All CALL targets reference a defined function.
      - WHILE, REPEAT and DO-WHILE bodies contain at least one op.
      - PUSH_VAR indices stay within 0-99.
      - BREAK appears inside a loop or switch; CONTINUE inside a loop.
    """

    def analyze(self, program: Program) -> None:
        defined: Set[int] = {f.num for f in program.functions}
        errors: List[str] = []

        self._foreign: Set[int] = set()
        for decl in program.foreign:
            if decl.num in self._foreign:
                errors.append(
                    f"Semantic error: foreign function {decl.num} declared twice"
                )
            self._foreign.add(decl.num)

        for func in program.functions:
            self._check_ops(func.body, defined, errors, context=f"function {func.num}")

        self._check_ops(program.main_code, defined, errors, context="main")

        if errors:
            raise SemanticError("\n".join(errors))

    # ------------------------------------------------------------------

    def _check_ops(
        self,
        ops: List[Op],
        defined: Set[int],
        errors: List[str],
        context: str,
        in_loop: bool = False,
        in_switch: bool = False,
    ) -> None:
        for kind, value in ops:
            if kind == "BREAK":
                if not (in_loop or in_switch):
                    errors.append(
                        f"Semantic error in {context}: break outside a loop or switch"
                    )

            elif kind == "CONTINUE":
                if not in_loop:
                    errors.append(
                        f"Semantic error in {context}: continue outside a loop"
                    )

            elif kind == "CALL":
                if value not in defined:
                    errors.append(
                        f"Semantic error in {context}: call to undefined function {value}"
                    )

            elif kind == "FFI_CALL":
                if value not in self._foreign:
                    errors.append(
                        f"Semantic error in {context}: call to undeclared foreign function {value}"
                    )

            elif kind == "IF_BLOCK":
                then_ops, else_ops = value
                self._check_ops(
                    then_ops,
                    defined,
                    errors,
                    context=f"{context}/if_then",
                    in_loop=in_loop,
                    in_switch=in_switch,
                )
                if else_ops is not None:
                    self._check_ops(
                        else_ops,
                        defined,
                        errors,
                        context=f"{context}/if_else",
                        in_loop=in_loop,
                        in_switch=in_switch,
                    )

            elif kind == "WHILE":
                body: List[Op] = value
                if not body:
                    errors.append(
                        f"Semantic error in {context}: WHILE has an empty body"
                    )
                else:
                    self._check_ops(
                        body, defined, errors, context=f"{context}/while", in_loop=True
                    )

            elif kind == "DO_WHILE":
                body = value
                if not body:
                    errors.append(
                        f"Semantic error in {context}: DO-WHILE has an empty body"
                    )
                else:
                    self._check_ops(
                        body, defined, errors, context=f"{context}/do", in_loop=True
                    )

            elif kind == "REPEAT":
                body = value
                if not body:
                    errors.append(
                        f"Semantic error in {context}: REPEAT has an empty body"
                    )
                else:
                    self._check_ops(
                        body, defined, errors, context=f"{context}/repeat", in_loop=True
                    )

            elif kind == "CAST":
                if not (0 <= value <= MAX_CAST_CODE):
                    errors.append(
                        f"Semantic error in {context}: cast type code {value} out of range (0-{MAX_CAST_CODE})"
                    )

            elif kind == "PUSH_VAR":
                if not (0 <= value <= 99):
                    errors.append(
                        f"Semantic error in {context}: variable index {value} out of range (0–99)"
                    )
