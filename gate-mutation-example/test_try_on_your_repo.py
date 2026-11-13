"""Tests for try_on_your_repo.py, on a tiny project built in a temp folder."""
from __future__ import annotations

import os
import sys

import try_on_your_repo as tool

MODULE = "def is_adult(age):\n    return age >= 18\n"
STRONG = ("from calc import is_adult\n\n"
          "def test_edges():\n"
          "    assert is_adult(18) is True\n"
          "    assert is_adult(17) is False\n")
WEAK = ("from calc import is_adult\n\n"
        "def test_runs():\n"
        "    is_adult(30)\n")
RED = ("from calc import is_adult\n\n"
       "def test_wrong():\n"
       "    assert is_adult(1) is True\n")

CMD = f"{sys.executable} -m pytest -q -p no:cacheprovider"


def make_project(tmp_path, test_body):
    (tmp_path / "calc.py").write_text(MODULE)
    (tmp_path / "test_calc.py").write_text(test_body)
    return tmp_path


def snapshot(root):
    out = {}
    for d, _, files in os.walk(root):
        for f in files:
            p = os.path.join(d, f)
            with open(p, "rb") as fh:
                out[os.path.relpath(p, root)] = fh.read()
    return out


def test_strong_test_catches_every_planted_bug(tmp_path, capsys):
    proj = make_project(tmp_path, STRONG)
    assert tool.main([str(proj), "--test", CMD, "--max", "10"]) == 0
    out = capsys.readouterr().out
    assert "SURVIVED  calc.py" not in out
    assert "2 of 2 planted bugs caught" in out          # ">=" flip and "return None"


def test_weak_test_lets_a_bug_survive(tmp_path, capsys):
    proj = make_project(tmp_path, WEAK)
    assert tool.main([str(proj), "--test", CMD]) == 0
    out = capsys.readouterr().out
    assert "SURVIVED  calc.py:2" in out
    assert "0 of 2 planted bugs caught" in out


def test_original_files_are_untouched(tmp_path):
    proj = make_project(tmp_path, WEAK)
    before = snapshot(proj)
    tool.main([str(proj), "--test", CMD])
    assert snapshot(proj) == before


def test_red_baseline_stops_with_exit_2(tmp_path, capsys):
    proj = make_project(tmp_path, RED)
    assert tool.main([str(proj), "--test", CMD]) == 2
    assert "do not pass on the unchanged copy" in capsys.readouterr().out


def test_finds_each_kind_of_site():
    src = ("def f(a, b, flag=True):\n"
           "    if a == b and flag:\n"
           "        return a < b\n"
           "    return False\n")
    kinds = {(s.before, s.after) for s in tool.sites_in("m.py", src)}
    assert ("==", "!=") in kinds
    assert ("and", "or") in kinds
    assert ("True", "False") in kinds
    assert ("<", ">=") in kinds
    assert ("a < b", "None") in kinds


def test_test_files_are_never_mutated():
    assert tool.is_test_file("tests/test_x.py")
    assert tool.is_test_file("pkg/conftest.py")
    assert not tool.is_test_file("pkg/core.py")


NO_IMPORT = ("def test_nothing():\n"
             "    assert 1 + 1 == 2\n")


def test_self_check_stops_when_tests_do_not_load_the_copy(tmp_path, capsys):
    proj = make_project(tmp_path, NO_IMPORT)
    before = snapshot(proj)
    assert tool.main([str(proj), "--test", CMD]) == 3
    assert "Self-check failed" in capsys.readouterr().out
    assert snapshot(proj) == before


def test_self_check_passes_when_tests_import_the_code(tmp_path, capsys):
    proj = make_project(tmp_path, WEAK)
    tool.main([str(proj), "--test", CMD])
    assert "Self-check passed" in capsys.readouterr().out


# --- --changed and "caught by" -------------------------------------------

import shutil
import subprocess

import pytest

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")

