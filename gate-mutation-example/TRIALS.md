# Trials of try_on_your_repo.py

Real runs, recorded as printed. Commit = this repo's commit at the time of the run.

| Project | Command | Result | Time |
|---|---|---|---|
| this repo's `gate-mutation-example` (cli.py, gate.py, json_safe.py) | `make self-check` | 7 of 8 planted bugs caught; survivor `gate.py:81` (`"receipt": True` on the attached path, no test asserts it) | 5-6 s; about 10 s since the self-check was added |

Runs on outside projects are next.
