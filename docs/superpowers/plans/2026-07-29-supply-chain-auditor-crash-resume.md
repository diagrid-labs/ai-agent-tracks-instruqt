# Supply Chain Auditor Crash-and-Resume Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a crash-and-resume durability demo to the LangGraph supply-chain auditor so it teaches the same lesson as the deepagents and MAF tracks — crash mid-pipeline, comment out one line, re-run, and Dapr resumes from durable Redis state without re-invoking the Claude `analyze` call.

**Architecture:** A new top-level append-only `ledger.py` records each genuinely-executed pipeline stage to `audit-ledger.log`; because each LangGraph node is a checkpointed Dapr Workflow activity, a completed stage replays from history and does not re-append on resume. An armed crash toggle in `graph.py`'s `render_report` (gated on the ledger count) drops the process after `analyze` checkpoints. A new `runtime.py` makes the one-shot `app.py` resume-aware by reconnecting to the deterministic workflow ID and polling an in-flight instance to completion instead of re-scheduling.

**Tech Stack:** Python 3.12, LangGraph, the `diagrid` Dapr-workflow adapter (`DaprWorkflowGraphRunner`), `dapr.ext.workflow` (`WorkflowStatus`), Pydantic models, pytest, `uv`.

## Global Constraints

- All work is under `langgraph/supply_chain_auditor/`. Paths below are relative to that directory unless stated otherwise.
- Run everything with `uv`: tests are `uv run pytest`.
- Test coverage floor is **≥80%** (the README states this; `pyproject.toml` enforces it). New modules need tests.
- `auditor_core/` is drift-checked / vendored across entry points — **do not** add the ledger or runtime helpers there. New demo infrastructure lives at the top level (`ledger.py`, `runtime.py`).
- Ledger line format is exactly `<iso-utc-timestamp>\t<stage>\t<detail>` (tab-separated), one line per executed stage.
- The crash toggle is a single line, gated on `ledger.count() >= 2`, shipped **armed** (uncommented), mirroring MAF's `ledger.CountEntries() >= 2`.
- The output directory is resolved from `AUDIT_OUTPUT_DIR`, defaulting to `./audit-out`.
- End every commit message with a trailing blank line then `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

---

### Task 1: The append-only stage ledger (`ledger.py`)

**Files:**
- Create: `langgraph/supply_chain_auditor/ledger.py`
- Test: `langgraph/supply_chain_auditor/tests/test_ledger.py`

**Interfaces:**
- Consumes: nothing (standalone module; only stdlib).
- Produces:
  - `output_dir() -> str` — returns `os.environ.get("AUDIT_OUTPUT_DIR")` or `"audit-out"`.
  - `record_stage(stage: str, detail: str) -> None` — appends one line `<iso-utc>\t<stage>\t<detail>` to `<output_dir()>/audit-ledger.log`, creating the directory; serialized under a module-level lock; tabs/newlines in `detail` are replaced with spaces.
  - `LedgerEntry` — a `dataclass` with fields `timestamp: str`, `stage: str`, `detail: str`.
  - `read_entries() -> list[LedgerEntry]` — parses the file, skipping blank/malformed lines (tolerant of a torn final line); returns `[]` if the file is absent.
  - `count() -> int` — `len(read_entries())`, read under the same lock as `record_stage`.

- [ ] **Step 1: Write the failing tests**

Create `langgraph/supply_chain_auditor/tests/test_ledger.py`:

```python
"""Tests for the append-only durability-demo stage ledger."""

from __future__ import annotations

import ledger


def test_record_and_read_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIT_OUTPUT_DIR", str(tmp_path))

    ledger.record_stage("gather_evidence", "dapr/dapr: fetched notes+diff")
    ledger.record_stage("analyze", "left-pad 1.3.0->1.3.1 verdict=block")

    entries = ledger.read_entries()
    assert [e.stage for e in entries] == ["gather_evidence", "analyze"]
    assert entries[1].detail == "left-pad 1.3.0->1.3.1 verdict=block"
    assert entries[0].timestamp  # non-empty ISO timestamp
    assert ledger.count() == 2


