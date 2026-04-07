from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .ast import Program, Op


@dataclass
class CodegenContext:
    stack_size: int = 1000


class CCodeGenerator:
    def __init__(self, program: Program, context: CodegenContext):
        self.program = program
        self.context = context
        self._label_counter = 0  # unique labels for while / repeat / if blocks

    def _new_label(self) -> int:
        label = self._label_counter
        self._label_counter += 1
        return label

    def generate(self) -> str:
        lines: List[str] = []

        # Includes & globals
        lines += [
            "#include <stdio.h>",
            "#include <stdlib.h>",
            "#include <math.h>",
            "#include <time.h>",
            "",
            f"#define STACK_SIZE {self.context.stack_size}",
            "",
            "static double stack[STACK_SIZE];",
            "static int    sp = 0;",
            "static double vars[100];   /* vars[0]–vars[99] */",
            "",
        ]

        # push / pop / peek helpers
        lines += [
            "static void push(double x) {",
            "    if (sp >= STACK_SIZE) { fprintf(stderr, \"Stack overflow\\n\"); exit(1); }",
            "    stack[sp++] = x;",
            "}",
            "",
            "static double pop(void) {",
            "    if (sp <= 0) { fprintf(stderr, \"Stack underflow\\n\"); exit(1); }",
            "    return stack[--sp];",
            "}",
            "",
            "static double peek(void) {",
            "    if (sp <= 0) { fprintf(stderr, \"Stack underflow\\n\"); exit(1); }",
            "    return stack[sp - 1];",
            "}",
            "",
        ]

        # Forward-declare all functions so order doesn't matter
        for func in self.program.functions:
            lines.append(f"static void func_{func.num}(void);")
        if self.program.functions:
            lines.append("")

        # Emit each function
        for func in self.program.functions:
            lines.append(f"static void func_{func.num}(void) {{")
            lines.extend(self._emit_ops(func.body, indent=1))
            lines.append("}")
            lines.append("")

        # main()
        lines.append("int main(void) {")
        # Seed RNG; zero-init vars (already zero-init by static storage in C,
        # but explicit is clearer).
        lines.append("    srand((unsigned)time(NULL));")
        lines.extend(self._emit_ops(self.program.main_code, indent=1))
        lines.append("    return 0;")
        lines.append("}")

        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------
    # Code emission
    # ------------------------------------------------------------------

    def _emit_ops(self, ops: List[Op], indent: int) -> List[str]:
        lines: List[str] = []
        pad = "    " * indent
        i = 0
        while i < len(ops):
            kind, value = ops[i]

            # ---- Control flow ----------------------------------------

            if kind == "IF_BLOCK":
                then_ops, else_ops = value
                lbl = self._new_label()
                lines.append(f"{pad}/* if_{lbl} */")
                lines.append(f"{pad}{{")
                lines.append(f"{pad}    double _cond_{lbl} = pop();")
                lines.append(f"{pad}    if (_cond_{lbl} != 0.0) {{")
                lines.extend(self._emit_ops(then_ops, indent + 2))
                if else_ops is not None:
                    lines.append(f"{pad}    }} else {{")
                    lines.extend(self._emit_ops(else_ops, indent + 2))
                lines.append(f"{pad}    }}")
                lines.append(f"{pad}}}")

            elif kind == "WHILE":
                body: List[Op] = value
                lbl = self._new_label()
                lines.append(f"{pad}/* while_{lbl} */")
                lines.append(f"{pad}while (pop() != 0.0) {{")
                lines.extend(self._emit_ops(body, indent + 1))
                lines.append(f"{pad}}}")

            elif kind == "REPEAT":
                body = value
                lbl = self._new_label()
                lines.append(f"{pad}/* repeat_{lbl} */")
                lines.append(f"{pad}{{")
                lines.append(f"{pad}    int _rcount_{lbl} = (int)pop();")
                lines.append(f"{pad}    for (int _ri_{lbl} = 0; _ri_{lbl} < _rcount_{lbl}; _ri_{lbl}++) {{")
                lines.append(f"{pad}        push((double)_ri_{lbl});  /* iteration index */")
                lines.extend(self._emit_ops(body, indent + 2))
                lines.append(f"{pad}    }}")
                lines.append(f"{pad}}}")

            # ---- Variables -------------------------------------------

            elif kind == "PUSH_VAR":
                lines.append(f"{pad}push(vars[{value}]);")

            elif kind == "&":
                lines.append(
                    f"{pad}{{ int _idx = (int)pop(); double _val = pop(); "
                    f"if (_idx < 0 || _idx > 99) {{ fprintf(stderr, \"Variable index out of range\\n\"); exit(1); }} "
                    f"vars[_idx] = _val; }}"
                )

            # ---- Literals -------------------------------------------

            elif kind == "NUM":
                # repr() gives full precision for floats and clean ints
                lines.append(f"{pad}push({value!r});")

            # ---- Arithmetic -----------------------------------------

            elif kind == "+":
                lines.append(f"{pad}{{ double _b = pop(); double _a = pop(); push(_a + _b); }}")

            elif kind == "-":
                lines.append(f"{pad}{{ double _b = pop(); double _a = pop(); push(_a - _b); }}")

            elif kind == "*":
                lines.append(f"{pad}{{ double _b = pop(); double _a = pop(); push(_a * _b); }}")

            elif kind == "/":
                lines.append(f"{pad}{{ double _b = pop(); double _a = pop();")
                lines.append(f"{pad}  if (_b == 0.0) {{ fprintf(stderr, \"Division by zero\\n\"); exit(1); }}")
                lines.append(f"{pad}  push(_a / _b); }}")

            elif kind == "%":
                lines.append(f"{pad}{{ double _b = pop(); double _a = pop();")
                lines.append(f"{pad}  if (_b == 0.0) {{ fprintf(stderr, \"Modulo by zero\\n\"); exit(1); }}")
                lines.append(f"{pad}  push(fmod(_a, _b)); }}")

            # ---- Comparisons ----------------------------------------

            elif kind == "LT":
                lines.append(f"{pad}{{ double _b = pop(); double _a = pop(); push(_a < _b ? 1.0 : 0.0); }}")
            elif kind == "GT":
                lines.append(f"{pad}{{ double _b = pop(); double _a = pop(); push(_a > _b ? 1.0 : 0.0); }}")
            elif kind == "EQ":
                lines.append(f"{pad}{{ double _b = pop(); double _a = pop(); push(_a == _b ? 1.0 : 0.0); }}")
            elif kind == "NE":
                lines.append(f"{pad}{{ double _b = pop(); double _a = pop(); push(_a != _b ? 1.0 : 0.0); }}")
            elif kind == "LE":
                lines.append(f"{pad}{{ double _b = pop(); double _a = pop(); push(_a <= _b ? 1.0 : 0.0); }}")
            elif kind == "GE":
                lines.append(f"{pad}{{ double _b = pop(); double _a = pop(); push(_a >= _b ? 1.0 : 0.0); }}")

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
                    f"if (_x < 0.0) {{ fprintf(stderr, \"SQRT of negative\\n\"); exit(1); }} "
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
                lines.append(f"{pad}{{ double _b = pop(); double _a = pop(); push(_a < _b ? _a : _b); }}")

            elif kind == "MAX2":
                lines.append(f"{pad}{{ double _b = pop(); double _a = pop(); push(_a > _b ? _a : _b); }}")

            elif kind == "POW":
                lines.append(
                    f"{pad}{{ double _exp = pop(); double _base = pop(); push(pow(_base, _exp)); }}"
                )

            elif kind == "LOG":
                lines.append(
                    f"{pad}{{ double _x = pop(); "
                    f"if (_x <= 0.0) {{ fprintf(stderr, \"LOG of non-positive\\n\"); exit(1); }} "
                    f"push(log(_x)); }}"
                )

            elif kind == "LOG10":
                lines.append(
                    f"{pad}{{ double _x = pop(); "
                    f"if (_x <= 0.0) {{ fprintf(stderr, \"LOG10 of non-positive\\n\"); exit(1); }} "
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
                    f"if (_x < -1.0 || _x > 1.0) {{ fprintf(stderr, \"ASIN domain error\\n\"); exit(1); }} "
                    f"push(asin(_x)); }}"
                )

            elif kind == "ACOS":
                lines.append(
                    f"{pad}{{ double _x = pop(); "
                    f"if (_x < -1.0 || _x > 1.0) {{ fprintf(stderr, \"ACOS domain error\\n\"); exit(1); }} "
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
                    f"if (_b == 0) {{ fprintf(stderr, \"IMOD by zero\\n\"); exit(1); }} "
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
                    f"if (_b < 0 || _b >= 64) {{ fprintf(stderr, \"BSHL shift out of range\\n\"); exit(1); }} "
                    f"push((double)(_a << _b)); }}"
                )

            elif kind == "BSHR":
                lines.append(
                    f"{pad}{{ int _b = (int)pop(); int _a = (int)pop(); "
                    f"if (_b < 0 || _b >= 64) {{ fprintf(stderr, \"BSHR shift out of range\\n\"); exit(1); }} "
                    f"push((double)(_a >> _b)); }}"
                )

            # ---- Stack manipulation ---------------------------------

            elif kind == "DUP":
                lines.append(f"{pad}push(peek());")

            elif kind == "SWAP":
                lines.append(f"{pad}{{ double _b = pop(); double _a = pop(); push(_b); push(_a); }}")

            elif kind == "DROP":
                lines.append(f"{pad}pop();")

            # ---- Misc ops ------------------------------------------

            elif kind == "DEPTH":
                lines.append(f"{pad}push((double)sp);")

            elif kind == "PICK":
                lines.append(
                    f"{pad}{{ int _n = (int)pop(); "
                    f"if (_n < 0 || _n >= sp) {{ fprintf(stderr, \"PICK index out of range\\n\"); exit(1); }} "
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
                    f"{pad}{{ double _x; if (scanf(\"%lf\", &_x) != 1) exit(1); push(_x); }}"
                )

            elif kind == "|":
                lines.append(f"{pad}printf(\"%g\\n\", pop());")

            elif kind == "~":
                lines.append(f"{pad}putchar((int)pop());")

            elif kind == "STRING":
                for code in value:
                    lines.append(f"{pad}putchar({code});")

            # ---- Functions -----------------------------------------

            elif kind == "CALL":
                lines.append(f"{pad}func_{value}();")

            # Silently skip anything else (unknown tokens should have been
            # caught by sema; bare ";" is already filtered by the parser)

            i += 1

        return lines
