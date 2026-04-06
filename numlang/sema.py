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
        for idx, (kind, value) in enumerate(ops):
            if kind == "CALL":
                if value not in defined:
                    errors.append(
                        f"Semantic error in {context}: call to undefined function {value}"
                    )
            elif kind == "IF":
                # IF should not be the last instruction
                if idx == len(ops) - 1:
                    errors.append(
                        f"Semantic error in {context}: IF has no following instruction"
                    )
            elif kind == "WHILE":
                body: List[Op] = value  # type: ignore[assignment]
                if not body:
                    errors.append(
                        f"Semantic error in {context}: WHILE (30) has an empty body"
                    )
                else:
                    self._check_ops(body, defined, errors, context=f"{context}/while")
