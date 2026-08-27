# Data

This directory holds published measurements.

**Rule: only public repositories.** Reports computed against private or client repositories
are gitignored and stay on the machine that produced them. A break rate is an unflattering
number about somebody's engineering, and publishing one for a repository whose owner did not
agree to it is not a thing this project does.

## Method for the published set

1. Select public repositories with a meaningful number of commits carrying agent trailers
   (`Co-Authored-By` naming a coding agent) alongside human commits, so both cohorts exist in
   the same codebase and the comparison holds team, domain and review process constant.
2. Clone at a recorded commit. The SHA goes in the report.
3. Run `breakrate.py scan <repo> --format json` with default settings: 7-day window, proxy mode.
4. Publish the raw JSON unchanged, including the runs that show no difference between cohorts.

Reports are named `<owner>__<repo>.json` and carry the tool and metric version inside, so a
result can be recomputed and disputed later.

## What is not here yet

The public set. It is the next piece of work: without it this is a tool, not a benchmark.
