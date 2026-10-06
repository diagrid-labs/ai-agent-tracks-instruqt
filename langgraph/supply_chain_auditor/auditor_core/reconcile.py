"""Reconcile deterministic heuristics with the LLM verdict.

This is the security crux. The rule: **the LLM may raise risk, never lower it
below the heuristic floor.** A prompt-injected diff that talks the model into a
low score still can't escape a deterministic CRITICAL heuristic, because:

* ``final_score = max(llm.score, floor)`` — the floor wins,
* heuristic findings are force-unioned in (the LLM can't delete them),
* band and recommendation are recomputed in code from the final score.
"""

from __future__ import annotations

from .models import (
    AuditVerdict,
    DependencyBump,
    Evidence,
    Finding,
    LLMVerdict,
    Recommendation,
    RiskBand,
    Severity,
    severity_rank,
)

# Score band thresholds.
_WARN_MIN = 25
_FAIL_MIN = 70


def clamp_score(score: int) -> int:
    """Clamp an arbitrary integer into the valid 0-100 range."""
    return max(0, min(100, score))


def band_from_score(score: int) -> RiskBand:
    """Map a 0-100 score to a band: PASS < 25 <= WARN < 70 <= FAIL."""
    if score >= _FAIL_MIN:
        return RiskBand.FAIL
    if score >= _WARN_MIN:
        return RiskBand.WARN
    return RiskBand.PASS


def _has_critical(findings: list[Finding]) -> bool:
    return any(f.severity is Severity.CRITICAL for f in findings)


def recommend(
    band: RiskBand,
    *,
    coverage_complete: bool,
    has_critical: bool,
    injection_observed: bool,
) -> Recommendation:
    """Derive the actionable recommendation.

    BLOCK only on FAIL or a deterministic CRITICAL (the high-precision layer).
    AUTO_MERGE_SAFE only when PASS *and* coverage is complete *and* nothing fired.
    Everything else needs a human.
    """
    if band is RiskBand.FAIL or has_critical:
        return Recommendation.BLOCK
    if band is RiskBand.WARN or not coverage_complete or injection_observed:
        return Recommendation.NEEDS_HUMAN_REVIEW
    return Recommendation.AUTO_MERGE_SAFE


def _merge_findings(heuristic: list[Finding], llm: list[Finding]) -> list[Finding]:
    """Union heuristic + LLM findings, deduped by (id, file_path), heuristic wins.

    Heuristic findings are added first and are never displaced, so the LLM
    cannot remove or override them.
    """
    merged: list[Finding] = []
    seen: set[tuple[str, str | None]] = set()
    for finding in [*heuristic, *llm]:
        key = (finding.id, finding.file_path)
        if key in seen:
            continue
        seen.add(key)
        merged.append(finding)
    merged.sort(
        key=lambda f: (severity_rank(f.severity), f.source_layer != "heuristic")
    )
    return merged


def combine(
    bump: DependencyBump,
    evidence: Evidence,
    heuristic_findings: list[Finding],
    floor: int,
    llm_verdict: LLMVerdict,
) -> AuditVerdict:
    """Produce the authoritative verdict from heuristics + the LLM output."""
    final_score = clamp_score(max(llm_verdict.score, floor))
    findings = _merge_findings(heuristic_findings, llm_verdict.findings)
    band = band_from_score(final_score)
    coverage_complete = (
        evidence.source_repo is not None
        and not evidence.diff_truncated
        and not evidence.notes_missing
    )
    recommendation = recommend(
        band,
        coverage_complete=coverage_complete,
        has_critical=_has_critical(heuristic_findings),
        injection_observed=llm_verdict.injection_observed,
    )
    return AuditVerdict(
        package=bump.package,
        ecosystem=bump.ecosystem,
        old_version=bump.old_version,
        new_version=bump.new_version,
        source_repo=evidence.source_repo,
        score=final_score,
        band=band,
        recommendation=recommendation,
        findings=findings,
        rationale=llm_verdict.rationale,
        coverage=llm_verdict.coverage,
        injection_observed=llm_verdict.injection_observed,
        notes_missing=evidence.notes_missing,
        yanked=evidence.yanked,
        diff_truncated=evidence.diff_truncated,
    )


def heuristic_only_verdict(
    bump: DependencyBump,
    evidence: Evidence,
    heuristic_findings: list[Finding],
    floor: int,
    *,
    rationale: str,
) -> AuditVerdict:
    """Build a verdict without an LLM (used when analysis is skipped/unavailable).

    Never returns PASS-with-AUTO_MERGE when evidence is incomplete: the floor and
    coverage checks still apply.
    """
    return combine(
        bump,
        evidence,
        heuristic_findings,
        floor,
        LLMVerdict(
            score=floor,
            findings=[],
            rationale=rationale,
            coverage="Heuristic-only analysis; the LLM did not review this bump.",
            injection_observed=False,
        ),
    )
