"""Render an :class:`AuditVerdict` as a Markdown PR comment.

The comment starts with a stable HTML marker so re-runs upsert one comment
instead of spamming the PR (see ``github_client.upsert_comment``).
"""

from __future__ import annotations

from .models import AuditVerdict, Finding, RiskBand, Severity, severity_rank

MARKER = "<!-- supply-chain-auditor -->"

_BAND_BADGE = {
    RiskBand.PASS: "🟢 PASS",
    RiskBand.WARN: "🟡 WARN",
    RiskBand.FAIL: "🔴 FAIL",
}

_SEVERITY_ICON = {
    Severity.CRITICAL: "🔴",
    Severity.HIGH: "🔴",
    Severity.MEDIUM: "🟡",
    Severity.LOW: "⚪",
}


def _check(ok: bool) -> str:
    return "✅" if ok else "⚠️"


def _safe(text: str) -> str:
    """Neutralize @mentions in untrusted/LLM prose rendered into the comment.

    ``&#64;`` renders as ``@`` on GitHub but does not trigger a notification.
    """
    return text.replace("@", "&#64;")


def _safe_code(text: str) -> str:
    """Keep untrusted text inside a Markdown code span (a backtick would break out)."""
    return text.replace("`", "'")


def _render_finding(finding: Finding) -> str:
    icon = _SEVERITY_ICON[finding.severity]
    layer = "heuristic" if finding.source_layer == "heuristic" else "model"
    location = f" — `{_safe_code(finding.file_path)}`" if finding.file_path else ""
    line = (
        f"- {icon} **{finding.severity.value}** `{_safe_code(finding.id)}` "
        f"({layer}){location}: {_safe(finding.title)}. {_safe(finding.why_it_matters)}"
    )
    if finding.evidence_excerpt:
        line += (
            f"\n  - evidence: `{_safe_code(finding.evidence_excerpt.strip()[:200])}`"
        )
    return line


def render(verdict: AuditVerdict, track_label: str = "") -> str:
    """Render the full Markdown comment body for a verdict."""
    badge = _BAND_BADGE[verdict.band]

    lines = [
        MARKER,
        f"## 🔒 Supply Chain Audit — `{_safe_code(verdict.package)}` "
        f"{verdict.old_version} → {verdict.new_version}  **[{badge}]**",
        "",
        f"> **Recommendation:** `{verdict.recommendation.value}` · "
        f"**Score:** {verdict.score}/100",
        "",
        f"**Source:** {verdict.source_repo or '_unresolved_'} · "
        f"**Notes present:** {_check(not verdict.notes_missing)} · "
        f"**Injection attempt:** {_check(not verdict.injection_observed)}",
        "",
    ]

    if verdict.findings:
        ordered = sorted(verdict.findings, key=lambda f: severity_rank(f.severity))
        lines.append("### Findings")
        lines.extend(_render_finding(f) for f in ordered)
    else:
        lines.append("### Findings\n- None — no red flags detected.")
    lines.append("")

    lines.extend(
        [
            "### Evidence checked",
            f"- Release notes / changelog {_check(not verdict.notes_missing)}"
            + ("" if not verdict.notes_missing else " missing"),
            f"- Upstream source diff {_check(not verdict.diff_truncated)}"
            + (" (truncated)" if verdict.diff_truncated else ""),
            "",
            "<details><summary>Auditor rationale</summary>",
            "",
            _safe(verdict.rationale.strip()) or "_(no rationale)_",
            "",
            f"Coverage: {_safe(verdict.coverage.strip())}",
            "</details>",
            "",
        ]
    )

    footer = "Automated Supply Chain Auditor"
    if track_label:
        footer += f" · {track_label} track"
    footer += " · advisory"
    lines.append(f"<sub>{footer}</sub>")
    return "\n".join(lines)
