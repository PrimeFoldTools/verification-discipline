"""CLI over gate.submit() — the exit-code contract a caller relies on.

Exit codes: 0 gate ran (created / attached / dry-run) · 3 record created UNCHECKED
because the store was unreadable (fail-open — must NOT read as a clean 0) · 1 bad
args / self error. Output is one JSON object on stdout, via the numpy-safe encoder.
"""
from __future__ import annotations

import argparse

import gate
from json_safe import dumps

_EXIT_BY_OUTCOME = {
    "dry_run": 0,
    "created": 0,
    "attached": 0,
    "created_fail_open": 3,   # UNCHECKED create — never a silent 0
}


def run(argv, *, submit_fn=None, client=None) -> int:
    submit_fn = submit_fn or gate.submit
    ap = argparse.ArgumentParser(prog="cli.py")
    ap.add_argument("--title", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    if not (args.title or "").strip():
        print(dumps({"outcome": "error", "error": "--title must be non-empty"}))
        return 1
    try:
        outcome = submit_fn({"title": args.title}, client=client, dry_run=args.dry_run)
    except Exception as exc:  # noqa: BLE001 - a self-error is exit 1, never a silent 0
        print(dumps({"outcome": "error", "error": f"{type(exc).__name__}: {exc}"}))
        return 1
    print(dumps(outcome))
    return _EXIT_BY_OUTCOME.get(outcome.get("outcome"), 1)
