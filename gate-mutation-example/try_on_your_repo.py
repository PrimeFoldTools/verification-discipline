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
import signal
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


ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
LINE = re.compile(r"[^\r\n]*(?:\r\n|\r|\n)|[^\r\n]+")


def split_lines(text: str) -> list[str]:
    """Split the way Python's parser counts lines: only \\n, \\r\\n and \\r. (str.splitlines
    also splits on form feed, U+2028 and others, which shifts every later line.)"""
    return LINE.findall(text)


def read_text(path: str) -> str:
    with open(path, "rb") as f:
        return f.read().decode("utf-8", errors="surrogateescape")


def under(rel: str, only: list[str]) -> bool:
    """True if `rel` is one of the `only` paths or inside one (whole path parts, not text prefix)."""
    parts = rel.replace(os.sep, "/").split("/")
    for p in only:
        want = [x for x in os.path.normpath(p).replace(os.sep, "/").split("/") if x not in ("", ".")]
        if parts[:len(want)] == want:
            return True
    return False


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
            if only and not under(rel, only):
                continue
            out.append(rel)
    return out


def sites_in(rel: str, text: str) -> list[Site]:
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, RecursionError):   # ValueError: null bytes, bad surrogates
        return []
    lines = split_lines(text)
    found: list[Site] = []

    def ch(line: int, byte_col: int) -> int:
        """ast columns count UTF-8 BYTES; convert to a character column on that line."""
        raw = lines[line - 1].encode("utf-8", errors="surrogateescape")
        return len(raw[:byte_col].decode("utf-8", errors="surrogateescape"))

    def seg(line: int, col: int, end: int) -> str:
        return lines[line - 1][col:end]

    def site_for(node: ast.AST) -> Site | None:
        # comparisons with one operator: a == b  ->  a != b
        if isinstance(node, ast.Compare) and len(node.ops) == 1 and type(node.ops[0]) in FLIP:
            left, right = node.left, node.comparators[0]
            if left.end_lineno != right.lineno:
                return None
            if any(isinstance(x, ast.Name) and x.id == "__name__" for x in (left, right)):
                return None                     # never flip an `if __name__ == "__main__"` guard
            lc, rc = ch(left.end_lineno, left.end_col_offset), ch(right.lineno, right.col_offset)
            gap = seg(right.lineno, lc, rc)
            op = OP_TEXT[type(node.ops[0])]
            idx = gap.find(op)
            if idx < 0 or gap.count(op) != 1:
                return None
            return Site(rel, right.lineno, lc + idx, lc + idx + len(op), op, FLIP[type(node.ops[0])])
        # True <-> False
        if isinstance(node, ast.Constant) and isinstance(node.value, bool) and node.lineno == node.end_lineno:
            before = "True" if node.value else "False"
            c0, c1 = ch(node.lineno, node.col_offset), ch(node.lineno, node.end_col_offset)
            if seg(node.lineno, c0, c1) == before:
                return Site(rel, node.lineno, c0, c1, before, "False" if node.value else "True")
            return None
        # a and b  <->  a or b (two operands on one line)
        if isinstance(node, ast.BoolOp) and len(node.values) == 2:
            a, b = node.values
            if a.end_lineno != b.lineno:
                return None
            ac, bc = ch(a.end_lineno, a.end_col_offset), ch(b.lineno, b.col_offset)
            gap = seg(b.lineno, ac, bc)
            word = "and" if isinstance(node.op, ast.And) else "or"
            idx = gap.find(word)
            if idx < 0 or gap.count(word) != 1:
                return None
            return Site(rel, b.lineno, ac + idx, ac + idx + len(word), word, "or" if word == "and" else "and")
        # return <expr>  ->  return None (single-line returns only)
        if isinstance(node, ast.Return) and node.value is not None and node.lineno == node.end_lineno:
            v = node.value
            if isinstance(v, ast.Constant) and v.value is None:
                return None
            c0, c1 = ch(v.lineno, v.col_offset), ch(v.lineno, v.end_col_offset)
            return Site(rel, v.lineno, c0, c1, seg(v.lineno, c0, c1), "None")
        return None

    for node in ast.walk(tree):
        try:
            site = site_for(node)
        except IndexError:                      # a node position outside the text: skip it
            continue
        if site is not None:
            found.append(site)
    return found


def kill_tree(proc: subprocess.Popen) -> None:
    """Kill the test command AND everything it started (wrappers, workers)."""
    if os.name == "nt":                          # not covered by a test or CI run yet
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
        return
    try:
        os.killpg(proc.pid, signal.SIGKILL)      # the command leads its own process group
    except (ProcessLookupError, PermissionError):
        proc.kill()


