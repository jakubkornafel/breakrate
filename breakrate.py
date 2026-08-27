#!/usr/bin/env python3
"""
breakrate — measure what agent-written code breaks.

Computes Break Rate: the share of merged changes that broke something that was working,
split by authorship cohort. Reads git history only; no instrumentation, no CI access
required, works retroactively on any repository.

Usage:
  python3 breakrate.py scan <repo> [--since 2026-01-01] [--until 2026-08-27]
                                   [--window-days 7] [--format md|json]
  python3 breakrate.py cohorts <repo> [--since ...]     # who wrote what, no break analysis

Specification: SPEC.md. The metric is versioned separately from this tool.
"""

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

TOOL_VERSION = "0.1.0"
METRIC_VERSION = "0.1"

RECORD = "\x1e"
FIELD = "\x1f"

# Known coding agents, matched against Co-Authored-By trailers as whole tokens.
# Substring matching is not safe here: "amp" occurs inside "example.com", which would
# silently reclassify human commits as agent work.
AGENT_NAMES = (
    "claude", "codex", "copilot", "devin", "cursor", "jules", "aider",
    "gemini", "openai", "anthropic", "gpt", "forge", "amp", "sonnet", "opus", "haiku",
)
AGENT_PATTERN = re.compile(
    r"(?<![a-z0-9])(" + "|".join(AGENT_NAMES) + r")(?![a-z0-9])", re.IGNORECASE
)

# Bot identities in the author or committer field.
BOT_EMAIL_MARKERS = ("[bot]", "noreply@anthropic.com", "noreply@openai.com")

# Narrow: vocabulary that means "something that worked stopped working".
# Plain "fix" is deliberately NOT here — in an active repository most commits are fixes,
# and counting them all turns the metric into a measure of commit granularity.
REGRESSION_SUBJECT = re.compile(
    r"\b(regression|regressions|hotfix|broke|broken|breakage|crash|crashes|crashing|"
    r"revert|reverts|reverted|no longer|stopped working|unbreak)\b",
    re.IGNORECASE,
)

# Broad: ordinary corrective work. Counted separately as churn, never as breakage.
CHURN_SUBJECT = re.compile(
    r"\b(fix|fixes|fixed|bugfix|repair|repairs|correct|corrects|corrected)\b",
    re.IGNORECASE,
)

REVERT_SUBJECT = re.compile(r"^revert\b", re.IGNORECASE)


# ----------------------------------------------------------------------------- git


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if result.returncode != 0:
        raise SystemExit(f"error: git {' '.join(args)} failed:\n{result.stderr.strip()}")
    return result.stdout


def read_commits(repo: Path, since: Optional[str], until: Optional[str]) -> List[Dict[str, Any]]:
    """Every non-merge commit in range, with its files and trailers.

    Fields are separated by unit separators emitted by git itself (%x1f), and the trailing
    separator after the body closes it, so whatever --name-only appends lands in its own
    field. That removes the need to guess which lines are paths.
    """
    fmt = "%x1e%H%x1f%at%x1f%an%x1f%ae%x1f%cn%x1f%ce%x1f%s%x1f%b%x1f"
    args = ["log", "--no-merges", "--name-only", f"--pretty=format:{fmt}"]
    if since:
        args.append(f"--since={since}")
    if until:
        args.append(f"--until={until}")

    commits = []
    for chunk in git(repo, *args).split(RECORD):
        if not chunk.strip():
            continue
        parts = chunk.split(FIELD)
        if len(parts) < 8:
            continue
        sha, timestamp, an, ae, cn, ce, subject, body = parts[:8]
        files_blob = parts[8] if len(parts) > 8 else ""
        files = [line.strip() for line in files_blob.splitlines() if line.strip()]

        commits.append(
            {
                "sha": sha.strip(),
                "short": sha.strip()[:8],
                "timestamp": int(timestamp),
                "author_name": an,
                "author_email": ae,
                "committer_name": cn,
                "committer_email": ce,
                "subject": subject,
                "body": body,
                "files": sorted(set(files)),
            }
        )
    return commits


# ----------------------------------------------------------------- cohort assignment


