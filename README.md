# breakrate

**Does your process hold, whoever writes the code?**

Every benchmark for coding agents measures whether a task was solved. None measures whether
the result stayed working. This computes that from git history, and splits it by who wrote the
change — so the number answers a question about your process, not about your agents.

```bash
python3 breakrate.py scan /path/to/repo
```

```
# Break Rate — dashboard

`2026-01-24 … 2026-06-19` · window 7d · mode `proxy` · metric v0.1

| Cohort         | Changes | Broke | Break Rate | Churn | Changes/week | Median time to fix |
|----------------|---------|-------|------------|-------|--------------|--------------------|
| agent_assisted |     142 |     5 |   **3.5%** | 52.1% |         6.79 |               1.7h |
| human          |     161 |     1 |   **0.6%** | 50.3% |         7.70 |               0.1h |
```

No instrumentation. No CI integration. No configuration. It reads git history, so it works
retroactively on a repository you already have, including one you did not write.

## The first measurement

Thirteen public repositories, measured on 2026-08-27. Across the ten that carry at least a
hundred changes in both cohorts:

| | agent-involved | human |
|---|---|---|
| Median break rate | **2.0%** | **2.1%** |
| Range across repositories | 0.3% – 7.1% | 0.0% – 3.9% |

The median difference between cohorts **inside** a repository is 0.5 points. The spread
**between** repositories is 6.8 points — thirteen times larger. Full table, caveats and method
in [data/RESULTS.md](data/RESULTS.md).

## What the cohorts are for

Not to prove that agents are worse. They break things at the same rate as people, in the same
codebase, and the variation that matters is between codebases. Where the two cohorts do diverge
sharply, what differs is the process the work passes through, not who produced it.

So read the comparison this way:

- **The two rates are close.** Whatever review you have is doing its job on both.
- **The agent rate is several times higher.** The gap is not evidence that agents are careless.
  It is evidence that the work they produce is entering your repository through a thinner
  process than the work people produce — no independent check, no gate that can refuse, nothing
  that runs the thing before it lands.

Bad process turns good input into breakage, and that is as true of a person as of a model.
This measures the process, using authorship only as the contrast that makes it visible.

## What it measures

**Break Rate** — the share of merged changes that broke something that was working.

Reported alongside **throughput**, always. The cheapest way to drive break rate to zero is to
stop shipping, and a number that rewards paralysis will get it.

Attribution comes from commit metadata: `Co-Authored-By` trailers naming a coding agent, bot
identities in the author field, or an explicit `Agent-Authored: true` trailer. Nothing is
self-reported.

The full definition, including the biases you should know before quoting a number, is in
[SPEC.md](SPEC.md). The metric is versioned separately from the tool.

## Why "churn" is a separate column

A later commit called "fix: tidy up naming" touching the same file is not evidence that
anything broke. It is ordinary work. Counting it as breakage produces break rates above 50%
in any active repository, which measures commit granularity rather than stability.

So corrective work is split in two: **regression vocabulary** (revert, hotfix, broke, crash,
regression, no longer working) counts as a break; plain corrective work counts as churn and is
reported separately. That single distinction is what makes the number worth arguing about.

## Usage

```bash
python3 breakrate.py scan <repo> [--since 2026-01-01] [--until 2026-08-27]
                                 [--window-days 7] [--format md|json]
python3 breakrate.py cohorts <repo>          # authorship breakdown only
./harvest.sh owner/repo [owner/repo ...]     # clone public repositories and measure them
```

Python 3.9+, standard library only, no dependencies.

## Status

**v0.1, draft.** Proxy mode (git-only) is implemented and is a screening instrument, not ground
truth. Strict mode — comparing CI check results between a change and its parent — is specified
and not yet built. Expect the regression vocabulary and the flaky-check rule to move once strict
mode has run against real CI data.

Numbers from different repositories compare only when window, mode and metric version match.
Every report records all three.

Measurements of private repositories are gitignored and stay out of this repository; see
[data/README.md](data/README.md) for why, and for the method behind the published set.

## Tests

```bash
python3 -m pytest tests/test_breakrate.py
```

## Licence

MIT © Jakub Kornafel
