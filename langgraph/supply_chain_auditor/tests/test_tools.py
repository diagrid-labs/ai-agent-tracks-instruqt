"""Tests for the LangChain tool surface (logic functions + a wrapper)."""

from __future__ import annotations

import json

import tools
from auditor_core import source_map
from auditor_core.github_client import CompareResult, GitHubError


class _FakeGitHub:
    """Duck-typed GitHubClient for the fetch-tool tests."""

    def __init__(self, *_, notes=None, compare=None, raise_=False):
        self._notes = notes
        self._compare = compare
        self._raise = raise_

    def get_release_notes(self, repo, new):
        if self._raise:
            raise GitHubError("boom")
        return self._notes

    def get_compare(self, repo, old, new):
        if self._raise:
            raise GitHubError("boom")
        return self._compare

    def close(self):
        pass


def test_parse_bump_text_returns_json():
    out = tools.parse_bump_text("Bump lodash from 4.17.20 to 4.17.21")
    assert json.loads(out)[0]["package"] == "lodash"


def test_resolve_repo_text(monkeypatch):
    monkeypatch.setattr(source_map, "resolve", lambda *a, **k: "o/r")
    assert tools.resolve_repo_text("p", "npm") == "o/r"
    monkeypatch.setattr(source_map, "resolve", lambda *a, **k: None)
    assert tools.resolve_repo_text("p", "npm") == "UNRESOLVED"


def test_fetch_release_notes_unresolved():
    assert "unavailable" in tools.fetch_release_notes_text("UNRESOLVED", "1", "2")


def test_fetch_release_notes_wraps_untrusted(monkeypatch):
    monkeypatch.setattr(
        tools, "GitHubClient", lambda **k: _FakeGitHub(notes="Real notes")
    )
    out = tools.fetch_release_notes_text("o/r", "1", "2")
    assert "<changelog_" in out
    assert "Real notes" in out


def test_fetch_source_diff_wraps_and_notes_truncation(monkeypatch):
    big = "+" + ("x" * 5000)
    compare = CompareResult(
        base="v1", head="v2", files=[{"filename": "b.js", "patch": big}]
    )
    monkeypatch.setattr(tools, "GitHubClient", lambda **k: _FakeGitHub(compare=compare))
    out = tools.fetch_source_diff_text("o/r", "1", "2", max_bytes=200)
    assert "<source_diff_" in out
    assert "truncated" in out


def test_fetch_source_diff_handles_error(monkeypatch):
    monkeypatch.setattr(tools, "GitHubClient", lambda **k: _FakeGitHub(raise_=True))
    assert "could not fetch diff" in tools.fetch_source_diff_text("o/r", "1", "2")


def test_scan_for_redflags_text():
    diff = 'diff --git a/package.json b/package.json\n@@ @@\n+  "postinstall": "x"\n'
    findings = json.loads(tools.scan_for_redflags_text(diff))
    assert any(f["id"] == "SC-INSTALL-HOOK" for f in findings)


def test_tool_wrapper_is_invokable():
    out = tools.parse_dependabot_bump.invoke({"pr_title": "Bump x from 1 to 2"})
    assert json.loads(out)[0]["package"] == "x"
