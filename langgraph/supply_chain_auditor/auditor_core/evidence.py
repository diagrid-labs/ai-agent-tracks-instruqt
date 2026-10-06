"""Gather the evidence for one dependency bump.

Resolves the source repo, fetches the release notes and the upstream compare
diff, and renders a risk-prioritized, explicitly-truncated diff that fits the
model's context budget. Risky files (manifests, CI workflows, anything matching
a red-flag token) are emitted first and in full; benign/large files are
summarized. If the diff can't be obtained at all, the repo is reported as
unresolved so the audit degrades to WARN rather than silently passing.
"""

from __future__ import annotations

import re

import httpx

from . import dependabot, source_map
from .github_client import CompareResult, GitHubClient, GitHubError
from .models import DependencyBump, Evidence
from .redflags import classify_file

# Default diff budget in bytes; the analyze step wraps this in the prompt.
DEFAULT_MAX_DIFF_BYTES = 60_000
# Release-note budget — a GitHub release body can be ~125K chars of
# attacker-controlled text; cap it so it can't crowd out the diff or flood context.
MAX_NOTES_BYTES = 20_000
# Cap the number of commit subjects included alongside the release body.
MAX_COMMIT_MESSAGES = 50

# Quick "this file looks risky" pre-filter to bump it to the front of the diff.
_RISK_TOKEN_RE = re.compile(
    r"postinstall|preinstall|\"prepare\"|eval\(|atob\(|child_process|os\.system|"
    r"subprocess|https?://\d|\.npmrc|id_rsa|fromCharCode",
    re.IGNORECASE,
)

# Inclusion priority by file class (lower = included first).
_CLASS_PRIORITY = {
    "workflow": 0,
    "manifest": 1,
    "source": 2,
    "lockfile": 3,
    "test": 4,
    "doc": 5,
}


def _file_priority(file: dict) -> int:
    filename = file.get("filename", "")
    base = _CLASS_PRIORITY.get(classify_file(filename), 2)
    if _RISK_TOKEN_RE.search(file.get("patch") or ""):
        base -= 10  # risky files jump to the front, ahead of everything benign
    return base


def render_and_truncate(
    files: list[dict], max_bytes: int = DEFAULT_MAX_DIFF_BYTES
) -> tuple[str, bool]:
    """Render changed files as a unified-diff string, risk-first, with visible truncation.

    Returns ``(diff_text, truncated)``. Truncation is always explicit
    (``[... omitted ...]`` markers) and never silently drops content.
    """
    ranked = sorted(files, key=_file_priority)
    parts: list[str] = []
    used = 0
    truncated = False
    for file in ranked:
        filename = file.get("filename", "")
        header = f"diff --git a/{filename} b/{filename}\n"
        patch = file.get("patch")
        if patch:
            block = f"{header}{patch}\n"
        else:
            block = f"{header}Binary files a/{filename} and b/{filename} differ\n"
        if used + len(block) <= max_bytes:
            parts.append(block)
            used += len(block)
            continue
        truncated = True
        summary = (
            f"{header}[... {file.get('additions', 0)} additions / "
            f"{file.get('deletions', 0)} deletions omitted by risk-prioritized "
            "truncation ...]\n"
        )
        if used + len(summary) <= max_bytes:
            parts.append(summary)
            used += len(summary)
    return "".join(parts), truncated


def build_notes(
    release_body: str | None, commit_messages: list[str]
) -> tuple[str, bool]:
    """Combine release notes + commit subjects into one text; flag if both empty."""
    sections: list[str] = []
    if release_body:
        sections.append(release_body)
    if commit_messages:
        rendered = "\n".join(f"- {m}" for m in commit_messages[:MAX_COMMIT_MESSAGES])
        omitted = len(commit_messages) - MAX_COMMIT_MESSAGES
        if omitted > 0:
            rendered += f"\n- [... {omitted} more commits omitted ...]"
        sections.append(f"Commit subjects:\n{rendered}")
    text = "\n\n".join(sections).strip()
    if len(text) > MAX_NOTES_BYTES:
        text = text[:MAX_NOTES_BYTES] + "\n[... release notes truncated ...]"
    return text, not text


def _unresolved(detail: str) -> Evidence:
    return Evidence(
        source_repo=None,
        notes_missing=True,
        resolution_detail=detail,
    )


def gather(
    bump: DependencyBump,
    gh: GitHubClient,
    http_client: httpx.Client | None = None,
    *,
    max_diff_bytes: int = DEFAULT_MAX_DIFF_BYTES,
) -> Evidence:
    """Resolve the repo and fetch notes + diff for ``bump``.

    Never raises: any failure degrades to an unresolved Evidence (which forces a
    HIGH provenance finding downstream).
    """
    if bump.ecosystem not in dependabot.SUPPORTED_ECOSYSTEMS:
        return _unresolved(
            f"ecosystem '{bump.ecosystem}' is not supported by the auditor"
        )
    repo = source_map.resolve(bump.package, bump.ecosystem, http_client)
    if not repo:
        return _unresolved(
            f"no source repo resolved for {bump.package} ({bump.ecosystem})"
        )

    try:
        compare: CompareResult = gh.get_compare(
            repo, bump.old_version, bump.new_version
        )
    except GitHubError as exc:
        return _unresolved(f"resolved {repo} but could not fetch diff: {exc}")

    diff_text, truncated = render_and_truncate(compare.files, max_diff_bytes)

    try:
        release_body = gh.get_release_notes(repo, bump.new_version)
    except GitHubError:
        release_body = None
    notes_text, notes_missing = build_notes(release_body, compare.commit_messages)
    yanked = source_map.check_withdrawn(
        bump.package, bump.ecosystem, bump.new_version, http_client
    )

    return Evidence(
        source_repo=repo,
        release_notes=notes_text,
        source_diff=diff_text,
        diff_truncated=truncated,
        notes_missing=notes_missing,
        yanked=yanked,
        resolution_detail=f"compared {compare.base}...{compare.head} in {repo}",
    )