TWO = ("def is_adult(age):\n"
       "    return age >= 18\n"
       "\n"
       "def is_senior(age):\n"
       "    return age >= 65\n")
TWO_TESTS = ("from calc import is_adult, is_senior\n\n"
             "def test_adult():\n"
             "    assert is_adult(18) is True\n"
             "    assert is_adult(17) is False\n\n"
             "def test_senior():\n"
             "    assert is_senior(65) is True\n"
             "    assert is_senior(64) is False\n")


def git_project(tmp_path):
    (tmp_path / "calc.py").write_text(TWO)
    (tmp_path / "test_calc.py").write_text(TWO_TESTS)
    for cmd in (["init", "-q"], ["add", "."],
                ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "x"]):
        subprocess.run(["git", "-C", str(tmp_path), *cmd], check=True)
    return tmp_path


@needs_git
def test_changed_only_plants_in_changed_lines(tmp_path, capsys):
    proj = git_project(tmp_path)
    (proj / "calc.py").write_text(TWO.replace("age >= 65", "age >= 60"))
    (proj / "test_calc.py").write_text(TWO_TESTS.replace("65", "60").replace("64", "59"))
    assert tool.main([str(proj), "--test", CMD, "--changed"]) == 0
    out = capsys.readouterr().out
    planted = [l for l in out.splitlines() if l.strip().startswith(("CAUGHT", "SURVIVED"))]
    assert planted and all("calc.py:5" in l for l in planted)


@needs_git
def test_changed_includes_new_untracked_file(tmp_path):
    proj = git_project(tmp_path)
    (proj / "extra.py").write_text("def flag():\n    return True\n")
    only = tool.changed_lines(str(proj), "HEAD")
    assert only == {"extra.py": {1, 2}}


@needs_git
def test_changed_with_nothing_changed(tmp_path, capsys):
    proj = git_project(tmp_path)
    assert tool.main([str(proj), "--test", CMD, "--changed"]) == 0
    assert "Nothing changed" in capsys.readouterr().out


def test_changed_outside_git_explains(tmp_path, capsys):
    proj = make_project(tmp_path, STRONG)
    assert tool.main([str(proj), "--test", CMD, "--changed"]) == 64
    assert "needs a git repository" in capsys.readouterr().out


def test_report_names_the_test_that_caught_it(tmp_path, capsys):
    proj = make_project(tmp_path, STRONG)
    tool.main([str(proj), "--test", CMD])
    assert "(by test_calc.py::test_edges)" in capsys.readouterr().out


def test_caught_by_parses_unittest_and_falls_back():
    assert tool.caught_by("FAIL: test_x (pkg.test_mod.T)\n") == "pkg.test_mod.T.test_x"
    assert tool.caught_by("something else") == "(test name not in output)"


@needs_git
def test_changed_handles_a_file_name_with_a_space(tmp_path):
    (tmp_path / "my file.py").write_text("def f(a):\n    return a == 1\n")
    for cmd in (["init", "-q"], ["add", "."],
                ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "x"]):
        subprocess.run(["git", "-C", str(tmp_path), *cmd], check=True)
    (tmp_path / "my file.py").write_text("def f(a):\n    return a == 2\n")
    assert tool.changed_lines(str(tmp_path), "HEAD") == {"my file.py": {2}}


# --- red-team fixes (2026-11-13) ---------------------------------------------
# Fixtures in fixtures/ are REAL captured output (pytest 8.4.2, unittest on
# Python 3.9.6 and 3.12.13), never hand-typed. Re-capture them when those change.

import ast
import signal
import time
from pathlib import Path

FIX = Path(__file__).parent / "fixtures"
needs_posix = pytest.mark.skipif(os.name == "nt", reason="POSIX process groups / shell")


def fixture(name):
    return (FIX / name).read_text(encoding="utf-8")


def planted_lines(out):
    return [l for l in out.splitlines()
            if l.strip().split(" ")[0] in ("CAUGHT", "SURVIVED", "TIMEOUT", "BROKE", "SKIPPED")]


