"""Tests for try_on_your_repo.py, on a tiny project built in a temp folder."""
from __future__ import annotations

import os
import re
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


# 6. the test command must be able to FAIL (kept from the old self-check) ---------

def test_a_test_command_that_always_exits_0_is_refused(tmp_path, capsys):
    (tmp_path / "calc.py").write_text(MODULE)
    (tmp_path / "test_calc.py").write_text(
        "import unittest\nfrom calc import is_adult\n\n"
        "class T(unittest.TestCase):\n"
        "    def test_edges(self):\n"
        "        self.assertTrue(is_adult(18))\n"
        "        self.assertFalse(is_adult(17))\n")
    # Loads and runs the tests, then ignores the result: exit code is always 0.
    (tmp_path / "runner_test.py").write_text(
        "import unittest\n"
        "unittest.TextTestRunner().run(unittest.defaultTestLoader.discover('.', pattern='test_*.py'))\n")
    before = snapshot(tmp_path)
    assert tool.main([str(tmp_path), "--test", f"{sys.executable} runner_test.py"]) == 3
    out = capsys.readouterr().out
    assert "Self-check failed" in out and "still reports success" in out
    assert not planted_lines(out)
    assert snapshot(tmp_path) == before


# 7. helper-script folders are skipped by default --------------------------------

def helper_project(tmp_path):
    """calc.py is the library; tools/helper.py is a helper script the tests also load.
    pkg/tools/inner.py is a real sub-package that happens to be called tools."""
    (tmp_path / "tools").mkdir()
    (tmp_path / "pkg" / "tools").mkdir(parents=True)
    (tmp_path / "calc.py").write_text(MODULE)
    (tmp_path / "tools" / "helper.py").write_text("def big(n):\n    return n > 100\n")
    (tmp_path / "pkg" / "__init__.py").write_text("")
    (tmp_path / "pkg" / "tools" / "__init__.py").write_text("")
    (tmp_path / "pkg" / "tools" / "inner.py").write_text("def small(n):\n    return n < 5\n")
    (tmp_path / "test_x.py").write_text(
        "import os, sys\nsys.path[:0] = [os.path.join(os.path.dirname(__file__), 'tools')]\n"
        "from calc import is_adult\nfrom helper import big\nfrom pkg.tools.inner import small\n\n"
        "def test_all():\n"
        "    assert is_adult(18) is True and is_adult(17) is False\n"
        "    assert big(101) is True and big(100) is False\n"
        "    assert small(4) is True and small(5) is False\n")
    return tmp_path


def test_helper_folders_are_skipped_by_default_and_named(tmp_path, capsys):
    proj = helper_project(tmp_path)
    assert tool.main([str(proj), "--test", CMD, "--max", "50"]) == 0
    out = capsys.readouterr().out
    assert planted_lines(out), out
    assert not any("tools/helper.py" in l for l in planted_lines(out)), out
    assert any("pkg/tools/inner.py" in l for l in planted_lines(out)), out   # not a top-level helper folder
    assert "Skipped helper folders: tools/" in out and "--include-helpers" in out, out
    assert "pkg/tools" not in out.split("Skipped helper folders")[1].splitlines()[0], out


def test_include_helpers_flag_plants_in_them_again(tmp_path, capsys):
    proj = helper_project(tmp_path)
    assert tool.main([str(proj), "--test", CMD, "--max", "50", "--include-helpers"]) == 0
    out = capsys.readouterr().out
    assert any("tools/helper.py" in l for l in planted_lines(out)), out
    assert "Skipped helper folders" not in out


def test_an_explicit_path_inside_a_helper_folder_still_works(tmp_path, capsys):
    proj = helper_project(tmp_path)
    assert tool.main([str(proj), "--test", CMD, "--max", "50", "--paths", "tools/helper.py"]) == 0
    out = capsys.readouterr().out
    assert planted_lines(out) and all("tools/helper.py" in l for l in planted_lines(out)), out


def test_nothing_is_said_about_helper_folders_when_there_are_none(tmp_path, capsys):
    proj = make_project(tmp_path, STRONG)
    assert tool.main([str(proj), "--test", CMD]) == 0
    assert "helper" not in capsys.readouterr().out


def test_a_broad_path_like_dot_does_not_switch_helper_folders_back_on(tmp_path, capsys):
    proj = helper_project(tmp_path)
    assert tool.main([str(proj), "--test", CMD, "--max", "50", "--paths", "."]) == 0
    out = capsys.readouterr().out
    assert planted_lines(out) and not any("tools/helper.py" in l for l in planted_lines(out)), out
    assert "Skipped helper folders: tools/" in out


