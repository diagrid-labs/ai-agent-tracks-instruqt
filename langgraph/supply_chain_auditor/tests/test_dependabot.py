"""Tests for Dependabot bump parsing."""

from __future__ import annotations

import pytest
from auditor_core import dependabot


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("npm_and_yarn", "npm"),
        ("pip", "pypi"),
        ("poetry", "pypi"),
        ("github_actions", "github_actions"),
        ("Docker", "docker"),  # unknown → lowercased passthrough
        ("", ""),
    ],
)
def test_normalize_ecosystem(raw, expected):
    assert dependabot.normalize_ecosystem(raw) == expected


def test_parse_from_metadata_single():
    bumps = dependabot.parse_from_metadata("pip", "urllib3", "1.26.5", "1.26.18")
    assert len(bumps) == 1
    assert bumps[0].package == "urllib3"
    assert bumps[0].ecosystem == "pypi"
    assert bumps[0].old_version == "1.26.5"
    assert bumps[0].new_version == "1.26.18"


def test_parse_from_metadata_grouped():
    bumps = dependabot.parse_from_metadata("npm_and_yarn", "a, b ,c", "1.0.0", "2.0.0")
    assert [b.package for b in bumps] == ["a", "b", "c"]
    assert all(b.ecosystem == "npm" for b in bumps)


def test_parse_from_metadata_missing_versions_returns_empty():
    assert dependabot.parse_from_metadata("pip", "x", "", "") == []


@pytest.mark.parametrize(
    "title,pkg,old,new",
    [
        ("Bump lodash from 4.17.20 to 4.17.21", "lodash", "4.17.20", "4.17.21"),
        (
            "build(deps): bump actions/checkout from 3 to 4",
            "actions/checkout",
            "3",
            "4",
        ),
        (
            "chore(deps-dev): Bump urllib3 from 1.26.5 to 1.26.18 in /backend",
            "urllib3",
            "1.26.5",
            "1.26.18",
        ),
    ],
)
def test_parse_from_title(title, pkg, old, new):
    bump = dependabot.parse_from_title(title)
    assert bump is not None
    assert (bump.package, bump.old_version, bump.new_version) == (pkg, old, new)


def test_parse_from_title_non_match_returns_none():
    assert dependabot.parse_from_title("Update README") is None


def test_parse_bump_prefers_metadata():
    bumps = dependabot.parse_bump(
        title="Bump lodash from 1 to 2",
        ecosystem="pip",
        names="urllib3",
        previous_version="1.26.5",
        new_version="1.26.18",
    )
    assert len(bumps) == 1 and bumps[0].package == "urllib3"


def test_parse_bump_falls_back_to_title():
    bumps = dependabot.parse_bump(title="Bump lodash from 4.17.20 to 4.17.21")
    assert len(bumps) == 1 and bumps[0].package == "lodash"


def test_parse_bump_no_signal_returns_empty():
    assert dependabot.parse_bump(title="random title") == []
