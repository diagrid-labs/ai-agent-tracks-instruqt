"""Tests for package -> source repo resolution."""

from __future__ import annotations

import httpx
import pytest
from auditor_core import source_map
from tests.conftest import mock_http_client


@pytest.mark.parametrize(
    "url,repo",
    [
        ("https://github.com/owner/repo", "owner/repo"),
        ("git+https://github.com/owner/repo.git", "owner/repo"),
        ("git://github.com/owner/repo.git", "owner/repo"),
        ("git@github.com:owner/repo.git", "owner/repo"),
        ("github:owner/repo", "owner/repo"),
        ("owner/repo", "owner/repo"),
        ("https://github.com/owner/repo/tree/main/pkg", "owner/repo"),
        ("https://gitlab.com/owner/repo", None),
        # Spoofed hosts must NOT resolve to a real github.com repo.
        ("https://evil-github.com/owner/repo", None),
        ("https://github.com.evil.com/owner/repo", None),
        ("not a url", None),
        (None, None),
    ],
)
def test_extract_github_repo(url, repo):
    assert source_map.extract_github_repo(url) == repo


@pytest.mark.parametrize(
    "package,repo",
    [
        ("actions/checkout", "actions/checkout"),
        ("actions/cache/save", "actions/cache"),
        ("single", None),
        ("./.github/actions/local", None),
    ],
)
def test_github_action_repo(package, repo):
    assert source_map.github_action_repo(package) == repo


def test_resolve_github_actions_no_network():
    assert (
        source_map.resolve("actions/checkout", "github_actions") == "actions/checkout"
    )


def test_resolve_unknown_ecosystem_is_none():
    assert source_map.resolve("x", "cargo") is None


def test_resolve_npm_reads_repository_url():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "registry.npmjs.org" in str(request.url)
        return httpx.Response(
            200,
            json={"repository": {"url": "git+https://github.com/lodash/lodash.git"}},
        )

    repo = source_map.resolve("lodash", "npm", mock_http_client(handler))
    assert repo == "lodash/lodash"


def test_resolve_npm_scoped_package_encodes_slash():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"repository": "babel/babel"})

    source_map.resolve("@babel/core", "npm", mock_http_client(handler))
    assert "%2F" in seen["url"]


def test_resolve_pypi_reads_project_urls():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "info": {
                    "project_urls": {"Source": "https://github.com/urllib3/urllib3"}
                }
            },
        )

    repo = source_map.resolve("urllib3", "pypi", mock_http_client(handler))
    assert repo == "urllib3/urllib3"


def test_resolve_pypi_falls_back_to_home_page():
    # No project_urls at all → the resolver falls back to info.home_page.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"info": {"home_page": "https://github.com/psf/requests"}},
        )

    repo = source_map.resolve("requests", "pypi", mock_http_client(handler))
    assert repo == "psf/requests"


def test_resolve_returns_none_on_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    assert source_map.resolve("x", "npm", mock_http_client(handler)) is None


def test_check_withdrawn_pypi_yanked():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"releases": {"1.2.3": [{"yanked": True}]}})

    assert source_map.check_withdrawn("p", "pypi", "1.2.3", mock_http_client(handler))


def test_check_withdrawn_pypi_not_yanked():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"releases": {"1.2.3": [{"yanked": False}]}})

    assert not source_map.check_withdrawn(
        "p", "pypi", "1.2.3", mock_http_client(handler)
    )


def test_check_withdrawn_npm_deprecated():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"versions": {"1.2.3": {"deprecated": "do not use"}}}
        )

    assert source_map.check_withdrawn("p", "npm", "1.2.3", mock_http_client(handler))


def test_check_withdrawn_unknown_ecosystem_is_false():
    assert source_map.check_withdrawn("p", "github_actions", "v1") is False


def test_check_withdrawn_error_is_false():
    handler = lambda r: httpx.Response(500)  # noqa: E731
    assert not source_map.check_withdrawn(
        "p", "pypi", "1.2.3", mock_http_client(handler)
    )
