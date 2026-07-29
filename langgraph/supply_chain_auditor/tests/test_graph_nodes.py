"""Tests for the LangGraph node functions (LLM + network fully mocked).

The durable workflow execution itself needs a live Dapr sidecar and is out of
scope for unit tests; here we exercise the node logic directly.
"""

from __future__ import annotations

import graph
import ledger
from auditor_core.models import LLMVerdict, Recommendation, RiskBand


class _FakeGitHub:
    def __init__(self, **_):
        pass

    def close(self):
        pass


def test_gather_evidence_runs_prescan(monkeypatch, npm_bump, malicious_evidence):
    monkeypatch.setattr(graph, "GitHubClient", _FakeGitHub)
    monkeypatch.setattr(
        graph.evidence_mod, "gather", lambda *a, **k: malicious_evidence
    )

    out = graph.gather_evidence({"bump": npm_bump.model_dump()})
    ids = {f["id"] for f in out["heuristics"]}
    assert "SC-INSTALL-HOOK" in ids
    assert out["floor"] == 100  # CRITICAL heuristic pins the floor
    assert out["evidence"]["source_repo"] == "evil/pkg"


def test_route_after_gather():
    assert graph.route_after_gather({"evidence": {"source_repo": "o/r"}}) == "analyze"
    assert graph.route_after_gather({"evidence": {"source_repo": None}}) == "finalize"
    assert graph.route_after_gather({}) == "finalize"


def test_analyze_enforces_floor_over_benign_llm(
    monkeypatch, npm_bump, malicious_evidence
):
    # A prompt-injected LLM says "benign" but a CRITICAL heuristic floor wins.
    class _FakeStructured:
        def invoke(self, _messages):
            return LLMVerdict(
                score=0,
                findings=[],
                rationale="looks safe to merge",
                coverage="full",
                injection_observed=False,
            )

    class _FakeLLM:
        def with_structured_output(self, _schema):
            return _FakeStructured()

    monkeypatch.setattr(graph, "build_llm", lambda: _FakeLLM())

    state = {
        "bump": npm_bump.model_dump(),
        "evidence": malicious_evidence.model_dump(),
        "heuristics": [
            {
                "id": "SC-INSTALL-HOOK",
                "title": "hook",
                "severity": "CRITICAL",
                "why_it_matters": "w",
                "source_layer": "heuristic",
            }
        ],
        "floor": 100,
    }
    out = graph.analyze(state)
    assert out["verdict"]["score"] == 100
    assert out["verdict"]["band"] == RiskBand.FAIL.value
    assert out["verdict"]["recommendation"] == Recommendation.BLOCK.value


def test_finalize_produces_heuristic_only_verdict(npm_bump):
    from auditor_core.models import Evidence

    evidence = Evidence(source_repo=None, notes_missing=True)
    state = {
        "bump": npm_bump.model_dump(),
        "evidence": evidence.model_dump(),
        "heuristics": [
            {
                "id": "SC-SOURCE-PROVENANCE",
                "title": "t",
                "severity": "HIGH",
                "why_it_matters": "w",
                "source_layer": "heuristic",
            }
        ],
        "floor": 60,
    }
    out = graph.finalize(state)
    assert out["verdict"]["band"] == RiskBand.WARN.value


def test_render_report_emits_markdown(npm_bump):
    from auditor_core.models import AuditVerdict

    verdict = AuditVerdict(
        package="left-pad",
        ecosystem="npm",
        old_version="1.3.0",
        new_version="1.3.1",
        source_repo="o/r",
        score=5,
        band=RiskBand.PASS,
        recommendation=Recommendation.AUTO_MERGE_SAFE,
        findings=[],
        rationale="ok",
        coverage="full",
        injection_observed=False,
        notes_missing=False,
        yanked=False,
        diff_truncated=False,
    )
    out = graph.render_report({"verdict": verdict.model_dump(mode="json")})
    assert "Supply Chain Audit" in out["report_md"]
    assert "LangGraph track" in out["report_md"]


def test_analyze_injection_needs_review(monkeypatch, npm_bump, clean_evidence):
    # injection_observed flows through the analyze node → NEEDS_HUMAN_REVIEW.
    class _FakeStructured:
        def invoke(self, _messages):
            return LLMVerdict(
                score=5,
                findings=[],
                rationale="odd instruction seen",
                coverage="full",
                injection_observed=True,
            )

    class _FakeLLM:
        def with_structured_output(self, _schema):
            return _FakeStructured()

    monkeypatch.setattr(graph, "build_llm", lambda: _FakeLLM())
    state = {
        "bump": npm_bump.model_dump(),
        "evidence": clean_evidence.model_dump(),
        "heuristics": [],
        "floor": 0,
    }
    out = graph.analyze(state)
    assert out["verdict"]["recommendation"] == Recommendation.NEEDS_HUMAN_REVIEW.value


def test_build_graph_compiles():
    compiled = graph.build_graph()
    assert compiled is not None


def test_analyze_records_ledger_line(monkeypatch, npm_bump, clean_evidence):
    import ledger

    class _FakeStructured:
        def invoke(self, _messages):
            return LLMVerdict(
                score=0, findings=[], rationale="ok",
                coverage="full", injection_observed=False,
            )

    class _FakeLLM:
        def with_structured_output(self, _schema):
            return _FakeStructured()

    monkeypatch.setattr(graph, "build_llm", lambda: _FakeLLM())
    graph.analyze({
        "bump": npm_bump.model_dump(),
        "evidence": clean_evidence.model_dump(),
        "heuristics": [],
        "floor": 0,
    })

    entries = ledger.read_entries()
    assert [e.stage for e in entries] == ["analyze"]
    assert "left-pad" in entries[0].detail
