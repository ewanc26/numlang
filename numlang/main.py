from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .codegen_c import CCodeGenerator, CodegenContext
from .parser import Parser, ParseError
from .sema import SemanticAnalyzer, SemanticError


class CompileError(Exception):
    pass


def compile_source(source: str) -> str:
    parser = Parser.from_source(source)
    program = parser.parse()
    analyzer = SemanticAnalyzer()
    analyzer.analyze(program)
    generator = CCodeGenerator(program, CodegenContext())
    return generator.generate()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="numlangc", description="Compile Numlang source to C")
    parser.add_argument("input", help="Input .num file")
    parser.add_argument("-o", "--output", required=True, help="Output C file")
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    output_path = Path(args.output)

    try:
        source = input_path.read_text(encoding="utf-8")
        c_code = compile_source(source)
        output_path.write_text(c_code, encoding="utf-8")
    except (OSError, ParseError, SemanticError, CompileError) as exc:
        print(f"numlangc: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())