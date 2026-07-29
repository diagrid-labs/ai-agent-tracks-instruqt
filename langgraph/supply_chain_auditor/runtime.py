"""Resume-aware execution of the audit workflow under a deterministic instance ID.

``runner.invoke()`` always schedules a *new* workflow, so a re-run after a crash would
restart from ``gather_evidence``. ``resume_or_invoke`` instead reconnects to the
deterministic ``workflow_id``: it schedules fresh only when no instance exists, polls an
in-flight instance to completion (the crash-recovery path — Dapr re-dispatches the pending
node into the restarted process), reuses a completed instance's stored output, and raises
on a terminal-failure state.

Reaching into ``runner._workflow_client`` mirrors the shipped diagrid crash demo
(``deepagents/deep-investigation/investigate-crash.py``).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from dapr.ext.workflow import WorkflowStatus
from diagrid.agent.langgraph.models import GraphWorkflowOutput

logger = logging.getLogger("supply_chain_auditor")

_IN_FLIGHT = (WorkflowStatus.RUNNING, WorkflowStatus.PENDING)


def _output_from_state(state: Any) -> dict:
    raw = getattr(state, "serialized_output", None)
    if not raw:
        return {}
    data = json.loads(raw) if isinstance(raw, str) else raw
    return GraphWorkflowOutput.from_dict(data).output


def resume_or_invoke(
    runner: Any,
    input: dict,
    workflow_id: str,
    *,
    timeout: float = 300.0,
) -> dict:
    """Run (or resume) the audit workflow under ``workflow_id``; return its output dict."""
    client = runner._workflow_client
    state = client.get_workflow_state(instance_id=workflow_id)

    if state is None:
        logger.info("No existing workflow %s — scheduling fresh", workflow_id)
        return runner.invoke(input, thread_id=workflow_id, workflow_id=workflow_id)

    status = state.runtime_status
    if status == WorkflowStatus.COMPLETED:
        logger.info("Workflow %s already completed — reusing stored output", workflow_id)
        return _output_from_state(state)

    if status in _IN_FLIGHT:
        logger.info("Workflow %s in flight (%s) — resuming by polling", workflow_id, status)
        final = client.wait_for_workflow_completion(
            workflow_id, timeout_in_seconds=int(timeout)
        )
        if final is None:
            raise RuntimeError(f"workflow {workflow_id} did not complete before timeout")
        if final.runtime_status != WorkflowStatus.COMPLETED:
            raise RuntimeError(
                f"workflow {workflow_id} ended in {final.runtime_status}: "
                f"{getattr(final, 'failure_details', None)}"
            )
        return _output_from_state(final)

    raise RuntimeError(
        f"workflow {workflow_id} in terminal state {status}: "
        f"{getattr(state, 'failure_details', None)}"
    )
