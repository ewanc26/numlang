#!/usr/bin/env python3
"""Smoke tests for the bootstrapped C++ Numlang compiler."""
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def run(cmd, expected=0):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if r.returncode != expected:
        raise AssertionError(
            f"{cmd!r} returned {r.returncode}, expected {expected}\nstdout={r.stdout!r}\nstderr={r.stderr!r}"
        )
    return r


def main():
    if len(sys.argv) != 3:
        print("usage: smoke_cpp.py <numlangc> <host-cc>", file=sys.stderr)
        return 2
    compiler = str(Path(sys.argv[1]).resolve())
    host_cc_arg = sys.argv[2]
    host_cc_path = Path(host_cc_arg)
    if host_cc_path.is_absolute() or host_cc_path.exists():
        # Keep real paths absolute for the wrapper script.
        cc = str(host_cc_path.resolve())
    else:
        # Keep PATH executables (e.g. "cc") unresolved for PATH lookup.
        cc = host_cc_arg
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="numlang smoke ' path ") as d:
        tmp = Path(d)
        wrapper = tmp / "host C compiler's wrapper"
        wrapper.write_text(
            "#!/bin/sh\nexec " + shlex.quote(cc) + ' "$@"\n', encoding="utf-8"
        )
        wrapper.chmod(0o755)
        r = run(
            [
                compiler,
                str(root / "examples/hello_world.num"),
                "--run",
                "--cc",
                str(wrapper),
            ]
        )
        assert r.stdout == "Hello, World!\n", repr(r.stdout)
        r = run(
            [compiler, str(root / "examples/hello.num"), "--run", "--cc", str(wrapper)]
        )
        assert r.stdout == "42\n", repr(r.stdout)
        p = tmp / "nul-followed-by-digit.num"
        p.write_text('"\\01"', encoding="utf-8")
        r = run([compiler, str(p), "--run", "--cc", str(wrapper)])
        assert r.stdout == "\x001", repr(r.stdout)
        p = tmp / "hex.num"
        p.write_text("0xA |", encoding="utf-8")
        r = run([compiler, str(p), "--run", "--cc", str(wrapper)])
        assert r.stdout == "10\n", repr(r.stdout)

        p = tmp / "hex-alpha.num"
        p.write_text("0xDE |", encoding="utf-8")
        r = run([compiler, str(p), "--run", "--cc", str(wrapper)])
        assert r.stdout == "222\n", repr(r.stdout)
        p = tmp / "binary.num"
        p.write_text("0b101 |", encoding="utf-8")
        r = run([compiler, str(p), "--run", "--cc", str(wrapper)])
        assert r.stdout == "5\n", repr(r.stdout)
        p = tmp / "suffixed-integer.num"
        p.write_text("42u |", encoding="utf-8")
        r = run([compiler, str(p), "--run", "--cc", str(wrapper)])
        assert r.stdout == "42\n", repr(r.stdout)
        p = tmp / "bitwise.num"
        p.write_text("5 3 42 |", encoding="utf-8")
        r = run([compiler, str(p), "--run", "--cc", str(wrapper)])
        assert r.stdout == "6\n", repr(r.stdout)
        p = tmp / "signed-right-shift.num"
        p.write_text("0 8 - 1 45 |", encoding="utf-8")
        r = run([compiler, str(p), "--run", "--cc", str(wrapper)])
        assert r.stdout == "-4\n", repr(r.stdout)
        p = tmp / "left-shift-wrap.num"
        p.write_text("2147483647 1 44 |", encoding="utf-8")
        r = run([compiler, str(p), "--run", "--cc", str(wrapper)])
        assert r.stdout == "-2\n", repr(r.stdout)
        p = tmp / "bitwise-range.num"
        p.write_text("2147483648 1 40 |", encoding="utf-8")
        r = run([compiler, str(p), "--run", "--cc", str(wrapper)], expected=1)
        assert "integer conversion out of range" in r.stderr, repr(r.stderr)
        p = tmp / "remainder-overflow.num"
        p.write_text("0 2147483648 - 0 1 - 38 |", encoding="utf-8")
        r = run([compiler, str(p), "--run", "--cc", str(wrapper)], expected=1)
        assert "integer remainder overflow" in r.stderr, repr(r.stderr)
        p = tmp / "invalid-shift.num"
        p.write_text("1 32.0 44 |", encoding="utf-8")
        r = run([compiler, str(p), "--run", "--cc", str(wrapper)], expected=1)
        assert "invalid shift" in r.stderr, repr(r.stderr)
        p = tmp / "large-float.num"
        p.write_text("1e100 |", encoding="utf-8")
        r = run([compiler, str(p), "--run", "--cc", str(wrapper)])
        assert r.stdout == "1e+100\n", repr(r.stdout)
        for name, source, diagnostic in [
            ("bad-binary.num", "0b102", "invalid binary literal"),
            ("bad-suffix.num", "42foo", "invalid integer suffix"),
            ("bad-octal.num", "08", "invalid integer"),
        ]:
            p = tmp / name
            p.write_text(source, encoding="utf-8")
            r = run([compiler, str(p), "--run", "--cc", str(wrapper)], expected=1)
            assert diagnostic in r.stderr, (name, r.stderr)
        p = tmp / "unsupported-control-flow.num"
        p.write_text("30", encoding="utf-8")
        r = run([compiler, str(p), "--run", "--cc", str(wrapper)], expected=1)
        assert "opcode 30 is not yet implemented" in r.stderr, repr(r.stderr)
        p = tmp / "arithmetic.num"
        p.write_text("2.0 3.0 + |", encoding="utf-8")
        r = run([compiler, str(p), "--run", "--cc", str(wrapper)])
        assert r.stdout == "5\n", repr(r.stdout)
        p = tmp / "integer-division.num"
        p.write_text("7 2 55 |", encoding="utf-8")
        r = run([compiler, str(p), "--run", "--cc", str(wrapper)])
        assert r.stdout == "3\n", repr(r.stdout)
        p = tmp / "integer-division-truncates.num"
        p.write_text("0 7 - 2 55 |", encoding="utf-8")
        r = run([compiler, str(p), "--run", "--cc", str(wrapper)])
        assert r.stdout == "-3\n", repr(r.stdout)  # C division truncates toward zero
        p = tmp / "integer-division-by-zero.num"
        p.write_text("7 0 55 |", encoding="utf-8")
        r = run([compiler, str(p), "--run", "--cc", str(wrapper)], expected=1)
        assert "integer division by zero" in r.stderr, repr(r.stderr)
        p = tmp / "integer-division-overflow.num"
        p.write_text("0 2147483648 - 0 1 - 55 |", encoding="utf-8")
        r = run([compiler, str(p), "--run", "--cc", str(wrapper)], expected=1)
        assert "integer division overflow" in r.stderr, repr(r.stderr)
        p = tmp / "integer-division-range.num"
        p.write_text("2147483648 1 55 |", encoding="utf-8")
        r = run([compiler, str(p), "--run", "--cc", str(wrapper)], expected=1)
        assert "integer conversion out of range" in r.stderr, repr(r.stderr)
        # Runtime opcodes 60-64: RAND, TIME, EXIT, DEPTH, PICK.
        p = tmp / "stack-depth.num"
        p.write_text("1.0 2.0 3.0 63 |", encoding="utf-8")
        r = run([compiler, str(p), "--run", "--cc", str(wrapper)])
        assert r.stdout == "3\n", repr(r.stdout)
        p = tmp / "pick.num"
        p.write_text("7.0 8.0 9.0 1 64 |", encoding="utf-8")
        r = run([compiler, str(p), "--run", "--cc", str(wrapper)])
        assert r.stdout == "8\n", repr(r.stdout)
        p = tmp / "pick-top.num"
        p.write_text("7.0 8.0 9.0 0 64 |", encoding="utf-8")
        r = run([compiler, str(p), "--run", "--cc", str(wrapper)])
        assert r.stdout == "9\n", repr(r.stdout)
        p = tmp / "pick-out-of-range.num"
        p.write_text("1.0 9 64 |", encoding="utf-8")
        r = run([compiler, str(p), "--run", "--cc", str(wrapper)], expected=1)
        assert "PICK index out of range" in r.stderr, repr(r.stderr)
        p = tmp / "pick-negative.num"
        p.write_text("1.0 0 1 - 64 |", encoding="utf-8")
        r = run([compiler, str(p), "--run", "--cc", str(wrapper)], expected=1)
        assert "PICK index out of range" in r.stderr, repr(r.stderr)
        p = tmp / "exit.num"
        p.write_text("42.0 62", encoding="utf-8")
        r = run([compiler, str(p), "--run", "--cc", str(wrapper)], expected=42)
        p = tmp / "time.num"
        p.write_text("61 |", encoding="utf-8")
        r = run([compiler, str(p), "--run", "--cc", str(wrapper)])
        now = time.time()
        printed = float(r.stdout)
        # "|" prints "%g" (six significant digits), so a Unix timestamp of
        # ~1.79e9 only survives to within its sixth digit (~1e4).
        assert abs(printed - now) < 10000, repr(r.stdout)
        p = tmp / "rand.num"
        p.write_text("60 | 60 | 60 |", encoding="utf-8")
        r = run([compiler, str(p), "--run", "--cc", str(wrapper)])
        values = [float(line) for line in r.stdout.split()]
        assert len(values) == 3 and all(0.0 <= v < 1.0 for v in values), repr(r.stdout)

        # Foreign C functions: declare with @N, call with $N.
        p = tmp / "ffi.num"
        p.write_text(
            '@0 "math.h" "hypot" 2 ;\n@1 "math.h" "fmax" 2 ;\n3 4 $0 |\n5 2 $1 |\n',
            encoding="utf-8",
        )
        r = run([compiler, str(p), "--run", "--cc", str(wrapper)])
        assert r.stdout == "5\n5\n", repr(r.stdout)

        p = tmp / "ffi-undeclared.num"
        p.write_text("3 4 $0 |", encoding="utf-8")
        r = run([compiler, str(p), "--run", "--cc", str(wrapper)], expected=1)
        assert "undeclared foreign function 0" in r.stderr, repr(r.stderr)

        p = tmp / "ffi-bad-arity.num"
        p.write_text('@0 "math.h" "hypot" 9 ;\n3 4 $0 |', encoding="utf-8")
        r = run([compiler, str(p), "--run", "--cc", str(wrapper)], expected=1)
        assert "arity must be 0-3" in r.stderr, repr(r.stderr)

        # Cramer's rule solves the 2x2 system with slot-held determinants.
        r = run(
            [
                compiler,
                str(root / "examples" / "cramer.num"),
                "--run",
                "--cc",
                str(wrapper),
            ]
        )
        assert r.stdout == "x = 2\ny = 3\n", repr(r.stdout)

        # The quadratic example walks the full formula with variables, the
        # discriminant, and sqrt (opcode 22).
        r = run(
            [
                compiler,
                str(root / "examples" / "quadratic.num"),
                "--run",
                "--cc",
                str(wrapper),
            ]
        )
        assert r.stdout == "root 1: 3\nroot 2: 2\n", repr(r.stdout)

        p = tmp / "variables.num"
        p.write_text("42.0 1 & |1 |", encoding="utf-8")
        r = run([compiler, str(p), "--run", "--cc", str(wrapper)])
        assert r.stdout == "42\n", repr(r.stdout)

        # Donut engine pipeline: the generator emits a finite 2-frame vertex
        # stream (F / px py z intensity per vertex / S protocol) that is a
        # byte-exact match of the canonical sigi engine capture
        # (tests/fixtures/donut_canonical_v2_2f.txt), and the SDL2 host
        # renders it headlessly when SDL2 is available.
        engine = tmp / "donut_engine.num"
        run(
            [
                "python3",
                str(root / "scripts" / "gen_donut_engine.py"),
                "--frames",
                "2",
                "--output",
                str(engine),
            ]
        )
        r = run([compiler, str(engine), "--run", "--cc", str(wrapper)])
        engine_out = r.stdout
        toks = engine_out.split()
        frames = 0
        values = 0
        i = 0
        while i < len(toks):
            assert toks[i] == "F", repr(toks[i : i + 3])
            i += 1
            frames += 1
            while i < len(toks) and toks[i] != "S":
                float(toks[i])  # px, py, z, intensity - one per vertex
                values += 1
                i += 1
            i += 1  # consume S
        assert frames == 2, frames
        assert values == 2 * 4 * 1500, values
        # Cross-language parity: the vendored canonical fixture and the
        # engine's own output must agree byte-for-byte for these frames.
        fixture = (root / "tests" / "fixtures" / "donut_canonical_v2_2f.txt").read_text(
            encoding="utf-8"
        )
        got_lines = engine_out.splitlines()
        want_lines = fixture.splitlines()
        assert len(want_lines) == 2 * 6002, len(want_lines)
        first_diff = None
        for k, (g, w) in enumerate(zip(got_lines, want_lines)):
            if g != w:
                first_diff = (k + 1, g, w)  # 1-based line number
                break
        assert first_diff is None and got_lines == want_lines, (
            "donut stream diverges from canonical fixture; "
            "first difference at line {} of {} (got {!r}, want {!r})".format(
                first_diff[0] if first_diff else (len(got_lines) + 1),
                len(want_lines),
                first_diff[1] if first_diff else "<eof>",
                first_diff[2] if first_diff else "<eof>",
            )
        )

        # User .c shims: a header ending in .c is included from the source
        # .num file's directory, even when compiled from a temp directory.
        p = tmp / "shim.num"
        p.write_text(
            '@0 "donut_smoke.c" "donut_smoke" 1 ;\n2.5 $0 |\n',
            encoding="utf-8",
        )
        (tmp / "donut_smoke.c").write_text(
            "#include <stdio.h>\n"
            "double donut_smoke(double v) { "
            'printf("shim:%g\\n", v); return 0.0; }\n',
            encoding="utf-8",
        )
        r = run([compiler, str(p), "--run", "--cc", str(wrapper)])
        assert r.stdout == "shim:2.5\n0\n", repr(r.stdout)

        # Headless render: the reconciled stream must play through the SDL2
        # host unchanged when SDL2 is available.
        sdl2_config = shutil.which("sdl2-config")
        if sdl2_config:
            host_bin = tmp / "donut_host"
            cfg = subprocess.run(
                [sdl2_config, "--cflags", "--libs"],
                capture_output=True,
                text=True,
                timeout=30,
            ).stdout.split()
            run(
                [
                    "cc",
                    "-std=c99",
                    "-O2",
                    str(root / "host" / "donut_host.c"),
                    "-o",
                    str(host_bin),
                ]
                + cfg
            )
            env = dict(os.environ, SDL_VIDEODRIVER="dummy")
            hr = subprocess.run(
                [str(host_bin), "--frames", "2"],
                input=engine_out,
                capture_output=True,
                text=True,
                timeout=30,
                env=env,
            )
            assert hr.returncode == 0, repr(hr.stderr)
            assert "2 frames, 3000 vertices" in hr.stderr, repr(hr.stderr)

        output = tmp / "generated C output.c"
        run([compiler, str(root / "examples/hello_world.num"), "-o", str(output)])
        assert "int main(void)" in output.read_text(encoding="utf-8")
        r = run([compiler, str(tmp / "missing.num"), "-o", str(output)], expected=1)
        assert "cannot read source file" in r.stderr
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
