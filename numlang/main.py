from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
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
    ap = argparse.ArgumentParser(
        prog="numlangc",
        description="Compile Numlang source to C (optionally compile & run)",
    )
    ap.add_argument("input", help="Input .num file")
    ap.add_argument("-o", "--output", help="Output C file (omit when using --run)")
    ap.add_argument(
        "--run",
        action="store_true",
        help="Compile with gcc and execute immediately (requires gcc on PATH)",
    )
    ap.add_argument(
        "--cc",
        default="gcc",
        metavar="CC",
        help="C compiler to use with --run (default: gcc)",
    )
    args = ap.parse_args(argv)

    if not args.run and args.output is None:
        ap.error("Either -o/--output or --run must be specified")

    input_path = Path(args.input)

    try:
        source = input_path.read_text(encoding="utf-8")
        c_code = compile_source(source)
    except OSError as exc:
        print(f"numlangc: {exc}", file=sys.stderr)
        return 1
    except (ParseError, SemanticError, CompileError) as exc:
        print(f"numlangc: {exc}", file=sys.stderr)
        return 1

    if args.run:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            c_file = tmp / "out.c"
            exe_file = tmp / "out"
            c_file.write_text(c_code, encoding="utf-8")
            try:
                result = subprocess.run(
                    [args.cc, str(c_file), "-o", str(exe_file), "-lm"],
                    capture_output=True,
                    text=True,
                )
            except FileNotFoundError:
                print(
                    f"numlangc: compiler '{args.cc}' not found — install it or pass a different --cc",
                    file=sys.stderr,
                )
                return 1
            if result.returncode != 0:
                print(f"numlangc: C compilation failed:\n{result.stderr}", file=sys.stderr)
                return 1
            run_result = subprocess.run([str(exe_file)])
            return run_result.returncode

    # Normal file output
    output_path = Path(args.output)
    try:
        output_path.write_text(c_code, encoding="utf-8")
    except OSError as exc:
        print(f"numlangc: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
