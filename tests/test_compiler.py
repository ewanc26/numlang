"""Tests for the Numlang compiler.

Run with:
    pytest tests/
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from numlang.lexer import Lexer, LexError
from numlang.parser import Parser, ParseError
from numlang.sema import SemanticAnalyzer, SemanticError
from numlang.codegen_c import CCodeGenerator, CodegenContext
from numlang.main import compile_source


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def compile_and_run(source: str, stdin: str = "") -> str:
    """Compile *source*, build with gcc, run, and return captured stdout."""
    c_code = compile_source(source)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        c_file = tmp / "out.c"
        exe_file = tmp / "out"
        c_file.write_text(c_code)
        result = subprocess.run(
            ["gcc", str(c_file), "-o", str(exe_file), "-lm"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"gcc failed:\n{result.stderr}")
        run = subprocess.run(
            [str(exe_file)],
            input=stdin,
            capture_output=True,
            text=True,
        )
        return run.stdout


def _skip_no_gcc() -> None:
    """Skip the calling test if gcc is not available."""
    import shutil
    if shutil.which("gcc") is None:
        pytest.skip("gcc not found on PATH")


# ---------------------------------------------------------------------------
# Lexer tests
# ---------------------------------------------------------------------------

class TestLexer:
    def test_integer(self):
        tokens = Lexer("42").tokenize()
        assert tokens[0].kind == "NUM"
        assert tokens[0].value == 42

    def test_float(self):
        tokens = Lexer("3.14").tokenize()
        assert tokens[0].kind == "NUM"
        assert tokens[0].value == pytest.approx(3.14)

    def test_string_literal(self):
        tokens = Lexer('"hi"').tokenize()
        assert tokens[0].kind == "STRING"
        assert tokens[0].value == [ord("h"), ord("i")]

    def test_escape_newline(self):
        tokens = Lexer('"\\n"').tokenize()
        assert tokens[0].value == [10]

    def test_escape_hex(self):
        tokens = Lexer('"\\x41"').tokenize()
        assert tokens[0].value == [65]  # 'A'

    def test_escape_octal(self):
        tokens = Lexer('"\\101"').tokenize()
        assert tokens[0].value == [65]  # 'A'

    def test_push_var_single(self):
        tokens = Lexer("|5").tokenize()
        assert tokens[0].kind == "PUSH_VAR"
        assert tokens[0].value == 5

    def test_push_var_double(self):
        tokens = Lexer("|42").tokenize()
        assert tokens[0].kind == "PUSH_VAR"
        assert tokens[0].value == 42

    def test_bare_pipe(self):
        tokens = Lexer("|").tokenize()
        assert tokens[0].kind == "|"

    def test_comment_skipped(self):
        tokens = Lexer("# this is ignored\n42").tokenize()
        assert tokens[0].value == 42

    def test_unterminated_string_raises(self):
        with pytest.raises(LexError):
            Lexer('"no close').tokenize()

    def test_unknown_char_raises(self):
        with pytest.raises(LexError):
            Lexer("@").tokenize()


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------

class TestParser:
    def _parse(self, src):
        return Parser.from_source(src).parse()

    def test_num_push(self):
        prog = self._parse("7")
        assert prog.main_code[0] == ("NUM", 7)

    def test_float_push(self):
        prog = self._parse("3.0")
        assert prog.main_code[0] == ("NUM", 3.0)

    def test_special_opcode_not_pushed(self):
        prog = self._parse("16")  # DUP
        assert prog.main_code[0] == ("DUP", None)

    def test_float_28_is_always_push(self):
        # 28 as float must push, never be treated as else-separator
        prog = self._parse("28.0")
        assert prog.main_code[0] == ("NUM", 28.0)

    def test_function_def(self):
        prog = self._parse("/1 42 ;")
        assert len(prog.functions) == 1
        assert prog.functions[0].num == 1
        assert prog.functions[0].body == [("NUM", 42)]

    def test_function_call(self):
        prog = self._parse(".3")
        assert prog.main_code[0] == ("CALL", 3)

    def test_if_block(self):
        prog = self._parse("1 20 7 ;")
        kind, val = prog.main_code[1]
        assert kind == "IF_BLOCK"
        then_ops, else_ops = val
        assert then_ops == [("NUM", 7)]
        assert else_ops is None

    def test_if_else_block(self):
        prog = self._parse("1 20 7 28 9 ;")
        kind, val = prog.main_code[1]
        assert kind == "IF_BLOCK"
        then_ops, else_ops = val
        assert then_ops == [("NUM", 7)]
        assert else_ops == [("NUM", 9)]

    def test_while_block(self):
        prog = self._parse("1 30 18 1 ;")
        kind, val = prog.main_code[1]
        assert kind == "WHILE"

    def test_repeat_block(self):
        prog = self._parse("5 50 18 ;")
        kind, val = prog.main_code[1]
        assert kind == "REPEAT"

    def test_new_math_opcodes(self):
        for code, name in [(46, "ASIN"), (47, "ACOS"), (48, "ATAN"), (49, "ATAN2")]:
            prog = self._parse(str(code))
            assert prog.main_code[0] == (name, None), f"Expected {name} for {code}"

    def test_depth_opcode(self):
        prog = self._parse("63")
        assert prog.main_code[0] == ("DEPTH", None)

    def test_pick_opcode(self):
        prog = self._parse("64")
        assert prog.main_code[0] == ("PICK", None)


# ---------------------------------------------------------------------------
# Semantic analysis tests
# ---------------------------------------------------------------------------

class TestSema:
    def _check(self, src):
        prog = Parser.from_source(src).parse()
        SemanticAnalyzer().analyze(prog)

    def test_call_defined_ok(self):
        self._check("/0 1 ; .0")

    def test_call_undefined_raises(self):
        with pytest.raises(SemanticError):
            self._check(".99")

    def test_empty_while_raises(self):
        with pytest.raises(SemanticError):
            self._check("1 30 ;")

    def test_empty_repeat_raises(self):
        with pytest.raises(SemanticError):
            self._check("3 50 ;")


# ---------------------------------------------------------------------------
# Code-generation / end-to-end tests (require gcc)
# ---------------------------------------------------------------------------

class TestCodegen:
    def test_hello_world(self):
        _skip_no_gcc()
        out = compile_and_run('"Hello\\n"')
        assert out == "Hello\n"

    def test_arithmetic(self):
        _skip_no_gcc()
        out = compile_and_run("3 4 + |")
        assert out.strip() == "7"

    def test_float_arithmetic(self):
        _skip_no_gcc()
        out = compile_and_run("1.5 2.5 + |")
        assert float(out.strip()) == pytest.approx(4.0)

    def test_print_char(self):
        _skip_no_gcc()
        out = compile_and_run("65 ~")  # 'A'
        assert out == "A"

    def test_variables(self):
        _skip_no_gcc()
        out = compile_and_run("42 0 & |0 |")
        assert out.strip() == "42"

    def test_if_true(self):
        _skip_no_gcc()
        out = compile_and_run('1 20 "yes\\n" ; ')
        assert out == "yes\n"

    def test_if_false(self):
        _skip_no_gcc()
        out = compile_and_run('0 20 "yes\\n" 28 "no\\n" ;')
        assert out == "no\n"

    def test_dup_swap_drop(self):
        _skip_no_gcc()
        out = compile_and_run("5 16 + |")  # DUP then add → 10
        assert out.strip() == "10"

    def test_while_countdown(self):
        _skip_no_gcc()
        # count from 3 down to 1
        src = "3 0 & |0 0 11 30 |0 | |0 1 - 0 & |0 0 11 ;"
        out = compile_and_run(src)
        assert out.strip().split() == ["3", "2", "1"]

    def test_repeat(self):
        _skip_no_gcc()
        out = compile_and_run("3 50 | ;")  # prints 0 1 2
        assert out.strip().split() == ["0", "1", "2"]

    def test_function_call(self):
        _skip_no_gcc()
        src = '/0 "hi\\n" ; .0'
        out = compile_and_run(src)
        assert out == "hi\n"

    def test_asin(self):
        _skip_no_gcc()
        import math
        out = compile_and_run("1.0 46 |")  # asin(1) = π/2
        assert float(out.strip()) == pytest.approx(math.pi / 2, abs=1e-4)

    def test_acos(self):
        _skip_no_gcc()
        import math
        out = compile_and_run("1.0 47 |")  # acos(1) = 0
        assert float(out.strip()) == pytest.approx(0.0, abs=1e-4)

    def test_atan(self):
        _skip_no_gcc()
        import math
        out = compile_and_run("1.0 48 |")  # atan(1) = π/4
        assert float(out.strip()) == pytest.approx(math.pi / 4, abs=1e-4)

    def test_atan2(self):
        _skip_no_gcc()
        import math
        out = compile_and_run("1 1 49 |")  # atan2(1,1) = π/4
        assert float(out.strip()) == pytest.approx(math.pi / 4, abs=1e-4)

    def test_depth(self):
        _skip_no_gcc()
        out = compile_and_run("1 2 3 63 |")  # stack depth = 3
        assert out.strip() == "3"

    def test_pick(self):
        _skip_no_gcc()
        # stack: [10, 20, 30]; pick(1) → 20
        out = compile_and_run("10 20 30 1 64 |")
        assert out.strip() == "20"

    def test_logical_not(self):
        _skip_no_gcc()
        out = compile_and_run("0 ! |")
        assert out.strip() == "1"

    def test_logical_and(self):
        _skip_no_gcc()
        out = compile_and_run("1 1 39 |")
        assert out.strip() == "1"

    def test_logical_or(self):
        _skip_no_gcc()
        out = compile_and_run("0 1 19 |")
        assert out.strip() == "1"

    def test_bitwise_and(self):
        _skip_no_gcc()
        out = compile_and_run("12 10 40 |")  # 12 & 10 = 8
        assert out.strip() == "8"

    def test_sqrt(self):
        _skip_no_gcc()
        out = compile_and_run("4 22 |")  # sqrt(4) = 2
        assert float(out.strip()) == pytest.approx(2.0)

    def test_string_escape(self):
        _skip_no_gcc()
        out = compile_and_run('"\\x41\\n"')  # \x41 = 'A'
        assert out == "A\n"
