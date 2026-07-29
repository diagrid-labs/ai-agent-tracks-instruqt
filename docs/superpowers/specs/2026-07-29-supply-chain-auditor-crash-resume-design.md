# Supply Chain Auditor (LangGraph): crash-and-resume durability demo

**Date:** 2026-07-29
**Component:** `langgraph/supply_chain_auditor`
**Status:** Approved for planning

## Problem

The deepagents and MAF tracks in this repo both ship a crash-and-resume durability
demo: run the solution, it crashes partway through, the learner comments out one
line, runs it again, and the workflow resumes from durable state **without repeating
the expensive LLM work that already completed.**

The LangGraph supply-chain auditor has the durable substrate for this (each pipeline
node runs as a checkpointed Dapr Workflow activity), and its README already *claims*
crash recovery — but nothing exercises it:

- There is no crash toggle.
- `app.py` calls `runner.invoke()`, which always schedules a **fresh** workflow under
  a random instance ID (`invoke` does not receive a `workflow_id`), so a re-run cannot
  reconnect to an in-flight instance — it starts over from `gather_evidence`.
- There is no artifact proving the expensive `analyze` (Claude) call is not repeated
  on resume.

## Goal

Demonstrate the same durability lesson as the reference tracks: run the auditor, it
crashes **after the `analyze` (Claude) node has completed and checkpointed**; the
learner comments out one line and re-runs; Dapr rehydrates the workflow from Redis,
replays `gather_evidence` + `analyze` from history (no re-fetch, no second Claude
call), and only `render_report` re-runs to completion. An append-only ledger makes
this **provable**.

Reconciles both reference patterns:

- **From MAF:** one armed-by-default toggle line in the real code; an append-only
  ledger as the proof artifact; single codebase.
- **From deepagents:** a resume-aware, one-shot CLI entry point that uses a
  deterministic workflow ID, detects an in-flight instance on restart, and polls it to
  completion rather than re-scheduling.

## Pipeline recap

```
START → gather_evidence → ┬─ analyze  ─┐→ render_report → END
                          └─ finalize ─┘
```

Each node is a checkpointed Dapr Workflow activity via the diagrid
`DaprWorkflowGraphRunner`. Only `analyze` calls the LLM. The demo audits a single
Dependabot bump with a resolvable source repo, so the `analyze` branch is taken.

## Approach

### 1. Crash toggle — one armed line in `graph.py`

A single, clearly-commented `os._exit(1)` at the **top of `render_report`** — the node
that runs *after* `analyze` has completed and checkpointed. Ships **armed**
(uncommented). No gate or counter: this is a single linear pipeline, so `render_report`
runs exactly once and the crash point is already deterministic.

```python
def render_report(state: AuditState) -> dict:
    # 💥 DURABILITY DEMO — armed by default. This crashes the process AFTER the analyze
    # (Claude) node has completed and been checkpointed to Redis. Comment this line out
    # and re-run: Dapr rehydrates the workflow, replays gather_evidence + analyze from
    # history (NO re-fetch, NO second Claude call), and only render_report re-runs.
    import os; os._exit(1)          # ← comment out for the resume run

    # ...existing render logic (record ledger line, render report)...
```

The crash line is placed **before** `render_report`'s own ledger append and render
work, so on the first run `render_report` writes nothing and, on resume, re-runs
cleanly with no duplicate ledger line.

Because the crash ships armed, a normal (non-durability) run will also crash in
`render_report`; the README notes this and tells the learner to comment the line out
for a clean run. This matches MAF's armed-by-default behavior.

### 2. Proof artifact — `ledger.py` (new top-level module)

An append-only `audit-ledger.log` written to `AUDIT_OUTPUT_DIR` (default: an
`audit-out` folder under the current working directory), mirroring MAF's
`AgentCallLedger`.

- **Line format:** `<iso-utc-timestamp>\t<stage>\t<detail>` (tab-separated).
- **API:** `record_stage(stage, detail)` (append, creating the dir), `read_entries()`,
  `count()`, with tolerant parsing that skips a torn final line left by a hard crash
  mid-append.
- **Directory resolution:** read `AUDIT_OUTPUT_DIR`; default to `./audit-out`. A single
  `output_dir()` helper, analogous to MAF's `DemoPaths.OutputDirectory()`.
- **Concurrency:** appends are serialized under a module-level lock (defensive; the
  pipeline is linear, but the lock keeps the module reusable and matches MAF).

Each of `gather_evidence`, `analyze`, `render_report` appends one line when it
genuinely executes:

| Stage | Detail example |
|---|---|
| `gather_evidence` | `dapr/dapr: fetched notes+diff` |
| `analyze` | `left-pad 1.3.0→1.3.1 verdict=block` |
| `render_report` | `left-pad` |

Because every node is a checkpointed Dapr activity, a completed stage **replays its
result from durable history and its function body is not re-executed** — so it does not
re-append on resume. The finished ledger:

```
2026-07-29T10:00:01Z   gather_evidence   dapr/dapr: fetched notes+diff
2026-07-29T10:00:04Z   analyze           left-pad 1.3.0→1.3.1 verdict=block
2026-07-29T10:02:37Z   render_report     left-pad          ← restart gap
```