def cohort_of(commit: Dict[str, Any]) -> str:
    identities = " ".join(
        [commit["author_email"], commit["committer_email"],
         commit["author_name"], commit["committer_name"]]
    ).lower()
    if any(marker in identities for marker in BOT_EMAIL_MARKERS):
        return "agent_authored"

    for line in commit["body"].splitlines():
        low = line.lower()
        if low.startswith("co-authored-by:") and AGENT_PATTERN.search(low):
            return "agent_assisted"
        if low.startswith("agent-authored:") and "true" in low:
            return "agent_assisted"
    return "human"


# --------------------------------------------------------------------- break detection


def attribute_breaks(commits: List[Dict[str, Any]], window_days: int) -> None:
    """Mark each commit with how, if at all, it was break-attributed."""
    window = timedelta(days=window_days).total_seconds()
    by_time = sorted(commits, key=lambda c: c["timestamp"])

    for index, commit in enumerate(by_time):
        commit["break_kind"] = None
        commit["break_by"] = None
        commit["break_after_hours"] = None
        touched = set(commit["files"])

        for later in by_time[index + 1:]:
            gap = later["timestamp"] - commit["timestamp"]
            if gap <= 0:
                continue
            if gap > window:
                break

            reverts = REVERT_SUBJECT.match(later["subject"]) and (
                commit["subject"][:40] in later["subject"]
                or commit["short"] in later["subject"] + later["body"]
            )
            explicit_sha = commit["short"] in (later["subject"] + later["body"])
            overlaps = bool(touched and touched.intersection(later["files"]))
            regression = REGRESSION_SUBJECT.search(later["subject"]) and overlaps
            churn = CHURN_SUBJECT.search(later["subject"]) and overlaps

            if reverts or explicit_sha:
                commit["break_kind"] = "revert"
            elif regression:
                commit["break_kind"] = "regression"
            elif churn:
                commit["break_kind"] = "churn"
            else:
                continue

            commit["break_by"] = later["short"]
            commit["break_after_hours"] = round(gap / 3600, 1)
            break


# -------------------------------------------------------------------------- reporting


def summarise(commits: List[Dict[str, Any]], window_days: int) -> Dict[str, Any]:
    cohorts: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"changes": 0, "broke": 0, "reverts": 0, "regressions": 0, "churn": 0, "hours": []}
    )

    for commit in commits:
        entry = cohorts[commit["cohort"]]
        entry["changes"] += 1
        if commit["break_kind"] == "churn":
            entry["churn"] += 1
            continue
        if commit["break_kind"]:
            entry["broke"] += 1
            entry["hours"].append(commit["break_after_hours"])
            if commit["break_kind"] == "revert":
                entry["reverts"] += 1
            else:
                entry["regressions"] += 1

    stamps = [c["timestamp"] for c in commits]
    weeks = max((max(stamps) - min(stamps)) / 604800, 1 / 7) if stamps else 1

    result = {}
    for name, entry in cohorts.items():
        result[name] = {
            "changes": entry["changes"],
            "broke": entry["broke"],
            "break_rate": round(entry["broke"] / entry["changes"], 4) if entry["changes"] else 0.0,
            "revert_rate": round(entry["reverts"] / entry["changes"], 4) if entry["changes"] else 0.0,
            "regression_rate": round(entry["regressions"] / entry["changes"], 4) if entry["changes"] else 0.0,
            "churn_rate": round(entry["churn"] / entry["changes"], 4) if entry["changes"] else 0.0,
            "throughput_per_week": round(entry["changes"] / weeks, 2),
            "median_hours_to_fix": median(entry["hours"]),
        }

    involved = [c for c in commits if c["cohort"] in ("agent_authored", "agent_assisted")]
    human = [c for c in commits if c["cohort"] == "human"]
    result["agent_involved"] = rollup(involved, weeks)
    result["human_total"] = rollup(human, weeks)
    return result


def rollup(subset: List[Dict[str, Any]], weeks: float) -> Dict[str, Any]:
    broke = [c for c in subset if c["break_kind"] in ("revert", "regression")]
    churned = [c for c in subset if c["break_kind"] == "churn"]
    return {
        "changes": len(subset),
        "broke": len(broke),
        "break_rate": round(len(broke) / len(subset), 4) if subset else 0.0,
        "churn_rate": round(len(churned) / len(subset), 4) if subset else 0.0,
        "throughput_per_week": round(len(subset) / weeks, 2),
        "median_hours_to_fix": median([c["break_after_hours"] for c in broke]),
    }