def run_tests(cmd: str, cwd: str, timeout: int) -> tuple[str, str]:
    """Return ("pass" | "fail" | "timeout", combined output without colour codes)."""
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", NO_COLOR="1", PY_COLORS="0")
    for var in ("FORCE_COLOR", "CLICOLOR_FORCE"):
        env.pop(var, None)
    group = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt"
             else {"start_new_session": True})
    proc = subprocess.Popen(shlex.split(cmd, posix=os.name != "nt"), cwd=cwd, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, errors="replace", **group)
    try:
        out, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        kill_tree(proc)
        try:
            proc.communicate(timeout=5)          # reap; a child that escaped the group may hold the pipe
        except subprocess.TimeoutExpired:
            pass
        return "timeout", ""
    return ("pass" if proc.returncode == 0 else "fail"), ANSI.sub("", out or "")


def broke_import(output: str) -> bool:
    """True if the run failed because the code could not be imported, not because a test
    noticed a wrong result (pytest collection error, unittest import failure)."""
    output = ANSI.sub("", output)
    return bool(re.search(r"^_+ ERROR collecting |during collection|Failed to import test module"
                          r"|unittest\.loader\._FailedTest|in loadTestsFromName", output, re.M))


def caught_by(output: str) -> str:
    """Name the test that failed, from unittest or pytest output (colour codes ignored)."""
    output = ANSI.sub("", output)
    names = [f"{m.group(3)}" if m.group(3).endswith("." + m.group(2)) else f"{m.group(3)}.{m.group(2)}"
             for m in re.finditer(r"^(FAIL|ERROR): (\S+) \(([^)]+)\)", output, re.M)]      # unittest
    if not names:
        names = [m.group(1) for m in re.finditer(                                          # pytest
            r"^(?:FAILED|ERROR) ((?:\S+::|\S+\.py).*?)(?: - .*)?$", output, re.M)]
    if not names:
        return "(test name not in output)"
    return names[0] + (f" (+{len(names) - 1} more)" if len(names) > 1 else "")


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
    # Pin the output format: user config (diff.mnemonicPrefix, diff.noprefix, diff.external,
    # textconv) must not change what we parse.
    diff = git("diff", "-U0", "--no-color", "--no-ext-diff", "--no-textconv",
               "--src-prefix=a/", "--dst-prefix=b/", "--relative", ref, "--", "*.py")
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
        try:
            n = len(split_lines(read_text(os.path.join(project, rel))))
        except OSError:                          # e.g. a broken symlink
            continue
        out[os.path.normpath(rel)] = set(range(1, n + 1))
    return out


def apply(text: str, s: Site) -> str:
    lines = split_lines(text)
    ln = lines[s.line - 1]
    if ln[s.col:s.end] != s.before:
        raise ValueError("site moved")
    lines[s.line - 1] = ln[:s.col] + s.after + ln[s.end:]
    return "".join(lines)


def marker_line(marker: str) -> str:
    """One line that appends the module's own __file__ to `marker` when the module is loaded."""
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_BINARY", 0)
    return ('(lambda _o: (lambda _f: (_o.write(_f, (str(globals().get("__file__", "")) + "\\n")'
            '.encode("utf-8", "surrogateescape")), _o.close(_f)))'
            f'(_o.open({marker!r}, {flags})))(__import__("os"))\n')


