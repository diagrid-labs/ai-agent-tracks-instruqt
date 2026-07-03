# Copyright 2026 The Dapr Authors
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tool functions the agent calls. All reads come from the local snapshot
in github_data.py — no live GitHub access at runtime."""
from langchain_core.tools import tool

import github_data as gh


def _format_record(record: dict) -> str:
    kind = "pull request" if record["type"] == "pr" else "issue"
    lines = [
        f"#{record['number']} [{kind}] {record['title']}",
        f"State: {record['state']}",
        f"Labels: {', '.join(record.get('labels', [])) or 'none'}",
        f"Author: {record.get('user') or 'unknown'}",
        f"URL: {record['html_url']}",
        "",
        "Body:",
        record.get("body") or "(no body)",
    ]
    if record["type"] == "pr":
        lines.append("")
        lines.append(f"Additions/Deletions: +{record.get('additions', 0)}/-{record.get('deletions', 0)}")
        lines.append(f"Files changed: {record.get('changed_files', 0)}")
        if record.get("linked_issue_numbers"):
            lines.append(f"Linked issues: {', '.join('#' + str(n) for n in record['linked_issue_numbers'])}")
        for f in record.get("files", []) or []:
            lines.append(f"\n--- {f['filename']} ({f['status']}, +{f['additions']}/-{f['deletions']}) ---")
            if f.get("patch"):
                lines.append(f["patch"])
            elif f.get("patch_truncated"):
                lines.append("(patch omitted: too large)")
    return "\n".join(lines)


@tool
def get_issue(number: int) -> str:
    """Get the title, state, labels, body, and (for PRs) changed files of a
    GitHub issue or pull request by number."""
    record = gh.get_issue_or_pr(number)
    if record is None:
        return f"No data found for #{number} in the local snapshot."
    return _format_record(record)


@tool
def list_linked_prs(issue_number: int) -> str:
    """List pull requests linked to the given issue number."""
    record = gh.get_issue_or_pr(issue_number)
    if record is None:
        return f"No data found for #{issue_number}."
    numbers = record.get("linked_pr_numbers", [])
    if not numbers:
        return f"No linked PRs found for #{issue_number}."
    lines = []
    for n in numbers:
        pr = gh.get_issue_or_pr(n)
        if pr is None:
            lines.append(f"#{n}: (not in local snapshot)")
            continue
        lines.append(f"#{n}: {pr['title']} (state={pr['state']})")
    return "\n".join(lines)


@tool
def get_comments(number: int) -> str:
    """Get all comments on a given issue or pull request number."""
    record = gh.get_issue_or_pr(number)
    if record is None:
        return f"No data found for #{number} in the local snapshot."
    comments = record.get("comments", [])
    if not comments:
        return f"No comments found on #{number}."
    out = []
    for c in comments:
        author = c.get("user") or "unknown"
        out.append(f"--- {author} ({c['created_at']}) ---\n{c['body']}")
    return "\n\n".join(out)


@tool
def search_related_issues(query: str) -> str:
    """Search the local snapshot's issues and PRs by keyword (matches title
    and body) to find work related to the investigation. Use terms from the
    seed issue, e.g. 'actor invocation' or 'data corruption'."""
    terms = [t.lower() for t in query.split() if t]
    if not terms:
        return "Provide at least one search term."
    matches = []
    for record in gh.all_records():
        haystack = f"{record['title']} {record.get('body') or ''}".lower()
        if all(t in haystack for t in terms):
            kind = "PR" if record["type"] == "pr" else "issue"
            matches.append(f"#{record['number']} [{kind}] {record['title']} (state={record['state']})")
    if not matches:
        return f"No issues or PRs matched: {query}"
    return "\n".join(matches[:15])


TOOLS = [get_issue, list_linked_prs, get_comments, search_related_issues]
