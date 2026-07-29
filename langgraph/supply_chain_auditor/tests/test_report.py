"""Tests for Markdown report rendering."""

from __future__ import annotations

from auditor_core import report
from auditor_core.models import (
    AuditVerdict,
    Finding,
    Recommendation,
    RiskBand,
    Severity,
)


def _verdict(**overrides) -> AuditVerdict:
    base = dict(
        package="left-pad",
        ecosystem="npm",
        old_version="1.3.0",
        new_version="1.3.1",
        source_repo="stevemao/left-pad",
        score=5,
        band=RiskBand.PASS,
        recommendation=Recommendation.AUTO_MERGE_SAFE,
        findings=[],
        rationale="Notes match the diff.",
        coverage="source diff resolved",
        injection_observed=False,
        notes_missing=False,
        yanked=False,
        diff_truncated=False,
    )
    base.update(overrides)
    return AuditVerdict(**base)


def test_render_includes_marker_and_package():
    out = report.render(_verdict())
    assert report.MARKER in out
    assert "left-pad" in out
    assert "1.3.0 → 1.3.1" in out


def test_render_pass_badge_and_no_findings():
    out = report.render(_verdict())
    assert "PASS" in out
    assert "None — no red flags detected." in out


def test_render_fail_lists_findings_sorted_by_severity():
    findings = [
        Finding(id="LOW1", title="low", severity=Severity.LOW, why_it_matters="w"),
        Finding(
            id="SC-INSTALL-HOOK",
            title="hook",
            severity=Severity.CRITICAL,
            why_it_matters="w",
            source_layer="heuristic",
        ),
    ]
    out = report.render(
        _verdict(
            score=100,
            band=RiskBand.FAIL,
            recommendation=Recommendation.BLOCK,
            findings=findings,
        )
    )
    assert "FAIL" in out
    assert "block" in out
    # CRITICAL must be listed before LOW.
    assert out.index("SC-INSTALL-HOOK") < out.index("LOW1")


def test_render_flags_truncation_and_missing_notes():
    out = report.render(
        _verdict(notes_missing=True, diff_truncated=True, band=RiskBand.WARN)
    )
    assert "missing" in out
    assert "truncated" in out


def test_render_includes_track_label():
    out = report.render(_verdict(), track_label="LangGraph")
    assert "LangGraph track" in out
