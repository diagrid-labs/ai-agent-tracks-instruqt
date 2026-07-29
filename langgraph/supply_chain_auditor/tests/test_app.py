"""Tests for the LangGraph app.run_audit orchestration (the durable runner is faked)."""

from __future__ import annotations

import app
import pytest
from auditor_core import report
from auditor_core.models import DependencyBump, PRContext


class _FakeClient:
    def get_workflow_state(self, instance_id):
        return None  # no existing instance → resume_or_invoke schedules fresh


class _FakeRunner:
    def __init__(self, result: dict):
        self._result = result
        self._workflow_client = _FakeClient()
        self.invocations: list[str] = []

    def invoke(self, input, *, thread_id, workflow_id):  # noqa: A002 - mirrors runner API
        self.invocations.append(workflow_id)
        return self._result


def _bump(pkg: str = "a") -> DependencyBump:
    return DependencyBump(
        package=pkg, ecosystem="npm", old_version="1", new_version="2"
    )


def test_run_audit_invokes_per_bump_and_combines():
    pr = PRContext(repo="diagridio/ai-agents", number=7)
    runner = _FakeRunner(
        {"report_md": f"{report.MARKER}\n## x", "verdict": {"band": "PASS"}}
    )
    body, verdicts = app.run_audit(pr, [_bump("a"), _bump("b")], runner)
    assert len(runner.invocations) == 2
    assert "/" not in runner.invocations[0]  # thread id is slugified
    assert body.count(report.MARKER) == 1
    assert len(verdicts) == 2


def test_run_audit_raises_on_empty_report():
    # A workflow result without report_md must fail loudly (→ fail-safe notice),
    # not silently post an empty comment.
    runner = _FakeRunner({"verdict": {"band": "WARN"}})
    with pytest.raises(RuntimeError):
        app.run_audit(PRContext(repo="o/r", number=1), [_bump()], runner)
