"""Resolve a package to its upstream GitHub source repo (``owner/repo``).

- **github_actions**: the package *is* the repo (``actions/checkout`` →
  ``actions/checkout``); no network needed.
- **npm**: the npm registry document's ``repository.url``.
- **pypi**: the PyPI JSON ``info.project_urls`` / ``home_page``.

Pure URL/name helpers are unit-tested directly; ``resolve`` does the network and
returns ``None`` on any failure (the caller degrades to WARN — "could not
verify" is never treated as safe).
"""

from __future__ import annotations

import re

import httpx

# Anchor github.com to the start, or to a `/`, `@`, or `:` boundary, so a spoofed
# host like `evil-github.com/owner/repo` does NOT resolve to `owner/repo`.
_GITHUB_URL_RE = re.compile(
    r"(?:^|[/@:])github\.com[/:]+(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?(?:[/#?].*)?$"
)
# npm "github:owner/repo" / "owner/repo" shorthand.
_SHORTHAND_RE = re.compile(
    r"^(?:github:)?(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?$"
)

_REGISTRY_TIMEOUT = 10.0


def extract_github_repo(url: str | None) -> str | None:
    """Extract ``owner/repo`` from a repository URL or npm shorthand.

    Handles ``https://github.com/o/r``, ``git+https://...``, ``git@github.com:o/r.git``,
    ``github:o/r``, and bare ``o/r``. Returns None if no GitHub repo is found.
    """
    if not url:
        return None
    text = url.strip()
    match = _GITHUB_URL_RE.search(text)
    if match:
        return _valid_repo(match.group("owner"), match.group("repo"))
    shorthand = _SHORTHAND_RE.match(text)
    if shorthand and "." not in shorthand.group("owner"):
        return _valid_repo(shorthand.group("owner"), shorthand.group("repo"))
    return None


def _valid_repo(owner: str, repo: str) -> str | None:
    """Join ``owner/repo``, rejecting path-traversal segments before it hits an API path."""
    if owner in ("..", ".") or repo in ("..", "."):
        return None
    return f"{owner}/{repo}"


def github_action_repo(package: str) -> str | None:
    """For a GitHub Actions ``uses:`` ref, the repo is its first two path segments.

    ``actions/checkout`` → ``actions/checkout``; ``actions/cache/save`` →
    ``actions/cache``. Docker/local actions (no ``owner/repo`` shape) → None.
    """
    parts = [p for p in (package or "").strip().split("/") if p]
    if len(parts) < 2 or parts[0].startswith("."):
        return None
    return f"{parts[0]}/{parts[1]}"


def _npm_doc_url(package: str) -> str:
    """npm registry URL, encoding the slash in scoped names (@scope/name)."""
    if package.startswith("@") and "/" in package:
        scope, _, name = package.partition("/")
        return f"https://registry.npmjs.org/{scope}%2F{name}"
    return f"https://registry.npmjs.org/{package}"


def _resolve_npm(package: str, client: httpx.Client) -> str | None:
    resp = client.get(_npm_doc_url(package), timeout=_REGISTRY_TIMEOUT)
    resp.raise_for_status()
    doc = resp.json()
    repository = doc.get("repository")
    if isinstance(repository, dict):
        return extract_github_repo(repository.get("url"))
    if isinstance(repository, str):
        return extract_github_repo(repository)
    return None


# Project-URL keys (lowercased) most likely to point at the source repo, in order.
_PYPI_URL_KEYS = ("source", "source code", "repository", "code", "homepage", "home")


def _resolve_pypi(package: str, client: httpx.Client) -> str | None:
    resp = client.get(
        f"https://pypi.org/pypi/{package}/json", timeout=_REGISTRY_TIMEOUT
    )
    resp.raise_for_status()
    info = resp.json().get("info", {})
    project_urls = {
        (k or "").strip().lower(): v
        for k, v in (info.get("project_urls") or {}).items()
    }
    for key in _PYPI_URL_KEYS:
        repo = extract_github_repo(project_urls.get(key))
        if repo:
            return repo
    # Fall back to scanning any project URL, then home_page.
    for value in project_urls.values():
        repo = extract_github_repo(value)
        if repo:
            return repo
    return extract_github_repo(info.get("home_page"))


def resolve(
    package: str, ecosystem: str, client: httpx.Client | None = None
) -> str | None:
    """Resolve ``package`` to ``owner/repo``, or None if it can't be determined.

    Never raises: any network/parse failure yields None so the caller degrades.
    """
    if ecosystem == "github_actions":
        return github_action_repo(package)
    if ecosystem not in ("npm", "pypi"):
        return None

    owns_client = client is None
    client = client or httpx.Client(follow_redirects=True)
    try:
        if ecosystem == "npm":
            return _resolve_npm(package, client)
        return _resolve_pypi(package, client)
    except (httpx.HTTPError, ValueError, KeyError):
        return None
    finally:
        if owns_client:
            client.close()


def _pypi_version_yanked(package: str, version: str, client: httpx.Client) -> bool:
    resp = client.get(
        f"https://pypi.org/pypi/{package}/json", timeout=_REGISTRY_TIMEOUT
    )
    resp.raise_for_status()
    files = resp.json().get("releases", {}).get(version) or []
    # Conservative: flag only when the version exists and every file is yanked.
    return bool(files) and all(f.get("yanked") for f in files)


def _npm_version_deprecated(package: str, version: str, client: httpx.Client) -> bool:
    resp = client.get(_npm_doc_url(package), timeout=_REGISTRY_TIMEOUT)
    resp.raise_for_status()
    entry = resp.json().get("versions", {}).get(version)
    return bool(entry and entry.get("deprecated"))


def check_withdrawn(
    package: str, ecosystem: str, version: str, client: httpx.Client | None = None
) -> bool:
    """True if ``version`` is yanked (PyPI) or deprecated (npm).

    Best-effort and conservative to avoid false positives: any fetch/parse
    failure returns False (provenance + diff checks remain the primary safety
    net), and github_actions — which has no registry withdrawal concept — is
    skipped.
    """
    if ecosystem not in ("npm", "pypi"):
        return False
    owns_client = client is None
    client = client or httpx.Client(follow_redirects=True)
    try:
        if ecosystem == "pypi":
            return _pypi_version_yanked(package, version, client)
        return _npm_version_deprecated(package, version, client)
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return False
    finally:
        if owns_client:
            client.close()
