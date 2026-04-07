from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

from .codegen_c import CCodeGenerator, CodegenContext
from .lexer import Lexer, LexError
from .parser import Parser, ParseError
from .sema import SemanticAnalyzer, SemanticError


class CompileError(Exception):
    pass


def compile_source(source: str, stack_size: int = 1000) -> str:
    parser = Parser.from_source(source)
    program = parser.parse()
    analyzer = SemanticAnalyzer()
    analyzer.analyze(program)
    ctx = CodegenContext(stack_size=stack_size)
    generator = CCodeGenerator(program, ctx)
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
    ap.add_argument(
        "--stack-size",
        type=int,
        default=1000,
        metavar="N",
        help="Runtime stack depth (default: 1000)",
    )
    ap.add_argument(
        "--emit-tokens",
        action="store_true",
        help="Print the token stream and exit (debug)",
    )
    ap.add_argument(
        "--emit-ast",
        action="store_true",
        help="Print the parsed AST and exit (debug)",
    )
    args = ap.parse_args(argv)

    if not args.run and args.output is None and not args.emit_tokens and not args.emit_ast:
        ap.error("Either -o/--output, --run, --emit-tokens, or --emit-ast must be specified")

    if args.stack_size < 1:
        ap.error("--stack-size must be at least 1")

    input_path = Path(args.input)

    try:
        source = input_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"numlangc: {exc}", file=sys.stderr)
        return 1

    # --emit-tokens: lex only, dump tokens
    if args.emit_tokens:
        try:
            lexer = Lexer(source)
            tokens = lexer.tokenize()
        except LexError as exc:
            print(f"numlangc: {exc}", file=sys.stderr)
            return 1
        for tok in tokens:
            print(f"  {tok.line:4}:{tok.col:<4} {tok.kind:<12} {tok.value!r}")
        return 0

    # --emit-ast: parse only, dump AST
    if args.emit_ast:
        try:
            parser = Parser.from_source(source)
            program = parser.parse()
        except (LexError, ParseError) as exc:
            print(f"numlangc: {exc}", file=sys.stderr)
            return 1
        print(f"Functions ({len(program.functions)}):")
        for func in program.functions:
            print(f"  /{ func.num}")
            for op in func.body:
                print(f"    {op}")
        print(f"\nMain ({len(program.main_code)} ops):")
        for op in program.main_code:
            print(f"  {op}")
        return 0

    # Normal compilation path
    try:
        c_code = compile_source(source, stack_size=args.stack_size)
    except (LexError, ParseError, SemanticError, CompileError) as exc:
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
