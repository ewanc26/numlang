from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class Program:
    operations: List[tuple[str, Any]]