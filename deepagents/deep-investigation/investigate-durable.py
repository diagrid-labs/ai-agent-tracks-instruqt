"""Durable: DeepAgents wrapped in DaprWorkflowDeepAgentRunner.

Scratchpad and workflow progress are persisted to the Dapr state store
defined in resources/statestore.yaml, so the investigation survives a
process restart.

Usage:
    dapr run --app-id deepagent --resources-path ./resources -- python investigate.py <issue-number>
"""
import asyncio
import argparse
import sys

from dotenv import load_dotenv
from deepagents import create_deep_agent

from diagrid.agent.deepagents import DaprWorkflowDeepAgentRunner

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


def log(msg: str):
    print(msg, flush=True)


async def main():
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

    runner = DaprWorkflowDeepAgentRunner(
        agent=agent,
        name="issue-investigation",
        max_steps=50,
    )

    try:
        runner.start()
        log("Agent runtime started")
        await asyncio.sleep(1)

        async for event in runner.run_async(
            input={
                "messages": [{
                    "role": "user",
                    "content": f"Investigate issue #{issue_number} and write the report.",
                }],
            },
            thread_id=f"investigation-{issue_number}",
        ):
            event_type = event["type"]
            log(f"Event: {event_type}")
            if event_type == "workflow_started":
                log(f"Workflow started: {event.get('workflow_id')}")
            elif event_type == "workflow_status_changed":
                log(f"Status: {event.get('status')}")
            elif event_type == "workflow_completed":
                write_report(issue_number, event.get("output", {}))
                break
            elif event_type == "workflow_failed":
                log(f"Workflow FAILED: {event.get('error')}")
                break
    finally:
        runner.shutdown()
        log("Workflow runtime stopped")


def write_report(issue_number: str, output: dict):
    files = output.get("files", {})
    report_name = f"investigation-{issue_number}.md"
    key = next((k for k in files if k.lstrip("/") == report_name), None)
    if key is not None:
        with open(report_name, "w", encoding="utf-8") as f:
            f.write(files[key]["content"])
        log(f"Wrote {report_name}")
    else:
        log(f"WARNING: agent did not produce {report_name}. Files in scratchpad: {list(files)}")


if __name__ == "__main__":
    asyncio.run(main())
