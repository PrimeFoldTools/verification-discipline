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
