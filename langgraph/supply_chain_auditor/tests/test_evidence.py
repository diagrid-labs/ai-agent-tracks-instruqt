"""Tests for evidence gathering, truncation, and notes assembly."""

from __future__ import annotations

from auditor_core import evidence, source_map
from auditor_core.github_client import CompareResult, GitHubError


def test_render_and_truncate_includes_small_files_fully():
    files = [{"filename": "a.js", "patch": "+a", "additions": 1, "deletions": 0}]
    text, truncated = evidence.render_and_truncate(files)
    assert "diff --git a/a.js b/a.js" in text
    assert "+a" in text
    assert truncated is False


def test_render_and_truncate_summarizes_oversized_file():
    big = "+" + ("x" * 5000)
    files = [{"filename": "big.js", "patch": big, "additions": 1, "deletions": 0}]
    text, truncated = evidence.render_and_truncate(files, max_bytes=200)
    assert truncated is True
    assert "omitted by risk-prioritized truncation" in text


def test_render_and_truncate_prioritizes_risky_files():
    files = [
        {"filename": "z_benign.txt", "patch": "+hello", "additions": 1},
        {"filename": "package.json", "patch": '+"postinstall": "x"', "additions": 1},
    ]
    text, _ = evidence.render_and_truncate(files)
    # The manifest (risky) is emitted before the benign file.
    assert text.index("package.json") < text.index("z_benign.txt")


def test_build_notes_combines_release_and_commits():
    text, missing = evidence.build_notes("Release body", ["fix a", "fix b"])
    assert "Release body" in text
    assert "- fix a" in text
    assert missing is False


def test_build_notes_empty_is_missing():
    text, missing = evidence.build_notes(None, [])
    assert text == ""
    assert missing is True


class _FakeGitHub:
    def __init__(self, compare=None, notes=None, raise_compare=False):
        self._compare = compare
        self._notes = notes
        self._raise = raise_compare

    def get_compare(self, repo, old, new):
        if self._raise:
            raise GitHubError("boom")
        return self._compare

    def get_release_notes(self, repo, new):
        return self._notes


def test_gather_unresolved_repo(monkeypatch, npm_bump):
    monkeypatch.setattr(source_map, "resolve", lambda *a, **k: None)
    ev = evidence.gather(npm_bump, _FakeGitHub())
    assert ev.source_repo is None
    assert ev.notes_missing is True


def test_gather_compare_failure_degrades(monkeypatch, npm_bump):
    monkeypatch.setattr(source_map, "resolve", lambda *a, **k: "o/r")
    ev = evidence.gather(npm_bump, _FakeGitHub(raise_compare=True))
    assert ev.source_repo is None
    assert "could not fetch diff" in ev.resolution_detail


def _compare() -> CompareResult:
    return CompareResult(
        base="v1.3.0",
        head="v1.3.1",
        files=[{"filename": "index.js", "patch": "+return n", "additions": 1}],
        commit_messages=["fix padding"],
    )


def test_gather_happy_path(monkeypatch, npm_bump):
    monkeypatch.setattr(source_map, "resolve", lambda *a, **k: "stevemao/left-pad")
    monkeypatch.setattr(source_map, "check_withdrawn", lambda *a, **k: False)
    ev = evidence.gather(npm_bump, _FakeGitHub(compare=_compare(), notes="Notes"))
    assert ev.source_repo == "stevemao/left-pad"
    assert "index.js" in ev.source_diff
    assert "Notes" in ev.release_notes
    assert ev.notes_missing is False
    assert ev.yanked is False


def test_gather_marks_yanked(monkeypatch, npm_bump):
    monkeypatch.setattr(source_map, "resolve", lambda *a, **k: "stevemao/left-pad")
    monkeypatch.setattr(source_map, "check_withdrawn", lambda *a, **k: True)
    ev = evidence.gather(npm_bump, _FakeGitHub(compare=_compare(), notes="Notes"))
    assert ev.yanked is True
