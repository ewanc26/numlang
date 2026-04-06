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
        lines.append("int main() {")
        for op in self.program.operations:
            if op in "0123456789":
                lines.append(f"    push({op}.0);")
            elif op == "+":
                lines.append("    { double b = pop(); double a = pop(); push(a + b); }")
            elif op == "-":
                lines.append("    { double b = pop(); double a = pop(); push(a - b); }")
            elif op == "*":
                lines.append("    { double b = pop(); double a = pop(); push(a * b); }")
            elif op == "/":
                lines.append("    { double b = pop(); double a = pop(); push(a / b); }")
            elif op == "^":
                lines.append("    { double b = pop(); double a = pop(); push(pow(a, b)); }")
            elif op == "&":
                lines.append("    { double b = pop(); double a = pop(); push((int)a & (int)b); }")
            elif op == "|":
                lines.append("    { double b = pop(); double a = pop(); push((int)a | (int)b); }")
            elif op == ".":
                lines.append("    printf(\"%g\\n\", pop());")
            elif op == ";":
                # Maybe end or something, but ignore for now
                pass
        lines.append("    return 0;")
        lines.append("}")
        return "\n".join(lines)