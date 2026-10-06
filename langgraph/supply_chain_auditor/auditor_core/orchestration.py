"""Shared one-shot orchestration helpers used by the framework entry points.

These are framework-agnostic and identical across entry points, so they live in
:mod:`auditor_core` (drift-checked) rather than being duplicated: parse the
Dependabot bump(s) from the environment, fill in PR details, combine per-bump
reports, and post (or dry-run) the PR comment.
"""

from __future__ import annotations

import logging
import os

from . import dependabot, report
from .github_client import GitHubClient, GitHubError
from .models import DependencyBump, PRContext

logger = logging.getLogger("supply_chain_auditor")


def parse_bumps(
    pr: PRContext, env: dict[str, str] | None = None
) -> list[DependencyBump]:
    """Parse bumps from Dependabot metadata env vars, falling back to the PR title."""
    env = env if env is not None else dict(os.environ)
    return dependabot.parse_bump(
        title=pr.title,
        body=pr.body,
        ecosystem=env.get("DEP_ECOSYSTEM", ""),
        names=env.get("DEP_NAMES", ""),
        previous_version=env.get("DEP_PREV_VERSION", ""),
        new_version=env.get("DEP_NEW_VERSION", ""),
    )


def fetch_pr_details(repo: str, pr_number: int) -> dict:
    """Fetch a PR's title + body from GitHub. Returns {} on failure (never raises).

    Lets a local run derive the bump from just repo + PR number, rather than the
    Dependabot metadata the GitHub Action injects.
    """
    if not repo or pr_number <= 0:
        return {}
    gh = GitHubClient(token=os.environ.get("GITHUB_TOKEN"))
    try:
        return gh.get_pull_request(repo, pr_number)
    except GitHubError as exc:
        logger.debug("fetch_pr_details failed for %s#%s: %s", repo, pr_number, exc)
        return {}
    finally:
        gh.close()


def ensure_pr_details(pr: PRContext) -> PRContext:
    """Fill the PR title/body from GitHub when the environment didn't provide them.

    In the GitHub Action the event payload sets PR_TITLE/PR_BODY; a local run that
    passes only PR_REPO + PR_NUMBER gets them fetched here so the bump can still be
    parsed from the title.
    """
    if pr.title or not pr.repo or pr.number <= 0:
        return pr
    details = fetch_pr_details(pr.repo, pr.number)
    if not details:
        logger.warning(
            "Could not fetch PR %s#%s details from GitHub.", pr.repo, pr.number
        )
        return pr
    return pr.model_copy(
        update={"title": details.get("title", ""), "body": details.get("body", "")}
    )


def combine_reports(sections: list[str]) -> str:
    """Combine per-dependency report bodies into one comment (single marker)."""
    cleaned = []
    for section in sections:
        lines = section.splitlines()
        if lines and lines[0].strip() == report.MARKER:
            lines = lines[1:]
        cleaned.append("\n".join(lines).strip())
    if len(cleaned) == 1:
        return f"{report.MARKER}\n{cleaned[0]}"
    body = "\n\n---\n\n".join(cleaned)
    return f"{report.MARKER}\n{body}"


def error_report(exc: Exception) -> str:
    """A fail-safe comment body when the audit could not complete."""
    return (
        f"{report.MARKER}\n"
        "## 🔒 Supply Chain Audit — ⚠️ ERROR\n\n"
        "The audit could not complete, so this dependency bump was **not** "
        "verified. **Manual review required before merging.**\n\n"
        f"Failure: `{type(exc).__name__}`\n\n"
        "<sub>Automated Supply Chain Auditor · advisory</sub>"
    )


def post_report(repo: str, pr_number: int, body: str) -> str:
    """Post or update the audit comment. Dry-run unless GITHUB_TOKEN + real PR.

    This is the single gated side effect used by the entry points.
    """
    token = os.environ.get("GITHUB_TOKEN")
    if not token or pr_number <= 0:
        return (
            f"[dry-run] would post audit comment to {repo}#{pr_number} "
            f"({len(body)} chars); set GITHUB_TOKEN to post for real."
        )
    gh = GitHubClient(token=token)
    try:
        return gh.upsert_comment(repo, pr_number, body, report.MARKER)
    except GitHubError as exc:
        return f"posting comment FAILED ({exc}); nothing was sent."
    finally:
        gh.close()
