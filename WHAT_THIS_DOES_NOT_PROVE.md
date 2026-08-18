# What this repo does not prove

I'd rather state the limits than have a screener find them.

This repo proves a **verification style** on **sanitized, self-contained artifacts**.
That is all it proves. Specifically, it does **not** prove:

- **The private fleet.** The real system is dozens of scheduled agents, monitors, and

  pipelines. What's here is one gate and one discipline, reduced to run standalone.

- **Trading alpha.** Nothing here says my strategies make money. The one trading number

  in the case study is a *rejection* result — my own gate promoting none of the current
  candidates — and it's there as evidence I'll reject flattering results, not as a
  performance claim.

- **Production uptime or scale.** No live traffic, no real users, no SLA. The fleet runs

  for one operator (me).

- **Employer-scale deployment.** This is solo work. It shows judgment and tooling, not

  experience shipping inside a large engineering org.

- **That the agents write good code.** The claim is the opposite: I assume they don't,

  and I build the checks that decide.

What it *does* show: given an agent that says it's done, I have a repeatable way to find
where it's most likely wrong and force that into the open — and I hold my own work to the
same test.
