# Break Rate — specification v0.1

> **Status:** draft, 2026-08-27 · **Author:** Jakub Kornafel · **Licence:** MIT

## Why this exists

Every public benchmark for coding agents measures whether a task was solved. None measures
whether the resulting code stayed working. The gap matters because the two things came apart:
a March 2026 study found agents resolving issues while introducing regressions in 6.08% of
changes, and cut that to 1.82% by handing the agent one context file — a 70% move on a number
nobody reports.

Teams currently answer "is our agent-written code stable?" with an anecdote. This spec defines
the number instead.

## The headline metric

**Break Rate (BR)** — the share of merged changes that broke something that was working.

```
BR = changes_that_broke_something / changes_evaluated
```

Reported separately for each authorship cohort, always alongside throughput (see
[counter-metric](#counter-metric-required)).

## Authorship cohorts

A change is classified from commit metadata only. No instrumentation, no self-reporting.

| Cohort | Rule |
|---|---|
| `agent_authored` | Commit author or committer is a bot identity — email contains `[bot]`, or matches a known agent sender (for example `noreply@anthropic.com`) |
| `agent_assisted` | Commit carries a `Co-Authored-By` trailer naming a known coding agent (Claude, Codex, Copilot, Devin, Cursor, Jules, Aider, Gemini…), or an explicit `Agent-Authored: true` trailer |
| `human` | Neither of the above |

`agent_involved` = `agent_authored` + `agent_assisted`, and is the cohort compared against
`human` in the headline.

**Why two agent cohorts:** in current practice most agent work reaches the repository as a
human-authored commit with an agent trailer. Collapsing that into "human" hides most of the
signal; collapsing it into "fully autonomous" overstates it. They are counted separately and
can be recombined.

## Detecting a break

Two modes. Strict is ground truth; proxy is the screening instrument that works on any
repository today.

### Strict mode — CI-based (not yet implemented)

A change broke something if a check that **passed on its parent** **failed on it**, excluding
checks identified as flaky (same tree, both outcomes present in the window). Requires per-commit
check results from a CI provider.

### Proxy mode — git-only (implemented)

A change `C` is break-attributed if, within `window_days` (default 7), a later commit `F` exists
such that **either**:

1. **Revert** — `F` reverts `C`: its subject matches `^Revert` and quotes `C`'s subject, or its
   message contains `C`'s abbreviated SHA; **or**
2. **Fix-follow** — `F`'s subject matches a fix pattern (`fix`, `hotfix`, `bugfix`, `repair`,
   `correct`, `broken`, `regression`, `revert`) **and** `F` touches at least one file that `C`
   also touched.

Merge commits are excluded from both the population and the detector.

## Known biases — read before quoting a number

Proxy mode is an approximation and this section is part of the metric, not a disclaimer.

- **Overcounts iterative development.** A follow-up commit named "fix spacing" on the same file
  counts as a break. Repositories that commit in small increments will read higher than
  repositories that squash.
- **Undercounts silent breakage.** Anything broken and never fixed, or fixed in a commit whose
  subject does not say so, is invisible.
- **Sensitive to commit hygiene.** Teams that write disciplined subjects are measured more
  accurately, and appear worse, than teams that write "wip".
- **Attribution is best-effort.** Agent work committed without a trailer is counted as human.
  This biases the comparison *against* finding an agent effect, which is the safer direction.
- **Not causal.** A high break rate in one cohort may reflect which work that cohort is given.
  The metric describes a repository, not a tool.

Numbers from different repositories are comparable only when the window, mode and cohort
definitions match. The tool records all three in every report.

## Counter-metric (required)

**Throughput** — merged non-merge changes per week, per cohort.

Break Rate must never be reported alone. The cheapest way to drive it to zero is to stop
shipping, and a metric that rewards paralysis will get it. Any claim about break rate is
incomplete without the throughput it was achieved at.

## Companion metrics

| Metric | Definition |
|---|---|
| **Revert Rate** | Share of changes explicitly reverted within the window |
| **Fix-follow Rate** | Share attributed by rule 2 alone — the softer half of Break Rate |
| **Rework Concentration** | Share of all break attributions landing in the top 10% of files |
| **Median Time to Fix** | Median hours between a break-attributed change and its first fix |

## Report contents

Every report records: repository, commit range, window in days, mode, tool version, cohort
definitions in force, and per-cohort counts — so that any number can be recomputed and disputed.

## Versioning

The metric is versioned separately from the tool. Changing a definition changes the version
and invalidates comparison with earlier numbers. v0.1 is a draft: expect the fix-follow pattern
list and the flaky-test rule to change once strict mode has run against real CI data.
