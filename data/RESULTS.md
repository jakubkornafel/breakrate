# First public measurement

> Thirteen public repositories, measured 2026-08-27 · metric v0.1 · proxy mode · 7-day window

Ten of the thirteen carry at least a hundred changes in **both** cohorts, which is the subset
the comparison below uses. The other three are reported in the table but are too one-sided to
compare against themselves.

## The headline

**Agent-involved and human-authored changes break things at the same rate.**

| | agent-involved | human |
|---|---|---|
| Median break rate | **2.0%** | **2.1%** |
| Range across repositories | 0.3% – 7.1% | 0.0% – 3.9% |

The median difference between the two cohorts **inside a repository is 0.5 percentage points**.
The spread **between repositories is 6.8 points** — thirteen times larger.

Whatever decides how much breaks, it is not who wrote the change.

In eight of the ten repositories the agent rate is the higher of the two, so this is not a
claim that agents are safer. It is a claim about magnitude: the gap between cohorts is small
and inconsistent in direction, while the gap between codebases is large and consistent.

## Every repository measured

| Repository | Agent changes | Break rate | Human changes | Break rate |
|---|---|---|---|---|
| monarch-initiative/dismech | 4203 | 1.4% | 3700 | 0.8% |
| windmill-labs/windmill | 2386 | 1.6% | 12124 | 1.5% |
| marigold-ui/marigold | 2266 | 7.1% | 2627 | 3.3% |
| BestNathan/nession | 1212 | 0.7% | 92 | 0.0% |
| conciv-dev/conciv | 868 | 2.1% | 103 | 0.0% |
| base/base | 781 | 1.4% | 4309 | 1.7% |
| oeduardobrandao/sm-crm | 715 | 0.3% | 581 | 2.9% |
| JamesAwesome/Ergomatic | 647 | 2.0% | 115 | 1.7% |
| WordPress/gutenberg | 586 | 5.1% | 39739 | 3.9% |
| SciML/ModelingToolkit.jl | 390 | 2.8% | 8473 | 2.4% |
| qte77/agentic-job-offer-to-application-kit | 280 | 0.0% | 14 | 0.0% |
| vercel/flags | 101 | 4.0% | 251 | 3.6% |
| matsumo0922/fukurou | 38 | 2.6% | 250 | 3.6% |

Two results are worth staring at. In `sm-crm` the agent rate is **an order of magnitude lower**
than the human rate in the same codebase. In `nession`, where 93% of the changes are
agent-involved, the break rate is 0.7% — lower than most repositories written by people.

## What this does not show

- **Causation.** A repository's rate reflects its review process, its test suite, its domain and
  what work each cohort is given. This measures the codebase, not the tool.
- **Ground truth.** Proxy mode infers breakage from revert and regression vocabulary in later
  commits. It undercounts anything broken and never fixed, and rewards disciplined commit
  messages with worse-looking numbers. See [SPEC.md](../SPEC.md).
- **A representative sample.** Thirteen repositories, selected because they carry agent commit
  trailers alongside human ones. Public projects with review culture are over-represented,
  which is precisely the population where the two cohorts would be expected to converge.

## Reproducing this

```bash
./harvest.sh windmill-labs/windmill vercel/flags base/base ...
```

Each JSON in `data/public/` records the repository, the commit it was measured at, the window,
the mode and both versions, so any number here can be recomputed and disputed.
