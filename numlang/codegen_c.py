from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .ast import Program, Op


@dataclass
class CodegenContext:
    pass


class CCodeGenerator:
    def __init__(self, program: Program, context: CodegenContext):
        self.program = program
        self.context = context
        self._while_counter = 0  # unique labels for while loops

    def generate(self) -> str:
        lines: List[str] = []

        # Includes & globals
        lines += [
            "#include <stdio.h>",
            "#include <stdlib.h>",
            "#include <math.h>",
            "",
            "#define STACK_SIZE 1000",
            "",
            "static double stack[STACK_SIZE];",
            "static int    sp = 0;",
            "static double vars[10] = {0};",
            "",
        ]

        # push / pop helpers
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

            if kind == "IF":
                # Consume the next op as the conditional body
                lines.append(f"{pad}{{")
                lines.append(f"{pad}    double _cond = pop();")
                lines.append(f"{pad}    if (_cond != 0.0) {{")
                i += 1
                if i < len(ops):
                    lines.extend(self._emit_ops([ops[i]], indent + 2))
                lines.append(f"{pad}    }}")
                lines.append(f"{pad}}}")

            elif kind == "WHILE":
                body: List[Op] = value  # type: ignore[assignment]
                label = self._while_counter
                self._while_counter += 1
                lines.append(f"{pad}/* while_{label} */")
                lines.append(f"{pad}while (pop() != 0.0) {{")
                lines.extend(self._emit_ops(body, indent + 1))
                lines.append(f"{pad}}}")

            elif kind == "PUSH_VAR":
                lines.append(f"{pad}push(vars[{value}]);")

            elif kind == "&":
                lines.append(f"{pad}{{ int _idx = (int)pop(); double _val = pop(); vars[_idx] = _val; }}")

            elif kind == "NUM":
                lines.append(f"{pad}push({value!r});")

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

            elif kind == "^":
                lines.append(f"{pad}{{ double _x; if (scanf(\"%lf\", &_x) != 1) exit(1); push(_x); }}")

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

            elif kind == "|":
                lines.append(f"{pad}printf(\"%g\\n\", pop());")

            elif kind == "CALL":
                lines.append(f"{pad}func_{value}();")

            elif kind == "DUP":
                lines.append(f"{pad}push(peek());")

            elif kind == "SWAP":
                lines.append(f"{pad}{{ double _b = pop(); double _a = pop(); push(_b); push(_a); }}")

            elif kind == "DROP":
                lines.append(f"{pad}pop();")

            # ";" and unknown tokens are silently ignored at codegen time
            # (sema should have caught real problems already)

            i += 1

        return lines
