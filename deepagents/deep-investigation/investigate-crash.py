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

"""Crash-demo: durable version with a deliberate crash inside get_comments
(tools_crash.py) to simulate an infrastructure failure mid-investigation.

First run: the workflow starts, get_issue completes and checkpoints, then
get_comments calls os._exit(1) — process dies hard. The workflow_id is
saved to crash_state.json before the crash.

Second run (after commenting out the os._exit(1) line in tools_crash.py):
the script detects crash_state.json, skips starting a new workflow, and
polls the existing one. Dapr resumes from its last checkpoint — get_issue
is NOT re-run. The workflow continues, finishes, and the report is written.

Usage:
    # Run 1 — will crash mid-way:
    dapr run --app-id deepagent --resources-path ./resources -- python investigate-crash.py <issue-number>

    # Comment out os._exit(1) in tools_crash.py, then:
    # Run 2 — resumes and completes:
    dapr run --app-id deepagent --resources-path ./resources -- python investigate-crash.py <issue-number>

    # Reset between full demos:
    rm -f crash_state.json
"""
import asyncio
import json
import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv
from deepagents import create_deep_agent

from diagrid.agent.deepagents import DaprWorkflowDeepAgentRunner
from dapr.ext.workflow import WorkflowStatus

from tools_crash import TOOLS

load_dotenv()

SYSTEM_PROMPT = """You are a senior engineer investigating a GitHub issue in the dapr/dapr repository.

You have tools to read issue/PR data from a local snapshot:
- get_issue(number): read an issue or PR's title, state, labels, body
- list_linked_prs(issue_number): find PRs linked to an issue
- get_comments(number): read all comments on an issue or PR
- search_related_issues(query): keyword-search the local snapshot for related issues/PRs

You MUST investigate the given issue number by calling tools in EXACTLY this order. Do NOT skip steps, do NOT reorder them, and call each tool exactly once:
1. Call get_issue to read the issue itself.
2. Call get_comments to read its comments.
3. Call list_linked_prs, then get_issue and get_comments on any linked pull request.
4. Call search_related_issues to find issues that show similar symptoms.
5. Write your findings to a file named investigation-<issue-number>.md with these sections:
   - Summary
   - Probable Root Cause
   - Related Work (linked PRs, related issues)
   - Suggested Next Steps

Use the write_file tool (built into your filesystem) to save the report.
"""

STATE_FILE = Path("crash_state.json")


def load_crash_state() -> dict:
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"workflow_scheduled": False, "workflow_id": None, "run_count": 0}


def save_crash_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def log(msg: str):
    print(msg, flush=True)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--issue", required=True, help="GitHub issue number to investigate")
    args = parser.parse_args()
    issue_number = args.issue

    crash_state = load_crash_state()
    crash_state["run_count"] += 1
    log(f"\n{'=' * 50}")
    log(f"RUN #{crash_state['run_count']}")
    log(f"workflow_scheduled={crash_state['workflow_scheduled']}  workflow_id={crash_state.get('workflow_id')}")
    log(f"{'=' * 50}\n")

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

        if not crash_state["workflow_scheduled"]:
            log("Starting new workflow...")
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
                    wf_id = event.get("workflow_id")
                    crash_state["workflow_scheduled"] = True
                    crash_state["workflow_id"] = wf_id
                    save_crash_state(crash_state)
                    log(f"Workflow started and saved: {wf_id}")
                elif event_type == "workflow_status_changed":
                    log(f"Status: {event.get('status')}")
                elif event_type == "workflow_completed":
                    write_report(issue_number, event.get("output", {}))
                    STATE_FILE.unlink(missing_ok=True)
                    break
                elif event_type == "workflow_failed":
                    log(f"Workflow FAILED: {event.get('error')}")
                    break
        else:
            saved_id = crash_state["workflow_id"]
            log(f"Workflow already started. Resuming by polling: {saved_id}")
            await poll_for_completion(runner, saved_id, issue_number)
            STATE_FILE.unlink(missing_ok=True)

    finally:
        runner.shutdown()
        log("Workflow runtime stopped")


async def poll_for_completion(runner: DaprWorkflowDeepAgentRunner, workflow_id: str, issue_number: str):
    from diagrid.agent.langgraph.models import GraphWorkflowOutput

    assert runner._workflow_client is not None, "workflow client not initialized"

    prev_status = None
    while True:
        await asyncio.sleep(1.0)
        wf_state = runner._workflow_client.get_workflow_state(instance_id=workflow_id)

        if wf_state is None:
            log("Workflow state not found in store!")
            break

        if wf_state.runtime_status != prev_status:
            log(f"Workflow status: {wf_state.runtime_status}")
            prev_status = wf_state.runtime_status

        if wf_state.runtime_status == WorkflowStatus.COMPLETED:
            raw = wf_state.serialized_output
            if raw:
                d = json.loads(raw) if isinstance(raw, str) else raw
                output = GraphWorkflowOutput.from_dict(d)
                write_report(issue_number, output.output)
            else:
                log("WARNING: workflow completed but output was empty")
            break
        elif wf_state.runtime_status == WorkflowStatus.FAILED:
            log(f"Workflow FAILED: {wf_state.failure_details}")
            break
        elif wf_state.runtime_status == WorkflowStatus.TERMINATED:
            log("Workflow was TERMINATED")
            break


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
