"""CLI entry point for the Numlang compiler.

Provides the ``numlangc`` command that compiles .num files to C,
with optional direct execution via gcc and debug token/AST dumps.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

from .codegen_c import CCodeGenerator, CodegenContext
from .lexer import Lexer, LexError
from .parser import ParseError, Parser
from .sema import SemanticAnalyzer, SemanticError


class CompileError(Exception):
    pass


def compile_source(source: str, stack_size: int = 1000) -> str:
    """Compile a Numlang source string into C source code.

    Runs the full pipeline: lex, parse, semantic analysis, codegen.
    """
    parser = Parser.from_source(source)
    program = parser.parse()
    analyzer = SemanticAnalyzer()
    analyzer.analyze(program)
    ctx = CodegenContext(stack_size=stack_size)
    generator = CCodeGenerator(program, ctx)
    return generator.generate()


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: parse args, compile, optionally execute."""
    if "--support" in (argv if argv is not None else sys.argv[1:]):
        print("Support Numlang development:")
        print("  Ko-fi: https://ko-fi.com/ewancroft")
        print("  GitHub Sponsors: https://github.com/sponsors/ewanc26")
        return 0
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
    ap.add_argument(
        "--support",
        action="store_true",
        help="Print sponsor links (Ko-fi: https://ko-fi.com/ewancroft · GitHub Sponsors: https://github.com/sponsors/ewanc26)",
    )
    args = ap.parse_args(argv)

    if (
        not args.run
        and args.output is None
        and not args.emit_tokens
        and not args.emit_ast
    ):
        ap.error(
            "Either -o/--output, --run, --emit-tokens, or --emit-ast must be specified"
        )

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
        except (LexError, ParseError, ValueError) as exc:
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
    except (LexError, ParseError, SemanticError, CompileError, ValueError) as exc:
        print(f"numlangc: {exc}", file=sys.stderr)
        return 1

    if args.run:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            c_file = tmp / "out.c"
            exe_file = tmp / "out"
            c_file.write_text(c_code, encoding="utf-8")
            user_sources = [
                str(input_path.parent / decl.header)
                for decl in Parser.from_source(source).parse().foreign
                if decl.header.endswith(".c")
            ]
            try:
                result = subprocess.run(
                    [args.cc, str(c_file), *user_sources, "-o", str(exe_file), "-lm"],
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
                print(
                    f"numlangc: C compilation failed:\n{result.stderr}", file=sys.stderr
                )
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
