"""The Supply Chain Auditor as an explicit LangGraph pipeline.

A *deterministic, staged* graph: you author the node order, and only the
``analyze`` node calls the LLM. Each node becomes a durable Dapr Workflow
activity (via the diagrid adapter), so a crash after ``gather_evidence`` resumes
at ``analyze`` without re-fetching — crash recovery on a real task.

    START → gather_evidence → (analyze | finalize) → render_report → END

``gather_evidence`` and ``finalize``/``analyze`` run the deterministic red-flag
prescan + reconcile, so the LLM can never lower the verdict below the heuristic
floor (see :mod:`auditor_core.reconcile`).
"""

from __future__ import annotations

import os
from typing import TypedDict

import ledger
from auditor_core import config, prompt, reconcile, redflags, report
from auditor_core import evidence as evidence_mod
from auditor_core.github_client import GitHubClient
from auditor_core.models import DependencyBump, Evidence, Finding, LLMVerdict
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph


class AuditState(TypedDict, total=False):
    """Channels threaded through the audit pipeline (all JSON-serializable)."""

    pr: dict
    bump: dict
    evidence: dict
    heuristics: list[dict]
    floor: int
    verdict: dict
    report_md: str


def build_llm() -> ChatAnthropic:
    """Build the Claude chat model (model id overridable via LLM_MODEL)."""
    return ChatAnthropic(
        model=os.environ.get("LLM_MODEL", config.DEFAULT_LLM_MODEL),
        max_tokens=int(os.environ.get("LLM_MAX_TOKENS", config.DEFAULT_MAX_TOKENS)),
    )


def _parse_state(
    state: AuditState,
) -> tuple[DependencyBump, Evidence, list[Finding], int]:
    """Rebuild the typed models from the (JSON-serialized) channel state.

    Uses ``.get`` with safe defaults so a partial/recovered state degrades rather
    than raising a KeyError mid-node.
    """
    bump = DependencyBump(**state["bump"])
    evidence = Evidence(**(state.get("evidence") or {"source_repo": None}))
    heuristics = [Finding(**f) for f in state.get("heuristics", [])]
    return bump, evidence, heuristics, state.get("floor", 0)


def gather_evidence(state: AuditState) -> dict:
    """Resolve the repo, fetch notes + diff, and run the deterministic prescan."""
    bump = DependencyBump(**state["bump"])
    gh = GitHubClient(token=os.environ.get("GITHUB_TOKEN"))
    try:
        evidence = evidence_mod.gather(bump, gh)
    finally:
        gh.close()
    heuristics, floor = redflags.prescan(evidence)
    ledger.record_stage(
        "gather_evidence",
        f"{evidence.source_repo or 'UNRESOLVED'}: fetched notes+diff",
    )
    return {
        "evidence": evidence.model_dump(),
        "heuristics": [f.model_dump(mode="json") for f in heuristics],
        "floor": floor,
    }


def route_after_gather(state: AuditState) -> str:
    """Skip the LLM when there's no source diff to reason about."""
    evidence = state.get("evidence") or {}
    return "analyze" if evidence.get("source_repo") else "finalize"


def analyze(state: AuditState) -> dict:
    """Grounded LLM judgement → reconciled verdict (heuristic floor enforced)."""
    bump, evidence, heuristics, floor = _parse_state(state)

    task = prompt.build_task_message(bump, evidence, heuristics)
    llm = build_llm().with_structured_output(LLMVerdict)
    llm_verdict: LLMVerdict = llm.invoke(
        [SystemMessage(content=prompt.SYSTEM), HumanMessage(content=task)]
    )

    verdict = reconcile.combine(bump, evidence, heuristics, floor, llm_verdict)
    ledger.record_stage(
        "analyze",
        f"{bump.package} {bump.old_version}->{bump.new_version} "
        f"verdict={verdict.recommendation.value}",
    )
    return {"verdict": verdict.model_dump(mode="json")}


def finalize(state: AuditState) -> dict:
    """No-LLM path: heuristic-only verdict (never PASSes on incomplete coverage)."""
    bump, evidence, heuristics, floor = _parse_state(state)
    verdict = reconcile.heuristic_only_verdict(
        bump,
        evidence,
        heuristics,
        floor,
        rationale="Source repository could not be resolved; analyzed metadata only.",
    )
    return {"verdict": verdict.model_dump(mode="json")}


def render_report(state: AuditState) -> dict:
    """Render the verdict to a Markdown comment body (posting happens in app.py)."""
    from auditor_core.models import AuditVerdict

    # 💥 DURABILITY DEMO — armed by default. By the time render_report runs, both
    # gather_evidence and analyze have each recorded a ledger line (count == 2), so this
    # crashes the process AFTER the analyze (Claude) call has completed and checkpointed
    # to Redis. Comment this line out and re-run: Dapr rehydrates the workflow, replays
    # gather_evidence + analyze from history (NO re-fetch, NO second Claude call), and
    # only render_report re-runs.
    if ledger.count() >= 2: os._exit(1)     # ← comment out for the resume run

    verdict = AuditVerdict(**state["verdict"])
    ledger.record_stage("render_report", verdict.package)
    return {"report_md": report.render(verdict, track_label="LangGraph")}


def build_graph():
    """Compile the audit pipeline graph."""
    graph = StateGraph(AuditState)
    graph.add_node("gather_evidence", gather_evidence)
    graph.add_node("analyze", analyze)
    graph.add_node("finalize", finalize)
    graph.add_node("render_report", render_report)

    graph.add_edge(START, "gather_evidence")
    graph.add_conditional_edges(
        "gather_evidence",
        route_after_gather,
        {"analyze": "analyze", "finalize": "finalize"},
    )
    graph.add_edge("analyze", "render_report")
    graph.add_edge("finalize", "render_report")
    graph.add_edge("render_report", END)
    return graph.compile()
