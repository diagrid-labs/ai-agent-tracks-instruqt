"""Tests for the shared one-shot orchestration helpers."""

from __future__ import annotations

from auditor_core import orchestration, report
from auditor_core.github_client import GitHubError
from auditor_core.models import PRContext


class _FakeGitHub:
    def __init__(self, *_, pr=None, upsert="created on o/r#5", raise_=False):
        self._pr = pr
        self._upsert = upsert
        self._raise = raise_

    def get_pull_request(self, repo, number):
        if self._raise:
            raise GitHubError("boom")
        return self._pr or {"title": "", "body": ""}

    def upsert_comment(self, repo, number, body, marker):
        if self._raise:
            raise GitHubError("boom")
        return self._upsert

    def close(self):
        pass


def test_parse_bumps_from_metadata_env():
    pr = PRContext(repo="o/r", number=1)
    bumps = orchestration.parse_bumps(
        pr,
        {
            "DEP_ECOSYSTEM": "pip",
            "DEP_NAMES": "urllib3",
            "DEP_PREV_VERSION": "1.26.5",
            "DEP_NEW_VERSION": "1.26.18",
        },
    )
    assert len(bumps) == 1
    assert bumps[0].package == "urllib3" and bumps[0].ecosystem == "pypi"


def test_parse_bumps_falls_back_to_title():
    pr = PRContext(repo="o/r", number=1, title="Bump lodash from 1 to 2")
    bumps = orchestration.parse_bumps(pr, {})
    assert bumps[0].package == "lodash"


def test_fetch_pr_details(monkeypatch):
    monkeypatch.setattr(
        orchestration,
        "GitHubClient",
        lambda **k: _FakeGitHub(pr={"title": "t", "body": "b"}),
    )
    assert orchestration.fetch_pr_details("o/r", 5)["title"] == "t"


def test_fetch_pr_details_skips_without_repo_or_number():
    assert orchestration.fetch_pr_details("", 5) == {}
    assert orchestration.fetch_pr_details("o/r", 0) == {}


def test_fetch_pr_details_empty_on_error(monkeypatch):
    monkeypatch.setattr(
        orchestration, "GitHubClient", lambda **k: _FakeGitHub(raise_=True)
    )
    assert orchestration.fetch_pr_details("o/r", 5) == {}


def test_ensure_pr_details_fetches_when_title_missing(monkeypatch):
    monkeypatch.setattr(
        orchestration,
        "fetch_pr_details",
        lambda repo, num: {"title": "Bump x from 1 to 2", "body": "b"},
    )
    pr = orchestration.ensure_pr_details(PRContext(repo="o/r", number=5))
    assert pr.title == "Bump x from 1 to 2"


def test_ensure_pr_details_noop_when_title_present(monkeypatch):
    def _boom(*_a, **_k):
        raise AssertionError("should not fetch when title present")

    monkeypatch.setattr(orchestration, "fetch_pr_details", _boom)
    pr = orchestration.ensure_pr_details(
        PRContext(repo="o/r", number=5, title="have it")
    )
    assert pr.title == "have it"


def test_combine_reports_single_keeps_one_marker():
    combined = orchestration.combine_reports([f"{report.MARKER}\n## body"])
    assert combined.count(report.MARKER) == 1
    assert "## body" in combined


def test_combine_reports_multiple_uses_single_marker_and_separator():
    combined = orchestration.combine_reports(
        [f"{report.MARKER}\n## a", f"{report.MARKER}\n## b"]
    )
    assert combined.count(report.MARKER) == 1
    assert "---" in combined and "## a" in combined and "## b" in combined


def test_combine_reports_empty_is_safe():
    assert orchestration.combine_reports([]) == f"{report.MARKER}\n"


def test_error_report_demands_manual_review():
    out = orchestration.error_report(RuntimeError("x"))
    assert report.MARKER in out
    assert "Manual review required" in out
    assert "RuntimeError" in out


def test_post_report_dry_run_without_token(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    assert orchestration.post_report("o/r", 5, "b").startswith("[dry-run]")


def test_post_report_dry_run_without_pr_number(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    assert orchestration.post_report("o/r", 0, "b").startswith("[dry-run]")


def test_post_report_posts_with_token(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setattr(
        orchestration,
        "GitHubClient",
        lambda **k: _FakeGitHub(upsert="created on o/r#5"),
    )
    assert "created" in orchestration.post_report("o/r", 5, "b")


def test_post_report_handles_failure(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setattr(
        orchestration, "GitHubClient", lambda **k: _FakeGitHub(raise_=True)
    )
    assert "FAILED" in orchestration.post_report("o/r", 5, "b")
