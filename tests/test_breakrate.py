#!/usr/bin/env python3
"""
Tests for breakrate. Builds throwaway git repositories and measures them.

Run: python3 -m pytest tests/test_breakrate.py
"""

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import breakrate  # noqa: E402


# --------------------------------------------------------------------------- helpers


class Repo:
    """A tiny git repository with commits placed at chosen times."""

    def __init__(self, path: Path):
        self.path = path
        self.clock = 1_767_225_600  # 2026-01-01T00:00:00Z
        self._run("init", "-q", "-b", "main")
        self._run("config", "user.name", "Test Human")
        self._run("config", "user.email", "human@example.com")

    def _run(self, *args, env_extra=None):
        env = {"GIT_TERMINAL_PROMPT": "0", "HOME": str(self.path), "PATH": "/usr/bin:/bin"}
        if env_extra:
            env.update(env_extra)
        subprocess.run(
            ["git", "-C", str(self.path), *args],
            check=True, capture_output=True, text=True, env=env,
        )

    def commit(self, subject, files=("app.py",), body="", author=None, hours_later=1):
        self.clock += int(hours_later * 3600)
        for name in files:
            target = self.path / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f"{subject}\n", encoding="utf-8")
            self._run("add", name)

        stamp = f"{self.clock} +0000"
        env = {"GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp}
        if author:
            name, email = author
            env["GIT_AUTHOR_NAME"] = name
            env["GIT_AUTHOR_EMAIL"] = email
            env["GIT_COMMITTER_NAME"] = name
            env["GIT_COMMITTER_EMAIL"] = email

        message = subject if not body else f"{subject}\n\n{body}"
        self._run("commit", "-q", "-m", message, env_extra=env)


CLAUDE = "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"


@pytest.fixture
def repo(tmp_path):
    return Repo(tmp_path)


def scan(repo, window_days=7):
    commits = breakrate.read_commits(repo.path, None, None)
    for commit in commits:
        commit["cohort"] = breakrate.cohort_of(commit)
    breakrate.attribute_breaks(commits, window_days)
    return commits


def by_subject(commits, subject):
    return next(c for c in commits if c["subject"] == subject)


# ------------------------------------------------------------------------- reading


def test_reads_commits_with_files_and_trailers(repo):
    repo.commit("feat: add thing", files=("a.py", "b.py"), body=CLAUDE)
    commits = scan(repo)

    assert len(commits) == 1
    assert commits[0]["files"] == ["a.py", "b.py"]
    assert "Claude" in commits[0]["body"]


def test_multiline_body_does_not_swallow_file_list(repo):
    repo.commit("feat: thing", files=("a.py",), body="line one\n\nline two\n\n" + CLAUDE)
    commits = scan(repo)
    assert commits[0]["files"] == ["a.py"]


# ------------------------------------------------------------------------- cohorts


def test_agent_trailer_marks_agent_assisted(repo):
    repo.commit("feat: written with help", body=CLAUDE)
    assert scan(repo)[0]["cohort"] == "agent_assisted"


def test_bot_author_marks_agent_authored(repo):
    repo.commit("feat: autonomous", author=("some-agent[bot]", "1@users.noreply.github.com"))
    assert scan(repo)[0]["cohort"] == "agent_authored"


def test_human_coauthor_is_still_human(repo):
    repo.commit("feat: pair work", body="Co-Authored-By: Szymon <s@example.com>")
    assert scan(repo)[0]["cohort"] == "human"


def test_explicit_optin_trailer(repo):
    repo.commit("feat: tagged by hand", body="Agent-Authored: true")
    assert scan(repo)[0]["cohort"] == "agent_assisted"


# -------------------------------------------------------------------- break detection


def test_revert_counts_as_break(repo):
    repo.commit("feat: risky change")
    repo.commit('Revert "feat: risky change"')
    assert by_subject(scan(repo), "feat: risky change")["break_kind"] == "revert"


def test_regression_wording_counts_as_break(repo):
    repo.commit("feat: new endpoint")
    repo.commit("fix: regression in new endpoint")
    assert by_subject(scan(repo), "feat: new endpoint")["break_kind"] == "regression"


def test_plain_fix_is_churn_not_break(repo):
    """The whole credibility of the metric rests on this distinction."""
    repo.commit("feat: new endpoint")
    repo.commit("fix: tidy up naming")
    assert by_subject(scan(repo), "feat: new endpoint")["break_kind"] == "churn"


def test_break_requires_touching_the_same_file(repo):
    repo.commit("feat: backend", files=("server.py",))
    repo.commit("fix: regression in styles", files=("styles.css",))
    assert by_subject(scan(repo), "feat: backend")["break_kind"] is None


def test_fix_outside_window_is_not_attributed(repo):
    repo.commit("feat: slow burn")
    repo.commit("fix: regression here", hours_later=24 * 30)
    assert by_subject(scan(repo), "feat: slow burn")["break_kind"] is None


def test_earlier_commit_is_never_blamed_on_a_later_one(repo):
    repo.commit("fix: regression in old code")
    repo.commit("feat: came afterwards")
    assert by_subject(scan(repo), "feat: came afterwards")["break_kind"] is None


def test_time_to_fix_is_recorded(repo):
    repo.commit("feat: thing")
    repo.commit("hotfix: thing broke", hours_later=3)
    assert by_subject(scan(repo), "feat: thing")["break_after_hours"] == 3.0


# ---------------------------------------------------------------------- aggregation


def test_break_rate_excludes_churn(repo):
    repo.commit("feat: one", body=CLAUDE)
    repo.commit("fix: cosmetic tweak")          # churn against "feat: one"
    repo.commit("feat: two", body=CLAUDE)
    repo.commit("hotfix: two is broken")        # break against "feat: two"

    commits = scan(repo)
    summary = breakrate.summarise(commits, 7)

    agent = summary["agent_assisted"]
    assert agent["changes"] == 2
    assert agent["broke"] == 1
    assert agent["break_rate"] == 0.5
    assert agent["churn_rate"] == 0.5


def test_throughput_is_reported_alongside(repo):
    for index in range(4):
        repo.commit(f"feat: change {index}", hours_later=24)
    summary = breakrate.summarise(scan(repo), 7)
    assert summary["human"]["throughput_per_week"] > 0


def test_cohort_rollup_matches_parts(repo):
    repo.commit("feat: agent work", body=CLAUDE)
    repo.commit("feat: bot work", author=("x[bot]", "2@users.noreply.github.com"))
    repo.commit("feat: human work")

    summary = breakrate.summarise(scan(repo), 7)
    assert summary["agent_involved"]["changes"] == 2
    assert summary["human_total"]["changes"] == 1


def test_median_helper():
    assert breakrate.median([]) is None
    assert breakrate.median([2.0]) == 2.0
    assert breakrate.median([1.0, 3.0]) == 2.0
