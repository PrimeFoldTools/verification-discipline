# Trials of try_on_your_repo.py

Real runs, recorded as printed. Run 2026-11-13 on branch `agent-features`, after the red-team fixes
(commits 027b2f1 and 684375c, plus the "test command must be able to fail" self-check step added after them).
Tool run with Python 3.12.13; outside projects were shallow clones (`--depth 1`), each tested in its own venv (pytest 9.2.0).
Each outside project was run again after that last step. The caught counts and the exit codes were the same each time; the one difference (3 unnamed "by" lines) is described below.

| Project | Command (after the tool's path and project) | Result | Time |
|---|---|---|---|
| this repo's `gate-mutation-example` (cli.py, gate.py, json_safe.py) | `make self-check` | 7 of 8 planted bugs caught, each line names its test. Survivor: `gate.py:81` (`"receipt": True` on the attached path, no test asserts it). Self-check: 3 of 3 files loaded from the copy, and the command fails when the code is broken | 52 s (the suite now includes the tool's own tests, and the self-check runs the suite 3 times before planting, so this is longer than the 5-6 s recorded before these fixes) |
| python-slugify @ 35aca63 | `--test "<venv>/bin/python -m pytest -q -x tests" --max 10` | 9 of 10 caught. Survivor: `tools/check_algorithms.py:40` `False -> True`. Self-check: 8 of 9 files loaded from the copy; `tools/check_dist.py` left out and named | 4 s |
| humanize @ a950045, installed with `pip install -e .` | `--test "<venv>/bin/python -m pytest -q -x --benchmark-disable tests" --max 10` | **Exit 3, nothing planted.** "Self-check failed: your tests did not load any source file from this copy." The editable install makes `import humanize` resolve to the original `src/`, not the copy | not timed (stops before planting) |
| humanize, same venv, copy's `src` first on the path | `--test "env PYTHONPATH=src <venv>/bin/python -m pytest -q -x --benchmark-disable tests" --max 10` | 10 of 10 caught. Self-check: 7 of 7 files loaded from the copy | 7 s |

What the runs showed:

- python-slugify sets `addopts = "--color=yes"` in its `pyproject.toml`, which beats `NO_COLOR` and `PY_COLORS`. The colour codes are stripped from the output instead, so every "by" name came out clean.
- The first python-slugify run printed `(by (test name not in output))` on 3 lines. pytest 9 reports failed subtests as `SUBFAILED(params) path::test - msg`, and `caught_by` did not know that form. Fixed, with a test on the real captured output (`fixtures/pytest_subtests_fail_color.txt`). Both later runs have a name on all 9 CAUGHT lines.
- 4 of the 10 planted bugs in python-slugify landed in `tools/` (dev scripts, not the library), because the tool treats every non-test `.py` file as source. `--paths slugify` would have limited it to the library. Not changed.
- My first humanize command failed its baseline because I passed `-p no:benchmark`, which its tests need. The tool printed the last 20 lines of the test output (`fixture 'benchmark' not found`), which made the cause obvious.
- I passed `--benchmark-disable` to humanize's tests. I did not time a run without it.
- Windows is not covered by any run here.
