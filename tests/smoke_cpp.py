#!/usr/bin/env python3
"""Smoke tests for the bootstrapped C++ Numlang compiler."""
import shlex, subprocess, sys, tempfile
from pathlib import Path

def run(cmd, expected=0):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if r.returncode != expected:
        raise AssertionError(f"{cmd!r} returned {r.returncode}, expected {expected}\nstdout={r.stdout!r}\nstderr={r.stderr!r}")
    return r

def main():
    if len(sys.argv) != 3:
        print("usage: smoke_cpp.py <numlangc> <host-cc>", file=sys.stderr)
        return 2
    compiler, cc = str(Path(sys.argv[1]).resolve()), str(Path(sys.argv[2]).resolve())
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="numlang smoke ' path ") as d:
        tmp = Path(d)
        wrapper = tmp / "host C compiler's wrapper"
        wrapper.write_text("#!/bin/sh\nexec " + shlex.quote(cc) + ' "$@"\n', encoding="utf-8")
        wrapper.chmod(0o755)
        r = run([compiler, str(root / "examples/hello_world.num"), "--run", "--cc", str(wrapper)])
        assert r.stdout == "Hello, World!\n", repr(r.stdout)
        r = run([compiler, str(root / "examples/hello.num"), "--run", "--cc", str(wrapper)])
        assert r.stdout == "42\n", repr(r.stdout)
        p = tmp / "nul-followed-by-digit.num"; p.write_text('"\\01" |', encoding="utf-8")
        r = run([compiler, str(p), "--run", "--cc", str(wrapper)])
        assert r.stdout == "\x001\n", repr(r.stdout)
        p = tmp / "hex.num"; p.write_text("0xA |", encoding="utf-8")
        r = run([compiler, str(p), "--run", "--cc", str(wrapper)])
        assert r.stdout == "10\n", repr(r.stdout)

        p = tmp / "hex-alpha.num"; p.write_text("0xDE |", encoding="utf-8")
        r = run([compiler, str(p), "--run", "--cc", str(wrapper)])
        assert r.stdout == "222\n", repr(r.stdout)
        p = tmp / "binary.num"; p.write_text("0b101 |", encoding="utf-8")
        r = run([compiler, str(p), "--run", "--cc", str(wrapper)])
        assert r.stdout == "5\n", repr(r.stdout)
        p = tmp / "suffixed-integer.num"; p.write_text("42u |", encoding="utf-8")
        r = run([compiler, str(p), "--run", "--cc", str(wrapper)])
        assert r.stdout == "42\n", repr(r.stdout)
        p = tmp / "bitwise.num"; p.write_text("5 3 42 |", encoding="utf-8")
        r = run([compiler, str(p), "--run", "--cc", str(wrapper)])
        assert r.stdout == "6\n", repr(r.stdout)
        p = tmp / "signed-right-shift.num"; p.write_text("0 8 - 1 45 |", encoding="utf-8")
        r = run([compiler, str(p), "--run", "--cc", str(wrapper)])
        assert r.stdout == "-4\n", repr(r.stdout)
        p = tmp / "left-shift-wrap.num"; p.write_text("2147483647 1 44 |", encoding="utf-8")
        r = run([compiler, str(p), "--run", "--cc", str(wrapper)])
        assert r.stdout == "-2147483648\n", repr(r.stdout)
        p = tmp / "bitwise-range.num"; p.write_text("2147483648 1 40 |", encoding="utf-8")
        r = run([compiler, str(p), "--run", "--cc", str(wrapper)], expected=1)
        assert "integer conversion out of range" in r.stderr, repr(r.stderr)
        p = tmp / "large-float.num"; p.write_text("1e100 |", encoding="utf-8")
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
        p = tmp / "unsupported-control-flow.num"; p.write_text("30", encoding="utf-8")
        r = run([compiler, str(p), "--run", "--cc", str(wrapper)], expected=1)
        assert "opcode 30 is not yet implemented" in r.stderr, repr(r.stderr)
        p = tmp / "arithmetic.num"; p.write_text("2.0 3.0 + |", encoding="utf-8")
        r = run([compiler, str(p), "--run", "--cc", str(wrapper)])
        assert r.stdout == "5\n", repr(r.stdout)
        p = tmp / "variables.num"; p.write_text("42.0 1 & |1 |", encoding="utf-8")
        r = run([compiler, str(p), "--run", "--cc", str(wrapper)])
        assert r.stdout == "42\n", repr(r.stdout)
        output = tmp / "generated C output.c"
        run([compiler, str(root / "examples/hello_world.num"), "-o", str(output)])
        assert "int main(void)" in output.read_text(encoding="utf-8")
        r = run([compiler, str(tmp / "missing.num"), "-o", str(output)], expected=1)
        assert "cannot read source file" in r.stderr
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
