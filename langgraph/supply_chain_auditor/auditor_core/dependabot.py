"""Parse the dependency bump(s) from a Dependabot PR.

Two sources, in order of reliability:

1. ``dependabot/fetch-metadata`` action outputs (ecosystem + names + versions),
   which the GitHub Action passes through as env vars. This is the primary path.
2. A regex fallback over the PR title (``Bump <pkg> from <old> to <new>``) for
   local dev or when metadata is unavailable.
"""

from __future__ import annotations

import re

from .models import DependencyBump

# Dependabot titles look like:
#   "Bump lodash from 4.17.20 to 4.17.21"
#   "build(deps): bump actions/checkout from 3 to 4"
#   "chore(deps-dev): Bump urllib3 from 1.26.5 to 1.26.18 in /backend"
_TITLE_RE = re.compile(
    r"[Bb]ump\s+(?P<pkg>\S+)\s+from\s+(?P<old>\S+)\s+to\s+(?P<new>\S+)"
)

# Normalize fetch-metadata ``package-ecosystem`` values to our internal set.
_ECOSYSTEM_ALIASES = {
    "npm_and_yarn": "npm",
    "npm": "npm",
    "yarn": "npm",
    "pnpm": "npm",
    "pip": "pypi",
    "uv": "pypi",
    "poetry": "pypi",
    "pipenv": "pypi",
    "pypi": "pypi",
    "github_actions": "github_actions",
    "github-actions": "github_actions",
}

SUPPORTED_ECOSYSTEMS = ("npm", "pypi", "github_actions")


def normalize_ecosystem(raw: str) -> str:
    """Map a fetch-metadata ecosystem string to our internal name.

    Unknown ecosystems pass through lowercased so callers can decide how to
    degrade (we never silently claim support we don't have).
    """
    key = (raw or "").strip().lower()
    return _ECOSYSTEM_ALIASES.get(key, key)


def parse_from_metadata(
    ecosystem: str,
    names: str,
    previous_version: str,
    new_version: str,
) -> list[DependencyBump]:
    """Build bumps from fetch-metadata outputs.

    ``names`` is a comma-separated list (grouped updates list several). v1
    shares the single previous/new version across grouped names — a documented
    simplification.
    """
    eco = normalize_ecosystem(ecosystem)
    old = (previous_version or "").strip()
    new = (new_version or "").strip()
    bumps: list[DependencyBump] = []
    for raw_name in (names or "").split(","):
        name = raw_name.strip()
        if not name or not old or not new:
            continue
        bumps.append(
            DependencyBump(
                package=name, ecosystem=eco, old_version=old, new_version=new
            )
        )
    return bumps


def parse_from_title(title: str, ecosystem: str = "") -> DependencyBump | None:
    """Parse a single bump from a Dependabot PR title, or None if it doesn't match."""
    match = _TITLE_RE.search(title or "")
    if not match:
        return None
    return DependencyBump(
        package=match.group("pkg"),
        ecosystem=normalize_ecosystem(ecosystem),
        old_version=match.group("old"),
        new_version=match.group("new"),
    )


def parse_bump(
    title: str = "",
    body: str = "",
    *,
    ecosystem: str = "",
    names: str = "",
    previous_version: str = "",
    new_version: str = "",
) -> list[DependencyBump]:
    """Resolve dependency bumps, preferring fetch-metadata over the title regex."""
    bumps = parse_from_metadata(ecosystem, names, previous_version, new_version)
    if bumps:
        return bumps
    single = parse_from_title(title, ecosystem)
    return [single] if single else []
