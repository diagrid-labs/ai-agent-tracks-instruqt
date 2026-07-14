"""Baseline: in-process DeepAgents run, in-memory scratchpad, no Dapr.

Usage: uv run python investigate.py <issue-number>
"""
import argparse
import sys

from dotenv import load_dotenv
from deepagents import create_deep_agent

from tools import TOOLS

load_dotenv()

SYSTEM_PROMPT = """You are a senior engineer investigating a GitHub issue in the dapr/dapr repository.

You have tools to read issue/PR data from a local snapshot:
- get_issue(number): read an issue or PR's title, state, labels, body
- list_linked_prs(issue_number): find PRs linked to an issue
- get_comments(number): read all comments on an issue or PR
- search_related_issues(query): keyword-search the local snapshot for related issues/PRs

Investigate the given issue number thoroughly:
1. Read the issue itself and its comments.
2. Find and read any linked pull requests, their comments, and changed files.
3. Search for related issues that show similar symptoms.
4. Write your findings to a file named investigation-<issue-number>.md with these sections:
   - Summary
   - Probable Root Cause
   - Related Work (linked PRs, related issues)
   - Suggested Next Steps

Use the write_file tool (built into your filesystem) to save the report.
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--issue", required=True, help="GitHub issue number to investigate")
    args = parser.parse_args()
    issue_number = args.issue

    agent = create_deep_agent(
        model="openai:gpt-4o-mini",
        tools=TOOLS,
        system_prompt=SYSTEM_PROMPT,
        name="issue-investigator",
    )

    result = agent.invoke({
        "messages": [{
            "role": "user",
            "content": f"Investigate issue #{issue_number} and write the report.",
        }]
    })

    for msg in result["messages"]:
        msg.pretty_print()

    files = result.get("files", {})
    report_name = f"investigation-{issue_number}.md"
    # Agent may write with or without a leading slash
    key = next((k for k in files if k.lstrip("/") == report_name), None)
    if key is not None:
        with open(report_name, "w", encoding="utf-8") as f:
            f.write(files[key]["content"])
        print(f"\nWrote {report_name}")
    else:
        print(f"\nWARNING: agent did not produce {report_name}. Files in scratchpad: {list(files)}")


if __name__ == "__main__":
    main()
