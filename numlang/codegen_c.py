"""C code generator for Numlang.

Translates the analysed AST into a standalone C file. Values are doubles
held in one memory array of cells. Scalars and pointers take one cell,
arrays and structs take consecutive cells, and a pointer value is the index
of the cell it addresses. File-scope and static objects have fixed cells;
automatic objects live in a frame on a runtime frame stack.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .ast import Expr, InitList, LVal, Op, Program, child_op_lists
from .ctypes_model import CType, function_type, pointer_to
from .sema import SemanticError

MEM_CELLS = 1 << 18
FIRST_OBJECT_CELL = 101  # cells 1..100 hold the legacy |n variables

# Operations allowed in initialisers of file-scope and static objects.
# They are evaluated before main starts, so they must not read memory,
# call functions or perform I/O.
_PURE_KINDS = frozenset(
    {
        "NUM",
        "CAST",
        "FUNC_REF",
        "DUP",
        "SWAP",
        "DROP",
        "+",
        "-",
        "*",
        "/",
        "%",
        "LT",
        "GT",
        "EQ",
        "NE",
        "LE",
        "GE",
        "NOT",
        "LOGICAL_OR",
        "LOGICAL_AND",
        "ABS",
        "SQRT",
        "FLOOR",
        "CEIL",
        "ROUND",
        "TRUNC",
        "NEG",
        "MIN2",
        "MAX2",
        "POW",
        "LOG",
        "LOG10",
        "SIN",
        "COS",
        "TAN",
        "ASIN",
        "ACOS",
        "ATAN",
        "ATAN2",
        "IMOD",
        "IDIV",
        "BAND",
        "BOR",
        "BXOR",
        "BNOT",
        "BSHL",
        "BSHR",
    }
)


@dataclass
class CodegenContext:
    """Configuration for the code generator — currently just stack depth."""

    stack_size: int = 1000


@dataclass
class Symbol:
    """A named object. ``addr`` is an absolute cell when ``static``,
    otherwise an offset from the current frame base ``_fb``."""

    ctype: CType
    static: bool
    addr: int


def _arith_name(name: str) -> str:
    return "int" if name == "enum" else name


def _compatible(a: CType, b: CType) -> bool:
    """Type compatibility for pointer targets; qualifiers are ignored here."""
    if a.kind != b.kind:
        return False
    if a.kind == "scalar":
        return _arith_name(a.name) == _arith_name(b.name)
    if a.kind == "pointer":
        return _compatible(a.target, b.target)
    if a.kind == "array":
        return a.count == b.count and _compatible(a.target, b.target)
    if a.kind == "struct":
        return a.struct_id() == b.struct_id()
    return True


def _has_const_member(ct: CType) -> bool:
    for member in ct.members.values():
        if member.ctype.is_const():
            return True
        if member.ctype.kind == "struct" and _has_const_member(member.ctype):
            return True
    return False


class CCodeGenerator:
    """Emits a complete C source file from a Numlang Program AST."""

    def __init__(self, program: Program, context: CodegenContext):
        self.program = program
        self.context = context
        self._label_counter = 0
        self._tmp_counter = 0
        self._foreign = {decl.num: decl for decl in program.foreign}
        self._file: List[Tuple[int, str, Symbol]] = []
        self._static_top = FIRST_OBJECT_CELL
        self._global_init: List[str] = []
        self._static_init: List[str] = []
        self._scopes: List[Dict[str, Symbol]] = []
        self._frame_top = 0
        self._limit = -1  # file-scope names with index <= limit are visible

    # ------------------------------------------------------------------
    # Names, storage and scopes
    # ------------------------------------------------------------------

    def _new_label(self) -> int:
        label = self._label_counter
        self._label_counter += 1
        return label

    def _new_tmp(self, prefix: str) -> str:
        self._tmp_counter += 1
        return f"_{prefix}{self._tmp_counter}"

    def _lookup(self, name: str) -> Optional[Symbol]:
        for scope in reversed(self._scopes):
            if name in scope:
                return scope[name]
        for idx, sym_name, sym in reversed(self._file):
            if idx <= self._limit and sym_name == name:
                return sym
        return None

    def _require(self, name: str) -> Symbol:
        sym = self._lookup(name)
        if sym is None:
            raise SemanticError(f"undeclared name '{name}'")
        return sym

    def _declare_local(self, name: str, sym: Symbol) -> None:
        scope = self._scopes[-1]
        if name in scope:
            raise SemanticError(f"redeclaration of '{name}'")
        scope[name] = sym

    def _alloc_static(self, ctype: CType) -> Symbol:
        addr = self._static_top
        self._static_top += ctype.cells()
        if self._static_top > MEM_CELLS // 2:
            raise SemanticError("static storage exceeds the memory model limit")
        return Symbol(ctype, True, addr)

    def _alloc_frame(self, ctype: CType) -> Symbol:
        addr = self._frame_top
        self._frame_top += ctype.cells()
        return Symbol(ctype, False, addr)

    @staticmethod
    def _sym_base(sym: Symbol) -> str:
        return str(sym.addr) if sym.static else f"_fb + {sym.addr}"

    # ------------------------------------------------------------------
    # Types of lvalues (static, no code emitted)
    # ------------------------------------------------------------------

    @staticmethod
    def _step_type(ct: CType, kind: str, arg) -> CType:
        if kind == "index":
            if ct.kind == "array":
                return ct.target
            if ct.kind == "pointer" and ct.target.kind != "func":
                return ct.target
            raise SemanticError("subscript of a value that is not an array or pointer")
        if kind == "dot":
            if ct.kind != "struct":
                raise SemanticError("'.' applied to a value that is not a struct")
            return ct.member(arg).ctype.with_quals(ct.quals)
        if ct.kind != "pointer" or ct.target.kind != "struct":
            raise SemanticError(
                "'->' applied to a value that is not a pointer to struct"
            )
        return ct.target.member(arg).ctype.with_quals(ct.target.quals)

    def _lval_type(self, lval: LVal) -> CType:
        ct = self._require(lval.root).ctype
        for kind, arg in lval.path:
            ct = self._step_type(ct, kind, arg)
        return ct

    # ------------------------------------------------------------------
    # Type checks for assignments and initialisers
    # ------------------------------------------------------------------

    def _check_assign(self, lhs: CType, ops: List[Op]) -> None:
        """Check a single-operand right-hand side against the target type.

        Only a right-hand side that is one operand is checked statically;
        longer expressions are left to the C compiler and runtime.
        """
        if len(ops) != 1:
            return
        kind, arg = ops[0]
        if kind == "NUM":
            if lhs.kind == "pointer" and arg != 0:
                raise SemanticError("integer assigned to a pointer without a cast")
            return
        if kind == "LOAD":
            src = self._lval_type(arg)
            if src.kind == "struct":
                raise SemanticError("struct value used as a scalar")
            rt = pointer_to(src.target) if src.kind == "array" else src
        elif kind == "ADDR":
            rt = pointer_to(self._lval_type(arg))
        elif kind == "FUNC_REF":
            rt = pointer_to(function_type())
        else:
            return
        if lhs.kind == "pointer":
            if rt.kind != "pointer":
                raise SemanticError("integer assigned to a pointer without a cast")
            if rt.target.is_const() and not lhs.target.is_const():
                raise SemanticError("assignment discards a const qualifier")
            if not _compatible(lhs.target, rt.target):
                raise SemanticError("incompatible pointer types in assignment")
        elif rt.kind == "pointer":
            raise SemanticError(
                "pointer assigned to an arithmetic object without a cast"
            )

    def _check_pure(self, ops: List[Op]) -> None:
        for kind, value in ops:
            if kind in _PURE_KINDS or kind == "SIZEOF_EXPR":
                continue
            if kind == "ADDR":
                sym = self._require(value.root)
                if not sym.static:
                    raise SemanticError(
                        "initialiser of a static or file-scope object takes the "
                        "address of an automatic object"
                    )
                for sub in child_op_lists((kind, value)):
                    self._check_pure(sub)
                continue
            raise SemanticError(
                "initialiser of a static or file-scope object is not a constant expression"
            )

    # ------------------------------------------------------------------
    # Initialisers
    # ------------------------------------------------------------------

    @staticmethod
    def _sub_count(ct: CType) -> int:
        if ct.kind == "array":
            return ct.count
        return len(ct.order)

    @staticmethod
    def _sub_at(ct: CType, idx: int) -> Tuple[int, CType]:
        if ct.kind == "array":
            return idx * ct.target.cells(), ct.target
        member = ct.members[ct.order[idx]]
        return member.cell_off, member.ctype

    @staticmethod
    def _sub_find(ct: CType, desig) -> Optional[int]:
        kind, arg = desig
        if ct.kind == "array":
            return arg if kind == "index" and 0 <= arg < ct.count else None
        if kind == "field" and arg in ct.members:
            return ct.order.index(arg)
        return None

    def _plan(self, ct: CType, base: int, items, k: int, out, braced: bool) -> int:
        """Assign each initialiser value to a cell offset, following C's
        brace elision. Returns the index of the first unconsumed item."""
        n = len(items)
        count = self._sub_count(ct)
        idx = 0
        while k < n:
            desig, value = items[k]
            if desig is not None:
                pos = self._sub_find(ct, desig)
                if pos is None:
                    if braced:
                        raise SemanticError(
                            "designator does not name a member of this object"
                        )
                    return k
                idx = pos
            elif idx >= count:
                break
            off, sub = self._sub_at(ct, idx)
            if sub.is_aggregate():
                if isinstance(value, InitList):
                    self._plan(sub, base + off, value.items, 0, out, True)
                    k += 1
                else:
                    if desig is not None:
                        raise SemanticError(
                            "a designated aggregate member needs braces"
                        )
                    k = self._plan(sub, base + off, items, k, out, False)
            else:
                if isinstance(value, InitList):
                    if (
                        len(value.items) != 1
                        or value.items[0][0] is not None
                        or not isinstance(value.items[0][1], Expr)
                    ):
                        raise SemanticError("scalar initialiser must be one expression")
                    out.append((base + off, sub, value.items[0][1].ops))
                else:
                    out.append((base + off, sub, value.ops))
                k += 1
            idx += 1
            if ct.kind == "struct" and ct.is_union:
                break
        if braced and k < n:
            raise SemanticError("excess elements in initialiser")
        return k

    def _init_lines(self, sym: Symbol, init, pure: bool, indent: int) -> List[str]:
        plan: List[Tuple[int, CType, List[Op]]] = []
        ct = sym.ctype
        if isinstance(init, Expr):
            if not ct.is_scalar():
                raise SemanticError("aggregate object needs a braced initialiser")
            plan.append((0, ct, init.ops))
        elif ct.is_scalar():
            if (
                len(init.items) != 1
                or init.items[0][0] is not None
                or not isinstance(init.items[0][1], Expr)
            ):
                raise SemanticError("scalar initialiser must be one expression")
            plan.append((0, ct, init.items[0][1].ops))
        else:
            self._plan(ct, 0, init.items, 0, plan, braced=True)
        lines: List[str] = []
        for off, ty, ops in plan:
            if pure:
                self._check_pure(ops)
            self._check_assign(ty, ops)
            lines += self._store_lines(sym, off, ty, ops, indent)
        return lines

    def _store_lines(
        self, sym: Symbol, off: int, ty: CType, ops: List[Op], indent: int
    ) -> List[str]:
        pad = "    " * indent
        cell = sym.addr + off
        target = str(cell) if sym.static else f"_fb + {cell}"
        conv = self._conversion(ty)
        return (
            [pad + "{"]
            + self._emit_ops(ops, indent + 1)
            + [f"{pad}    mem[cell_chk({target})] = {conv};", pad + "}"]
        )

    @staticmethod
    def _conversion(ty: CType) -> str:
        """C expression that pops a value and converts it for storage in ty."""
        if ty.kind == "pointer" or ty.name == "double":
            return "pop()"
        return f"num_cast(pop(), {ty.cast_code()})"

    def _emit_decls(self, decls, indent: int) -> List[str]:
        lines: List[str] = []
        pad = "    " * indent
        for decl in decls:
            if decl.is_static:
                sym = self._alloc_static(decl.ctype)
                self._declare_local(decl.name, sym)
                if decl.init is not None:
                    self._static_init += self._init_lines(
                        sym, decl.init, pure=True, indent=1
                    )
            else:
                sym = self._alloc_frame(decl.ctype)
                lines.append(
                    f"{pad}zero_cells(_fb + {sym.addr}, {decl.ctype.cells()});"
                )
                if decl.init is not None:
                    lines += self._init_lines(sym, decl.init, pure=False, indent=indent)
                self._declare_local(decl.name, sym)
        return lines

    # ------------------------------------------------------------------
    # Lvalues
    # ------------------------------------------------------------------

    def _lval_addr(self, lval: LVal, indent: int) -> Tuple[List[str], str, CType]:
        """Emit code that leaves the cell address of lval in a C variable.

        Returns (lines, variable name, C-side static type of the object).
        """
        pad = "    " * indent
        inner = "    " * (indent + 1)
        sym = self._require(lval.root)
        name = self._new_tmp("a")
        lines = [f"{pad}long {name} = {self._sym_base(sym)};"]
        ct = sym.ctype
        for kind, arg in lval.path:
            new = self._step_type(ct, kind, arg)
            if kind == "index":
                iv = self._new_tmp("i")
                lines.append(pad + "{")
                lines += self._emit_ops(arg, indent + 1)
                lines.append(f"{inner}long {iv} = (long)pop();")
                if ct.kind == "array":
                    lines.append(
                        f'{inner}if ({iv} < 0 || {iv} >= {ct.count}) mem_fail("Array index out of range");'
                    )
                    lines.append(f"{inner}{name} += {iv} * {new.cells()};")
                else:
                    lines.append(
                        f"{inner}{name} = cell_at(mem[cell_chk({name})]) + {iv} * {new.cells()};"
                    )
                lines.append(pad + "}")
            elif kind == "dot":
                off = ct.member(arg).cell_off
                if off:
                    lines.append(f"{pad}{name} += {off};")
            else:
                off = ct.target.member(arg).cell_off
                lines.append(f"{pad}{name} = cell_at(mem[cell_chk({name})]) + {off};")
            ct = new
        return lines, name, ct

    def _emit_assign(self, lval: LVal, rhs: List[Op], indent: int) -> List[str]:
        pad = "    " * indent
        inner = "    " * (indent + 1)
        addr, name, ct = self._lval_addr(lval, indent + 1)
        if ct.kind == "array":
            raise SemanticError(f"array '{lval.root}' is not assignable")
        if ct.is_const():
            raise SemanticError(f"assignment to const object '{lval.root}'")
        if ct.kind == "struct":
            if len(rhs) != 1 or rhs[0][0] != "LOAD":
                raise SemanticError(
                    "struct assignment needs a struct object on the right-hand side"
                )
            if _has_const_member(ct):
                raise SemanticError("assignment to a struct with const members")
            src_addr, src_name, src_ct = self._lval_addr(rhs[0][1], indent + 1)
            if src_ct.kind != "struct" or src_ct.struct_id() != ct.struct_id():
                raise SemanticError("incompatible struct types in assignment")
            n = ct.cells()
            return (
                [pad + "{"]
                + addr
                + src_addr
                + [
                    f"{inner}for (long _k = 0; _k < {n}; _k++) "
                    f"mem[cell_chk({name} + _k)] = mem[cell_chk({src_name} + _k)];",
                    pad + "}",
                ]
            )
        self._check_assign(ct, rhs)
        return (
            [pad + "{"]
            + addr
            + [inner + "{"]
            + self._emit_ops(rhs, indent + 2)
            + [
                f"{inner}    mem[cell_chk({name})] = {self._conversion(ct)};",
                inner + "}",
                pad + "}",
            ]
        )

    # ------------------------------------------------------------------
    # Program layout
    # ------------------------------------------------------------------

    def generate(self) -> str:
        self._collect_file_scope()
        function_blocks: List[str] = []
        for func in self.program.functions:
            function_blocks += self._emit_function(func)
        main_lines = self._emit_main()
        return self._assemble(function_blocks, main_lines)

    def _collect_file_scope(self) -> None:
        """Allocate file-scope objects and collect their initialisers."""
        for idx, op in enumerate(self.program.main_code):
            if op[0] != "DECL":
                continue
            for decl in op[1]:
                self._limit = idx
                self._scopes = []
                if any(name == decl.name for _i, name, _s in self._file):
                    raise SemanticError(f"redeclaration of '{decl.name}'")
                sym = self._alloc_static(decl.ctype)
                self._file.append((idx, decl.name, sym))
                if decl.init is not None:
                    self._global_init += self._init_lines(
                        sym, decl.init, pure=True, indent=1
                    )

    def _emit_function(self, func) -> List[str]:
        self._limit = func.position - 1
        self._scopes = []
        self._frame_top = 0
        body = self._emit_body(func.body, 1)
        frame = self._frame_top
        return (
            [
                f"static void func_{func.num}(void) {{",
                "    long _fb = ftop;",
                f"    ftop += {frame};",
                '    if (ftop > MEM_CELLS) mem_fail("Stack overflow");',
                f"    zero_cells(_fb, {frame});",
            ]
            + body
            + ["    ftop = _fb;", "}", ""]
        )

    def _emit_main(self) -> List[str]:
        self._scopes = []
        self._frame_top = 0
        body: List[str] = []
        for idx, op in enumerate(self.program.main_code):
            self._limit = idx - 1
            if op[0] == "DECL":
                continue
            body += self._emit_op(op, 1)
        frame = self._frame_top
        return (
            [
                "int main(void) {",
                "    srand((unsigned)time(NULL));",
                f"    ftop = {self._static_top};",
                "    long _fb = ftop;",
                f"    ftop += {frame};",
                '    if (ftop > MEM_CELLS) mem_fail("Out of memory");',
                f"    zero_cells(_fb, {frame});",
            ]
            + self._global_init
            + self._static_init
            + body
            + ["    return 0;", "}"]
        )

    def _assemble(self, function_blocks: List[str], main_lines: List[str]) -> str:
        lines: List[str] = [
            "#include <stdio.h>",
            "#include <stdlib.h>",
            "#include <math.h>",
            "#include <time.h>",
        ]
        lines += sorted(
            {
                f"#include <{decl.header}>"
                for decl in self.program.foreign
                if not decl.header.endswith(".c")
            }
        )
        for decl in self.program.foreign:
            if decl.header.endswith(".c"):
                params = ", ".join(["double"] * decl.arity) or "void"
                lines.append(f"double {decl.symbol}({params});")
        lines += [
            "",
            f"#define STACK_SIZE {self.context.stack_size}",
            f"#define MEM_CELLS {MEM_CELLS}L",
            "",
            "static double stack[STACK_SIZE];",
            "static int    sp = 0;",
            "",
            "/* Memory: cell 0 is NULL; legacy |n variables are cells 1-100. */",
            "static double mem[MEM_CELLS];",
            "static long ftop = 0;",
            "",
            'static void mem_fail(const char *msg) { fprintf(stderr, "%s\\n", msg); exit(1); }',
            "",
            "static long cell_chk(long a) {",
            '    if (a <= 0 || a >= MEM_CELLS) mem_fail("Invalid memory access");',
            "    return a;",
            "}",
            "",
            "static long cell_at(double v) {",
            '    if (v == 0.0) mem_fail("Null pointer dereference");',
            '    if (!(v >= 1.0 && v < (double)MEM_CELLS) || v != floor(v)) mem_fail("Invalid pointer");',
            "    return (long)v;",
            "}",
            "",
            "static void zero_cells(long base, long n) {",
            "    for (long k = 0; k < n; k++) mem[cell_chk(base + k)] = 0.0;",
            "}",
            "",
            "#define ARR_COUNT 16",
            "static double *arrays[ARR_COUNT];",
            "static int arr_len[ARR_COUNT];",
            "",
            "static void arr_new(int id, int n) {",
            '    if (id < 0 || id >= ARR_COUNT || n < 0) { fprintf(stderr, "Array size or id out of range\\n"); exit(1); }',
            "    free(arrays[id]);",
            "    arrays[id] = calloc(n > 0 ? (size_t)n : 1, sizeof(double));",
            '    if (arrays[id] == NULL) { fprintf(stderr, "Out of memory\\n"); exit(1); }',
            "    arr_len[id] = n;",
            "}",
            "",
            "static double *arr_slot(int id, int index) {",
            "    if (id < 0 || id >= ARR_COUNT || index < 0 || index >= arr_len[id]) {",
            '        fprintf(stderr, "Array index out of range\\n"); exit(1);',
            "    }",
            "    return &arrays[id][index];",
            "}",
            "",
            "/* Conversion to C type N: 0 signed char, 1 unsigned char, 2 short,",
            "   3 unsigned short, 4 int, 5 unsigned int, 6 long, 7 unsigned long,",
            "   8 long long, 9 unsigned long long, 10 float, 11 double, 12 _Bool. */",
            "static double num_cast(double x, int code) {",
            "    static const int width[10] = {8, 8, 16, 16, 32, 32, 64, 64, 64, 64};",
            "    static const int is_signed[10] = {1, 0, 1, 0, 1, 0, 1, 0, 1, 0};",
            "    if (code == 10) return (double)(float)x;",
            "    if (code == 11) return x;",
            "    if (code == 12) return x != 0.0 ? 1.0 : 0.0;",
            '    if (!isfinite(x)) { fprintf(stderr, "Conversion of non-finite value\\n"); exit(1); }',
            "    double m = ldexp(1.0, width[code]);",
            "    double r = fmod(trunc(x), m);",
            "    if (r < 0.0) r += m;",
            "    if (is_signed[code] && r >= m / 2.0) r -= m;",
            "    return r;",
            "}",
            "",
            "static void push(double x) {",
            '    if (sp >= STACK_SIZE) { fprintf(stderr, "Stack overflow\\n"); exit(1); }',
            "    stack[sp++] = x;",
            "}",
            "",
            "static double pop(void) {",
            '    if (sp <= 0) { fprintf(stderr, "Stack underflow\\n"); exit(1); }',
            "    return stack[--sp];",
            "}",
            "",
            "static double peek(void) {",
            '    if (sp <= 0) { fprintf(stderr, "Stack underflow\\n"); exit(1); }',
            "    return stack[sp - 1];",
            "}",
            "",
        ]
        for func in self.program.functions:
            lines.append(f"static void func_{func.num}(void);")
        if self.program.functions:
            lines.append("")
        # Function handles are MEM_CELLS + N, so they never alias a cell address.
        lines.append("static void call_fnptr(double v) {")
        lines.append(
            '    if (v != floor(v) || v < (double)MEM_CELLS) mem_fail("Invalid function pointer");'
        )
        lines.append("    switch ((long)v) {")
        for func in self.program.functions:
            lines.append(
                f"    case {MEM_CELLS + func.num}L: func_{func.num}(); return;"
            )
        lines.append("    default: break;")
        lines.append("    }")
        lines.append('    mem_fail("Invalid function pointer");')
        lines.append("}")
        lines.append("")
        lines += function_blocks
        lines += main_lines
        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------
    # Code emission
    # ------------------------------------------------------------------

    def _emit_body(self, ops: List[Op], indent: int) -> List[str]:
        """Emit a block with its own scope for declarations."""
        self._scopes.append({})
        try:
            return self._emit_ops(ops, indent)
        finally:
            self._scopes.pop()

    def _emit_ops(self, ops: List[Op], indent: int) -> List[str]:
        lines: List[str] = []
        for op in ops:
            lines += self._emit_op(op, indent)
        return lines

    def _emit_op(self, op: Op, indent: int) -> List[str]:
        kind, value = op
        pad = "    " * indent
        p1 = "    " * (indent + 1)
        lines: List[str] = []

        # ---- Control flow ----------------------------------------

        if kind == "IF_BLOCK":
            then_ops, else_ops = value
            lbl = self._new_label()
            lines.append(f"{pad}/* if_{lbl} */")
            lines.append(f"{pad}{{")
            lines.append(f"{p1}double _cond_{lbl} = pop();")
            lines.append(f"{p1}if (_cond_{lbl} != 0.0) {{")
            lines.extend(self._emit_body(then_ops, indent + 2))
            if else_ops is not None:
                lines.append(f"{p1}}} else {{")
                lines.extend(self._emit_body(else_ops, indent + 2))
            lines.append(f"{p1}}}")
            lines.append(f"{pad}}}")

        elif kind == "WHILE":
            lbl = self._new_label()
            lines.append(f"{pad}/* while_{lbl} */")
            lines.append(f"{pad}while (pop() != 0.0) {{")
            lines.extend(self._emit_body(value, indent + 1))
            lines.append(f"{pad}}}")

        elif kind == "REPEAT":
            lbl = self._new_label()
            lines.append(f"{pad}/* repeat_{lbl} */")
            lines.append(f"{pad}{{")
            lines.append(f"{p1}int _rcount_{lbl} = (int)pop();")
            lines.append(
                f"{p1}for (int _ri_{lbl} = 0; _ri_{lbl} < _rcount_{lbl}; _ri_{lbl}++) {{"
            )
            lines.append(f"{p1}    push((double)_ri_{lbl});  /* iteration index */")
            lines.extend(self._emit_body(value, indent + 2))
            lines.append(f"{p1}}}")
            lines.append(f"{pad}}}")

        elif kind == "DO_WHILE":
            lbl = self._new_label()
            lines.append(f"{pad}/* do_{lbl} */")
            lines.append(f"{pad}do {{")
            lines.extend(self._emit_body(value, indent + 1))
            lines.append(f"{pad}}} while (pop() != 0.0);")

        elif kind == "SWITCH":
            scrutinee, groups = value
            lines.append(f"{pad}{{")
            lines.extend(self._emit_ops(scrutinee, indent + 1))
            lines.append(f"{p1}switch ((long long)pop()) {{")
            self._scopes.append({})
            try:
                for label, group_ops in groups:
                    if label is None:
                        lines.append(f"{p1}default: ;")
                    else:
                        lines.append(f"{p1}case {label}: ;")
                    lines.extend(self._emit_ops(group_ops, indent + 2))
            finally:
                self._scopes.pop()
            lines.append(f"{p1}}}")
            lines.append(f"{pad}}}")

        elif kind == "BREAK":
            lines.append(f"{pad}break;")

        elif kind == "CONTINUE":
            lines.append(f"{pad}continue;")

        elif kind == "GOTO":
            lines.append(f"{pad}goto L_{value};")

        elif kind == "LABEL":
            lines.append(f"{pad}if (0) goto L_{value};")
            lines.append(f"{pad}L_{value}: ;")

        # ---- Declarations and memory -----------------------------

        elif kind == "DECL":
            lines.extend(self._emit_decls(value, indent))

        elif kind == "PUSH_VAR":
            lines.append(f"{pad}push(mem[{value + 1}]);")

        elif kind == "&":
            lines.append(
                f"{pad}{{ long _idx = (long)pop(); double _val = pop(); "
                f'if (_idx < 0 || _idx > 99) {{ fprintf(stderr, "Variable index out of range\\n"); exit(1); }} '
                f"mem[_idx + 1] = _val; }}"
            )

        elif kind == "LOAD":
            addr, name, ct = self._lval_addr(value, indent + 1)
            if ct.kind == "array":
                use = f"push((double){name});"
            elif ct.is_scalar():
                use = f"push(mem[cell_chk({name})]);"
            else:
                raise SemanticError(
                    "struct object used as a value; copy it with assignment"
                )
            lines += [pad + "{"] + addr + [p1 + use, pad + "}"]

        elif kind == "ADDR":
            addr, name, _ct = self._lval_addr(value, indent + 1)
            lines += (
                [pad + "{"] + addr + [f"{p1}push((double)cell_chk({name}));", pad + "}"]
            )

        elif kind == "ASSIGN":
            lval, rhs = value
            lines += self._emit_assign(lval, rhs, indent)

        elif kind == "CALL_PTR":
            addr, name, ct = self._lval_addr(value, indent + 1)
            if not (ct.kind == "pointer" and ct.target.kind == "func"):
                raise SemanticError(
                    "call through a value that is not a function pointer"
                )
            lines += (
                [pad + "{"]
                + addr
                + [f"{p1}call_fnptr(mem[cell_chk({name})]);", pad + "}"]
            )

        elif kind == "FUNC_REF":
            lines.append(f"{pad}push({float(MEM_CELLS + value)!r});")

        elif kind == "SIZEOF_EXPR":
            lines.append(f"{pad}push({self._lval_type(value).bytes()});")

        # ---- Literals -------------------------------------------

        elif kind == "NUM":
            # repr() gives full precision for floats and clean ints
            lines.append(f"{pad}push({value!r});")

        # ---- Arithmetic -----------------------------------------

        elif kind == "+":
            lines.append(
                f"{pad}{{ double _b = pop(); double _a = pop(); push(_a + _b); }}"
            )

        elif kind == "-":
            lines.append(
                f"{pad}{{ double _b = pop(); double _a = pop(); push(_a - _b); }}"
            )

        elif kind == "*":
            lines.append(
                f"{pad}{{ double _b = pop(); double _a = pop(); push(_a * _b); }}"
            )

        elif kind == "/":
            lines.append(f"{pad}{{ double _b = pop(); double _a = pop();")
            lines.append(
                f'{pad}  if (_b == 0.0) {{ fprintf(stderr, "Division by zero\\n"); exit(1); }}'
            )
            lines.append(f"{pad}  push(_a / _b); }}")

        elif kind == "%":
            lines.append(f"{pad}{{ double _b = pop(); double _a = pop();")
            lines.append(
                f'{pad}  if (_b == 0.0) {{ fprintf(stderr, "Modulo by zero\\n"); exit(1); }}'
            )
            lines.append(f"{pad}  push(fmod(_a, _b)); }}")

        # ---- Comparisons ----------------------------------------

        elif kind == "LT":
            lines.append(
                f"{pad}{{ double _b = pop(); double _a = pop(); push(_a < _b ? 1.0 : 0.0); }}"
            )
        elif kind == "GT":
            lines.append(
                f"{pad}{{ double _b = pop(); double _a = pop(); push(_a > _b ? 1.0 : 0.0); }}"
            )
        elif kind == "EQ":
            lines.append(
                f"{pad}{{ double _b = pop(); double _a = pop(); push(_a == _b ? 1.0 : 0.0); }}"
            )
        elif kind == "NE":
            lines.append(
                f"{pad}{{ double _b = pop(); double _a = pop(); push(_a != _b ? 1.0 : 0.0); }}"
            )
        elif kind == "LE":
            lines.append(
                f"{pad}{{ double _b = pop(); double _a = pop(); push(_a <= _b ? 1.0 : 0.0); }}"
            )
        elif kind == "GE":
            lines.append(
                f"{pad}{{ double _b = pop(); double _a = pop(); push(_a >= _b ? 1.0 : 0.0); }}"
            )

        # ---- Logical --------------------------------------------

        elif kind == "NOT":
            lines.append(f"{pad}{{ double _a = pop(); push(_a == 0.0 ? 1.0 : 0.0); }}")

        elif kind == "LOGICAL_OR":
            lines.append(
                f"{pad}{{ double _b = pop(); double _a = pop(); "
                f"push((_a != 0.0 || _b != 0.0) ? 1.0 : 0.0); }}"
            )

        elif kind == "LOGICAL_AND":
            lines.append(
                f"{pad}{{ double _b = pop(); double _a = pop(); "
                f"push((_a != 0.0 && _b != 0.0) ? 1.0 : 0.0); }}"
            )

        # ---- Math built-ins ------------------------------------

        elif kind == "ABS":
            lines.append(f"{pad}push(fabs(pop()));")

        elif kind == "SQRT":
            lines.append(
                f"{pad}{{ double _x = pop(); "
                f'if (_x < 0.0) {{ fprintf(stderr, "SQRT of negative\\n"); exit(1); }} '
                f"push(sqrt(_x)); }}"
            )

        elif kind == "FLOOR":
            lines.append(f"{pad}push(floor(pop()));")

        elif kind == "CEIL":
            lines.append(f"{pad}push(ceil(pop()));")

        elif kind == "ROUND":
            lines.append(f"{pad}push(round(pop()));")

        elif kind == "TRUNC":
            lines.append(f"{pad}push(trunc(pop()));")

        elif kind == "NEG":
            lines.append(f"{pad}push(-pop());")

        elif kind == "MIN2":
            lines.append(
                f"{pad}{{ double _b = pop(); double _a = pop(); push(_a < _b ? _a : _b); }}"
            )

        elif kind == "MAX2":
            lines.append(
                f"{pad}{{ double _b = pop(); double _a = pop(); push(_a > _b ? _a : _b); }}"
            )

        elif kind == "POW":
            lines.append(
                f"{pad}{{ double _exp = pop(); double _base = pop(); push(pow(_base, _exp)); }}"
            )

        elif kind == "LOG":
            lines.append(
                f"{pad}{{ double _x = pop(); "
                f'if (_x <= 0.0) {{ fprintf(stderr, "LOG of non-positive\\n"); exit(1); }} '
                f"push(log(_x)); }}"
            )

        elif kind == "LOG10":
            lines.append(
                f"{pad}{{ double _x = pop(); "
                f'if (_x <= 0.0) {{ fprintf(stderr, "LOG10 of non-positive\\n"); exit(1); }} '
                f"push(log10(_x)); }}"
            )

        elif kind == "SIN":
            lines.append(f"{pad}push(sin(pop()));")

        elif kind == "COS":
            lines.append(f"{pad}push(cos(pop()));")

        elif kind == "TAN":
            lines.append(f"{pad}push(tan(pop()));")

        elif kind == "ASIN":
            lines.append(
                f"{pad}{{ double _x = pop(); "
                f'if (_x < -1.0 || _x > 1.0) {{ fprintf(stderr, "ASIN domain error\\n"); exit(1); }} '
                f"push(asin(_x)); }}"
            )

        elif kind == "ACOS":
            lines.append(
                f"{pad}{{ double _x = pop(); "
                f'if (_x < -1.0 || _x > 1.0) {{ fprintf(stderr, "ACOS domain error\\n"); exit(1); }} '
                f"push(acos(_x)); }}"
            )

        elif kind == "ATAN":
            lines.append(f"{pad}push(atan(pop()));")

        elif kind == "ATAN2":
            lines.append(
                f"{pad}{{ double _x = pop(); double _y = pop(); push(atan2(_y, _x)); }}"
            )

        elif kind == "IMOD":
            lines.append(
                f"{pad}{{ int _b = (int)pop(); int _a = (int)pop(); "
                f'if (_b == 0) {{ fprintf(stderr, "IMOD by zero\\n"); exit(1); }} '
                f"push((double)(_a % _b)); }}"
            )

        # ---- Bitwise --------------------------------------------

        elif kind == "BAND":
            lines.append(
                f"{pad}{{ int _b = (int)pop(); int _a = (int)pop(); push((double)(_a & _b)); }}"
            )

        elif kind == "BOR":
            lines.append(
                f"{pad}{{ int _b = (int)pop(); int _a = (int)pop(); push((double)(_a | _b)); }}"
            )

        elif kind == "BXOR":
            lines.append(
                f"{pad}{{ int _b = (int)pop(); int _a = (int)pop(); push((double)(_a ^ _b)); }}"
            )

        elif kind == "BNOT":
            lines.append(f"{pad}{{ int _a = (int)pop(); push((double)(~_a)); }}")

        elif kind == "BSHL":
            lines.append(
                f"{pad}{{ int _b = (int)pop(); int _a = (int)pop(); "
                f'if (_b < 0 || _b >= 64) {{ fprintf(stderr, "BSHL shift out of range\\n"); exit(1); }} '
                f"push((double)(_a << _b)); }}"
            )

        elif kind == "BSHR":
            lines.append(
                f"{pad}{{ int _b = (int)pop(); int _a = (int)pop(); "
                f'if (_b < 0 || _b >= 64) {{ fprintf(stderr, "BSHR shift out of range\\n"); exit(1); }} '
                f"push((double)(_a >> _b)); }}"
            )

        # ---- Integer division and fixed-size arrays -------------

        elif kind == "IDIV":
            lines.append(
                f"{pad}{{ int _b = (int)pop(); int _a = (int)pop(); "
                f'if (_b == 0) {{ fprintf(stderr, "IDIV by zero\\n"); exit(1); }} '
                f"push((double)(_a / _b)); }}"
            )

        elif kind == "ARR_NEW":
            lines.append(
                f"{pad}{{ int _n = (int)pop(); int _id = (int)pop(); arr_new(_id, _n); }}"
            )

        elif kind == "ARR_SET":
            lines.append(
                f"{pad}{{ double _v = pop(); int _i = (int)pop(); int _id = (int)pop(); "
                f"*arr_slot(_id, _i) = _v; }}"
            )

        elif kind == "ARR_GET":
            lines.append(
                f"{pad}{{ int _i = (int)pop(); int _id = (int)pop(); push(*arr_slot(_id, _i)); }}"
            )

        # ---- Explicit conversions -------------------------------

        elif kind == "CAST":
            lines.append(f"{pad}push(num_cast(pop(), {value}));")

        # ---- Foreign C calls ------------------------------------

        elif kind == "FFI_CALL":
            decl = self._foreign[value]
            # Arguments sit on the stack in order, so pop them last-first.
            pops = " ".join(
                f"double _f{k} = pop();" for k in reversed(range(decl.arity))
            )
            args = ", ".join(f"_f{k}" for k in range(decl.arity))
            lines.append(f"{pad}{{ {pops} push({decl.symbol}({args})); }}")

        # ---- Stack manipulation ---------------------------------

        elif kind == "DUP":
            lines.append(f"{pad}push(peek());")

        elif kind == "SWAP":
            lines.append(
                f"{pad}{{ double _b = pop(); double _a = pop(); push(_b); push(_a); }}"
            )

        elif kind == "DROP":
            lines.append(f"{pad}pop();")

        # ---- Misc ops ------------------------------------------

        elif kind == "DEPTH":
            lines.append(f"{pad}push((double)sp);")

        elif kind == "PICK":
            lines.append(
                f"{pad}{{ int _n = (int)pop(); "
                f'if (_n < 0 || _n >= sp) {{ fprintf(stderr, "PICK index out of range\\n"); exit(1); }} '
                f"push(stack[sp - 1 - _n]); }}"
            )

        elif kind == "RAND":
            lines.append(f"{pad}push((double)rand() / ((double)RAND_MAX + 1.0));")

        elif kind == "TIME":
            lines.append(f"{pad}push((double)time(NULL));")

        elif kind == "EXIT":
            lines.append(f"{pad}exit((int)pop());")

        # ---- I/O -----------------------------------------------

        elif kind == "^":
            lines.append(
                f'{pad}{{ double _x; if (scanf("%lf", &_x) != 1) exit(1); push(_x); }}'
            )

        elif kind == "|":
            lines.append(f'{pad}printf("%g\\n", pop());')

        elif kind == "~":
            lines.append(f"{pad}putchar((int)pop());")

        elif kind == "STRING":
            for code in value:
                lines.append(f"{pad}putchar({code});")

        # ---- Functions -----------------------------------------

        elif kind == "CALL":
            lines.append(f"{pad}func_{value}();")

        else:
            raise SemanticError(f"unsupported operation '{kind}'")

        return lines
