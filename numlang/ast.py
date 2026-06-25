"""AST node types for the Numlang compiler.

An Op is a (kind, value) pair representing a single instruction in the
intermediate representation between parsing and code generation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Any, Tuple

# An instruction is a (kind, value) tuple.
# value may be:
#   - None          for ops that need no operand
#   - int/float     for literals
#   - List[Op]      for WHILE bodies
Op = Tuple[str, Any]


@dataclass
class Function:
    num: int
    body: List[Op]


@dataclass
class Program:
    functions: List[Function]
    main_code: List[Op]
