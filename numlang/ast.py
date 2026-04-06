from __future__ import annotations

from dataclasses import dataclass, field
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