@pytest.mark.parametrize("folder", ["tools", "scripts", "docs", "examples", "benchmarks"])
def test_each_of_the_five_helper_folders_is_skipped_by_default_and_named(tmp_path, capsys, folder):
    (tmp_path / folder).mkdir()
    (tmp_path / "calc.py").write_text(MODULE)
    (tmp_path / folder / "helper.py").write_text("def big(n):\n    return n > 100\n")
    (tmp_path / "test_x.py").write_text(
        f"import os, sys\nsys.path[:0] = [os.path.join(os.path.dirname(__file__), {folder!r})]\n"
        "from calc import is_adult\nfrom helper import big\n\n"
        "def test_all():\n"
        "    assert is_adult(18) is True and is_adult(17) is False\n"
        "    assert big(101) is True and big(100) is False\n")
    assert tool.main([str(tmp_path), "--test", CMD, "--max", "50"]) == 0
    out = capsys.readouterr().out
    assert planted_lines(out), out
    assert not any(f"{folder}/helper.py" in l for l in planted_lines(out)), out
    assert f"Skipped helper folders: {folder}/" in out, out


# 8. an import that fails INSIDE a test function is BROKE, not CAUGHT (end-to-end runs) -----









LAZY_TEST = ("def test_edges():\n"
             "    from calc import is_adult\n"
             "    assert is_adult(18) is True\n"
             "    assert is_adult(17) is False\n")
LAZY_UNITTEST = ("import unittest\n\n"
                 "class T(unittest.TestCase):\n"
                 "    def test_edges(self):\n"
                 "        from calc import is_adult\n"
                 "        self.assertTrue(is_adult(18))\n"
                 "        self.assertFalse(is_adult(17))\n")


def test_a_mutant_that_breaks_a_lazy_import_shows_as_broke_with_pytest(tmp_path, capsys):
    (tmp_path / "calc.py").write_text(IMPORT_BREAKER)
    (tmp_path / "test_calc.py").write_text(LAZY_TEST)
    assert tool.main([str(tmp_path), "--test", CMD]) == 0
    out = capsys.readouterr().out
    lines = planted_lines(out)
    assert any(l.split()[0] == "BROKE" and "calc.py:1" in l for l in lines), out
    assert not any(l.split()[0] == "CAUGHT" and "calc.py:1" in l for l in lines), out
    assert "2 of 2 planted bugs caught" in out


def test_a_mutant_that_breaks_a_lazy_import_shows_as_broke_with_unittest(tmp_path, capsys):
    (tmp_path / "calc.py").write_text(IMPORT_BREAKER)
    (tmp_path / "test_calc.py").write_text(LAZY_UNITTEST)
    assert tool.main([str(tmp_path), "--test", f"{sys.executable} -m unittest -q"]) == 0
    out = capsys.readouterr().out
    lines = planted_lines(out)
    assert any(l.split()[0] == "BROKE" and "calc.py:1" in l for l in lines), out
    assert not any(l.split()[0] == "CAUGHT" and "calc.py:1" in l for l in lines), out


def test_a_real_catch_after_a_lazy_import_still_counts(tmp_path, capsys):
    (tmp_path / "calc.py").write_text(MODULE)
    (tmp_path / "test_calc.py").write_text(LAZY_TEST)
    assert tool.main([str(tmp_path), "--test", CMD]) == 0
    out = capsys.readouterr().out
    assert "2 of 2 planted bugs caught" in out and "BROKE" not in out, out


# 9. the report explains TIMEOUT ------------------------------------------------

def run_with_timeouts_after_setup(monkeypatch, setup_runs=3):
    """Real test runs for the baseline and the two self-check runs; every run after that times out."""
    real, calls = tool.run_tests, []

    def fake(cmd, cwd, timeout):
        calls.append(cmd)
        return real(cmd, cwd, timeout) if len(calls) <= setup_runs else ("timeout", "")
    monkeypatch.setattr(tool, "run_tests", fake)


def test_the_report_explains_timeout_when_one_happened(tmp_path, capsys, monkeypatch):
    proj = make_project(tmp_path, STRONG)
    run_with_timeouts_after_setup(monkeypatch)
    assert tool.main([str(proj), "--test", CMD, "--timeout", "7"]) == 0
    out = capsys.readouterr().out
    assert [l.split()[0] for l in planted_lines(out) if "->" in l] == ["TIMEOUT", "TIMEOUT"], out
    assert "A TIMEOUT line means your tests did not finish within 7 seconds" in out, out
    assert "counts toward the total but not as caught" in out, out
    assert "0 of 2 planted bugs caught" in out


