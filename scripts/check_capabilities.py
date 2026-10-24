#!/usr/bin/env python3
"""Validate capabilities.json, the matrix shared by all four esoteric languages.

Usage: scripts/check_capabilities.py [--language NAME] [--require-complete]

Structure is checked for every language. With --language and --require-complete,
every in-scope row for that language must be implemented, and each implemented
cell must name tests that exist in the repo.
"""

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
MATRIX = ROOT / "capabilities.json"
STATUSES = {"implemented", "partial", "missing", "non_applicable"}


def fail(message: str) -> None:
    print(f"capability matrix error: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--language")
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()

    data = json.loads(MATRIX.read_text(encoding="utf-8"))
    if data.get("schema") != 1:
        fail("schema must be 1")
    languages = data.get("languages")
    if not languages:
        fail("languages must be listed")
    if args.language and args.language not in languages:
        fail(f"unknown language {args.language!r}")

    ids: set[str] = set()
    for row in data.get("rows", []):
        row_id = row.get("id")
        if not row_id or row_id in ids:
            fail(f"row id missing or duplicated: {row_id!r}")
        ids.add(row_id)
        cells = row.get("cells", {})
        if set(cells) != set(languages):
            fail(f"{row_id}: cells must cover exactly {languages}")
        for language, cell in cells.items():
            status = cell.get("status")
            if status not in STATUSES:
                fail(f"{row_id}/{language}: invalid status {status!r}")
            if status == "non_applicable" and not cell.get("rationale"):
                fail(f"{row_id}/{language}: non_applicable needs a rationale")
            if status == "implemented" and not cell.get("tests"):
                fail(f"{row_id}/{language}: implemented needs tests")

    if args.language and args.require_complete:
        incomplete = []
        for row in data["rows"]:
            cell = row["cells"][args.language]
            if cell["status"] not in {"implemented", "non_applicable"}:
                incomplete.append(f"{row['id']}={cell['status']}")
            for test in cell.get("tests", []):
                if not (ROOT / test).exists():
                    fail(f"{row['id']}: test {test} does not exist")
        if incomplete:
            fail(f"{args.language} is not complete: " + ", ".join(incomplete))

    print(f"capability matrix OK: {len(ids)} rows, languages {', '.join(languages)}")


if __name__ == "__main__":
    main()
