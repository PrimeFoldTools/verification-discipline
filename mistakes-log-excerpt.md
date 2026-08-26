# Failure log — six entries

Sanitized excerpts from a running ledger I keep (180+ entries). Every time an
agent or I get something wrong, the failure, the countermeasure, and the test that
now catches it go here. Future sessions read it first, so a given mistake is expensive
once, not weekly. Format: **Failure → Countermeasure → Test**.

---

**1. A test that passed on the broken code.**

- *Failure:* a fix for a "reports healthy while dead" monitor shipped with a test that

  checked whether "healthy" appeared anywhere in the output. The broken output still
  contained it, so the test passed on the bug it was meant to catch.

- *Countermeasure:* a test earns trust only after I've seeded the exact defect and

  watched it go red. Green out of the box is a decoration.

- *Test:* a mutation harness that flips the guard and asserts the suite fails.

**2. `default=str` turned a false into a truthy string.**

- *Failure:* serializing a gate's verdict with `json.dumps(..., default=str)` renders a

  numpy `False` as the string `"False"` — which is truthy. A failing gate would read
  back as a pass.

- *Countermeasure:* a numpy-safe encoder that converts non-native scalars to their

  native type and refuses to stringify. `default=str` is banned on verdict paths.

- *Test:* `test_json_safe_refuses_to_stringify_a_fake_false` (in this repo).

**3. Two guards that masked each other.**

- *Failure:* two validation signals both fired on every probe case, so disabling either

  one alone left the suite green. Each looked tested; neither was.

- *Countermeasure:* when two guards can catch the same case, at least one test must

  isolate each — a case that trips one and not the other.

- *Test:* isolation pins per guard, verified by mutating each guard independently.

**4. Relayed a claim instead of reading the source.**

- *Failure:* a handoff note said "all the writers bypass the gate." Nearly acted on it.

  The code showed a different, simpler cause: the gate had no entry point to call.

- *Countermeasure:* a note is a claim, not a fact — including my own prior notes. Read

  the primary source before repeating a state claim.

- *Test:* a standing checklist gate on the words "done / ready / verified" that forces a

  specific check against the specific claim.

**5. A drift check that matched substrings, not values.**

- *Failure:* a sync check compared whether a value appeared *anywhere* in a document. A

  stale year still matched via an unrelated row, so real drift slipped through.

- *Countermeasure:* compare extracted values at their exact location, never

  presence-anywhere. Presence-anywhere is fail-open.

- *Test:* the check is control-tested by seeding each drift class and confirming it goes

  red before trusting a green.

**6. A scoped commit swept in a parallel session's work.**

- *Failure:* `git add <file>` on a shared tree captured another session's uncommitted

  edits to the same file, under my commit message.

- *Countermeasure:* `git diff --cached` (the hunks, not just the filenames) before every

  commit on a shared tree. A per-file add is not scope-safe.

- *Test:* the review step is now hunk-level, and the recovery pattern (rebuild

  mine-only, amend) is documented.