def test_the_report_is_silent_about_timeout_when_none_happened(tmp_path, capsys):
    proj = make_project(tmp_path, STRONG)
    assert tool.main([str(proj), "--test", CMD]) == 0
    assert "TIMEOUT" not in capsys.readouterr().out









# 11. a project whose only source files are in helper folders ------------------------

def test_a_project_with_only_helper_folder_code_says_so_instead_of_blaming_installation(tmp_path, capsys):
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "helper.py").write_text("def big(n):\n    return n > 100\n")
    (tmp_path / "test_x.py").write_text(
        "import os, sys\nsys.path[:0] = [os.path.join(os.path.dirname(__file__), 'tools')]\n"
        "from helper import big\n\ndef test_big():\n    assert big(101) is True and big(100) is False\n")
    assert tool.main([str(tmp_path), "--test", CMD]) == 4
    out = capsys.readouterr().out
    assert "Skipped helper folders: tools/" in out and "--include-helpers" in out, out
    assert "Nothing was checked" in out and "installed as a package" not in out and "Self-check failed" not in out, out
    assert not planted_lines(out), out
    assert tool.main([str(tmp_path), "--test", CMD, "--include-helpers"]) == 0   # and the flag works
    assert any("tools/helper.py" in l for l in planted_lines(capsys.readouterr().out))


# 12. the test counts quoted in the READMEs are the real ones -------------------------

def collected(*files):
    out = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", *files],
                         cwd=Path(__file__).parent, capture_output=True, text=True,
                         env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1")).stdout
    return int(re.search(r"(\d+) tests? collected", out).group(1))


def test_the_test_counts_in_the_readmes_are_the_real_counts():
    here = Path(__file__).parent
    total, gate, tool_n = collected(), collected("test_cli.py"), collected("test_try_on_your_repo.py")
    assert total == gate + tool_n
    # The repo's top README is absent when the tool runs this suite in a copy of this folder.
    readmes = [p for p in (here / "README.md", here.parent / "README.md") if p.exists()]
    assert readmes
    for readme in readmes:
        line = next(l for l in readme.read_text(encoding="utf-8").splitlines() if l.startswith("make test"))
        assert f"# {total} tests" in line and f"{gate} on the gate" in line \
            and f"{tool_n} on try_on_your_repo.py" in line, (readme.name, line, total, gate, tool_n)
    if (here.parent / "README.md").exists():
        assert f"all {total} tests pass" in (here.parent / "README.md").read_text(encoding="utf-8")


# 13. BROKE = the planted file started loading and never finished (audit, 2026-11-13) ----
# Nothing here reads tracebacks, so the verdict does not depend on pytest's --tb, on how the
# test imports the module, or on unittest vs pytest. These are real runs, not captured text.

SAME_LINE = "def calc(n):\n    if n > 0:\n        return 10 / n\n    return 0\n"
ALIAS_SRC = "if 1 > 0:\n    X = 10\nY = X\n"


def lines_for(out, src_line):
    return [l.split()[0] for l in planted_lines(out) if f"calc.py:{src_line} " in l]


def test_a_crash_inside_a_function_on_the_import_line_is_still_caught(tmp_path, capsys):
    (tmp_path / "calc.py").write_text(SAME_LINE)
    (tmp_path / "test_calc.py").write_text(
        "import importlib\n\ndef test_calc():\n    assert importlib.import_module('calc').calc(0) == 0\n")
    assert tool.main([str(tmp_path), "--test", CMD, "--max", "50"]) == 0
    out = capsys.readouterr().out
    assert lines_for(out, 2) == ["CAUGHT"] and "BROKE" not in out, out      # `>` -> `<=` divides by zero in calc()
    assert "2 of 3 planted bugs caught" in out, out


def test_an_import_crash_through_an_alias_is_broke(tmp_path, capsys):
    (tmp_path / "calc.py").write_text(ALIAS_SRC)
    (tmp_path / "test_calc.py").write_text(
        "from importlib import import_module as load\n\ndef test_calc():\n    assert load('calc').Y == 10\n")
    assert tool.main([str(tmp_path), "--test", CMD, "--max", "50"]) == 0
    out = capsys.readouterr().out
    assert lines_for(out, 1) == ["BROKE"], out
    assert "0 of 0 planted bugs caught" in out, out


