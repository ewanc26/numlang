#!/usr/bin/env python3
"""Differential tests: numlang programs versus equivalent C programs.

Usage: tests/differential/run_differential.py [--numlangc PATH] [--cc CC]

Each NAME.num has a NAME.c expressing the same operation. Both are run and
their stdout and exit status must match. The C side is compiled with
-std=c23 -Wall -Wextra -Werror -pedantic.
"""

import argparse
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
C_FLAGS = ["-std=c23", "-Wall", "-Wextra", "-Werror", "-pedantic"]


def run(cmd, **kwargs):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60, **kwargs)


def check(source: pathlib.Path, numlangc: str, cc: str, tmp: pathlib.Path) -> bool:
    nl = run([numlangc, str(source), "--run", "--cc", cc])
    c_src = source.with_suffix(".c")
    c_bin = tmp / f"{source.stem}_ref"
    build = run([cc, *C_FLAGS, str(c_src), "-o", str(c_bin), "-lm"])
    if build.returncode != 0:
        print(f"FAIL {source.stem}: C reference did not build\n{build.stderr}")
        return False
    ref = run([str(c_bin)])
    if nl.stdout != ref.stdout or nl.returncode != ref.returncode:
        print(f"FAIL {source.stem}: stdout or exit status differs")
        print(f"  numlang: {nl.returncode} {nl.stdout!r} {nl.stderr.strip()}")
        print(f"  C:       {ref.returncode} {ref.stdout!r}")
        return False
    print(f"PASS {source.stem}")
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--numlangc", default="numlangc")
    parser.add_argument("--cc", default="cc")
    args = parser.parse_args()

    sources = sorted(HERE.glob("*.num"))
    if not sources:
        print("no differential cases found", file=sys.stderr)
        raise SystemExit(1)

    with tempfile.TemporaryDirectory() as tmp:
        results = [check(s, args.numlangc, args.cc, pathlib.Path(tmp)) for s in sources]
    passed = sum(results)
    print(f"{passed}/{len(results)} differential cases passed")
    if passed != len(results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
