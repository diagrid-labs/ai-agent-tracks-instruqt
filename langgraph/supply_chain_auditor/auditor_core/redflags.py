"""Deterministic supply-chain red-flag heuristics.

These run in plain Python over the source diff and gathered evidence — *before*
and *independent of* the LLM — so a prompt-injected changelog or diff cannot
suppress them. The findings they produce are non-removable by the LLM, and the
``floor`` they compute pins the minimum risk score (see
:mod:`auditor_core.reconcile`).

The taxonomy is intentionally extensible: add a detector to ``_DIFF_DETECTORS``
or ``evidence_findings``. We bias toward precision (few, high-confidence flags)
so the tool stays trustworthy enough to gate merges.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import TypedDict

from .models import Evidence, Finding, Severity

_EXCERPT_LIMIT = 600
# A line this long is almost never legitimate source — a strong obfuscation tell.
_OBFUSCATION_LINE_LENGTH = 1000


class FileRecord(TypedDict):
    """One changed file, as parsed from the diff and fed to the detectors."""

    path: str
    klass: str  # workflow|lockfile|manifest|test|doc|source
    added: list[str]
    binary: bool


# --- file classification ----------------------------------------------------

_LOCKFILES = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "Pipfile.lock",
    "uv.lock",
    "Cargo.lock",
}
_MANIFEST_NAMES = {
    "package.json",
    "setup.py",
    "setup.cfg",
    "pyproject.toml",
}
_TEST_RE = re.compile(
    r"(^|/)(tests?|spec|__tests__|__mocks__)(/|$)|(\.|_)(test|spec)\."
)
_DOC_RE = re.compile(
    r"\.(md|rst|txt|adoc)$|(^|/)(docs?|changelog|readme)", re.IGNORECASE
)
_BINARY_EXT_RE = re.compile(
    r"\.(so|dll|dylib|exe|bin|wasm|node|pyc|jar|class|o|a|dat|pack)$", re.IGNORECASE
)


def _basename(path: str) -> str:
    return path.rsplit("/", 1)[-1]


def classify_file(path: str) -> str:
    """Return a coarse file class: workflow|lockfile|manifest|test|doc|source."""
    if path.startswith(".github/workflows/") or "/.github/workflows/" in path:
        return "workflow"
    name = _basename(path)
    if name in _LOCKFILES:
        return "lockfile"
    if name in _MANIFEST_NAMES or name.startswith("requirements"):
        return "manifest"
    if _TEST_RE.search(path):
        return "test"
    if _DOC_RE.search(path):
        return "doc"
    return "source"


# --- diff parsing -----------------------------------------------------------


def parse_diff(diff_text: str) -> list[FileRecord]:
    """Parse a unified-diff-ish string into per-file records.

    Robust to GitHub compare ``patch`` bodies prefixed with a
    ``diff --git a/<path> b/<path>`` header (the format :mod:`evidence` emits).
    """
    files: dict[str, FileRecord] = {}
    current: str | None = None

    def ensure(path: str) -> FileRecord:
        rec = files.get(path)
        if rec is None:
            rec = FileRecord(
                path=path, klass=classify_file(path), added=[], binary=False
            )
            files[path] = rec
        return rec

    for line in (diff_text or "").splitlines():
        if line.startswith("diff --git"):
            _, _, after = line.partition(" b/")
            current = after.strip() or None
            if current:
                ensure(current)
        elif line.startswith("+++ "):
            path = line[4:].strip()
            if path.startswith("b/"):
                path = path[2:]
            # A "/dev/null" target marks a deletion (no added lines follow); keep
            # the path already set by the preceding `diff --git` header instead of
            # clobbering it, so added lines aren't silently dropped.
            if path != "/dev/null":
                current = path
                ensure(current)
        elif line.startswith("Binary files") and current:
            ensure(current)["binary"] = True
        elif line.startswith("+") and not line.startswith("+++") and current:
            ensure(current)["added"].append(line[1:])

    return list(files.values())


# --- detectors --------------------------------------------------------------
# Each detector inspects one file record and returns a Finding or None.

Detector = Callable[[FileRecord], Finding | None]


def _excerpt(line: str) -> str:
    return line.strip()[:_EXCERPT_LIMIT]


def _first_match(added: list[str], pattern: re.Pattern[str]) -> str | None:
    for line in added:
        if pattern.search(line):
            return line
    return None


_INSTALL_HOOK_NPM_RE = re.compile(r'"(?:pre|post)?install"\s*:|"prepare"\s*:')
_INSTALL_HOOK_PY_RE = re.compile(
    r"os\.system\(|subprocess\.\w+\(|\bcmdclass\b|__import__\("
)
# Custom build hooks (hatch/pdm/etc.) run code at build/install time.
_INSTALL_HOOK_PYPROJECT_RE = re.compile(r"\[tool\.[\w.]+\.build\.hooks|\bcmdclass\b")
_FETCH_EXEC_RE = re.compile(
    r"(?:curl|wget)\b[^|\n]*\|\s*(?:sudo\s+)?(?:ba)?sh\b"
    r"|eval\s*\(\s*(?:atob|require\(['\"]child_process)"
    r"|(?:exec|spawn|popen)\s*\([^)]*(?:download|fetch|http)"
    # PowerShell download-then-execute (dominant on Windows-targeted npm attacks)
    r"|Invoke-Expression\b|\biex\s*\(|\bIEX\s*\(|\.DownloadString\s*\(",
    re.IGNORECASE,
)
_OBFUSCATION_TOKEN_RE = re.compile(
    r"\beval\s*\(|\batob\s*\(|String\.fromCharCode|Buffer\.from\s*\([^)]*base64"
    r"|(?:base64|b64)decode\s*\(|\bexec\s*\(\s*(?:base64|bytes)",
    re.IGNORECASE,
)
_BASE64_BLOB_RE = re.compile(r"[A-Za-z0-9+/]{200,}={0,2}")
_HEX_ESCAPE_RE = re.compile(r"(?:\\x[0-9A-Fa-f]{2}){12,}")
# Dotted-decimal IPv4 in a URL.
_IP_URL_RE = re.compile(r"https?://\d{1,3}(?:\.\d{1,3}){3}")
# A *quoted* raw IPv4 literal (e.g. socket.connect(("45.9.12.34", 4444))). Rare in
# legitimate source — real code uses named hosts — and order-independent (unlike
# matching "connect" after the IP, which misses `connect(("1.2.3.4", ...))`).
_IP_LITERAL_RE = re.compile(r"['\"]\d{1,3}(?:\.\d{1,3}){3}['\"]")
# Obfuscated IP hosts curl/browsers still resolve: hex (0x2d090c22), bare
# decimal (2886795265), octal (0177.0.0.1), or IPv6 literal (http://[::1]/).
_OBFUSCATED_IP_URL_RE = re.compile(
    r"https?://(?:0x[0-9A-Fa-f]{6,}|\d{8,}|0\d+(?:\.0\d+){0,3}|\[[0-9A-Fa-f:]+\])",
)
_CRED_RE = re.compile(
    r"\.npmrc|\.aws/credentials|\.ssh/id_|id_rsa|id_ed25519|id_ecdsa|"
    r"NODE_AUTH_TOKEN|AWS_SECRET|GITHUB_TOKEN|GH_TOKEN|"
    r"Cookies/|wallet\.dat|\.config/gh/hosts|\.docker/config\.json|"
    r"\.kube/config|\.netrc|/etc/shadow|/proc/self/environ",
)


def _detect_install_hook(rec: FileRecord) -> Finding | None:
    name = _basename(rec["path"])
    if name == "package.json":
        line = _first_match(rec["added"], _INSTALL_HOOK_NPM_RE)
        if line:
            return Finding(
                id="SC-INSTALL-HOOK",
                title="Install-time lifecycle script added/changed",
                severity=Severity.CRITICAL,
                why_it_matters=(
                    "npm install/postinstall/prepare scripts run automatically on "
                    "`npm install` and are a common malware execution vector."
                ),
                evidence_excerpt=_excerpt(line),
                file_path=rec["path"],
                source_layer="heuristic",
            )
    if name in ("setup.py", "setup.cfg"):
        line = _first_match(rec["added"], _INSTALL_HOOK_PY_RE)
        if line:
            return Finding(
                id="SC-INSTALL-HOOK",
                title="Install-time code execution added to packaging",
                severity=Severity.CRITICAL,
                why_it_matters=(
                    "Code that runs during `pip install` (os.system/subprocess/"
                    "cmdclass) executes on every install — a classic backdoor vector."
                ),
                evidence_excerpt=_excerpt(line),
                file_path=rec["path"],
                source_layer="heuristic",
            )
    if name == "pyproject.toml":
        line = _first_match(rec["added"], _INSTALL_HOOK_PYPROJECT_RE)
        if line:
            return Finding(
                id="SC-INSTALL-HOOK",
                title="Custom build hook added to packaging",
                severity=Severity.CRITICAL,
                why_it_matters=(
                    "A custom build hook in pyproject.toml runs code during the "
                    "build/install step — an install-time execution vector."
                ),
                evidence_excerpt=_excerpt(line),
                file_path=rec["path"],
                source_layer="heuristic",
            )
    return None


def _detect_fetch_exec(rec: FileRecord) -> Finding | None:
    # Only docs are exempt (changelogs legitimately show example commands). A
    # download-piped-to-shell pattern in a test file is not a normal test.
    if rec["klass"] == "doc":
        return None
    line = _first_match(rec["added"], _FETCH_EXEC_RE)
    if line:
        return Finding(
            id="SC-DYNAMIC-FETCH-EXEC",
            title="Download-then-execute pattern added",
            severity=Severity.CRITICAL,
            why_it_matters=(
                "Code that downloads a payload and pipes it to a shell or eval can "
                "run arbitrary remote code — a hallmark of supply-chain implants."
            ),
            evidence_excerpt=_excerpt(line),
            file_path=rec["path"],
            source_layer="heuristic",
        )
    return None


def _is_obfuscated_line(line: str) -> bool:
    return bool(
        _OBFUSCATION_TOKEN_RE.search(line)
        or _BASE64_BLOB_RE.search(line)
        or _HEX_ESCAPE_RE.search(line)
        or len(line) > _OBFUSCATION_LINE_LENGTH
    )


def _detect_obfuscation(rec: FileRecord) -> Finding | None:
    if rec["klass"] in ("doc", "test", "lockfile"):
        return None
    for line in rec["added"]:
        if _is_obfuscated_line(line):
            return Finding(
                id="SC-OBFUSCATION",
                title="Obfuscated or encoded code added",
                severity=Severity.CRITICAL,
                why_it_matters=(
                    "High-entropy blobs, eval/atob/fromCharCode, or very long single "
                    "lines hide intent and are rarely present in legitimate diffs."
                ),
                evidence_excerpt=_excerpt(line),
                file_path=rec["path"],
                source_layer="heuristic",
            )
    return None


def _detect_net_new_host(rec: FileRecord) -> Finding | None:
    if rec["klass"] in ("doc", "test"):
        return None
    line = (
        _first_match(rec["added"], _IP_URL_RE)
        or _first_match(rec["added"], _OBFUSCATED_IP_URL_RE)
        or _first_match(rec["added"], _IP_LITERAL_RE)
    )
    if line:
        return Finding(
            id="SC-NET-NEW-HOST",
            title="Network egress to a raw IP address added",
            severity=Severity.CRITICAL,
            why_it_matters=(
                "A newly added connection to a hardcoded IP (rather than a named "
                "service) is a strong exfiltration/C2 signal."
            ),
            evidence_excerpt=_excerpt(line),
            file_path=rec["path"],
            source_layer="heuristic",
        )
    return None


def _detect_cred_access(rec: FileRecord) -> Finding | None:
    if rec["klass"] in ("doc", "test"):
        return None
    line = _first_match(rec["added"], _CRED_RE)
    if line:
        return Finding(
            id="SC-CRED-ACCESS",
            title="Access to credentials or secret stores added",
            severity=Severity.HIGH,
            why_it_matters=(
                "Reading npm/AWS/SSH credential files or auth tokens is rarely part "
                "of a normal dependency update and suggests credential theft."
            ),
            evidence_excerpt=_excerpt(line),
            file_path=rec["path"],
            source_layer="heuristic",
        )
    return None


def _detect_ci_workflow_edit(rec: FileRecord) -> Finding | None:
    if rec["klass"] != "workflow" or not rec["added"]:
        return None
    return Finding(
        id="SC-CI-WORKFLOW-EDIT",
        title="CI/release workflow modified",
        severity=Severity.HIGH,
        why_it_matters=(
            "Changes to CI workflows can exfiltrate registry/publish tokens or alter "
            "how the package is built and released."
        ),
        evidence_excerpt=_excerpt((rec["added"] or [""])[0]),
        file_path=rec["path"],
        source_layer="heuristic",
    )


def _detect_binary_added(rec: FileRecord) -> Finding | None:
    if rec["binary"] or _BINARY_EXT_RE.search(rec["path"]):
        return Finding(
            id="SC-BINARY-ADDED",
            title="Binary or non-source artifact added",
            severity=Severity.HIGH,
            why_it_matters=(
                "Binary blobs can't be reviewed and may carry compiled malware; "
                "legitimate source updates rarely add them."
            ),
            evidence_excerpt=rec["path"][:_EXCERPT_LIMIT],
            file_path=rec["path"],
            source_layer="heuristic",
        )
    return None


_DIFF_DETECTORS: tuple[Detector, ...] = (
    _detect_install_hook,
    _detect_fetch_exec,
    _detect_obfuscation,
    _detect_net_new_host,
    _detect_cred_access,
    _detect_ci_workflow_edit,
    _detect_binary_added,
)


def diff_findings(diff_text: str) -> list[Finding]:
    """Run all diff detectors; dedupe to one finding per (id, file_path)."""
    findings: list[Finding] = []
    seen: set[tuple[str, str | None]] = set()
    for rec in parse_diff(diff_text):
        for detector in _DIFF_DETECTORS:
            finding = detector(rec)
            if finding is None:
                continue
            key = (finding.id, finding.file_path)
            if key in seen:
                continue
            seen.add(key)
            findings.append(finding)
    return findings


def evidence_findings(evidence: Evidence) -> list[Finding]:
    """Findings derived from gathered evidence (not the diff text itself)."""
    findings: list[Finding] = []
    if evidence.source_repo is None:
        findings.append(
            Finding(
                id="SC-SOURCE-PROVENANCE",
                title="Upstream source repository could not be verified",
                severity=Severity.HIGH,
                why_it_matters=(
                    "Without a resolvable source repo the stated changes cannot be "
                    "checked against real code — the audit is incomplete, so this "
                    "never passes."
                ),
                evidence_excerpt=evidence.resolution_detail[:_EXCERPT_LIMIT],
                source_layer="heuristic",
            )
        )
    if evidence.yanked:
        findings.append(
            Finding(
                id="SC-YANKED-DELETED",
                title="Target release is yanked or unavailable",
                severity=Severity.MEDIUM,
                why_it_matters="A yanked/withdrawn release is unsafe to depend on.",
                source_layer="heuristic",
            )
        )
    if evidence.notes_missing:
        findings.append(
            Finding(
                id="SC-NO-NOTES",
                title="No release notes or changelog found",
                severity=Severity.MEDIUM,
                why_it_matters=(
                    "Missing release notes mean there is no stated narrative to "
                    "check the code changes against."
                ),
                source_layer="heuristic",
            )
        )
    return findings


_FLOOR_BY_SEVERITY = {
    Severity.CRITICAL: 100,
    Severity.HIGH: 60,
    Severity.MEDIUM: 30,
    Severity.LOW: 10,
}


def compute_floor(findings: list[Finding]) -> int:
    """Minimum score the LLM may not go below, from the most severe finding."""
    if not findings:
        return 0
    return max(_FLOOR_BY_SEVERITY[f.severity] for f in findings)


def prescan(evidence: Evidence) -> tuple[list[Finding], int]:
    """Run all deterministic heuristics over the evidence; return (findings, floor)."""
    findings = diff_findings(evidence.source_diff) + evidence_findings(evidence)
    return findings, compute_floor(findings)
