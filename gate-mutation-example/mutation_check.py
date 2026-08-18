"""Prove the tests have teeth: flip a load-bearing line, confirm the suite goes
RED, restore byte-identically, confirm GREEN. A test that can't fail is a
decoration — this is how I tell the difference. Run: `make mutations`.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile

# (label, file, old, new) — each mutation is a defect the suite MUST catch.
MUTATIONS = [
    ("fail-open exit 3 -> 0 (UNCHECKED create reads as clean)",
     "cli.py", '"created_fail_open": 3,', '"created_fail_open": 0,'),
    ("dedup threshold 3 -> 99 (nothing ever dedups)",
     "gate.py", "if overlap >= 3 and", "if overlap >= 99 and"),
    ("empty-title guard removed",
     "cli.py", 'if not (args.title or "").strip():', "if False:"),
    ("json_safe falls back to str() (the numpy-bool truthy bug)",
     "json_safe.py", "return json.dumps(obj, default=_to_native)",
     "return json.dumps(obj, default=str)"),
]


def _pytest() -> int:
    return subprocess.run([sys.executable, "-B", "-m", "pytest", "-q"],
                          capture_output=True, text=True).returncode


def main() -> int:
    if _pytest() != 0:
        print("BASELINE NOT GREEN — fix the suite before mutating.")
        return 1
    all_caught = True
    for label, fname, old, new in MUTATIONS:
        src = open(fname).read()
        if src.count(old) != 1:
            print(f"  ANCHOR NOT UNIQUE ({src.count(old)}): {label}")
            all_caught = False
            continue
        backup = tempfile.mktemp()
        shutil.copy(fname, backup)
        open(fname, "w").write(src.replace(old, new, 1))
        caught = _pytest() != 0
        shutil.copy(backup, fname)                       # restore
        assert open(fname, "rb").read() == src.encode(), f"restore not byte-identical: {fname}"
        print(f"  {'RED (caught)' if caught else 'GREEN (SURVIVED!)'}  {label}")
        all_caught = all_caught and caught
    ok = _pytest() == 0
    print(f"\npost-restore suite: {'green' if ok else 'RED'}")
    print("ALL MUTATIONS CAUGHT" if all_caught and ok else "A MUTATION SURVIVED")
    return 0 if (all_caught and ok) else 1


if __name__ == "__main__":
    sys.exit(main())
