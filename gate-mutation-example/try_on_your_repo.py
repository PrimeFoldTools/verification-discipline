"""Can your tests fail? Plant a few small bugs in a COPY of your project and see.

    python3 try_on_your_repo.py /path/to/project --test "python3 -m pytest -q"

It copies your project to a temporary folder, runs your tests once (they must
pass), then plants one bug at a time: a flipped comparison, a swapped True/False,
`and` turned into `or`, a `return x` turned into `return None`. After each one it
runs your tests again. A failing run means your tests caught the bug. A passing
run means the bug survived. Your own files are never touched.

This is a two-minute smoke check, not full mutation testing. For that, use
mutmut: https://github.com/boxed/mutmut
"""
from __future__ import annotations

import argparse
import ast
import os
import random
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass

SKIP_DIRS = {".git", ".hg", ".venv", "venv", "env", ".tox", ".nox", "node_modules",
             "__pycache__", "build", "dist", ".mypy_cache", ".pytest_cache", ".eggs"}

FLIP = {ast.Eq: "!=", ast.NotEq: "==", ast.Lt: ">=", ast.GtE: "<",
        ast.Gt: "<=", ast.LtE: ">"}
OP_TEXT = {ast.Eq: "==", ast.NotEq: "!=", ast.Lt: "<", ast.GtE: ">=",
           ast.Gt: ">", ast.LtE: "<="}


@dataclass
class Site:
    path: str        # relative to project root
    line: int        # 1-based
    col: int         # 0-based start of the text to replace
    end: int         # 0-based end (same line)
    before: str
    after: str


def is_test_file(rel: str) -> bool:
    parts = rel.replace(os.sep, "/").split("/")
    name = parts[-1]
    return (name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py"
            or any(p in ("tests", "test", "testing") for p in parts[:-1]))


def source_files(root: str, only: list[str] | None) -> list[str]:
    out = []
    for d, dirs, files in os.walk(root):
        dirs[:] = sorted(x for x in dirs if x not in SKIP_DIRS and not x.endswith(".egg-info"))
        for f in sorted(files):
            if not f.endswith(".py"):
                continue
            rel = os.path.relpath(os.path.join(d, f), root)
            if is_test_file(rel) or f == "setup.py":
                continue
            if only and not any(rel.startswith(p.rstrip("/")) for p in only):
                continue
            out.append(rel)
    return out


def sites_in(rel: str, text: str) -> list[Site]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    lines = text.splitlines(keepends=True)
    found: list[Site] = []

    def seg(line: int, col: int, end: int) -> str:
        return lines[line - 1][col:end]

    for node in ast.walk(tree):
        # comparisons with one operator: a == b  ->  a != b
        if isinstance(node, ast.Compare) and len(node.ops) == 1 and type(node.ops[0]) in FLIP:
            left, right = node.left, node.comparators[0]
            if left.end_lineno != right.lineno:
                continue
            gap = seg(right.lineno, left.end_col_offset, right.col_offset)
            op = OP_TEXT[type(node.ops[0])]
            idx = gap.find(op)
            if idx < 0 or gap.count(op) != 1:
                continue
            col = left.end_col_offset + idx
            found.append(Site(rel, right.lineno, col, col + len(op), op, FLIP[type(node.ops[0])]))
        # True <-> False
        elif isinstance(node, ast.Constant) and isinstance(node.value, bool) and node.lineno == node.end_lineno:
            before = "True" if node.value else "False"
            if seg(node.lineno, node.col_offset, node.end_col_offset) == before:
                found.append(Site(rel, node.lineno, node.col_offset, node.end_col_offset,
                                  before, "False" if node.value else "True"))
        # a and b  <->  a or b (two operands on one line)
        elif isinstance(node, ast.BoolOp) and len(node.values) == 2:
            a, b = node.values
            if a.end_lineno != b.lineno:
                continue
            gap = seg(b.lineno, a.end_col_offset, b.col_offset)
            word = "and" if isinstance(node.op, ast.And) else "or"
            idx = gap.find(word)
            if idx < 0 or gap.count(word) != 1:
                continue
            col = a.end_col_offset + idx
            found.append(Site(rel, b.lineno, col, col + len(word), word, "or" if word == "and" else "and"))
        # return <expr>  ->  return None (single-line returns only)
        elif isinstance(node, ast.Return) and node.value is not None and node.lineno == node.end_lineno:
            v = node.value
            if isinstance(v, ast.Constant) and v.value is None:
                continue
            before = seg(v.lineno, v.col_offset, v.end_col_offset)
            found.append(Site(rel, v.lineno, v.col_offset, v.end_col_offset, before, "None"))
    return found


