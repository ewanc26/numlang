from __future__ import annotations

from typing import List, Set

from .ast import Program, Op


class SemanticError(Exception):
    pass


class SemanticAnalyzer:
    def analyze(self, program: Program) -> None:
        defined: Set[int] = {f.num for f in program.functions}
        errors: List[str] = []

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
    ) -> None:
        for kind, value in ops:
            if kind == "CALL":
                if value not in defined:
                    errors.append(
                        f"Semantic error in {context}: call to undefined function {value}"
                    )

            elif kind == "IF_BLOCK":
                then_ops, else_ops = value
                self._check_ops(then_ops, defined, errors, context=f"{context}/if_then")
                if else_ops is not None:
                    self._check_ops(else_ops, defined, errors, context=f"{context}/if_else")

            elif kind == "WHILE":
                body: List[Op] = value
                if not body:
                    errors.append(
                        f"Semantic error in {context}: WHILE has an empty body"
                    )
                else:
                    self._check_ops(body, defined, errors, context=f"{context}/while")

            elif kind == "REPEAT":
                body = value
                if not body:
                    errors.append(
                        f"Semantic error in {context}: REPEAT has an empty body"
                    )
                else:
                    self._check_ops(body, defined, errors, context=f"{context}/repeat")

            elif kind == "PUSH_VAR":
                if not (0 <= value <= 99):
                    errors.append(
                        f"Semantic error in {context}: variable index {value} out of range (0–99)"
                    )
