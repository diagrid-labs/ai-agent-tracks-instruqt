"""Thin GitHub REST client for the auditor.

Read paths: the upstream ``compare`` diff and the release notes for a version
bump. Write path: upsert a PR comment (idempotent via a marker). All requests go
through an injectable ``httpx.Client`` so tests can drive it with a
``MockTransport``. Methods raise :class:`GitHubError` on failure; the evidence
and tool layers catch it and degrade gracefully.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx

_API = "https://api.github.com"
_TIMEOUT = 20.0


class GitHubError(Exception):
    """Raised when a GitHub API call fails (network, HTTP error, or no tag match)."""


@dataclass(frozen=True)
class CompareResult:
    """Result of a ``compare`` call: changed files + commit subjects."""

    base: str
    head: str
    files: list[dict] = field(default_factory=list)
    commit_messages: list[str] = field(default_factory=list)


def tag_candidates(version: str) -> list[str]:
    """Plausible tag spellings for a version, most specific first.

    Handles the common ``v1.2.3`` vs ``1.2.3`` variance.
    """
    version = version.strip()
    bare = version[1:] if version.startswith("v") else version
    seen: list[str] = []
    for candidate in (version, f"v{bare}", bare):
        if candidate and candidate not in seen:
            seen.append(candidate)
    return seen


class GitHubClient:
    """Minimal GitHub API client."""

    def __init__(
        self,
        token: str | None = None,
        *,
        base_url: str = _API,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._owns_client = client is None
        self._client = client or httpx.Client(follow_redirects=True)

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def _get(self, path: str) -> httpx.Response:
        try:
            return self._client.get(
                f"{self._base_url}{path}", headers=self._headers(), timeout=_TIMEOUT
            )
        except httpx.HTTPError as exc:  # network-level failure
            raise GitHubError(f"GET {path} failed: {exc}") from exc

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    # --- reads --------------------------------------------------------------

    def get_compare(self, repo: str, old: str, head: str) -> CompareResult:
        """Compare two versions, trying tag spellings until one resolves.

        Raises GitHubError if no candidate base...head pair exists.
        """
        last_status = None
        for base_tag in tag_candidates(old):
            for head_tag in tag_candidates(head):
                resp = self._get(f"/repos/{repo}/compare/{base_tag}...{head_tag}")
                if resp.status_code == 200:
                    data = resp.json()
                    commits = [
                        (c.get("commit", {}).get("message") or "").splitlines()[0]
                        for c in data.get("commits", [])
                    ]
                    return CompareResult(
                        base=base_tag,
                        head=head_tag,
                        files=data.get("files", []) or [],
                        commit_messages=[m for m in commits if m],
                    )
                last_status = resp.status_code
        raise GitHubError(
            f"no comparable tags for {repo} {old}...{head} (last status {last_status})"
        )

    def get_release_notes(self, repo: str, new: str) -> str | None:
        """Release body for the new version's tag, or None if no release exists."""
        for tag in tag_candidates(new):
            resp = self._get(f"/repos/{repo}/releases/tags/{tag}")
            if resp.status_code == 200:
                body = (resp.json().get("body") or "").strip()
                return body or None
        return None

    def get_pull_request(self, repo: str, number: int) -> dict:
        """Fetch a PR's title and body. Raises GitHubError on failure.

        Lets a local run derive the bump from just repo + PR number, instead of
        relying on the Dependabot metadata the GitHub Action injects.
        """
        resp = self._get(f"/repos/{repo}/pulls/{number}")
        if resp.status_code != 200:
            raise GitHubError(
                f"could not fetch PR {repo}#{number} (status {resp.status_code})"
            )
        data = resp.json()
        return {"title": data.get("title") or "", "body": data.get("body") or ""}

    # --- write --------------------------------------------------------------

    def _find_marked_comment(
        self, repo: str, pr_number: int, marker: str
    ) -> int | None:
        """Find the auditor's existing comment id, paginating all comment pages.

        A busy PR can have >100 comments; without following the ``Link`` header
        the marker (and thus idempotency) would be missed and a duplicate posted.
        """
        url: str | None = (
            f"{self._base_url}/repos/{repo}/issues/{pr_number}/comments?per_page=100"
        )
        while url:
            try:
                resp = self._client.get(url, headers=self._headers(), timeout=_TIMEOUT)
            except httpx.HTTPError as exc:
                raise GitHubError(f"listing comments failed: {exc}") from exc
            if resp.status_code != 200:
                raise GitHubError(
                    f"listing comments failed (status {resp.status_code})"
                )
            for comment in resp.json():
                if marker in (comment.get("body") or ""):
                    return comment["id"]
            url = resp.links.get("next", {}).get("url")
        return None

    def upsert_comment(self, repo: str, pr_number: int, body: str, marker: str) -> str:
        """Create or update the auditor's PR comment, keyed by ``marker``.

        Returns a short status string. Raises GitHubError on failure.
        """
        existing_id = self._find_marked_comment(repo, pr_number, marker)
        try:
            if existing_id is not None:
                resp = self._client.patch(
                    f"{self._base_url}/repos/{repo}/issues/comments/{existing_id}",
                    headers=self._headers(),
                    json={"body": body},
                    timeout=_TIMEOUT,
                )
                action = "updated"
            else:
                resp = self._client.post(
                    f"{self._base_url}/repos/{repo}/issues/{pr_number}/comments",
                    headers=self._headers(),
                    json={"body": body},
                    timeout=_TIMEOUT,
                )
                action = "created"
        except httpx.HTTPError as exc:
            raise GitHubError(f"posting comment failed: {exc}") from exc
        if resp.status_code >= 300:
            raise GitHubError(f"posting comment failed (status {resp.status_code})")
        return f"comment {action} on {repo}#{pr_number}"