def run_tests(cmd: str, cwd: str, timeout: int) -> tuple[str, str]:
    """Return ("pass" | "fail" | "timeout", combined output)."""
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    try:
        r = subprocess.run(shlex.split(cmd, posix=os.name != "nt"), cwd=cwd, env=env,
                           capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return "timeout", ""
    return ("pass" if r.returncode == 0 else "fail"), (r.stdout or "") + (r.stderr or "")


def caught_by(output: str) -> str:
    """Name the test that failed, from pytest or unittest output."""
    m = re.search(r"^(?:FAILED|ERROR) (\S+)", output, re.M)          # pytest
    if m:
        return m.group(1)
    m = re.search(r"^(?:FAIL|ERROR): (\S+) \(([^)]+)\)", output, re.M)  # unittest
    if m:
        return f"{m.group(2)}.{m.group(1)}"
    return "(test name not in output)"


def changed_lines(project: str, ref: str) -> dict[str, set[int]] | str:
    """Lines added or changed since `ref` (plus new untracked .py files), keyed by
    path relative to `project`. Returns an error message string on failure."""
    def git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-c", "core.quotepath=off", "-C", project, *args],
                              capture_output=True, text=True)
    try:
        if git("rev-parse", "--is-inside-work-tree").returncode != 0:
            return f"--changed needs a git repository, and {project} is not one."
    except FileNotFoundError:
        return "--changed needs git, and git is not installed."
    diff = git("diff", "-U0", "--no-color", "--relative", ref, "--", "*.py")
    if diff.returncode != 0:
        return f"git could not compare against '{ref}': {diff.stderr.strip()}"
    out: dict[str, set[int]] = {}
    path = None
    for line in diff.stdout.splitlines():
        if line.startswith("+++ "):
            name = line[4:].rstrip("\t")        # git adds a tab after names with spaces
            path = None if name == "/dev/null" else name[2:] if name.startswith("b/") else name
        elif line.startswith("@@") and path:
            m = re.match(r"@@ -\S+ \+(\d+)(?:,(\d+))? @@", line)
            if m:
                start, count = int(m.group(1)), int(m.group(2) if m.group(2) is not None else 1)
                out.setdefault(os.path.normpath(path), set()).update(range(start, start + count))
    new = git("ls-files", "--others", "--exclude-standard", "--", "*.py")
    for rel in new.stdout.splitlines():
        with open(os.path.join(project, rel), encoding="utf-8", errors="surrogateescape") as f:
            out[os.path.normpath(rel)] = set(range(1, len(f.read().splitlines()) + 1))
    return out