def test_an_import_crash_is_broke_even_with_no_traceback_at_all(tmp_path, capsys):
    (tmp_path / "calc.py").write_text(ALIAS_SRC)
    (tmp_path / "test_calc.py").write_text("def test_calc():\n    import calc\n    assert calc.Y == 10\n")
    assert tool.main([str(tmp_path), "--test", CMD + " --tb=no -x", "--max", "50"]) == 0
    out = capsys.readouterr().out
    assert lines_for(out, 1) == ["BROKE"], out


def test_an_import_crash_through_an_alias_is_broke_with_unittest(tmp_path, capsys):
    (tmp_path / "calc.py").write_text(ALIAS_SRC)
    (tmp_path / "test_calc.py").write_text(
        "import unittest\nfrom importlib import import_module as load\n\n"
        "class T(unittest.TestCase):\n    def test_calc(self):\n        self.assertEqual(load('calc').Y, 10)\n")
    assert tool.main([str(tmp_path), "--test", f"{sys.executable} -m unittest -q", "--max", "50"]) == 0
    assert lines_for(capsys.readouterr().out, 1) == ["BROKE"]


def test_a_project_with_only_helper_folder_code_exits_nonzero_and_says_nothing_was_checked(tmp_path, capsys):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "calc.py").write_text("def calc(n):\n    return n > 0\n")
    (tmp_path / "test_calc.py").write_text(
        "from scripts.calc import calc\n\ndef test_calc():\n    assert calc(1) is True\n    assert calc(0) is False\n")
    assert tool.main([str(tmp_path), "--test", CMD]) == 4
    out = capsys.readouterr().out
    assert "Nothing was checked" in out and "--include-helpers" in out and not planted_lines(out), out


CLI_SRC = ("import sys\n\ndef main():\n    n = int(sys.argv[1])\n    if n >= 18:\n"
           "        print('adult')\n        return 0\n    print('minor')\n    return 1\n\n"
           "if __name__ == '__main__':\n    sys.exit(main())\n")
CLI_TEST = ("import os, subprocess, sys\nHERE = os.path.dirname(os.path.abspath(__file__))\n\n"
            "def run(n):\n    return subprocess.run([sys.executable, os.path.join(HERE, 'cli.py'), str(n)],\n"
            "                          capture_output=True, text=True)\n\n"
            "def test_adult():\n    r = run(18)\n    assert r.returncode == 0 and 'adult' in r.stdout\n\n"
            "def test_minor():\n    r = run(17)\n    assert r.returncode == 1\n")


def test_a_script_run_as_main_is_still_tested_and_a_real_catch_is_not_called_broke(tmp_path, capsys):
    (tmp_path / "cli.py").write_text(CLI_SRC)
    (tmp_path / "test_cli_main.py").write_text(CLI_TEST)
    assert tool.main([str(tmp_path), "--test", CMD, "--max", "50"]) == 0
    out = capsys.readouterr().out
    assert "loaded 1 of 1 source files" in out and "Left out" not in out, out
    assert lines_for(out.replace("cli.py", "calc.py"), 5) == ["CAUGHT"], out     # `>=` -> `<`
    assert "BROKE" not in out, out


def test_a_file_that_does_not_reach_its_last_line_when_loaded_is_left_out_by_name(tmp_path, capsys):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text(
        "try:\n    from . import _speedups\nexcept ImportError:\n    _speedups = None\n\n"
        "def add(a, b):\n    return a + b if a > 0 else b\n")
    (tmp_path / "pkg" / "_speedups.py").write_text("if 1 > 0:\n    raise ImportError('no compiled extension')\n")
    (tmp_path / "test_pkg.py").write_text(
        "import pkg\n\ndef test_add():\n    assert pkg.add(1, 2) == 3\n    assert pkg.add(-1, 2) == 2\n")
    assert tool.main([str(tmp_path), "--test", CMD, "--max", "50"]) == 0
    out = capsys.readouterr().out
    assert "do not reach their last line" in out and "pkg/_speedups.py" in out.split("Left out")[1], out
    assert not any("_speedups.py:" in l for l in planted_lines(out)), out
    assert any("pkg/__init__.py:" in l for l in planted_lines(out)), out


def test_survived_is_described_as_the_test_command_passing(tmp_path, capsys):
    proj = make_project(tmp_path, WEAK)
    assert tool.main([str(proj), "--test", CMD]) == 0
    out = capsys.readouterr().out
    assert "never checked that line" not in out
    assert "SURVIVED means the test command passed with the bug planted" in out, out
