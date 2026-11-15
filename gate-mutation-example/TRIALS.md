# Trials of try_on_your_repo.py

Two runs, both recorded as printed. Run 1 is the first section; Run 2 (after the helper-folder and import-error fixes, re-run on the final code) is at the end.

## Run 1

Real runs. Run 2026-11-13 on branch `agent-features`, after the red-team fixes
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
- 4 of the 10 planted bugs in python-slugify landed in `tools/` (dev scripts, not the library), because the tool treated every non-test `.py` file as source. Fixed after this run: see Run 2 below.
- My first humanize command failed its baseline because I passed `-p no:benchmark`, which its tests need. The tool printed the last 20 lines of the test output (`fixture 'benchmark' not found`), which made the cause obvious.
- I passed `--benchmark-disable` to humanize's tests. I did not time a run without it.
- Windows is not covered by any run here.

## Run 2: after skipping helper folders and counting import errors inside test functions

This run used a rule that read tracebacks to spot a broken import. An outside audit then showed the rule scored two cases wrongly (see Run 3). The rows below are kept as recorded.

Run 2026-11-13 on branch `agent-features` (base 048714d) plus the uncommitted changes of this session.
Same projects, same commits as Run 1, fresh shallow clones (`git clone --depth 1`; HEAD checked: 35aca63 and a950045).
Tool run with Python 3.12.13. Each project tested in its own venv, pytest 9.2.0. Times are the "(Ns)" the tool printed.

| Project | Command (after the tool's path and project) | Result | Time |
|---|---|---|---|
| python-slugify @ 35aca63 | `--test "<venv>/bin/python -m pytest -q -x tests" --max 10` | **10 of 10 caught**, no BROKE, no TIMEOUT. Printed `Skipped helper folders: tools/ (helper scripts, not your library). Add --include-helpers to plant bugs there too.` Self-check: 6 of 6 files loaded from the copy. All 10 bugs landed in `slugify/` | 4 s |
| humanize @ a950045, installed with `pip install -e ".[tests]"` | `--test "<venv>/bin/python -m pytest -q -x --benchmark-disable tests" --max 10` | **Exit 3, nothing planted**, same message as Run 1 (the editable install resolves `humanize` to the original `src/`) | not timed (stops before planting) |
| humanize, same venv, copy's `src` first on the path | `--test "env PYTHONPATH=src <venv>/bin/python -m pytest -q -x --benchmark-disable tests" --max 10` | 10 of 10 caught, no BROKE. Self-check: 7 of 7 files loaded from the copy. No skip line: humanize has `docs/` and `scripts/`, but no `.py` file in either | 8 s |
| this repo's `gate-mutation-example` | `make self-check` | 7 of 8 caught, the same 8 spots and the same survivor as Run 1 (`gate.py:81`). No BROKE lines, so the new import rule did not turn a real catch into BROKE | 84 s |

What changed between Run 1 and Run 2:

- python-slugify: 9 of 10 in Run 1, 10 of 10 in Run 2. The one survivor in Run 1 was in `tools/check_algorithms.py`, a helper script, and that folder is now skipped. This is a change in where the bugs were planted (a different set of candidate spots), not proof that the tests got stronger.
- humanize, both commands: same result as Run 1.
- Own example: same 7 of 8. The time went from 52 s to 84 s. The suite it runs grew from 45 to 62 tests between the two runs, and the tool runs it 3 times before planting. That probably explains the time; I did not isolate the cause. The picture in the README still shows the 52 s run; the output format did not change (the only differences are the temp folder name and the seconds), so it was not re-rendered.

What did not change:

- The Windows run: still none.
- I passed `--benchmark-disable` to humanize's tests and did not time a run without it.
- Nothing here exercised an import error inside a test function on a real project. That case is covered by the captured pytest and unittest output in `fixtures/` (names start with `pytest_lazy_` and `unittest_lazy_`), and by end-to-end tests on a small temp project.

## Run 3: after replacing the traceback rule with load markers

Run 2026-11-13 PM, base 048714d plus the changes later committed as 6a48ed8. This code is a new snapshot, not the one an outside audit reviewed.
An outside audit found two scoring errors in Run 2's code, plus a documented gap with `--tb=no`. Rule now: BROKE means the planted file started loading and never reached its last line (a marker line at the top and one at the bottom of the file; nothing reads tracebacks).
Tool run with Python 3.12.13; projects and commits as before, venvs with pytest 9.2.0. Times are the "(Ns)" the tool printed.

The audit's four cases, run against the new code (project and test text are in the audit's probe script):

| Case | Before (Run 2 code) | Now |
|---|---|---|
| Import succeeds, function crashes on the same line (`import_module("calc").calc(0)`) | BROKE, **1 of 2** caught (the committed parent said 2 of 3) | CAUGHT, **2 of 3** caught |
| Import crash through an alias (`import_module as load`) | CAUGHT, 1 of 1 | BROKE, not counted |
| Import crash with `--tb=no` | CAUGHT, 1 of 1 | BROKE, not counted |
| Project whose only source is in `scripts/` | printed a message, exit 0 | `Nothing was checked`, exit 4 |

| Project | Command (after the tool's path and project) | Result | Time |
|---|---|---|---|
| python-slugify @ 35aca63 | `--test "<venv>/bin/python -m pytest -q -x tests" --max 10` | 10 of 10 caught, no BROKE. Skip line for `tools/`. Self-check: 6 of 6 files loaded, none left out (`__main__.py` is among them) | 3 s |
| humanize @ a950045, `pip install -e ".[tests]"` | same as Run 2 | Exit 3, nothing planted, same message | not timed |
| humanize, `PYTHONPATH=src` first | same as Run 2 | 10 of 10 caught, no BROKE. Self-check: 7 of 7 loaded | 7 s |
| this repo's `gate-mutation-example` | `make self-check` | 7 of 8 caught, same survivor (`gate.py:81`). 3 of 3 files loaded | 100 s |

What did not change: Windows is still untested; I did not time humanize without `--benchmark-disable`.
What this does not cover: a different file that crashes while loading because of the planted bug, when your tests import that other file, still counts as CAUGHT.
The Run 2 and Run 1 numbers are not rewritten.
