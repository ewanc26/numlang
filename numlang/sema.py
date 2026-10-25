"""Semantic analysis pass for Numlang programs.

Checks for undefined function calls, empty loop bodies, out-of-range
variable indices, misplaced break/continue, duplicate switch labels and
unresolved goto targets before code generation.
"""

from __future__ import annotations

from typing import List, Set

from .ast import Op, Program, child_op_lists

# Type codes accepted by the :N conversion operator (see the num_cast helper in codegen_c).
MAX_CAST_CODE = 12


class SemanticError(Exception):
    """Raised when a program violates Numlang's semantic rules."""


class SemanticAnalyzer:
    """Walks the AST to catch errors the parser can't detect.

    Currently checks:
      - All CALL, CALL_PTR/FUNC_REF and FFI_CALL targets are declared.
      - WHILE, REPEAT and DO-WHILE bodies contain at least one op.
      - PUSH_VAR indices stay within 0-99.
      - BREAK appears inside a loop or switch; CONTINUE inside a loop.
      - SWITCH labels are unique and there is at most one default.
      - Each GOTO names a LABEL in the same function, and labels are unique.
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
            context = f"function {func.num}"
            self._check_ops(func.body, defined, errors, context)
            self._check_labels(func.body, context, errors)

        self._check_ops(program.main_code, defined, errors, "main")
        self._check_labels(program.main_code, "main", errors)

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
        for op in ops:
            kind, value = op
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

            elif kind == "FUNC_REF":
                if value not in defined:
                    errors.append(
                        f"Semantic error in {context}: reference to undefined function {value}"
                    )

            elif kind == "FFI_CALL":
                if value not in self._foreign:
                    errors.append(
                        f"Semantic error in {context}: call to undeclared foreign function {value}"
                    )

            elif kind in ("WHILE", "DO_WHILE", "REPEAT"):
                label = {"WHILE": "WHILE", "DO_WHILE": "DO-WHILE", "REPEAT": "REPEAT"}[
                    kind
                ]
                if not value:
                    errors.append(
                        f"Semantic error in {context}: {label} has an empty body"
                    )
                    continue

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

            elif kind == "SWITCH":
                self._check_switch(value, errors, context)

            # Recurse into nested op lists with the loop/switch context updated.
            if kind == "SWITCH":
                scrutinee, groups = value
                self._check_ops(scrutinee, defined, errors, context, in_loop, in_switch)
                for _label, group_ops in groups:
                    self._check_ops(group_ops, defined, errors, context, in_loop, True)
            elif kind in ("WHILE", "DO_WHILE", "REPEAT"):
                self._check_ops(value, defined, errors, context, True, in_switch)
            else:
                for nested in child_op_lists(op):
                    self._check_ops(
                        nested, defined, errors, context, in_loop, in_switch
                    )

    def _check_switch(self, value, errors: List[str], context: str) -> None:
        _scrutinee, groups = value
        seen: Set[int] = set()
        defaults = 0
        for label, _ops in groups:
            if label is None:
                defaults += 1
                continue
            if label in seen:
                errors.append(
                    f"Semantic error in {context}: duplicate case label {label}"
                )
            seen.add(label)
        if defaults > 1:
            errors.append(f"Semantic error in {context}: more than one default label")

    def _check_labels(self, ops: List[Op], context: str, errors: List[str]) -> None:
        defined: Set[str] = set()
        used: Set[str] = set()
        self._collect_labels(ops, defined, used, errors, context)
        for name in sorted(used - defined):
            errors.append(
                f"Semantic error in {context}: goto to undefined label '{name}'"
            )

    def _collect_labels(
        self,
        ops: List[Op],
        defined: Set[str],
        used: Set[str],
        errors: List[str],
        context: str,
    ) -> None:
        for op in ops:
            kind, value = op
            if kind == "LABEL":
                if value in defined:
                    errors.append(
                        f"Semantic error in {context}: duplicate label '{value}'"
                    )
                defined.add(value)
            elif kind == "GOTO":
                used.add(value)
            for nested in child_op_lists(op):
                self._collect_labels(nested, defined, used, errors, context)