def apply(text: str, s: Site) -> str:
    lines = text.splitlines(keepends=True)
    ln = lines[s.line - 1]
    assert ln[s.col:s.end] == s.before, "site moved"
    lines[s.line - 1] = ln[:s.col] + s.after + ln[s.end:]
    return "".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Plant small bugs in a copy of your project and see if your tests catch them.")
    p.add_argument("project", help="path to your project")
    p.add_argument("--test", default="python3 -m pytest -q -x", help='test command (default: "python3 -m pytest -q -x")')
    p.add_argument("--max", type=int, default=10, help="how many bugs to plant (default 10)")
    p.add_argument("--timeout", type=int, default=120, help="seconds per test run (default 120)")
    p.add_argument("--seed", type=int, default=0, help="which bugs get picked (default 0)")
    p.add_argument("--paths", nargs="*", help="only plant bugs under these folders, e.g. src/")
    p.add_argument("--changed", nargs="?", const="HEAD", metavar="REF",
                   help="only plant bugs in lines changed since REF (default HEAD: your uncommitted edits)")
    a = p.parse_args(argv)

    src_root = os.path.abspath(a.project)
    if not os.path.isdir(src_root):
        print(f"Not a folder: {src_root}")
        return 64
    only = None
    if a.changed:
        only = changed_lines(src_root, a.changed)
        if isinstance(only, str):
            print(only)
            return 64
        if not only:
            print(f"Nothing changed in .py files since {a.changed}. Nothing to check.")
            return 0
    work = tempfile.mkdtemp(prefix="try_on_your_repo_")
    root = os.path.join(work, "project")
    try:
        shutil.copytree(src_root, root, ignore=shutil.ignore_patterns(*SKIP_DIRS, "*.egg-info"))
        print(f"Working in a copy: {root}")
        t0 = time.time()
        if run_tests(a.test, root, a.timeout)[0] != "pass":
            print("Your tests do not pass on the unchanged copy. Fix that first, then run this again.")
            return 2
        files = source_files(root, a.paths)
        # Self-check: break every source file in the copy at once. If the tests
        # still pass, they are not loading this copy (an installed package, or
        # tests that never import the code), and every planted bug would look
        # like it survived. Stop instead of reporting that.
        saved = {}
        for rel in files:
            path = os.path.join(root, rel)
            with open(path, "rb") as f:
                saved[path] = f.read()
            with open(path, "wb") as f:
                f.write(b'raise ImportError("try_on_your_repo self-check")\n' + saved[path])
        loads_copy = run_tests(a.test, root, a.timeout)[0] != "pass"
        for path, data in saved.items():
            with open(path, "wb") as f:
                f.write(data)
        if not files or not loads_copy:
            print("Self-check failed: your tests still pass with every source file broken.")
            print("They are not loading the code in this copy. Common causes: the project is")
            print("installed as a package (pip install / pip install -e), or the tests never")
            print("import it. Run your tests against the source folder, then try again.")
            return 3
        print("Self-check passed: your tests load the code in this copy.")
        all_sites: list[Site] = []
        for rel in files:
            with open(os.path.join(root, rel), encoding="utf-8", errors="surrogateescape") as f:
                all_sites += sites_in(rel, f.read())
        if only is not None:
            all_sites = [s for s in all_sites if s.line in only.get(os.path.normpath(s.path), ())]
            if not all_sites:
                print(f"Your changes since {a.changed} have no spots to plant a bug in.")
                return 0
        if not all_sites:
            print("No places found to plant a bug.")
            return 0
        picks = random.Random(a.seed).sample(all_sites, min(a.max, len(all_sites)))
        caught = 0
        print(f"Planting {len(picks)} bugs, one at a time (out of {len(all_sites)} possible spots):\n")
        for s in picks:
            path = os.path.join(root, s.path)
            with open(path, "rb") as f:
                original = f.read()
            text = original.decode("utf-8", errors="surrogateescape")
            with open(path, "wb") as f:
                f.write(apply(text, s).encode("utf-8", errors="surrogateescape"))
            result, output = run_tests(a.test, root, a.timeout)
            with open(path, "wb") as f:
                f.write(original)
            with open(path, "rb") as f:
                assert f.read() == original, f"restore not byte-identical: {s.path}"
            verdict = {"fail": "CAUGHT", "pass": "SURVIVED", "timeout": "TIMEOUT"}[result]
            caught += verdict == "CAUGHT"
            by = f"   (by {caught_by(output)})" if verdict == "CAUGHT" else ""
            print(f"  {verdict:<8}  {s.path}:{s.line}  {s.before}  ->  {s.after}{by}")
        print(f"\n{caught} of {len(picks)} planted bugs caught.  ({time.time() - t0:.0f}s)")
        if caught < len(picks):
            print("SURVIVED means your tests never checked that line. It is not always a bug;")
            print("it is where to look first.")
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
