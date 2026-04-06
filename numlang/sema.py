from __future__ import annotations

from .ast import Program


class SemanticError(Exception):
    pass


class SemanticAnalyzer:
    def analyze(self, program: Program) -> None:
        # For now, no analysis
        pass