**`analyze` appearing exactly once is the headline proof** that the Claude call was not
repeated on resume. The timestamp jump on the `render_report` line is the visible
restart gap (MAF's signature).

The ledger lives at the top level (not in `auditor_core/`) because `auditor_core` is
drift-checked / vendored across entry points (see `config.py`); the ledger is
langgraph-demo infrastructure and should not have to be kept in sync.

### 3. Resume-aware entry point — `runtime.py` + `app.py`

Add a small `runtime.py` with `resume_or_invoke(runner, input, workflow_id) -> dict`,
mirroring deepagents' `investigate-crash.py` resume logic. Given the runner is started,
it inspects `runner._workflow_client.get_workflow_state(workflow_id)`:

| State | Action |
|---|---|
| `None` | Schedule fresh: `runner.invoke(input, thread_id=workflow_id, workflow_id=workflow_id)` (deterministic instance ID). |
| `RUNNING` / `PENDING` | **Resume path:** poll to completion via `wait_for_workflow_completion`; do **not** re-schedule (Dapr re-dispatches the pending `render_report` into the restarted process). Parse `GraphWorkflowOutput` from the completed state. |
| `COMPLETED` | Idempotent re-run: read the stored output; no rework. |
| `FAILED` / `TERMINATED` | Raise. |

Reaching into `runner._workflow_client` (a private attribute) is acceptable: the
shipped diagrid crash demos (`investigate-crash.py`, the adapter's own
`test_crash_recovery.py`) already do exactly this.

`app.py`'s `run_audit` swaps its `runner.invoke(...)` call for
`resume_or_invoke(runner, input, workflow_id)`, where `workflow_id` is the
deterministic `audit-{repo}-{number}-{package}` value it already computes as
`thread_id`. The per-bump loop, combined-report assembly, and advisory exit-0 behavior
are unchanged. Production `app.py` stays a clean one-shot; the only demo-only artifact
in the codebase is the single commented line in `graph.py`.

### 4. Documentation

`README.md`:

- Add a **"Crash-and-Resume"** section (parallel to MAF's RUNBOOK section and the
  deepagents README): arm (default) → run → crash after `analyze` → inspect the ledger
  (`gather_evidence` + `analyze` lines present) → comment out the line → re-run →
  resume → verify. Include the reset command:
  `docker exec dapr_redis redis-cli flushall`.
- Fix the existing paragraph in the "How it works" section that says a crash after
  `gather_evidence` "resumes at `analyze` without re-fetching." It now resumes at
  `render_report`, after `analyze`, so the LLM call is not repeated.

### 5. Tests

- New `tests/test_ledger.py`: append / read / `count` / torn-line tolerance, mirroring
  MAF's `AgentCallLedgerTests`. Uses `tmp_path`; asserts stage name, detail round-trip,
  and that a malformed final line is skipped rather than raising.
- `tests/conftest.py`: add an **autouse** fixture that sets `AUDIT_OUTPUT_DIR` to
  `tmp_path` (via `monkeypatch`) so the existing node tests
  (`test_gather_evidence_*`, `test_analyze_*`, `render_report` tests) write their ledger
  lines to a temp dir instead of the repo working tree.
- The crash/resume itself remains a **manual README walkthrough** (as in both reference
  tracks) — unit tests do not spin up a Dapr sidecar.

## Files changed

| File | Change |
|---|---|
| `langgraph/supply_chain_auditor/ledger.py` | **New.** Append-only stage ledger: `record_stage`, `read_entries`, `count`, `output_dir`, tolerant parse, append lock. |
| `langgraph/supply_chain_auditor/runtime.py` | **New.** `resume_or_invoke(runner, input, workflow_id)` — schedule-fresh / resume-poll / reuse-completed / raise-on-terminal. |
| `langgraph/supply_chain_auditor/graph.py` | Add the armed `os._exit(1)` toggle at the top of `render_report`; add `ledger.record_stage(...)` to `gather_evidence`, `analyze`, `render_report`. |
| `langgraph/supply_chain_auditor/app.py` | `run_audit` calls `resume_or_invoke(...)` instead of `runner.invoke(...)`. |
| `langgraph/supply_chain_auditor/README.md` | Add the "Crash-and-Resume" section + reset command; fix the stale "resumes at analyze" wording. |
| `langgraph/supply_chain_auditor/tests/test_ledger.py` | **New.** Ledger unit tests. |
| `langgraph/supply_chain_auditor/tests/conftest.py` | Autouse fixture pointing `AUDIT_OUTPUT_DIR` at `tmp_path`. |

## Trade-off

The "one codebase" choice (over separate crash files) means a small amount of
demo-facing code in the real pipeline: one commented crash line plus one
`record_stage` call per node in `graph.py`. This is isolated and keeps the durability
lesson visible in the actual pipeline the learner is studying.

## Verification

- `uv run pytest` passes, including the new `test_ledger.py`, with the existing node
  tests unaffected (they write ledger lines to `tmp_path`).
- Manual README walkthrough (needs a Dapr sidecar + Redis):
  1. Arm (default) and run the auditor on a real Dependabot PR with a resolvable repo.
  2. Observe the process die during `render_report`, after `analyze`; the ledger holds
     the `gather_evidence` + `analyze` lines.
  3. Comment out the `os._exit(1)` line; re-run the same command.
  4. Observe the workflow resume from Redis and complete; the report is produced.
  5. Confirm the finished ledger has exactly three lines — one per stage, `analyze`
     appearing once — with a clear timestamp gap before the `render_report` line.