def median(values: List[float]) -> Optional[float]:
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    middle = len(values) // 2
    if len(values) % 2:
        return values[middle]
    return round((values[middle - 1] + values[middle]) / 2, 1)


def concentration(commits: List[Dict[str, Any]]) -> float:
    """Share of break attributions landing in the busiest tenth of files."""
    counts: Dict[str, int] = defaultdict(int)
    for commit in commits:
        if commit["break_kind"] in ("revert", "regression"):
            for path in commit["files"]:
                counts[path] += 1
    if not counts:
        return 0.0
    ranked = sorted(counts.values(), reverse=True)
    top = max(1, len(ranked) // 10)
    return round(sum(ranked[:top]) / sum(ranked), 3)


def format_markdown(report: Dict[str, Any]) -> str:
    meta = report["meta"]
    rows = []
    order = ["agent_authored", "agent_assisted", "agent_involved", "human", "human_total"]
    seen = set()
    for name in order + sorted(report["cohorts"]):
        if name in seen or name not in report["cohorts"]:
            continue
        seen.add(name)
        c = report["cohorts"][name]
        hours = f"{c['median_hours_to_fix']}h" if c.get("median_hours_to_fix") is not None else "—"
        rows.append(
            f"| {name} | {c['changes']} | {c['broke']} | **{c['break_rate'] * 100:.1f}%** | "
            f"{c.get('churn_rate', 0) * 100:.1f}% | {c['throughput_per_week']} | {hours} |"
        )

    return "\n".join(
        [
            f"# Break Rate — {meta['repo']}",
            "",
            f"`{meta['range']}` · window {meta['window_days']}d · mode `{meta['mode']}` · "
            f"metric v{meta['metric_version']} · tool v{meta['tool_version']}",
            "",
            "| Cohort | Changes | Broke | Break Rate | Churn | Changes/week | Median time to fix |",
            "|---|---|---|---|---|---|---|",
            *rows,
            "",
            f"Rework concentration: **{report['rework_concentration'] * 100:.0f}%** of "
            "attributions land in the busiest tenth of files.",
            "",
            "> Break Rate is meaningless without throughput: the cheapest way to reach zero is to "
            "stop shipping. Proxy mode over-counts iterative development and under-counts silent "
            "breakage — see SPEC.md before quoting these numbers.",
        ]
    )


# ----------------------------------------------------------------------------- commands


def cmd_scan(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    commits = read_commits(repo, args.since, args.until)
    if not commits:
        raise SystemExit("error: no commits in range")

    for commit in commits:
        commit["cohort"] = cohort_of(commit)
    attribute_breaks(commits, args.window_days)

    stamps = [c["timestamp"] for c in commits]
    report = {
        "meta": {
            "repo": repo.name,
            "range": (
                f"{datetime.fromtimestamp(min(stamps), timezone.utc):%Y-%m-%d}"
                f" … {datetime.fromtimestamp(max(stamps), timezone.utc):%Y-%m-%d}"
            ),
            "commits": len(commits),
            "window_days": args.window_days,
            "mode": "proxy",
            "metric_version": METRIC_VERSION,
            "tool_version": TOOL_VERSION,
        },
        "cohorts": summarise(commits, args.window_days),
        "rework_concentration": concentration(commits),
    }

    if args.format == "json":
        print(json.dumps(report, indent=2))
    else:
        print(format_markdown(report))
    return 0


def cmd_cohorts(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    commits = read_commits(repo, args.since, args.until)
    counts: Dict[str, int] = defaultdict(int)
    for commit in commits:
        counts[cohort_of(commit)] += 1
    total = sum(counts.values()) or 1
    for name, count in sorted(counts.items(), key=lambda item: -item[1]):
        print(f"{name:16} {count:5}  {count / total * 100:5.1f}%")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Measure what agent-written code breaks.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser("scan", help="compute Break Rate for a repository")
    scan.add_argument("repo")
    scan.add_argument("--since")
    scan.add_argument("--until")
    scan.add_argument("--window-days", type=int, default=7)
    scan.add_argument("--format", choices=("md", "json"), default="md")
    scan.set_defaults(func=cmd_scan)

    cohorts = subparsers.add_parser("cohorts", help="authorship breakdown only")
    cohorts.add_argument("repo")
    cohorts.add_argument("--since")
    cohorts.add_argument("--until")
    cohorts.set_defaults(func=cmd_cohorts)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