# 1. ast column offsets are UTF-8 BYTES, not characters ----------------------

NON_ASCII = ('def f(a, b, flag=True):\n'
             '    s = "✓é"; x = a == b and flag\n'
             '    t = ["✓", True]; return a < b\n'
             '    return "✓" + s\n')


def test_sites_after_non_ascii_text_are_exact_and_every_mutant_is_valid():
    sites = tool.sites_in("m.py", NON_ASCII)
    kinds = {(s.before, s.after) for s in sites}
    for want in [("==", "!="), ("and", "or"), ("True", "False"), ("<", ">="),
                 ('"✓" + s', "None"), ("a < b", "None")]:
        assert want in kinds, f"site {want} missing: {sorted(kinds)}"
    original = ast.dump(ast.parse(NON_ASCII))
    for s in sites:
        mutant = tool.apply(NON_ASCII, s)
        compile(mutant, "m.py", "exec")
        assert ast.dump(ast.parse(mutant)) != original
        changed = [i for i, (x, y) in enumerate(zip(NON_ASCII.splitlines(), mutant.splitlines())) if x != y]
        assert changed == [s.line - 1]
        assert mutant.count("\n") == NON_ASCII.count("\n")        # no line break eaten


def test_line_numbers_survive_characters_that_splitlines_splits_on():
    # str.splitlines() also splits on form feed and U+2028; ast does not.
    src = 'x = "a b"\n# page break \x0c here\ndef f(a, b):\n    return a == b\n'
    sites = tool.sites_in("m.py", src)
    assert [(s.before, s.line) for s in sites if s.before == "=="] == [("==", 4)]
    for s in sites:
        compile(tool.apply(src, s), "m.py", "exec")


def test_unparseable_text_gives_no_sites_instead_of_crashing():
    assert tool.sites_in("m.py", "x = 1\x00\n") == []
    assert tool.sites_in("m.py", "x = '\udcff'\n") == []


# 2. mutants that break the code instead of changing its behaviour ------------

IMPORT_BREAKER = ("ENABLED = True\n"
                  "assert ENABLED, 'off'\n"
                  "\n"
                  "def is_adult(age):\n"
                  "    return age >= 18\n")


def test_a_mutant_that_breaks_the_import_is_not_counted_as_caught(tmp_path, capsys):
    (tmp_path / "calc.py").write_text(IMPORT_BREAKER)
    (tmp_path / "test_calc.py").write_text(STRONG)
    assert tool.main([str(tmp_path), "--test", CMD]) == 0
    out = capsys.readouterr().out
    lines = planted_lines(out)
    assert any(l.split()[0] == "BROKE" and "calc.py:1" in l for l in lines), out
    assert not any(l.split()[0] == "CAUGHT" and "calc.py:1" in l for l in lines)
    assert "2 of 2 planted bugs caught" in out


def test_a_mutant_that_does_not_compile_is_reported_separately(tmp_path, capsys, monkeypatch):
    proj = make_project(tmp_path, STRONG)
    bad = tool.Site("calc.py", 2, 15, 17, ">=", "(((")
    monkeypatch.setattr(tool, "sites_in", lambda rel, text: [bad])
    tool.main([str(proj), "--test", CMD])
    out = capsys.readouterr().out
    assert [l.split()[0] for l in planted_lines(out)] == ["BROKE"]
    assert "did not compile" in out


def test_a_name_main_guard_is_never_flipped():
    src = 'def main():\n    pass\n\nif __name__ == "__main__":\n    main()\n'
    assert not [s for s in tool.sites_in("m.py", src) if s.before == "=="]


