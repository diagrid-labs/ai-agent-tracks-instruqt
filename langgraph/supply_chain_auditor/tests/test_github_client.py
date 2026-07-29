"""Tests for the GitHub REST client (driven by httpx MockTransport)."""

from __future__ import annotations

import httpx
import pytest
from auditor_core.github_client import GitHubClient, GitHubError, tag_candidates
from tests.conftest import mock_http_client


def test_tag_candidates():
    assert tag_candidates("1.2.3") == ["1.2.3", "v1.2.3"]
    assert tag_candidates("v1.2.3") == ["v1.2.3", "1.2.3"]


def test_get_compare_tries_tag_variants():
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        # Only the v-prefixed pair resolves.
        if "compare/v1.0.0...v1.0.1" in url:
            return httpx.Response(
                200,
                json={
                    "files": [{"filename": "a.js", "patch": "+x", "additions": 1}],
                    "commits": [{"commit": {"message": "fix: thing\n\nbody"}}],
                },
            )
        return httpx.Response(404)

    gh = GitHubClient(client=mock_http_client(handler))
    result = gh.get_compare("o/r", "1.0.0", "1.0.1")
    assert result.base == "v1.0.0" and result.head == "v1.0.1"
    assert result.files[0]["filename"] == "a.js"
    assert result.commit_messages == ["fix: thing"]


def test_get_compare_raises_when_no_tag_matches():
    gh = GitHubClient(client=mock_http_client(lambda r: httpx.Response(404)))
    with pytest.raises(GitHubError):
        gh.get_compare("o/r", "1.0.0", "1.0.1")


def test_get_release_notes_found():
    def handler(request: httpx.Request) -> httpx.Response:
        if "releases/tags/v2.0.0" in str(request.url):
            return httpx.Response(200, json={"body": "Release notes here"})
        return httpx.Response(404)

    gh = GitHubClient(client=mock_http_client(handler))
    assert gh.get_release_notes("o/r", "2.0.0") == "Release notes here"


def test_get_release_notes_missing_returns_none():
    gh = GitHubClient(client=mock_http_client(lambda r: httpx.Response(404)))
    assert gh.get_release_notes("o/r", "2.0.0") is None


def test_get_pull_request():
    def handler(request: httpx.Request) -> httpx.Response:
        if "/pulls/635" in str(request.url):
            return httpx.Response(
                200, json={"title": "Bump x from 1 to 2", "body": "b"}
            )
        return httpx.Response(404)

    gh = GitHubClient(client=mock_http_client(handler))
    pr = gh.get_pull_request("o/r", 635)
    assert pr["title"] == "Bump x from 1 to 2"
    assert pr["body"] == "b"


def test_get_pull_request_raises_on_error():
    gh = GitHubClient(client=mock_http_client(lambda r: httpx.Response(404)))
    with pytest.raises(GitHubError):
        gh.get_pull_request("o/r", 1)


def test_upsert_comment_creates_when_absent():
    calls = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json=[])  # no existing comments
        if request.method == "POST":
            calls["method"] = "POST"
            return httpx.Response(201, json={"id": 1})
        return httpx.Response(500)

    gh = GitHubClient(token="t", client=mock_http_client(handler))
    status = gh.upsert_comment("o/r", 7, "body", "<!-- marker -->")
    assert calls["method"] == "POST"
    assert "created" in status


def test_upsert_comment_updates_when_marker_present():
    calls = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json=[{"id": 99, "body": "old <!-- marker -->"}])
        if request.method == "PATCH":
            calls["method"] = "PATCH"
            assert "/comments/99" in str(request.url)
            return httpx.Response(200, json={"id": 99})
        return httpx.Response(500)

    gh = GitHubClient(token="t", client=mock_http_client(handler))
    status = gh.upsert_comment("o/r", 7, "new body", "<!-- marker -->")
    assert calls["method"] == "PATCH"
    assert "updated" in status


def test_upsert_comment_paginates_to_find_marker():
    calls = {"patched": False}
    next_link = (
        "<https://api.github.com/repos/o/r/issues/7/comments?per_page=100&page=2>; "
        'rel="next"'
    )

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if request.method == "GET" and "page=2" not in url:
            return httpx.Response(
                200, json=[{"id": 1, "body": "unrelated"}], headers={"Link": next_link}
            )
        if request.method == "GET":  # page 2 carries the marker
            return httpx.Response(200, json=[{"id": 99, "body": "old <!-- marker -->"}])
        if request.method == "PATCH":
            calls["patched"] = True
            assert "/comments/99" in url
            return httpx.Response(200, json={"id": 99})
        return httpx.Response(500)

    gh = GitHubClient(token="t", client=mock_http_client(handler))
    status = gh.upsert_comment("o/r", 7, "b", "<!-- marker -->")
    assert calls["patched"] and "updated" in status


def test_upsert_comment_list_failure_raises():
    gh = GitHubClient(client=mock_http_client(lambda r: httpx.Response(403)))
    with pytest.raises(GitHubError):
        gh.upsert_comment("o/r", 7, "b", "<!-- marker -->")


def test_upsert_comment_post_failure_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json=[])
        return httpx.Response(500)  # POST fails

    gh = GitHubClient(token="t", client=mock_http_client(handler))
    with pytest.raises(GitHubError):
        gh.upsert_comment("o/r", 7, "b", "<!-- marker -->")
