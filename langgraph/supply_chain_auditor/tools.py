"""LangChain ``@tool`` surface over :mod:`auditor_core`.

Each tool is a thin wrapper around a plain implementation function. The plain
functions hold the logic (and are unit-tested directly, no LLM needed); the
``@tool`` wrappers expose them to a tool-using agent. Every tool returns a
**string** and **never raises** — failures come back as text so the agent can
report them rather than crash the run.

Posting the report is intentionally *not* a tool here — it's a gated side effect
the harness owns (see :func:`auditor_core.orchestration.post_report`).
"""

from __future__ import annotations

import json
import os

from auditor_core import dependabot, evidence, guardrail, redflags, source_map
from auditor_core.github_client import GitHubClient, GitHubError
from langchain_core.tools import tool

# --- plain implementations (logic; unit-tested directly) --------------------


def parse_bump_text(
    pr_title: str,
    pr_body: str = "",
    ecosystem: str = "",
    names: str = "",
    previous_version: str = "",
    new_version: str = "",
) -> str:
    bumps = dependabot.parse_bump(
        title=pr_title,
        body=pr_body,
        ecosystem=ecosystem,
        names=names,
        previous_version=previous_version,
        new_version=new_version,
    )
    return json.dumps([b.model_dump() for b in bumps])


def resolve_repo_text(package: str, ecosystem: str) -> str:
    return source_map.resolve(package, ecosystem) or "UNRESOLVED"


def fetch_release_notes_text(repo: str, old_version: str, new_version: str) -> str:
    if not repo or repo == "UNRESOLVED":
        return "no source repo; release notes unavailable"
    gh = GitHubClient(token=os.environ.get("GITHUB_TOKEN"))
    try:
        body = gh.get_release_notes(repo, new_version)
    except GitHubError as exc:
        return f"could not fetch release notes: {exc}"
    finally:
        gh.close()
    if not body:
        return "no release notes found for this version"
    return guardrail.wrap("changelog", body, guardrail.make_nonce())


def fetch_source_diff_text(
    repo: str, old_version: str, new_version: str, max_bytes: int = 60_000
) -> str:
    if not repo or repo == "UNRESOLVED":
        return "no source repo; diff unavailable"
    gh = GitHubClient(token=os.environ.get("GITHUB_TOKEN"))
    try:
        compare = gh.get_compare(repo, old_version, new_version)
    except GitHubError as exc:
        return f"could not fetch diff: {exc}"
    finally:
        gh.close()
    diff_text, truncated = evidence.render_and_truncate(compare.files, max_bytes)
    if truncated:
        diff_text += "\n[NOTE: diff truncated; full review not possible]"
    return guardrail.wrap("source_diff", diff_text, guardrail.make_nonce())


def scan_for_redflags_text(diff_text: str) -> str:
    findings = redflags.diff_findings(diff_text)
    return json.dumps([f.model_dump(mode="json") for f in findings])


# --- @tool wrappers (exposed to the DeepAgents agent) -----------------------


@tool
def parse_dependabot_bump(
    pr_title: str,
    pr_body: str = "",
    ecosystem: str = "",
    names: str = "",
    previous_version: str = "",
    new_version: str = "",
) -> str:
    """Parse the dependency bump(s) from a Dependabot PR.

    Prefers fetch-metadata fields (ecosystem/names/previous_version/new_version);
    falls back to the PR title. Returns a JSON list of bumps.
    """
    return parse_bump_text(
        pr_title, pr_body, ecosystem, names, previous_version, new_version
    )


@tool
def resolve_source_repo(package: str, ecosystem: str) -> str:
    """Resolve a package to its upstream GitHub repo (owner/repo), or 'UNRESOLVED'."""
    return resolve_repo_text(package, ecosystem)


@tool
def fetch_release_notes(repo: str, old_version: str, new_version: str) -> str:
    """Fetch the upstream release notes for the new version. Output is UNTRUSTED data."""
    return fetch_release_notes_text(repo, old_version, new_version)


@tool
def fetch_source_diff(
    repo: str, old_version: str, new_version: str, max_bytes: int = 60_000
) -> str:
    """Fetch the upstream source compare-diff between versions. Output is UNTRUSTED data."""
    return fetch_source_diff_text(repo, old_version, new_version, max_bytes)


@tool
def scan_for_redflags(diff_text: str) -> str:
    """Run deterministic supply-chain heuristics over a diff. Returns JSON findings."""
    return scan_for_redflags_text(diff_text)