def test_broke_import_is_recognised_in_real_pytest_and_unittest_output():
    for name in ["pytest_import_error.txt", "unittest_import_error_py39.txt",
                 "unittest_import_error_py312.txt", "unittest_named_import_error_py39.txt"]:
        assert tool.broke_import(fixture(name)), name
    for name in ["pytest_fail.txt", "pytest_fail_color.txt", "pytest_two_fail.txt",
                 "unittest_fail_py39.txt", "unittest_fail_py312.txt"]:
        assert not tool.broke_import(fixture(name)), name


# 3. self-check must be per file ----------------------------------------------

def test_a_file_the_tests_load_from_somewhere_else_is_flagged_not_planted(tmp_path, capsys):
    outside = tmp_path / "outside"
    proj = tmp_path / "proj"
    outside.mkdir(); proj.mkdir()
    (outside / "b.py").write_text("def g(x):\n    return x >= 1\n")
    (proj / "a.py").write_text("def f(x):\n    return x >= 1\n")
    (proj / "b.py").write_text("def g(x):\n    return x >= 1\n")        # the copy the tests never load
    (proj / "test_ab.py").write_text(
        f"import sys\nsys.path.insert(0, {str(outside)!r})\n"
        "import a, b\n\n"
        "def test_f():\n    assert a.f(1) is True and a.f(0) is False\n"
        "def test_g():\n    assert b.g(1) is True and b.g(0) is False\n")
    assert tool.main([str(proj), "--test", CMD]) == 0
    out = capsys.readouterr().out
    import re
    assert not any(re.search(r"(?<![\w.])b\.py:\d", l) for l in planted_lines(out)), out
    assert "Left out" in out and "not load them from this copy: b.py" in out
    assert any(re.search(r"(?<![\w.])a\.py:2", l) for l in planted_lines(out))


# 4. caught_by -----------------------------------------------------------------

def test_caught_by_on_real_captured_output():
    assert tool.caught_by(fixture("pytest_fail.txt")) == "test_calc.py::test_edges"
    assert tool.caught_by(fixture("pytest_fail_color.txt")) == "test_calc.py::test_edges"
    assert tool.caught_by(fixture("pytest_two_fail.txt")) == "test_calc.py::test_edges (+2 more)"
    assert tool.caught_by(fixture("unittest_fail_py39.txt")) == "test_ut.T.test_boom (+1 more)"
    assert tool.caught_by(fixture("unittest_fail_py312.txt")) == "test_ut.T.test_boom (+1 more)"


def test_unittest_summary_line_is_not_read_as_a_pytest_failure():
    assert tool.caught_by("FAILED (failures=1)\n") == "(test name not in output)"


