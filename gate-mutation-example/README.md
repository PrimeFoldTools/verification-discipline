# gate-mutation-example — runnable

A small, self-contained insert gate and the test discipline around it. No network,
no external store, no private state. Two commands:

```
make test        # 9 tests, all with a fake client — the gate runs offline
make mutations   # flip 4 load-bearing lines, prove each turns the suite RED
```

## What it proves

The case study argues that a passing test means nothing until you've watched it fail
on the defect it claims to catch. `make mutations` is that argument, executable: it
introduces four real bugs — a fail-open path that reads as success, a dedup gate that
never dedups, a dropped input guard, and the `default=str` bug that turns a fake
`False` into a truthy `"False"` — and shows the suite catching each one, then restores
every file byte-for-byte.

The gate itself carries the failure modes worth testing: a **fail-open** path (if the
store can't be read, write the record ANYWAY and flag it, because dropping work
silently is worse than a duplicate), a **receipt** on every write (so a monitor can
later find any record that skipped the gate), and a **precision-first** dedup rule (a
false merge destroys work, so a merge needs strong overlap AND a specific dimension).

## Provenance

This is a clean-room reduction of a production gate I built for a Notion-backed work
queue (private repo, commit `e917063`, 2026-08-18). The private version's real test
suite is 23 tests / 6 mutations; the Notion client, database IDs, and internal agent
names are stripped here so the example runs standalone. The discipline is identical.

## Files

- `gate.py` — the gate: create / attach / fail-open, each leaving a receipt
- `cli.py` — exit-code contract (0 ran · 3 created-unchecked · 1 error)
- `json_safe.py` — the encoder that refuses to stringify a fake boolean
- `test_cli.py` — fixture-first tests, fake client
- `mutation_check.py` — the teeth-check harness
