from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .ast import Program


@dataclass
class CodegenContext:
    pass


class CCodeGenerator:
    def __init__(self, program: Program, context: CodegenContext):
        self.program = program
        self.context = context

    def generate(self) -> str:
        lines = []
        lines.append("#include <stdio.h>")
        lines.append("#include <stdlib.h>")
        lines.append("#include <math.h>")
        lines.append("")
        lines.append("#define STACK_SIZE 1000")
        lines.append("")
        lines.append("double stack[STACK_SIZE];")
        lines.append("int sp = 0;")
        lines.append("double vars[10] = {0};")
        lines.append("")
        lines.append("void push(double x) {")
        lines.append("    if (sp >= STACK_SIZE) {")
        lines.append("        fprintf(stderr, \"Stack overflow\\n\");")
        lines.append("        exit(1);")
        lines.append("    }")
        lines.append("    stack[sp++] = x;")
        lines.append("}")
        lines.append("")
        lines.append("double pop() {")
        lines.append("    if (sp <= 0) {")
        lines.append("        fprintf(stderr, \"Stack underflow\\n\");")
        lines.append("        exit(1);")
        lines.append("    }")
        lines.append("    return stack[--sp];")
        lines.append("}")
        lines.append("")

        # Generate function definitions
        for func in self.program.functions:
            lines.append(f"void func_{func.num}() {{")
            for kind, value in func.code:
                lines.extend(self._generate_op(kind, value))
            lines.append("}")
            lines.append("")

        lines.append("int main() {")
        for kind, value in self.program.main_code:
            lines.extend(self._generate_op(kind, value))
        lines.append("    return 0;")
        lines.append("}")
        return "\n".join(lines)

    def _generate_op(self, kind, value):
        lines = []
        if kind == "PUSH_VAR":
            lines.append(f"    push(vars[{value}]);")
        elif kind == "&":
            lines.append("    { int var = (int)pop(); double val = pop(); vars[var] = val; }")
        elif kind in "0123456789":
            lines.append(f"    push({kind}.0);")
        elif kind == "NUM":
            lines.append(f"    push({value}.0);")
        elif kind == "+":
            lines.append("    { double b = pop(); double a = pop(); push(a + b); }")
        elif kind == "-":
            lines.append("    { double b = pop(); double a = pop(); push(a - b); }")
        elif kind == "*":
            lines.append("    { double b = pop(); double a = pop(); push(a * b); }")
        elif kind == "/":
            lines.append("    { double b = pop(); double a = pop(); push(a / b); }")
        elif kind == "^":
            lines.append("    { double x; if (scanf(\"%lf\", &x) != 1) exit(1); push(x); }")
        elif kind == "|":
            lines.append("    printf(\"%g\\n\", pop());")
        elif kind == ".":
            lines.append(f"    func_{value}();")
        elif kind == ";":
            pass
        elif kind == "CALL":  # Assuming ^ is CALL
            lines.append(f"    func_{value}();")
        return lines