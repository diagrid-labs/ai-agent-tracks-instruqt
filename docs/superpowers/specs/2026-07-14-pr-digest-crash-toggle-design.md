# PrDigest durability demo: replace the crash gate with a one-line toggle

**Date:** 2026-07-14
**Component:** `MAF/PrDigest`
**Status:** Approved for planning

## Problem

The crash-and-resume durability demo currently relies on a self-disabling crash
apparatus baked into production-looking code:

- `CRASH_AFTER_AGENT_CALLS` environment variable (wired in `AppHost.cs`, read in the activity)
- a `CrashGate` class that counts calls and drops an `agent-calls.crash-marker` file so the
  restarted process does not crash again
- a static `_executedCalls` counter (`Interlocked`) inside `RecordAgentCallActivity`

This machinery reads like real logic and pollutes `RecordAgentCallActivity`, whose only
genuine job is to append each executed agent call to the durability ledger. For an Instruqt
learning track, a crash gate embedded in the app is a poor example.

## Goal

Demonstrate the same durability lesson — run the solution, it crashes partway through the
fan-out on the first run and resumes to completion on the second — with a mechanism that is
obviously a demo toggle rather than production logic. The learner may comment/uncomment a
single line of code between the two runs.

## Approach

The learner replaces the self-disabling marker file: **uncomment one line → run → crash;
comment it out → run → resume from durable Valkey state.**

Delete the entire crash apparatus (env var, `CrashGate`, counter, marker file) and replace it
with a single, clearly-commented `Environment.FailFast` line.

### Placement

The toggle line lives inside `RecordAgentCallActivity.RunAsync`, **before** the ledger append,
gated by PR number:

```csharp
// 💥 DURABILITY DEMO — uncomment the next line for a first run to simulate a crash
// partway through the fan-out, then comment it out and run again: the workflow
// rehydrates from Valkey and finishes WITHOUT repeating agent calls already recorded.
// if (record.Number == 204) Environment.FailFast("Simulated crash — demonstrating durable resume.");

new AgentCallLedger(outputDir).Append(record.Number, record.Title, DateTime.UtcNow);
```

Rationale:

- Gating on `record.Number == 204` (the 4th of the seven static fixtures 201–207) gives a
  **deterministic mid-run crash point** with no static counter and no `Interlocked`. The
  activity runs once per genuine (non-replayed) call, so the crash reliably fires after real
  work — regardless of the concurrent fan-out ordering.
- Because the crash trips **before** `Append`, PR #204 is not recorded on the first run. On
  resume, #204's already-completed agent (LLM) call replays from durable history (it is not
  re-invoked) and #204 is recorded exactly once. The finished ledger holds 7 unique lines.
- Committed **commented-out**, so the normal (non-durability) runbook flow never crashes.

`RecordAgentCallActivity` otherwise returns to being a pure, single-purpose ledger recorder:
no counter, no threshold parsing, no crash-gate log message.

## Files changed

| File | Change |
|---|---|
| `PrDigest.ApiService/Activities/RecordAgentCallActivity.cs` | Remove `_executedCalls`, `ParseThreshold`, `CrashGate` usage, `LogCrashing`; add the commented toggle line before `Append`; rewrite the class comment to describe only the ledger role plus a short note on the demo toggle. |
| `PrDigest.ApiService/Demo/CrashGate.cs` | Delete. |
| `PrDigest.Tests/CrashGateTests.cs` | Delete (tests a removed class). |
| `PrDigest.AppHost/AppHost.cs` | Remove the `CRASH_AFTER_AGENT_CALLS` env-var wiring and its comment. |
| `RUNBOOK.md` | Rewrite the "Crash-and-Resume Verification" section: uncomment the line → run → crash → comment out → run → resume. Drop the env-var arm/disarm steps and all `agent-calls.crash-marker` references (including the Output Location section). |
| `digest-out/agent-calls.crash-marker` | Delete the stale local artifact (git-ignored; not committed). |

## Trade-off

The concurrent fan-out means the *number* of PRs recorded before the crash may vary slightly
run-to-run (the original counter guaranteed exactly N). This affects only the illustrative
"pre-crash the ledger has a few lines" observation. The provable **final** state — 7 unique
ledger lines, no duplicated LLM calls — remains deterministic, and that is what the
verification checks.

## Verification

- `dotnet build` succeeds after `CrashGate.cs` and `CrashGateTests.cs` are removed.
- `dotnet test` passes (the remaining tests still compile and run).
- Manual RUNBOOK walkthrough: uncomment the line, run, observe the process die after ~a few
  agent calls; comment it out, run again, observe resume to `Completed`; confirm
  `agent-calls.log` has 7 lines / 7 unique PR numbers.