def with_marker(text: str, marker: str) -> str | None:
    """`text` with the marker line added after the docstring and `from __future__` imports
    (a line above those is a SyntaxError). None if the file does not parse."""
    try:
        body = ast.parse(text).body
    except (SyntaxError, ValueError, RecursionError):
        return None
    lines = split_lines(text)
    after, i = 0, 0
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        after, i = body[0].end_lineno, 1
    while i < len(body) and isinstance(body[i], ast.ImportFrom) and body[i].module == "__future__":
        after, i = body[i].end_lineno, i + 1
    if after == 0:                               # keep a shebang / encoding comment on top
        while after < len(lines) and (not lines[after].strip() or lines[after].lstrip().startswith("#")):
            after += 1
    if after and not lines[after - 1].endswith(("\n", "\r")):
        lines[after - 1] += "\n"
    lines.insert(after, marker_line(marker))
    return "".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Plant small bugs in a copy of your project and see if your tests catch them.")
    p.add_argument("project", help="path to your project")
    p.add_argument("--test", default="python3 -m pytest -q -x", help='test command (default: "python3 -m pytest -q -x")')
    p.add_argument("--max", type=int, default=10, help="how many bugs to plant (default 10)")
    p.add_argument("--timeout", type=int, default=120, help="seconds per test run (default 120)")
    p.add_argument("--seed", type=int, default=0, help="which bugs get picked (default 0)")
    p.add_argument("--paths", nargs="*", help="only plant bugs under these folders or files, e.g. src/")
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
        result, output = run_tests(a.test, root, a.timeout)
        if result == "timeout":
            print(f"Your tests did not finish within {a.timeout} seconds on the unchanged copy.")
            print("Raise --timeout or narrow --test, then run this again.")
            return 2
        if result != "pass":
            print("Your tests do not pass on the unchanged copy. Fix that first, then run this again.")
            print("Last lines of the test output:")
            for line in output.strip().splitlines()[-20:]:
                print(f"    {line}")
            return 2
        files = source_files(root, a.paths)
        # Self-check, per file: add one line to each source file that records the
        # file's own path when Python loads it, run the tests, and see which files
        # the tests really loaded FROM THIS COPY. A file loaded from somewhere else
        # (an installed package, another folder on the path) or never loaded would
        # make every bug planted in it look like it survived, so it is left out.
        marker = os.path.join(work, "loaded.txt")
        saved: dict[str, bytes] = {}
        for rel in files:
            path = os.path.join(root, rel)
            with open(path, "rb") as f:
                raw = f.read()
            marked = with_marker(raw.decode("utf-8", errors="surrogateescape"), marker)
            if marked is not None:
                saved[path] = raw
                with open(path, "wb") as f:
                    f.write(marked.encode("utf-8", errors="surrogateescape"))
        result, check_output = run_tests(a.test, root, a.timeout)
        for path, raw in saved.items():
            with open(path, "wb") as f:
                f.write(raw)
        if saved and result != "pass":
            print("Self-check failed: your tests stopped passing once one marker line was added to")
            print("each source file. Something checks the source text or its line numbers.")
            for line in check_output.strip().splitlines()[-20:]:
                print(f"    {line}")
            return 3
        loaded: set[str] = set()
        if os.path.exists(marker):
            with open(marker, encoding="utf-8", errors="surrogateescape") as f:
                for line in f.read().splitlines():
                    loaded.add(os.path.normcase(os.path.realpath(os.path.join(root, line))))
        checked = [rel for rel in files if os.path.join(root, rel) in saved]
        usable = [rel for rel in checked
                  if os.path.normcase(os.path.realpath(os.path.join(root, rel))) in loaded]
        skipped = [rel for rel in checked if rel not in usable]
        if not usable:
            print("Self-check failed: your tests did not load any source file from this copy.")
            print("Common causes: the project is installed as a package (pip install / pip install -e),")
            print("or the tests never import it. Run your tests against the source folder, then try again.")
            return 3
        print(f"Self-check passed: your tests loaded {len(usable)} of {len(checked)} source files from this copy.")
        if skipped:
            shown = ", ".join(skipped[:8]) + (f", and {len(skipped) - 8} more" if len(skipped) > 8 else "")
            print(f"Left out, because your tests did not load them from this copy: {shown}")
            print("(Either the tests never import them, or they load another copy, e.g. an installed package.)")
        all_sites: list[Site] = []
        for rel in usable:
            all_sites += sites_in(rel, read_text(os.path.join(root, rel)))
        if only is not None:
            all_sites = [s for s in all_sites if s.line in only.get(os.path.normpath(s.path), ())]
            if not all_sites:
                print(f"Your changes since {a.changed} have no spots to plant a bug in.")
                return 0
        if not all_sites:
            print("No places found to plant a bug.")
            return 0
        picks = random.Random(a.seed).sample(all_sites, min(a.max, len(all_sites)))
        caught = counted = broke = 0
        print(f"Planting {len(picks)} bugs, one at a time (out of {len(all_sites)} possible spots):\n")
        for s in picks:
            path = os.path.join(root, s.path)
            with open(path, "rb") as f:
                original = f.read()
            note = ""
            try:
                mutant = apply(original.decode("utf-8", errors="surrogateescape"), s)
                compile(mutant, s.path, "exec")
            except ValueError:
                verdict, note = "SKIPPED", "   (the line had moved)"
            except (SyntaxError, RecursionError):
                verdict, note = "BROKE", "   (did not compile)"
            else:
                with open(path, "wb") as f:
                    f.write(mutant.encode("utf-8", errors="surrogateescape"))
                try:
                    result, output = run_tests(a.test, root, a.timeout)
                finally:
                    with open(path, "wb") as f:
                        f.write(original)
                with open(path, "rb") as f:
                    if f.read() != original:
                        raise RuntimeError(f"restore not byte-identical: {s.path}")
                if result == "fail" and broke_import(output):
                    verdict, note = "BROKE", "   (broke the import)"
                else:
                    verdict = {"fail": "CAUGHT", "pass": "SURVIVED", "timeout": "TIMEOUT"}[result]
                    if verdict == "CAUGHT":
                        note = f"   (by {caught_by(output)})"
            if verdict == "BROKE":
                broke += 1
            if verdict in ("CAUGHT", "SURVIVED", "TIMEOUT"):
                counted += 1
            caught += verdict == "CAUGHT"
            print(f"  {verdict:<8}  {s.path}:{s.line}  {s.before}  ->  {s.after}{note}")
        print(f"\n{caught} of {counted} planted bugs caught.  ({time.time() - t0:.0f}s)")
        if broke:
            print(f"{broke} more broke the code instead of changing what it does (it did not compile, or it")
            print("could not be imported). A crash is not a test noticing a bug, so those are not counted.")
        if caught < counted:
            print("SURVIVED means your tests never checked that line. It is not always a bug;")
            print("it is where to look first.")
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
