"""Tests for prompt assembly and the untrusted-content wrapping."""

from __future__ import annotations

from auditor_core import prompt
from auditor_core.models import DependencyBump, Evidence, Finding, Severity


def test_system_prompt_states_trust_boundary():
    assert "UNTRUSTED" in prompt.SYSTEM
    assert "injection_observed" in prompt.SYSTEM
    assert "floor" in prompt.SYSTEM.lower()


def test_deepagent_prompt_extends_system_with_tool_guidance():
    assert prompt.SYSTEM in prompt.SYSTEM_DEEPAGENT
    assert "scan_for_redflags" in prompt.SYSTEM_DEEPAGENT
    assert "subagent" in prompt.SYSTEM_DEEPAGENT.lower()


def test_build_task_message_wraps_untrusted_blocks_and_lists_heuristics():
    bump = DependencyBump(
        package="left-pad", ecosystem="npm", old_version="1.3.0", new_version="1.3.1"
    )
    evidence = Evidence(
        source_repo="o/r",
        release_notes="changelog text",
        source_diff="+ malicious",
    )
    heuristics = [
        Finding(
            id="SC-INSTALL-HOOK",
            title="hook",
            severity=Severity.CRITICAL,
            why_it_matters="w",
            evidence_excerpt="postinstall",
            source_layer="heuristic",
        )
    ]
    msg = prompt.build_task_message(
        bump, evidence, heuristics, changelog_nonce="cafe1234", diff_nonce="beef5678"
    )

    assert "left-pad (npm)" in msg
    assert "1.3.0 -> 1.3.1" in msg
    assert "SC-INSTALL-HOOK [CRITICAL]" in msg
    assert prompt.guardrail.GUARDRAIL_PREAMBLE in msg
    # Distinct nonces per block: a tag forged in one can't close the other.
    assert "<changelog_cafe1234>" in msg
    assert "<source_diff_beef5678>" in msg
    assert "changelog text" in msg


def test_build_task_message_handles_unresolved_and_empty_evidence():
    bump = DependencyBump(
        package="x", ecosystem="pypi", old_version="1", new_version="2"
    )
    evidence = Evidence(source_repo=None, notes_missing=True)
    msg = prompt.build_task_message(
        bump, evidence, [], changelog_nonce="0000", diff_nonce="1111"
    )
    assert "UNRESOLVED" in msg
    assert "(no release notes found)" in msg
    assert "(none — no deterministic red flags fired)" in msg
