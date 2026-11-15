# verification-discipline

A runnable gate that proves its own tests can fail, and a command that checks whether yours can. For anyone running AI coding agents.

![A real run: 8 bugs planted in a copy of the example project, 7 caught by its tests, each with the test that caught it](assets/try-on-your-repo-run.png)

I run a fleet of coding agents that ship real work. They are capable and confident,
which is exactly what a wrong answer also looks like. So most of what I actually build
is the machinery that assumes the agents are lying until proven otherwise.

This repo is a small, honest sample of that machinery — enough to run, not the whole
fleet.

## Start here

- **[CASE_STUDY.md](CASE_STUDY.md)** — how I catch AI systems claiming they're done.
- **[gate-mutation-example/](gate-mutation-example/)** — runnable. `make test` then

  `make mutations`: a real gate, and proof its tests can actually fail.

- **[WHAT_THIS_DOES_NOT_PROVE.md](WHAT_THIS_DOES_NOT_PROVE.md)** — read this before you

  over-read the rest.

- **[mistakes-log-excerpt.md](mistakes-log-excerpt.md)** — six real failures, each with

  the countermeasure and the test that now catches it.

- **[andon](https://github.com/PrimeFoldTools/andon)** — the installable kit version of

  this discipline: defect ledger → countermeasure → mechanical guard, stripped from the
  system I run daily.

## The one-line version

My validation stack is built to reject flattering results, including my own. That
willingness — not any single green check — is the thing on offer.

## Runnable in 30 seconds

```
cd gate-mutation-example
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
make test        # 65 tests, offline: 9 on the gate (fake client), 56 on try_on_your_repo.py
make mutations   # 4 seeded bugs, each caught, files restored byte-for-byte
```

Needs Python 3 and `pytest`. Tested on Python 3.9.6 and 3.12.13 (macOS), pytest 8.4.2: all 65 tests pass on both. Other Python versions and Windows are untested. Nothing here touches a network or a private store.

## Try it on your own project

Can your tests fail? This plants small bugs, one at a time, in a copy of your project and runs your tests after each one. Your own files are never touched.

```
python3 gate-mutation-example/try_on_your_repo.py /path/to/your/project --test "python3 -m pytest -q -x"
```

First it runs a self-check: it adds one line to each source file in the copy that records the file's path when Python loads it, and checks which files your tests really loaded from the copy. Files they load from somewhere else (often an installed package) or never load are left out and named in the report, because bugs planted there would look like survivors. Then it breaks every file that did load and checks that your test command fails. If no file loads from the copy, or the command still passes with the code broken, it stops instead of giving you a misleading report.

Just changed some code, or your agent did? Check only those lines:

```
python3 gate-mutation-example/try_on_your_repo.py /path/to/your/project --changed
```

`--changed` plants bugs only in lines changed since your last commit (or since any git ref: `--changed main`). Each CAUGHT line names the test that caught it, when pytest or unittest reports one.

By default it leaves out top-level `tools/`, `scripts/`, `docs/`, `examples/` and `benchmarks/`, because those usually hold helper scripts, not your library. That is a choice about where bugs go, not a sign that your tests are stronger. It prints which of those folders it skipped. `--include-helpers` turns them back on, and `--paths tools/x.py` still plants in the file you name.

Each bug is a flipped comparison, a swapped `True`/`False`, `and` turned into `or`, or a `return x` turned into `return None`. A CAUGHT line means your tests noticed. A SURVIVED line means the test command passed with that bug planted: look there first. A BROKE line means the planted bug stopped the file from loading: it did not compile, or it started loading and never reached its last line, wherever your tests import it and whatever `--tb` setting you use. That is a crash, not a test noticing, so it is not counted. One case still counts as CAUGHT: a different file crashes while loading because of the planted bug, and your tests import that other file. A TIMEOUT line means your tests did not finish within `--timeout` seconds with that bug planted; it counts toward the total, not as caught. On its own example project it caught 7 of 8; the one that survived (`gate.py:81`, a receipt flag no test asserts) is in the picture above.

It runs your test command 3 times to check the setup, then once per planted bug: 13 runs at the default of 10 bugs. Measured (see `gate-mutation-example/TRIALS.md`): 3 s on python-slugify, 7 s on humanize, and 100 s on this repo's own example, whose suite is slow (that is the run in the picture above). It is a smoke check, not full mutation testing. For that, use [mutmut](https://github.com/boxed/mutmut). Python only, standard library only.

### Known limits

- SURVIVED means the test command passed with that bug planted. The line may run with nothing checking its result, or the change may have no visible effect. It is not always a flaw.
- A file that does not reach its last line when your tests load it (an import that fails and is caught, an exit at import) is left out and named, because a later failure could not be told apart from a broken import.
- It plants a small sample of bugs (`--max`, default 10). `--seed` makes a run repeatable. It is a smoke check, not a coverage score.
- Your tests must pass in a plain copy of the project. Tests that need a database, secrets or absolute paths will stop at the first run.
- Python only. It never edits your real files.

Related tools for full mutation testing: [mutmut](https://github.com/boxed/mutmut) and [cosmic-ray](https://github.com/sixty-north/cosmic-ray) (Python), [Stryker](https://github.com/stryker-mutator/stryker-js) (JavaScript), [PIT](https://github.com/hcoles/pitest) (Java).

## Licensing

Code (anything under `gate-mutation-example/`) is MIT — see [LICENSE](LICENSE).
Prose (the case study, the excerpts, this README) is not open-licensed — see
[LICENSE-CONTENT.md](LICENSE-CONTENT.md).

## Want this on your own setup?

- [Andon](https://github.com/PrimeFoldTools/andon): the installable version of this discipline for Claude Code and Codex.
- [primefold.tools](https://primefold.tools): what we build.
- Send us one incident: what your agent claimed, and what was true. The first three are free. primefoldtools@gmail.com
