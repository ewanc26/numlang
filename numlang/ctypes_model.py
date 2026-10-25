"""C type model for Numlang's memory model.

Two layouts are kept side by side:

* The cell layout addresses storage. Every scalar and pointer occupies one
  cell (one double). Arrays and structs are laid out cell after cell in
  declaration order; union members all start at cell 0.
* The byte layout is used only by ``sizeof``. It follows the LP64 rules that
  gcc and clang use on 64-bit Linux and macOS: natural alignment, struct
  padding, and union sizes rounded to their alignment.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional

# Scalar keys -> (cast code for :N and num_cast, size in bytes).
# Cast codes match the table documented in README.md and num_cast in codegen_c.
SCALARS: dict[str, tuple[int, int]] = {
    "char": (0, 1),  # signed char
    "uchar": (1, 1),
    "short": (2, 2),
    "ushort": (3, 2),
    "int": (4, 4),
    "uint": (5, 4),
    "long": (6, 8),
    "ulong": (7, 8),
    "llong": (8, 8),
    "ullong": (9, 8),
    "float": (10, 4),
    "double": (11, 8),
    "bool": (12, 1),
    "enum": (4, 4),  # enumerations are int-sized, as in gcc and clang
}

POINTER_BYTES = 8
QUALIFIERS = ("const", "volatile", "restrict")


class TypeLayoutError(ValueError):
    """Raised for types that cannot be laid out (incomplete or invalid)."""


@dataclass(eq=False)
class Member:
    name: str
    ctype: "CType"
    cell_off: int
    byte_off: int


@dataclass(eq=False)
class CType:
    """A C type. ``kind`` is scalar, pointer, array, struct or func."""

    kind: str
    name: str = ""  # scalar key (see SCALARS)
    target: Optional["CType"] = None  # pointee, element or function
    count: Optional[int] = None  # array element count
    quals: frozenset = frozenset()
    tag: Optional[str] = None  # struct / union tag, for diagnostics
    members: Dict[str, Member] = field(default_factory=dict)
    order: List[str] = field(default_factory=list)
    is_union: bool = False
    complete: bool = False
    size_cells: int = 0
    size_bytes: int = 0
    align_bytes: int = 1

    # ---- classification ------------------------------------------------

    def is_scalar(self) -> bool:
        return self.kind in ("scalar", "pointer")

    def is_aggregate(self) -> bool:
        return self.kind in ("array", "struct")

    def is_const(self) -> bool:
        return "const" in self.quals

    def struct_id(self) -> int:
        """Identity of a struct definition, shared by qualified copies."""
        return id(self.members)

    # ---- layout --------------------------------------------------------

    def cells(self) -> int:
        if self.kind == "scalar" or self.kind == "pointer":
            return 1
        if self.kind == "array":
            if self.count is None:
                raise TypeLayoutError("array of unknown size used as an object")
            return self.count * self.target.cells()
        if self.kind == "struct":
            self._need_complete()
            return self.size_cells
        raise TypeLayoutError("function type used as an object")

    def bytes(self) -> int:
        if self.kind == "scalar":
            return SCALARS[self.name][1]
        if self.kind == "pointer":
            return POINTER_BYTES
        if self.kind == "array":
            if self.count is None:
                raise TypeLayoutError("sizeof applied to an array of unknown size")
            return self.count * self.target.bytes()
        if self.kind == "struct":
            self._need_complete()
            return self.size_bytes
        raise TypeLayoutError("sizeof applied to a function type")

    def align(self) -> int:
        if self.kind == "scalar":
            return SCALARS[self.name][1]
        if self.kind == "pointer":
            return POINTER_BYTES
        if self.kind == "array":
            return self.target.align()
        if self.kind == "struct":
            self._need_complete()
            return self.align_bytes
        return 1

    def cast_code(self) -> int:
        """Cast code used when storing a double into this scalar type."""
        if self.kind == "scalar":
            return SCALARS[self.name][0]
        raise TypeLayoutError("not an arithmetic type")

    def _need_complete(self) -> None:
        if not self.complete:
            tag = f" '{self.tag}'" if self.tag else ""
            raise TypeLayoutError(f"use of incomplete type{tag}")

    # ---- qualifiers ----------------------------------------------------

    def with_quals(self, extra) -> "CType":
        """Return this type with extra qualifiers applied.

        For arrays the qualifiers go to the element type, as in C.
        """
        extra = frozenset(extra)
        if not extra:
            return self
        if self.kind == "array":
            return replace(self, target=self.target.with_quals(extra))
        return replace(self, quals=self.quals | extra)

    def unqualified(self) -> "CType":
        return replace(self, quals=frozenset()) if self.quals else self

    # ---- helpers for struct layout -------------------------------------

    def member(self, name: str) -> Member:
        self._need_complete()
        if name not in self.members:
            tag = f" '{self.tag}'" if self.tag else ""
            raise TypeLayoutError(f"no member named '{name}' in{tag or ' struct'}")
        return self.members[name]


def scalar(name: str) -> CType:
    return CType("scalar", name=name, complete=True)


def pointer_to(target: CType, quals=()) -> CType:
    return CType("pointer", target=target, quals=frozenset(quals), complete=True)


def array_of(elem: CType, count: Optional[int]) -> CType:
    return CType("array", target=elem, count=count, complete=True)


def function_type() -> CType:
    return CType("func", complete=True)


def new_struct(tag: Optional[str], is_union: bool) -> CType:
    """An incomplete struct or union, filled in later by complete_struct."""
    return CType("struct", tag=tag, is_union=is_union, complete=False)


def complete_struct(st: CType, fields: list[tuple[str, CType]]) -> None:
    """Fill in members and compute both layouts for a struct or union."""
    if st.complete:
        raise TypeLayoutError(f"redefinition of '{st.tag or 'struct'}'")
    if not fields:
        raise TypeLayoutError("struct or union with no members")
    seen: set[str] = set()
    for name, ctype in fields:
        if name in seen:
            raise TypeLayoutError(f"duplicate member '{name}'")
        seen.add(name)
        if ctype.kind == "func":
            raise TypeLayoutError(f"member '{name}' has function type")
    members: Dict[str, Member] = {}
    order: List[str] = []
    align = 1
    if st.is_union:
        cells = 0
        size = 0
        for name, ctype in fields:
            members[name] = Member(name, ctype, 0, 0)
            order.append(name)
            cells = max(cells, ctype.cells())
            size = max(size, ctype.bytes())
            align = max(align, ctype.align())
        size_bytes = _round_up(size, align)
        size_cells = cells
    else:
        cells = 0
        offset = 0
        for name, ctype in fields:
            a = ctype.align()
            offset = _round_up(offset, a)
            members[name] = Member(name, ctype, cells, offset)
            order.append(name)
            cells += ctype.cells()
            offset += ctype.bytes()
            align = max(align, a)
        size_bytes = _round_up(offset, align)
        size_cells = cells
    st.members = members
    st.order = order
    st.align_bytes = align
    st.size_bytes = size_bytes
    st.size_cells = size_cells
    st.complete = True


def _round_up(value: int, unit: int) -> int:
    return (value + unit - 1) // unit * unit


def arithmetic_from_words(words: list[str]) -> CType:
    """Map C arithmetic type keywords (in any order) to a scalar type."""
    counts: dict[str, int] = {}
    for word in words:
        counts[word] = counts.get(word, 0) + 1
    if counts.get("_Bool"):
        if len(words) != 1:
            raise TypeLayoutError("invalid combination of type specifiers")
        return scalar("bool")
    if counts.get("float"):
        if len(words) != 1:
            raise TypeLayoutError("invalid combination of type specifiers")
        return scalar("float")
    if counts.get("double"):
        if counts.get("long") or len(words) != 1:
            raise TypeLayoutError(
                "'long double' and combined double types are not supported"
            )
        return scalar("double")
    unsigned = bool(counts.get("unsigned"))
    if counts.get("char"):
        if counts.get("short") or counts.get("long") or counts.get("int"):
            raise TypeLayoutError("invalid combination of type specifiers")
        return scalar("uchar" if unsigned else "char")
    if counts.get("short"):
        if counts.get("long"):
            raise TypeLayoutError("invalid combination of type specifiers")
        return scalar("ushort" if unsigned else "short")
    longs = counts.get("long", 0)
    if longs >= 2:
        return scalar("ullong" if unsigned else "llong")
    if longs == 1:
        return scalar("ulong" if unsigned else "long")
    return scalar("uint" if unsigned else "int")
