from __future__ import annotations

from dataclasses import dataclass
from typing import List, Any


@dataclass
class Function:
    num: int
    code: List[tuple[str, Any]]


@dataclass
class Program:
    functions: List[Function]
    main_code: List[tuple[str, Any]]