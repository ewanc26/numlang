"""AST node types for the Numlang compiler.

An Op is a (kind, value) pair representing a single instruction in the
intermediate representation between parsing and code generation.

The parser resolves every declaration to a concrete C type (see
ctypes_model), so code generation only needs names, addresses and layouts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple

from .ctypes_model import CType

# An instruction is a (kind, value) tuple. Value shapes by kind:
#   numeric/legacy ops   None, int or float (see parser tables)
#   IF_BLOCK             (then_ops, else_ops_or_None)
#   WHILE/REPEAT/DO_WHILE  List[Op]
#   LOAD/ADDR/CALL_PTR/SIZEOF_EXPR   LVal
#   ASSIGN               (LVal, List[Op])
#   FUNC_REF             int (function number)
#   DECL                 List[Decl]
#   SWITCH               (List[Op], List[(label_or_None, List[Op])])
#   GOTO / LABEL         str (label name)
Op = Tuple[str, Any]


@dataclass
class Function:
    num: int
    body: List[Op]
    # Number of top-level ops that precede the definition. A function sees
    # only the file-scope names declared before this point, as in C.
    position: int = 0


@dataclass
class Foreign:
    num: int
    header: str
    symbol: str
    arity: int


@dataclass
class Program:
    functions: List[Function]
    main_code: List[Op]
    foreign: List[Foreign] = field(default_factory=list)


@dataclass
class Decl:
    """A declared object: resolved type, optional initialiser, storage class."""

    name: str
    ctype: CType
    init: Any = None  # Expr, InitList or None
    is_static: bool = False


@dataclass
class Expr:
    """An initialiser expression: a list of ops that leaves one value."""

    ops: List[Op]


@dataclass
class InitList:
    """A braced initialiser list.

    ``items`` holds (designator, value) pairs. A designator is None,
    ("field", name) or ("index", n). A value is an Expr or a nested InitList.
    """

    items: List[Tuple[Optional[tuple], Any]]


@dataclass
class LVal:
    """A named object and the accessors applied to it.

    ``path`` holds ("index", ops), ("dot", name) and ("arrow", name) steps,
    applied in order to the object named ``root``.
    """

    root: str
    path: List[Tuple[str, Any]]


def lval_child_lists(lval: LVal) -> List[List[Op]]:
    return [arg for kind, arg in lval.path if kind == "index"]


def init_child_lists(init: Any) -> List[List[Op]]:
    if init is None:
        return []
    if isinstance(init, Expr):
        return [init.ops]
    out: List[List[Op]] = []
    for _designator, item in init.items:
        out += init_child_lists(item)
    return out


def child_op_lists(op: Op) -> List[List[Op]]:
    """Return the nested op lists of an op, for passes that walk the tree."""
    kind, value = op
    if kind == "IF_BLOCK":
        then_ops, else_ops = value
        return [then_ops] + ([else_ops] if else_ops is not None else [])
    if kind in ("WHILE", "REPEAT", "DO_WHILE"):
        return [value]
    if kind in ("LOAD", "ADDR", "CALL_PTR", "SIZEOF_EXPR"):
        return lval_child_lists(value)
    if kind == "ASSIGN":
        lval, rhs = value
        return lval_child_lists(lval) + [rhs]
    if kind == "DECL":
        out: List[List[Op]] = []
        for decl in value:
            out += init_child_lists(decl.init)
        return out
    if kind == "SWITCH":
        ops, groups = value
        return [ops] + [group_ops for _label, group_ops in groups]
    return []
