"""Tests for the heuristic+LLM reconcile — the security guarantee."""

from __future__ import annotations

import pytest
from auditor_core import reconcile
from auditor_core.models import (
    DependencyBump,
    Evidence,
    Finding,
    LLMVerdict,
    Recommendation,
    RiskBand,
    Severity,
)


@pytest.fixture
def bump() -> DependencyBump:
    return DependencyBump(
        package="p", ecosystem="npm", old_version="1.0.0", new_version="1.0.1"
    )


@pytest.fixture
def complete_evidence() -> Evidence:
    return Evidence(source_repo="o/r", release_notes="notes", source_diff="diff")


def _critical_finding() -> Finding:
    return Finding(
        id="SC-INSTALL-HOOK",
        title="hook",
        severity=Severity.CRITICAL,
        why_it_matters="w",
        source_layer="heuristic",
    )


@pytest.mark.parametrize(
    "score,band",
    [
        (0, RiskBand.PASS),
        (24, RiskBand.PASS),
        (25, RiskBand.WARN),
        (69, RiskBand.WARN),
        (70, RiskBand.FAIL),
        (100, RiskBand.FAIL),
    ],
)
def test_band_from_score(score, band):
    assert reconcile.band_from_score(score) == band


@pytest.mark.parametrize("raw,clamped", [(-5, 0), (0, 0), (50, 50), (150, 100)])
def test_clamp_score(raw, clamped):
    assert reconcile.clamp_score(raw) == clamped


def test_llm_cannot_lower_below_heuristic_floor(bump, complete_evidence):
    # Attacker-influenced LLM returns a benign score; CRITICAL heuristic floor wins.
    heuristics = [_critical_finding()]
    llm = LLMVerdict(
        score=0,
        findings=[],
        rationale="looks fine",
        coverage="full",
        injection_observed=False,
    )
    verdict = reconcile.combine(bump, complete_evidence, heuristics, 100, llm)
    assert verdict.score == 100
    assert verdict.band is RiskBand.FAIL
    assert verdict.recommendation is Recommendation.BLOCK


def test_heuristic_findings_are_non_removable(bump, complete_evidence):
    heuristics = [_critical_finding()]
    llm = LLMVerdict(
        score=0, findings=[], rationale="r", coverage="c", injection_observed=False
    )
    verdict = reconcile.combine(bump, complete_evidence, heuristics, 100, llm)
    assert any(f.id == "SC-INSTALL-HOOK" for f in verdict.findings)


def test_llm_can_raise_risk_above_floor(bump, complete_evidence):
    llm = LLMVerdict(
        score=85,
        findings=[
            Finding(
                id="SC-NARRATIVE-MISMATCH",
                title="t",
                severity=Severity.HIGH,
                why_it_matters="w",
            )
        ],
        rationale="notes don't match diff",
        coverage="full",
        injection_observed=False,
    )
    verdict = reconcile.combine(bump, complete_evidence, [], 0, llm)
    assert verdict.score == 85
    assert verdict.band is RiskBand.FAIL
    assert any(f.source_layer == "llm" for f in verdict.findings)


def test_clean_pass_is_auto_merge_safe(bump, complete_evidence):
    llm = LLMVerdict(
        score=5,
        findings=[],
        rationale="benign",
        coverage="full",
        injection_observed=False,
    )
    verdict = reconcile.combine(bump, complete_evidence, [], 0, llm)
    assert verdict.band is RiskBand.PASS
    assert verdict.recommendation is Recommendation.AUTO_MERGE_SAFE


def test_incomplete_coverage_never_auto_merges(bump):
    evidence = Evidence(source_repo=None, notes_missing=True)
    heuristics, floor = (
        [
            Finding(
                id="SC-SOURCE-PROVENANCE",
                title="t",
                severity=Severity.HIGH,
                why_it_matters="w",
                source_layer="heuristic",
            )
        ],
        60,
    )
    verdict = reconcile.heuristic_only_verdict(
        bump, evidence, heuristics, floor, rationale="no repo"
    )
    assert verdict.band is RiskBand.WARN
    assert verdict.recommendation is Recommendation.NEEDS_HUMAN_REVIEW


def test_injection_observed_forces_human_review(bump, complete_evidence):
    llm = LLMVerdict(
        score=5,
        findings=[],
        rationale="benign",
        coverage="full",
        injection_observed=True,
    )
    verdict = reconcile.combine(bump, complete_evidence, [], 0, llm)
    assert verdict.recommendation is Recommendation.NEEDS_HUMAN_REVIEW


def test_truncated_diff_prevents_auto_merge(bump):
    # PASS score but incomplete coverage (diff truncated) → never auto-merge.
    evidence = Evidence(source_repo="o/r", diff_truncated=True)
    llm = LLMVerdict(
        score=5, findings=[], rationale="ok", coverage="full", injection_observed=False
    )
    verdict = reconcile.combine(bump, evidence, [], 0, llm)
    assert verdict.band is RiskBand.PASS
    assert verdict.recommendation is Recommendation.NEEDS_HUMAN_REVIEW


def test_injection_with_critical_heuristic_still_blocks(bump, complete_evidence):
    # BLOCK (from the CRITICAL) must win over the injection→review branch.
    llm = LLMVerdict(
        score=0, findings=[], rationale="safe", coverage="full", injection_observed=True
    )
    verdict = reconcile.combine(
        bump, complete_evidence, [_critical_finding()], 100, llm
    )
    assert verdict.recommendation is Recommendation.BLOCK


def test_out_of_range_llm_score_is_clamped(bump, complete_evidence):
    over = LLMVerdict(
        score=150, findings=[], rationale="r", coverage="c", injection_observed=False
    )
    assert reconcile.combine(bump, complete_evidence, [], 0, over).score == 100
    under = LLMVerdict(
        score=-50, findings=[], rationale="r", coverage="c", injection_observed=False
    )
    assert reconcile.combine(bump, complete_evidence, [], 0, under).score == 0


def test_llm_cannot_override_heuristic_finding_with_same_id(bump, complete_evidence):
    # An LLM finding reusing a heuristic id must not displace the heuristic one.
    llm_dup = Finding(
        id="SC-INSTALL-HOOK",
        title="overridden",
        severity=Severity.LOW,
        why_it_matters="w",
        source_layer="llm",
    )
    llm = LLMVerdict(
        score=0,
        findings=[llm_dup],
        rationale="r",
        coverage="c",
        injection_observed=False,
    )
    verdict = reconcile.combine(
        bump, complete_evidence, [_critical_finding()], 100, llm
    )
    hooks = [f for f in verdict.findings if f.id == "SC-INSTALL-HOOK"]
    assert len(hooks) == 1
    assert hooks[0].source_layer == "heuristic"


def test_high_only_heuristic_is_warn_and_review(bump, complete_evidence):
    # A HIGH heuristic (floor 60) → WARN band → NEEDS_HUMAN_REVIEW (not BLOCK).
    high = Finding(
        id="SC-CI-WORKFLOW-EDIT",
        title="ci",
        severity=Severity.HIGH,
        why_it_matters="w",
        source_layer="heuristic",
    )
    llm = LLMVerdict(
        score=60, findings=[], rationale="r", coverage="c", injection_observed=False
    )
    verdict = reconcile.combine(bump, complete_evidence, [high], 60, llm)
    assert verdict.band is RiskBand.WARN
    assert verdict.recommendation is Recommendation.NEEDS_HUMAN_REVIEW
