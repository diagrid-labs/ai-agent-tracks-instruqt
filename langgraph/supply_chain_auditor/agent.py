"""Wire the audit pipeline graph into a durable Dapr Workflow runner.

The diagrid ``DaprWorkflowGraphRunner`` executes each LangGraph node as a Dapr
Workflow activity. It connects to a Dapr sidecar — locally via ``dapr run``, or
in CI directly to Diagrid Catalyst via the standard ``DAPR_GRPC_ENDPOINT`` /
``DAPR_API_TOKEN`` environment variables.
"""

from __future__ import annotations

from diagrid.agent.langgraph import DaprWorkflowGraphRunner
from graph import build_graph

RUNNER_NAME = "supply-chain-auditor-langgraph"


def build_runner() -> DaprWorkflowGraphRunner:
    """Construct the durable workflow runner for the audit pipeline."""
    return DaprWorkflowGraphRunner(
        graph=build_graph(),
        name=RUNNER_NAME,
        role="Supply chain auditor",
        goal=(
            "Verify a Dependabot dependency bump against its upstream release "
            "notes and source diff, and flag supply-chain risks."
        ),
    )
