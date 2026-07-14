"""Crash-demo: durable version with a deliberate crash inside get_comments
(tools_crash.py) to simulate an infrastructure failure mid-investigation.

The workflow ID is derived from the issue number (investigation-<issue>), so
there is NO local state file — Dapr is the single source of truth.

First run: the workflow starts, get_issue completes and checkpoints, then
get_comments calls os._exit(1) — the process dies hard. Dapr has already
persisted the workflow state under investigation-<issue>.

Second run (after commenting out the os._exit(1) line in tools_crash.py):
the script derives the same workflow ID, asks Dapr for its state, finds it
still running, and polls it to completion. Dapr resumes from its last
checkpoint — get_issue is NOT re-run. The workflow finishes and the report
is written.

Usage:
    # Run 1 — will crash mid-way:
    dapr run --app-id deepagent --resources-path ./resources -- python investigate-crash.py --issue <issue-number>

    # Comment out os._exit(1) in tools_crash.py, then:
    # Run 2 — resumes and completes:
    dapr run --app-id deepagent --resources-path ./resources -- python investigate-crash.py --issue <issue-number>

    # Reset between full demos (purges all Dapr/Redis state):
    docker exec dapr_redis redis-cli flushall
"""
import asyncio
import json
import argparse

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

    # Deterministic instance ID: run 2 finds the same Dapr workflow with no
    # local state file. Dapr is the single source of truth.
    workflow_id = f"investigation-{issue_number}"

    try:
        runner.start()
        log("Agent runtime started")
        # Give the runtime a moment to reconnect to the sidecar and re-dispatch
        # any in-flight instance's pending work into this process.
        await asyncio.sleep(1)

        assert runner._workflow_client is not None, "workflow client not initialized"
        state = runner._workflow_client.get_workflow_state(instance_id=workflow_id)

        log(f"\n{'=' * 50}")
        if state is None:
            log(f"No existing workflow for {workflow_id} — starting fresh")
        else:
            log(f"Found existing workflow {workflow_id}: {state.runtime_status}")
        log(f"{'=' * 50}\n")

        if state is None:
            # Fresh run: schedule the workflow under the deterministic ID and
            # stream its progress events.
            async for event in runner.run_async(
                input={
                    "messages": [{
                        "role": "user",
                        "content": f"Investigate issue #{issue_number} and write the report.",
                    }],
                },
                thread_id=workflow_id,
                workflow_id=workflow_id,
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
        elif state.runtime_status == WorkflowStatus.COMPLETED:
            # Already finished (e.g. a re-run of a solved issue): rewrite the
            # report from Dapr's stored output instead of re-investigating.
            log("Workflow already completed — writing report from stored output")
            write_report_from_state(state, issue_number)
        elif state.runtime_status in (WorkflowStatus.FAILED, WorkflowStatus.TERMINATED):
            log(f"Workflow in terminal state {state.runtime_status}: {state.failure_details}")
        else:
            # Still in flight (RUNNING / PENDING) — this is the crash-recovery
            # path. start() already told Dapr to resume the pending work into
            # this process; just poll the same instance to completion.
            log(f"Resuming existing workflow by polling: {workflow_id}")
            await poll_for_completion(runner, workflow_id, issue_number)

    finally:
        runner.shutdown()
        log("Workflow runtime stopped")


async def poll_for_completion(runner: DaprWorkflowDeepAgentRunner, workflow_id: str, issue_number: str):
    assert runner._workflow_client is not None, "workflow client not initialized"
    client = runner._workflow_client

    try:
        await asyncio.to_thread(client.wait_for_workflow_start, workflow_id, timeout_in_seconds=60)
        log("Workflow is running — waiting for it to finish...")

        wf_state = await asyncio.to_thread(
            client.wait_for_workflow_completion, workflow_id, timeout_in_seconds=300
        )
    except TimeoutError:
        log("Timed out waiting for the workflow to finish — check the Dapr sidecar/state store.")
        return

    if wf_state is None:
        log("Workflow state not found in store!")
    elif wf_state.runtime_status == WorkflowStatus.COMPLETED:
        write_report_from_state(wf_state, issue_number)
    elif wf_state.runtime_status == WorkflowStatus.FAILED:
        log(f"Workflow FAILED: {wf_state.failure_details}")
    else:
        log(f"Workflow ended in state: {wf_state.runtime_status}")


def write_report_from_state(wf_state, issue_number: str):
    from diagrid.agent.langgraph.models import GraphWorkflowOutput

    raw = wf_state.serialized_output
    if raw:
        d = json.loads(raw) if isinstance(raw, str) else raw
        output = GraphWorkflowOutput.from_dict(d)
        write_report(issue_number, output.output)
    else:
        log("WARNING: workflow completed but output was empty")


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