def test_colour_in_the_environment_does_not_hide_the_test_name(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("PY_COLORS", "1")
    proj = make_project(tmp_path, STRONG)
    tool.main([str(proj), "--test", CMD])
    assert "(by test_calc.py::test_edges)" in capsys.readouterr().out


def test_colour_forced_on_the_command_line_does_not_hide_the_test_name(tmp_path, capsys):
    proj = make_project(tmp_path, STRONG)
    tool.main([str(proj), "--test", CMD + " --color=yes"])
    assert "(by test_calc.py::test_edges)" in capsys.readouterr().out


# 5. timeout must kill the whole process group ---------------------------------

@needs_posix
def test_timeout_kills_child_processes_too(tmp_path):
    pidfile = tmp_path / "pid"
    script = tmp_path / "spawn.py"
    script.write_text("import subprocess, sys, time\n"
                      "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
                      f"open({str(pidfile)!r}, 'w').write(str(p.pid))\n"
                      "time.sleep(60)\n")
    result, _ = tool.run_tests(f"{sys.executable} {script}", str(tmp_path), 2)
    assert result == "timeout"
    pid = int(pidfile.read_text())
    try:
        deadline = time.time() + 5
        while True:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            assert time.time() < deadline, "grandchild still running after the timeout"
            time.sleep(0.05)
    finally:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


# extras ------------------------------------------------------------------------

def test_paths_match_whole_folder_names(tmp_path, capsys):
    (tmp_path / "src").mkdir(); (tmp_path / "src2").mkdir()
    (tmp_path / "src" / "mod_a.py").write_text("def f(x):\n    return x >= 1\n")
    (tmp_path / "src2" / "mod_b.py").write_text("def g(x):\n    return x >= 1\n")
    (tmp_path / "test_x.py").write_text(
        "import os, sys\nH = os.path.dirname(__file__)\n"
        "sys.path[:0] = [os.path.join(H, 'src'), os.path.join(H, 'src2')]\n"
        "from mod_a import f\nfrom mod_b import g\n\n"
        "def test_f():\n    assert f(1) is True and f(0) is False\n"
        "def test_g():\n    assert g(1) is True and g(0) is False\n")
    assert tool.main([str(tmp_path), "--test", CMD, "--paths", "src"]) == 0
    out = capsys.readouterr().out
    assert planted_lines(out) and all("src/mod_a.py" in l for l in planted_lines(out)), out


@needs_git
def test_changed_survives_git_mnemonic_prefix_config(tmp_path):
    proj = git_project(tmp_path)
    subprocess.run(["git", "-C", str(proj), "config", "diff.mnemonicPrefix", "true"], check=True)
    (proj / "calc.py").write_text(TWO.replace("age >= 65", "age >= 60"))
    assert tool.changed_lines(str(proj), "HEAD") == {"calc.py": {5}}


@needs_git
@needs_posix
def test_changed_ignores_a_configured_external_diff_tool(tmp_path):
    proj = git_project(tmp_path)
    ext = tmp_path.parent / (tmp_path.name + "_ext.sh")
    ext.write_text("#!/bin/sh\necho not-a-diff\nexit 0\n")
    ext.chmod(0o755)
    subprocess.run(["git", "-C", str(proj), "config", "diff.external", str(ext)], check=True)
    (proj / "calc.py").write_text(TWO.replace("age >= 65", "age >= 60"))
    assert tool.changed_lines(str(proj), "HEAD") == {"calc.py": {5}}


def test_failing_baseline_shows_the_last_20_lines_of_output(tmp_path, capsys):
    proj = make_project(tmp_path, STRONG)
    cmd = f"{sys.executable} -c \"import sys; [print('L%02d' % i) for i in range(40)]; sys.exit(1)\""
    assert tool.main([str(proj), "--test", cmd]) == 2
    out = capsys.readouterr().out
    assert "L39" in out and "L20" in out and "L19" not in out


@needs_posix
def test_baseline_timeout_has_its_own_message(tmp_path, capsys):
    proj = make_project(tmp_path, STRONG)
    cmd = f"{sys.executable} -c 'import time; time.sleep(30)'"
    assert tool.main([str(proj), "--test", cmd, "--timeout", "1"]) == 2
    out = capsys.readouterr().out
    assert "did not finish" in out and "do not pass" not in out


def test_self_check_marker_goes_below_docstring_and_future_imports(tmp_path, capsys):
    (tmp_path / "calc.py").write_text(
        '#!/usr/bin/env python3\n"""Doc."""\nfrom __future__ import annotations\n\n'
        "def is_adult(age: int) -> bool:\n    return age >= 18")        # no trailing newline
    (tmp_path / "test_calc.py").write_text(STRONG)
    assert tool.main([str(tmp_path), "--test", CMD]) == 0
    out = capsys.readouterr().out
    assert "loaded 1 of 1 source files" in out and "2 of 2 planted bugs caught" in out


def test_caught_by_names_the_test_behind_pytest_subtest_failures():
    # Real output of python-slugify's suite (its pyproject sets --color=yes, which beats
    # NO_COLOR) under pytest 9.2.0, whose built-in subtests report `SUBFAILED(params) id`.
    assert tool.caught_by(fixture("pytest_subtests_fail_color.txt")) == (
        "tests/test_modern_word_boundary.py::ModernWordBoundaryTests::"
        "test_replacement_delimiters_are_budgeted_and_preserved")