def test_count_is_zero_when_file_absent(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIT_OUTPUT_DIR", str(tmp_path))
    assert ledger.count() == 0
    assert ledger.read_entries() == []


def test_output_dir_defaults_to_audit_out(monkeypatch):
    monkeypatch.delenv("AUDIT_OUTPUT_DIR", raising=False)
    assert ledger.output_dir() == "audit-out"


def test_torn_final_line_is_skipped(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIT_OUTPUT_DIR", str(tmp_path))
    ledger.record_stage("analyze", "ok")
    # Simulate a hard crash mid-append leaving a partial line.
    with open(tmp_path / "audit-ledger.log", "a", encoding="utf-8") as fh:
        fh.write("2026-07-29T10:00:00Z\tgather")  # no newline, missing detail is fine
        fh.write("\n\x00 torn garbage")           # unparseable trailing line
    entries = ledger.read_entries()
    # The one well-formed line survives; garbage is skipped, no exception.
    assert any(e.stage == "analyze" for e in entries)


def test_detail_tabs_and_newlines_sanitized(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIT_OUTPUT_DIR", str(tmp_path))
    ledger.record_stage("analyze", "line1\twith\ttabs\nand newline")
    entry = ledger.read_entries()[0]
    assert "\t" not in entry.detail and "\n" not in entry.detail
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd langgraph/supply_chain_auditor && uv run pytest tests/test_ledger.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ledger'` (or import error).

- [ ] **Step 3: Write the implementation**

Create `langgraph/supply_chain_auditor/ledger.py`:

```python
"""Append-only durability-demo ledger.

Records each genuinely-executed pipeline stage as one line in ``audit-ledger.log``.
Because every LangGraph node runs as a checkpointed Dapr Workflow activity, a
completed stage replays from durable history and its body is not re-executed on
resume — so a stage recorded here appears exactly once across a crash-and-restart,
proving the expensive ``analyze`` (Claude) call is not repeated.

This is demo infrastructure, kept out of the drift-checked ``auditor_core`` package.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone

_LEDGER_FILENAME = "audit-ledger.log"
_APPEND_LOCK = threading.Lock()


@dataclass
class LedgerEntry:
    timestamp: str
    stage: str
    detail: str


def output_dir() -> str:
    """Directory the ledger (and report) are written to; overridable via env."""
    return os.environ.get("AUDIT_OUTPUT_DIR") or "audit-out"


def _ledger_path() -> str:
    return os.path.join(output_dir(), _LEDGER_FILENAME)


def _sanitize(value: str) -> str:
    return value.replace("\t", " ").replace("\r", " ").replace("\n", " ")


def record_stage(stage: str, detail: str) -> None:
    """Append one tab-separated line recording that ``stage`` executed."""
    timestamp = datetime.now(timezone.utc).isoformat()
    line = "\t".join((timestamp, _sanitize(stage), _sanitize(detail)))
    with _APPEND_LOCK:
        os.makedirs(output_dir(), exist_ok=True)
        with open(_ledger_path(), "a", encoding="utf-8") as fh:
            fh.write(line + "\n")


def _parse(line: str) -> LedgerEntry | None:
    if not line or not line.strip():
        return None
    parts = line.rstrip("\n").split("\t", 2)
    if len(parts) < 2:
        return None
    timestamp, stage = parts[0], parts[1]
    if not timestamp or not stage:
        return None
    detail = parts[2] if len(parts) > 2 else ""
    return LedgerEntry(timestamp=timestamp, stage=stage, detail=detail)


def read_entries() -> list[LedgerEntry]:
    """Parse the ledger, skipping blank/malformed lines. Empty if absent."""
    path = _ledger_path()
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", errors="replace") as fh:
        lines = fh.readlines()
    return [entry for entry in (_parse(line) for line in lines) if entry is not None]


def count() -> int:
    """Number of recorded stages; used by the durability-demo crash gate."""
    with _APPEND_LOCK:
        return len(read_entries())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd langgraph/supply_chain_auditor && uv run pytest tests/test_ledger.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add langgraph/supply_chain_auditor/ledger.py langgraph/supply_chain_auditor/tests/test_ledger.py
git commit -m "$(printf 'Add append-only stage ledger for the auditor durability demo\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 2: Keep node tests off the real filesystem (conftest fixture)

Task 3 adds `ledger.record_stage(...)` calls inside the graph nodes. The existing node
tests in `tests/test_graph_nodes.py` call those nodes directly, so without isolation they
would write `audit-ledger.log` into the repo working tree. Add an autouse fixture that
redirects the ledger to a temp dir for every test. Doing this **before** Task 3 keeps the
suite green when the node changes land.

**Files:**
- Modify: `langgraph/supply_chain_auditor/tests/conftest.py`

**Interfaces:**
- Consumes: `ledger.output_dir()` reads `AUDIT_OUTPUT_DIR` (from Task 1).
- Produces: an autouse fixture setting `AUDIT_OUTPUT_DIR` to a per-test temp dir.

- [ ] **Step 1: Add the autouse fixture**

Add to the end of `langgraph/supply_chain_auditor/tests/conftest.py`:

```python
@pytest.fixture(autouse=True)
def _isolate_audit_ledger(tmp_path, monkeypatch):
    """Redirect the durability-demo ledger to a temp dir so node tests never write
    audit-ledger.log into the repo working tree."""
    monkeypatch.setenv("AUDIT_OUTPUT_DIR", str(tmp_path / "audit-out"))
```

(`pytest` and `monkeypatch` are already available; `pytest` is imported at the top of the file.)

- [ ] **Step 2: Run the full suite to verify nothing broke**

Run: `cd langgraph/supply_chain_auditor && uv run pytest -q`
Expected: PASS (all existing tests plus Task 1's, unchanged count except the 5 new ledger tests).

- [ ] **Step 3: Commit**

```bash
git add langgraph/supply_chain_auditor/tests/conftest.py
git commit -m "$(printf 'Isolate the audit ledger to a temp dir in tests\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 3: Record stages and arm the crash in `graph.py`

Add a `ledger.record_stage(...)` call to `gather_evidence`, `analyze`, and `render_report`,
and place the armed crash gate at the top of `render_report` (before its append). The crash
gate uses `ledger.count() >= 2`, which is false in the isolated `render_report` unit test
(empty temp ledger) so `pytest` survives, and true in a real run.

**Files:**
- Modify: `langgraph/supply_chain_auditor/graph.py`
- Test: `langgraph/supply_chain_auditor/tests/test_graph_nodes.py` (add one test; existing tests must still pass)

**Interfaces:**
- Consumes: `ledger.record_stage(stage, detail)`, `ledger.count()` (from Task 1); `AUDIT_OUTPUT_DIR` isolated in tests (Task 2).
- Produces: `gather_evidence`, `analyze`, `render_report` each append one ledger line when they execute; `render_report` crashes via `os._exit(1)` when `ledger.count() >= 2`.

- [ ] **Step 1: Write a failing test asserting the analyze node records a ledger line**

Add to `langgraph/supply_chain_auditor/tests/test_graph_nodes.py` (it already imports `graph`; add `import ledger` at the top of the file alongside the other imports):

```python
def test_analyze_records_ledger_line(monkeypatch, npm_bump, clean_evidence):
    import ledger

    class _FakeStructured:
        def invoke(self, _messages):
            return LLMVerdict(
                score=0, findings=[], rationale="ok",
                coverage="full", injection_observed=False,
            )

    class _FakeLLM:
        def with_structured_output(self, _schema):
            return _FakeStructured()

    monkeypatch.setattr(graph, "build_llm", lambda: _FakeLLM())
    graph.analyze({
        "bump": npm_bump.model_dump(),
        "evidence": clean_evidence.model_dump(),
        "heuristics": [],
        "floor": 0,
    })

    entries = ledger.read_entries()
    assert [e.stage for e in entries] == ["analyze"]
    assert "left-pad" in entries[0].detail
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd langgraph/supply_chain_auditor && uv run pytest tests/test_graph_nodes.py::test_analyze_records_ledger_line -v`
Expected: FAIL — `read_entries()` returns `[]` (the node doesn't record yet), so the list comparison fails.

- [ ] **Step 3: Add the import and the three ledger calls + crash gate**

In `langgraph/supply_chain_auditor/graph.py`, add `import ledger` to the import block (top-level module, alongside `import os`).

In `gather_evidence`, record after computing `heuristics, floor` and before the `return`:

```python
    heuristics, floor = redflags.prescan(evidence)
    ledger.record_stage(
        "gather_evidence",
        f"{evidence.source_repo or 'UNRESOLVED'}: fetched notes+diff",
    )
    return {
        "evidence": evidence.model_dump(),
        "heuristics": [f.model_dump(mode="json") for f in heuristics],
        "floor": floor,
    }
```

In `analyze`, record after `reconcile.combine(...)` and before the `return`:

```python
    verdict = reconcile.combine(bump, evidence, heuristics, floor, llm_verdict)
    ledger.record_stage(
        "analyze",
        f"{bump.package} {bump.old_version}->{bump.new_version} "
        f"verdict={verdict.recommendation.value}",
    )
    return {"verdict": verdict.model_dump(mode="json")}
```

Replace the body of `render_report` with the crash gate first, then the ledger append, then the render:

```python
def render_report(state: AuditState) -> dict:
    """Render the verdict to a Markdown comment body (posting happens in app.py)."""
    from auditor_core.models import AuditVerdict

    # 💥 DURABILITY DEMO — armed by default. By the time render_report runs, both
    # gather_evidence and analyze have each recorded a ledger line (count == 2), so this
    # crashes the process AFTER the analyze (Claude) call has completed and checkpointed
    # to Redis. Comment this line out and re-run: Dapr rehydrates the workflow, replays
    # gather_evidence + analyze from history (NO re-fetch, NO second Claude call), and
    # only render_report re-runs.
    if ledger.count() >= 2: os._exit(1)     # ← comment out for the resume run

    verdict = AuditVerdict(**state["verdict"])
    ledger.record_stage("render_report", verdict.package)
    return {"report_md": report.render(verdict, track_label="LangGraph")}
```

Note: `bump.package`, `bump.old_version`, `bump.new_version`, and `verdict.recommendation` all exist on the current models (confirmed in `auditor_core/models.py` and the existing tests). `verdict.recommendation` is an enum, so use `.value`.

- [ ] **Step 4: Run the new test and the full node-test file**

Run: `cd langgraph/supply_chain_auditor && uv run pytest tests/test_graph_nodes.py -v`
Expected: PASS. In particular `test_render_report_emits_markdown` still passes because its ledger (fresh temp dir) has count 0, so the crash gate is not tripped; `test_analyze_records_ledger_line` passes; `test_gather_evidence_runs_prescan` still passes (it now also writes a ledger line to the temp dir, which it does not assert on).

- [ ] **Step 5: Run the whole suite**

Run: `cd langgraph/supply_chain_auditor && uv run pytest -q`
Expected: PASS, coverage ≥80%.

- [ ] **Step 6: Commit**

```bash
git add langgraph/supply_chain_auditor/graph.py langgraph/supply_chain_auditor/tests/test_graph_nodes.py
git commit -m "$(printf 'Record pipeline stages to the ledger and arm the durability crash\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 4: Resume-aware runner helper (`runtime.py`)

Add `resume_or_invoke`, which reconnects to a deterministic workflow instance ID: schedule
fresh if none exists, poll to completion if one is in flight (the resume path), reuse a
completed instance's stored output, or raise on a terminal-failure state. This mirrors the
shipped deepagents crash demo (`deepagents/deep-investigation/investigate-crash.py`), which
reaches into `runner._workflow_client` for the same purpose.

**Files:**
- Create: `langgraph/supply_chain_auditor/runtime.py`
- Test: `langgraph/supply_chain_auditor/tests/test_runtime.py`

**Interfaces:**
- Consumes: a started `DaprWorkflowGraphRunner`-like object exposing `.invoke(input, *, thread_id, workflow_id)` and `._workflow_client` with `.get_workflow_state(instance_id)` and `.wait_for_workflow_completion(instance_id, timeout_in_seconds)`; `dapr.ext.workflow.WorkflowStatus`; `diagrid.agent.langgraph.models.GraphWorkflowOutput`.
- Produces: `resume_or_invoke(runner, input: dict, workflow_id: str, *, timeout: float = 300.0) -> dict` — returns the graph's final output dict (the `output` field of `GraphWorkflowOutput`), or `{}` if a completed workflow had no stored output.

- [ ] **Step 1: Write the failing tests**

Create `langgraph/supply_chain_auditor/tests/test_runtime.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd langgraph/supply_chain_auditor && uv run pytest tests/test_runtime.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'runtime'`.

- [ ] **Step 3: Write the implementation**

Create `langgraph/supply_chain_auditor/runtime.py`:

```python
"""Resume-aware execution of the audit workflow under a deterministic instance ID.

``runner.invoke()`` always schedules a *new* workflow, so a re-run after a crash would
restart from ``gather_evidence``. ``resume_or_invoke`` instead reconnects to the
deterministic ``workflow_id``: it schedules fresh only when no instance exists, polls an
in-flight instance to completion (the crash-recovery path — Dapr re-dispatches the pending
node into the restarted process), reuses a completed instance's stored output, and raises
on a terminal-failure state.

Reaching into ``runner._workflow_client`` mirrors the shipped diagrid crash demo
(``deepagents/deep-investigation/investigate-crash.py``).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from dapr.ext.workflow import WorkflowStatus
from diagrid.agent.langgraph.models import GraphWorkflowOutput

logger = logging.getLogger("supply_chain_auditor")

_IN_FLIGHT = (WorkflowStatus.RUNNING, WorkflowStatus.PENDING)


def _output_from_state(state: Any) -> dict:
    raw = getattr(state, "serialized_output", None)
    if not raw:
        return {}
    data = json.loads(raw) if isinstance(raw, str) else raw
    return GraphWorkflowOutput.from_dict(data).output


def resume_or_invoke(
    runner: Any,
    input: dict,
    workflow_id: str,
    *,
    timeout: float = 300.0,
) -> dict:
    """Run (or resume) the audit workflow under ``workflow_id``; return its output dict."""
    client = runner._workflow_client
    state = client.get_workflow_state(instance_id=workflow_id)

    if state is None:
        logger.info("No existing workflow %s — scheduling fresh", workflow_id)
        return runner.invoke(input, thread_id=workflow_id, workflow_id=workflow_id)

    status = state.runtime_status
    if status == WorkflowStatus.COMPLETED:
        logger.info("Workflow %s already completed — reusing stored output", workflow_id)
        return _output_from_state(state)

    if status in _IN_FLIGHT:
        logger.info("Workflow %s in flight (%s) — resuming by polling", workflow_id, status)
        final = client.wait_for_workflow_completion(
            workflow_id, timeout_in_seconds=int(timeout)
        )
        if final is None:
            raise RuntimeError(f"workflow {workflow_id} did not complete before timeout")
        if final.runtime_status != WorkflowStatus.COMPLETED:
            raise RuntimeError(
                f"workflow {workflow_id} ended in {final.runtime_status}: "
                f"{getattr(final, 'failure_details', None)}"
            )
        return _output_from_state(final)

    raise RuntimeError(
        f"workflow {workflow_id} in terminal state {status}: "
        f"{getattr(state, 'failure_details', None)}"
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd langgraph/supply_chain_auditor && uv run pytest tests/test_runtime.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add langgraph/supply_chain_auditor/runtime.py langgraph/supply_chain_auditor/tests/test_runtime.py
git commit -m "$(printf 'Add resume-aware runner helper for durable audit re-runs\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 5: Wire `app.py` to the resume-aware helper

Swap `run_audit`'s `runner.invoke(...)` for `resume_or_invoke(...)` so re-running the auditor
for the same PR resumes the in-flight workflow instead of restarting. Behavior is otherwise
unchanged (per-bump loop, combined report, advisory exit 0).

**Files:**
- Modify: `langgraph/supply_chain_auditor/app.py`
- Modify: `langgraph/supply_chain_auditor/tests/test_app.py` (update the `_FakeRunner` — required, not optional)

**Interfaces:**
- Consumes: `runtime.resume_or_invoke(runner, input, workflow_id)` (from Task 4).
- Produces: unchanged public surface of `run_audit(pr, bumps, runner) -> tuple[str, list[dict]]`.

Note the current `tests/test_app.py` `_FakeRunner.invoke(self, input, thread_id)` has no
`_workflow_client` and does not accept a `workflow_id` kwarg. Once `run_audit` routes through
`resume_or_invoke` (which reads `runner._workflow_client` and calls `invoke(input,
thread_id=..., workflow_id=...)`), this fake must be updated. Task 4's helper is unit-tested
directly; this task keeps `run_audit`'s own tests passing while preserving their existing
assertions (per-bump invocation count, `MARKER` count, verdict count, empty-report raise).

- [ ] **Step 1: Update `run_audit` in `app.py`**

Add the import near the other top-level imports in `app.py`:

```python
from runtime import resume_or_invoke
```

In `run_audit`, replace the `runner.invoke(...)` call (leave the blank-result guard,
`sections.append`, and verdict collection exactly as they are):

```python
    for bump in bumps:
        thread_id = f"audit-{pr.repo}-{pr.number}-{bump.package}".replace("/", "-")
        result = resume_or_invoke(
            runner,
            {"pr": pr.model_dump(), "bump": bump.model_dump()},
            workflow_id=thread_id,
        )
        report_md = result.get("report_md", "") if isinstance(result, dict) else ""
```

- [ ] **Step 2: Update the `_FakeRunner` in `tests/test_app.py`**

Replace the existing `_FakeRunner` class with one that carries a fake workflow client (so
`resume_or_invoke` routes to a fresh schedule) and records the `workflow_id` it is invoked
with. The `invocations` list, its contents, and the returned `_result` are unchanged, so all
existing assertions (`len(runner.invocations) == 2`, `"/" not in runner.invocations[0]`,
`body.count(report.MARKER) == 1`, `len(verdicts) == 2`, and the empty-report `RuntimeError`)
still hold:

```python
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
```

- [ ] **Step 3: Run the app tests**

Run: `cd langgraph/supply_chain_auditor && uv run pytest tests/test_app.py -v`
Expected: PASS (both `test_run_audit_invokes_per_bump_and_combines` and
`test_run_audit_raises_on_empty_report`).

- [ ] **Step 4: Run the whole suite**

Run: `cd langgraph/supply_chain_auditor && uv run pytest -q`
Expected: PASS, coverage ≥80%.

- [ ] **Step 5: Commit**

```bash
git add langgraph/supply_chain_auditor/app.py langgraph/supply_chain_auditor/tests/test_app.py
git commit -m "$(printf 'Make app.py resume in-flight audit workflows on re-run\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 6: Document the crash-and-resume walkthrough (`README.md`)

Add a "Crash-and-Resume" section and fix the stale claim that a crash resumes "at `analyze`".
No code; documentation only. This task also carries the final full-suite verification.

**Files:**
- Modify: `langgraph/supply_chain_auditor/README.md`

**Interfaces:**
- Consumes: the crash gate + ledger + resume behavior from Tasks 1–5.
- Produces: nothing (docs).

- [ ] **Step 1: Fix the stale "How it works" wording**

In `README.md`, find the bullet under "How it works" describing `graph.py` (currently ends
"...so a crash after `gather_evidence` resumes at `analyze` without re-fetching."). Replace
that sentence with:

```
Each node runs as a durable Dapr Workflow activity, so a crash after the LLM
`analyze` node resumes at `render_report` — Dapr replays `gather_evidence` and
`analyze` from durable state, so neither the GitHub fetch nor the Claude call is
repeated. See "Crash-and-Resume" below.
```

- [ ] **Step 2: Add the Crash-and-Resume section**

Insert a new section after the "Run" section (before "Test") in `README.md`:

```markdown
## Crash-and-Resume (durability demo)

This is the durability lesson: the workflow is interrupted mid-run by a **real process
crash**, and on restart it resumes from durable Redis state — **without re-invoking the
Claude `analyze` call that already completed.** An append-only *stage ledger*
(`audit-ledger.log`) makes this provable.

### How it works

- **The crash — one line you toggle by hand.** `graph.py`'s `render_report` node ships
  with an armed crash gated on the ledger count:

  ```python
  if ledger.count() >= 2: os._exit(1)     # ← comment out for the resume run
  ```

  By the time `render_report` runs, `gather_evidence` and `analyze` have each recorded a
  ledger line (count == 2), so the process dies **after** the Claude call has completed
  and been checkpointed. There is no environment variable or marker file — *you* are the
  switch. (Because it ships armed, a normal run also crashes here; comment it out for a
  clean, non-crashing run.)
- **The stage ledger.** Each node appends one line — `<timestamp>\t<stage>\t<detail>` —
  to `audit-ledger.log`. Recording happens inside a checkpointed workflow activity, so on
  resume a completed stage replays from durable history and is **not** re-appended. The
  finished ledger holds each stage exactly once, with a visible time gap at the restart.
- **Resume is automatic.** `app.py` runs the workflow under a deterministic instance ID
  (`audit-<repo>-<pr>-<package>`). On the second run it finds the in-flight instance in
  Redis and polls it to completion instead of starting over — Dapr re-dispatches the
  pending `render_report` node into the restarted process.

The ledger and report are written to `AUDIT_OUTPUT_DIR` (default: an `audit-out` folder in
the working directory). Set it to a known path so you can find them easily.

### Run 1 — crash

The crash ships **armed**, so no edit is needed. Set the output dir and run against a real
Dependabot PR with a resolvable source repo (so the `analyze` branch is taken):

```bash
export AUDIT_OUTPUT_DIR="$PWD/audit-out"
ANTHROPIC_API_KEY=sk-ant-... PR_REPO=dapr/dapr-agents PR_NUMBER=635 DEP_ECOSYSTEM=pip \
  uv run dapr run --app-id supply-chain-auditor-langgraph --resources-path ./resources -- python app.py
```

The process dies inside `render_report`, after `analyze` completed and checkpointed.
Inspect the ledger — it holds the `gather_evidence` and `analyze` lines:

```bash
cat "$AUDIT_OUTPUT_DIR/audit-ledger.log"
```

### Run 2 — comment out and resume

Comment out the crash line in `graph.py`'s `render_report`:

```python
# if ledger.count() >= 2: os._exit(1)
```

Re-run the **same** command. Dapr rehydrates instance `audit-dapr-dapr-agents-635-<pkg>`,
replays `gather_evidence` + `analyze` from history (no re-fetch, no second Claude call), and
runs only `render_report` to completion.

### Verify — durability, proven

```bash
cat "$AUDIT_OUTPUT_DIR/audit-ledger.log"
```

Confirm:

1. **Exactly three lines — `gather_evidence`, `analyze`, `render_report`, each once.** The
   `analyze` line was written on run 1 and **not** repeated on resume: the Claude call ran
   exactly once.
2. **A clear timestamp gap** before the `render_report` line — the wall-clock cost of the
   crash + restart, inside a single logical workflow run.

### Reset for a fresh demo

Purge the workflow state **and** the ledger (so stale lines do not count toward the crash
gate):

```bash
docker exec dapr_redis redis-cli flushall
rm -f "$AUDIT_OUTPUT_DIR/audit-ledger.log"
```
```

- [ ] **Step 3: Sanity-check the doc renders and links are consistent**

Run: `cd langgraph/supply_chain_auditor && grep -n "audit-ledger.log\|AUDIT_OUTPUT_DIR\|render_report\|ledger.count" README.md`
Expected: the new references are present and consistent (the crash line text matches `graph.py`).

- [ ] **Step 4: Commit**

```bash
git add langgraph/supply_chain_auditor/README.md
git commit -m "$(printf 'Document the crash-and-resume durability demo\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

## Final Verification

- [ ] Run the full test suite: `cd langgraph/supply_chain_auditor && uv run pytest -q` — Expected: PASS, coverage ≥80%.
- [ ] Confirm no `audit-ledger.log` or `audit-out/` was committed to the repo: `git status --porcelain langgraph/supply_chain_auditor` shows a clean tree (add `audit-out/` to `.gitignore` if a stray artifact appears).
- [ ] Manual durability walkthrough (needs a Dapr sidecar + Redis running): follow the README's Run 1 → Run 2 → Verify steps and confirm the ledger ends with three lines (`analyze` appearing once) and a visible timestamp gap on the `render_report` line.

## Self-Review Notes

- **Spec coverage:** Task 1 → `ledger.py`; Task 2 → conftest isolation; Task 3 → crash toggle + stage recording in `graph.py`; Task 4 → `runtime.py` resume helper; Task 5 → `app.py` wiring; Task 6 → README section + stale-wording fix. All "Files changed" rows in the spec are covered.
- **Crash-gate test safety:** the `render_report` unit test runs with an empty temp ledger (count 0), so `if ledger.count() >= 2` is false and `os._exit` never fires under pytest — verified by keeping `test_render_report_emits_markdown` in Task 3's expected-pass list.
- **Type/name consistency:** `ledger.record_stage`, `ledger.count`, `ledger.read_entries`, `ledger.output_dir`, and `LedgerEntry.{timestamp,stage,detail}` are used identically across Tasks 1, 3, and 4/6; `resume_or_invoke(runner, input, workflow_id, *, timeout=300.0)` is defined in Task 4 and called with the same signature in Task 5.
```