# verification-discipline

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

## The one-line version

My validation stack is built to reject flattering results, including my own. That
willingness — not any single green check — is the thing on offer.

## Runnable in 30 seconds

```
cd gate-mutation-example
make test        # 9 tests, offline, fake client
make mutations   # 4 seeded bugs, each caught, files restored byte-for-byte
```

Requires Python 3 and `pytest`. Nothing here touches a network or a private store.

## Licensing

Code (anything under `gate-mutation-example/`) is MIT — see [LICENSE](LICENSE).
Prose (the case study, the excerpts, this README) is not open-licensed — see
[LICENSE-CONTENT.md](LICENSE-CONTENT.md).
