"""Tests for the resume-aware runner helper (Dapr client fully faked)."""

from __future__ import annotations

import json

import pytest
from dapr.ext.workflow import WorkflowStatus

import runtime


class _FakeState:
    def __init__(self, status, serialized_output=None, failure_details=None):
        self.runtime_status = status
        self.serialized_output = serialized_output
        self.failure_details = failure_details


class _FakeClient:
    def __init__(self, state=None, completion_state=None):
        self._state = state
        self._completion_state = completion_state
        self.waited = False

    def get_workflow_state(self, instance_id):
        return self._state

    def wait_for_workflow_completion(self, instance_id, timeout_in_seconds=None):
        self.waited = True
        return self._completion_state


class _FakeRunner:
    def __init__(self, client, invoke_result=None):
        self._workflow_client = client
        self.invoke_result = invoke_result or {}
        self.invoked_with = None

    def invoke(self, input, *, thread_id, workflow_id):
        self.invoked_with = {"input": input, "thread_id": thread_id, "workflow_id": workflow_id}
        return self.invoke_result


def _output_json(output: dict) -> str:
    return json.dumps({"output": output, "channel_state": None, "steps": 3, "status": "completed", "error": None})


def test_no_existing_workflow_schedules_fresh():
    runner = _FakeRunner(_FakeClient(state=None), invoke_result={"report_md": "hi"})
    out = runtime.resume_or_invoke(runner, {"bump": {}}, "audit-x")
    assert out == {"report_md": "hi"}
    assert runner.invoked_with["workflow_id"] == "audit-x"
    assert runner.invoked_with["thread_id"] == "audit-x"


def test_running_workflow_is_polled_not_rescheduled():
    completion = _FakeState(WorkflowStatus.COMPLETED, serialized_output=_output_json({"report_md": "done"}))
    client = _FakeClient(state=_FakeState(WorkflowStatus.RUNNING), completion_state=completion)
    runner = _FakeRunner(client)
    out = runtime.resume_or_invoke(runner, {"bump": {}}, "audit-x")
    assert out == {"report_md": "done"}
    assert client.waited is True
    assert runner.invoked_with is None  # never re-scheduled


def test_completed_workflow_returns_stored_output_without_invoke():
    state = _FakeState(WorkflowStatus.COMPLETED, serialized_output=_output_json({"report_md": "cached"}))
    runner = _FakeRunner(_FakeClient(state=state))
    out = runtime.resume_or_invoke(runner, {"bump": {}}, "audit-x")
    assert out == {"report_md": "cached"}
    assert runner.invoked_with is None


def test_failed_workflow_raises():
    runner = _FakeRunner(_FakeClient(state=_FakeState(WorkflowStatus.FAILED, failure_details="boom")))
    with pytest.raises(RuntimeError):
        runtime.resume_or_invoke(runner, {"bump": {}}, "audit-x")


def test_running_workflow_poll_timeout_raises():
    client = _FakeClient(state=_FakeState(WorkflowStatus.RUNNING), completion_state=None)
    runner = _FakeRunner(client)
    with pytest.raises(RuntimeError):
        runtime.resume_or_invoke(runner, {"bump": {}}, "audit-x")
    assert client.waited is True
    assert runner.invoked_with is None  # never re-scheduled


def test_running_workflow_resumed_then_failed_raises():
    completion = _FakeState(WorkflowStatus.FAILED, failure_details="boom")
    client = _FakeClient(state=_FakeState(WorkflowStatus.RUNNING), completion_state=completion)
    runner = _FakeRunner(client)
    with pytest.raises(RuntimeError):
        runtime.resume_or_invoke(runner, {"bump": {}}, "audit-x")
    assert client.waited is True
    assert runner.invoked_with is None  # never re-scheduled
