# How I Catch AI Systems Claiming They're Done

*Case study — Collin Nerdahl. Every number below traces to a primary artifact.*

I run a fleet of coding agents that runs real workflows overnight: trading-strategy
validation, a newsletter pipeline, dozens of scheduled monitors. The agents are capable
and confident. A wrong answer looks the same. So most of what I built isn't the agents.
It's the machinery that assumes they're lying until proven otherwise.

## The gate that went green on the bug it existed to catch

I asked an agent to fix a bug where a monitoring script would report "healthy" for a job
that had silently stopped running. It wrote the fix, wrote a test, ran the test, and the
test passed. Done. Except the test passed on the broken code too. It checked whether the
string "healthy" appeared anywhere in the output, and the broken output still contained
it. The check couldn't fail. It was testing that the letters existed, not that the fix
worked.

This is the most common way an AI lies to you: it writes a check that cannot come out red,
then reports the green as proof. My rule now: a test earns trust only after I've fed it the
exact defect it claims to catch and watched it fail. Green on a bug I seeded is a real test.
Green out of the box tells me nothing.

## The claim I most wanted to be true

My own resume claimed the agent fleet had "run daily for 12+ months." The line even carried
a note grading itself as conservatively rounded down. It was overstated by about 2.4×. I
re-derived it from the actual timestamps: directory birth, first commits, the oldest
installed schedule. The fleet was five months old. The practice behind it runs longer — but
the fleet line was the one I'd propagated without checking, because it flattered the story,
and my own verification pass caught it, not a reviewer.

It now reads "running daily since March 2026." A date instead of a duration: it doesn't
decay, and it survives a follow-up question. The claim got weaker and the document got
stronger. That trade is the whole job.

## Three ways I make an agent's "done" earn its keep

Individual catches don't scale. The standing procedure does. When an agent tells me a task
is complete, three things happen before I believe it.

1. **A written failure log.** Every time I get burned, the symptom, the correction, and

   where it's now codified go into a running ledger of 180+ entries. Future sessions
   read it first, so the same mistake is expensive once, not weekly. It reads more like a
   regression suite than a diary.

2. **A claim-check gate.** Before I let myself write "ready," "done," or "verified" about

   anything load-bearing, a hook forces a specific check against the specific claim. It
   fired on me the day I nearly called a resume "finished" while the sendable PDF was stale.
   The phrase tripped the gate, not my memory.

3. **Adversarial verification.** For public, capital-adjacent, or gate-changing work, I run

   independent critics whose only job is to refute the finding, usually with different lenses: one checks whether
   the logic holds, one whether the test is even valid, one asks what breaks downstream if I'm wrong. Critics who think alike miss the same things.
   On the resume itself that was five verifiers and three critics. Two of their findings did
   not survive my own re-check and are marked refuted in the record. Relaying a claim I
   haven't verified is the failure I'm guarding against.

I write and review code where the invariant matters; my main leverage is orchestrating
agents, specifying failure modes, and building the verification layer. The verification is
the part that's mine.

## Twice, while I was drafting this

While drafting this, the pattern held in real time. I built a small tool and went to commit
it. A pre-commit guard refused, because I'd used a JSON setting that can turn a numpy `False`
into the string `"False"`, which is truthy, so a failing gate would read back as a pass. My
own tripwire, written after an earlier burn, stopped me from shipping that exact class of bug
into a tool whose whole purpose was correctness.

An hour earlier, a handoff note told me "all the writers bypass the safety gate." I almost
relayed it. When I read the code, the real cause was simpler: the gate had no command-line
entry point, so the writers couldn't call it even if they wanted to. "All writers are broken"
and "the gate has no door" lead to different fixes. The note was a claim, not a fact. A claim
from my own prior notes gets checked like any other.

## Why this is the credential

For an evaluations or agent-infrastructure role, the useful signal isn't that my system works.
It's that I assume it doesn't, and I've built the reflexes and the tooling to prove it either
way. My validation stack is built to reject flattering results, including my own.¹ Most people
would bury a system that rejects their own work. I lead with it, because that willingness is the
entire point.

Here's the test: hand me an agent that says it's done. I'll tell you the three places it's
most likely lying, and how I'd force each one into the open without the agent in the room.

---

¹ In the current TIER-1 audit set, 0 of 23 valid cells cleared the global BH-FDR promotion
gate (the gate does promote — this set didn't earn it); one further cell errored with zero
out-of-sample trades and was dropped from the valid set.

*The proof artifacts behind this case study — the failure log, the claim-check gate, the
mutation harnesses, the adversarial-verification runner — are sanitized into the runnable
example in this repo. This case study is its written companion.*
