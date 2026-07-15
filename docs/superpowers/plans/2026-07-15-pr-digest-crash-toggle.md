# PrDigest Crash Toggle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the PrDigest durability demo's self-disabling crash-gate machinery with a single, clearly-commented `Environment.FailFast` line the learner toggles by hand.

**Architecture:** Delete the crash apparatus (`CRASH_AFTER_AGENT_CALLS` env var, the `CrashGate` class, its static call counter, and the marker file). `RecordAgentCallActivity` returns to being a pure ledger recorder, carrying one commented-out demo toggle gated on the 3rd PR of the run (`record.Number == 9893`), placed before the ledger append. The learner uncomments it for run 1 (crash mid-fan-out) and comments it out for run 2 (resume from Valkey).

**Tech Stack:** .NET 10, C#, .NET Aspire, Dapr Workflow, xUnit.

## Global Constraints

- The seven PRs used at `maxPrs=7`, in order, are `9719, 9855, 9893, 9974, 10053, 10054, 10093` (`GitHubDataReader` sorts the ten fixtures in `data/dapr/dapr/prs` ascending and takes the first 7). The 3rd is **#9893** — the crash gate must target this number.
- The toggle line must ship **commented-out** so normal (non-durability) runs never crash.
- The crash must trip **before** the ledger append so the in-flight PR is recorded only on the resumed run (no duplicate ledger line).
- Do not introduce any static counter, `Interlocked` state, env var, or marker file — the learner is the toggle.

---

### Task 1: Remove the crash apparatus from the API service

**Files:**
- Modify: `MAF/PrDigest/PrDigest.ApiService/Activities/RecordAgentCallActivity.cs` (full rewrite)
- Delete: `MAF/PrDigest/PrDigest.ApiService/Demo/CrashGate.cs`
- Delete: `MAF/PrDigest/PrDigest.Tests/CrashGateTests.cs`
- Modify: `MAF/PrDigest/PrDigest.AppHost/AppHost.cs` (remove `CRASH_AFTER_AGENT_CALLS` wiring)
- Delete (local, git-ignored): `MAF/PrDigest/digest-out/agent-calls.crash-marker`

**Interfaces:**
- Consumes: `AgentCallRecord(int Number, string Title)` from `PrDigest.ApiService.Models`; `AgentCallLedger(string directory).Append(int, string, DateTime)` and `DemoPaths.OutputDirectory()` from `PrDigest.ApiService.Demo`. All unchanged.
- Produces: `RecordAgentCallActivity` still a `WorkflowActivity<AgentCallRecord, bool>` returning `true` — the workflow's `context.CallActivityAsync<bool>(nameof(RecordAgentCallActivity), ...)` call is unaffected.

- [ ] **Step 1: Rewrite `RecordAgentCallActivity.cs`**

Replace the entire file contents with:

```csharp
using Dapr.Workflow;
using PrDigest.ApiService.Demo;
using PrDigest.ApiService.Models;

namespace PrDigest.ApiService.Activities;

// Durably records that one PrAnalyzer agent call executed, by appending to the agent-call
// ledger. Because this runs as a checkpointed workflow activity, a completed record is
// replayed from history (not re-executed) after a crash — so the ledger ends up with each
// PR exactly once, proving the expensive LLM calls were never repeated on resume.
public sealed partial class RecordAgentCallActivity(ILogger<RecordAgentCallActivity> logger)
    : WorkflowActivity<AgentCallRecord, bool>
{
    public override Task<bool> RunAsync(WorkflowActivityContext context, AgentCallRecord record)
    {
        var outputDir = DemoPaths.OutputDirectory();

        // 💥 DURABILITY DEMO — uncomment the next line for a first run to simulate a crash
        // partway through the fan-out (#9893 is the 3rd of the 7 PRs in the run), then comment
        // it out and run again: the workflow rehydrates from durable Valkey state and finishes
        // WITHOUT repeating the agent calls already recorded below.
        // if (record.Number == 9893) Environment.FailFast("Simulated crash — demonstrating durable resume.");

        new AgentCallLedger(outputDir).Append(record.Number, record.Title, DateTime.UtcNow);
        LogRecorded(logger, record.Number);
        return Task.FromResult(true);
    }

    [LoggerMessage(LogLevel.Information, "📒 Recorded agent call for PR #{Number}.")]
    static partial void LogRecorded(ILogger logger, int number);
}
```

- [ ] **Step 2: Delete the `CrashGate` class and its tests**

Run:

```bash
cd /Users/marcduiker/dev/diagrid-labs/ai-agent-tracks-instruqt/MAF/PrDigest
git rm PrDigest.ApiService/Demo/CrashGate.cs PrDigest.Tests/CrashGateTests.cs
```

Expected: both files staged for deletion.

- [ ] **Step 3: Remove the env-var wiring from `AppHost.cs`**

In `MAF/PrDigest/PrDigest.AppHost/AppHost.cs`, delete these six lines (the comment block and the `WithEnvironment` call for the crash gate):

```csharp
    // Durability demo: when this is a positive integer, the API hard-crashes after that many
    // PrAnalyzer agent calls (once), so the crash-and-resume lab fires at the same point every
    // run. Unset/0 means never crash (normal runs). Arm it with `export CRASH_AFTER_AGENT_CALLS=3`
    // before `aspire run`.
    .WithEnvironment("CRASH_AFTER_AGENT_CALLS",
        Environment.GetEnvironmentVariable("CRASH_AFTER_AGENT_CALLS") ?? "0")
```

The remaining chain must read (context — do not duplicate these lines, they already exist):

```csharp
    .WithEnvironment("REPO", "dapr/dapr")
    // Pin the API's HTTP endpoint to a fixed host port so the RUNBOOK URLs are stable.
    .WithEndpoint("http", endpoint => endpoint.Port = 5090)
```

- [ ] **Step 4: Delete the stale local crash-marker artifact**

Run (it is git-ignored, so this is a plain filesystem delete, not a git operation):

```bash
cd /Users/marcduiker/dev/diagrid-labs/ai-agent-tracks-instruqt/MAF/PrDigest
rm -f digest-out/agent-calls.crash-marker
```

- [ ] **Step 5: Confirm no lingering references**

Run:

```bash
cd /Users/marcduiker/dev/diagrid-labs/ai-agent-tracks-instruqt/MAF/PrDigest
grep -rn -e "CrashGate" -e "CRASH_AFTER_AGENT_CALLS" -e "crash-marker" -e "ShouldCrash" -e "_executedCalls" -e "ParseThreshold" . --include="*.cs" | grep -v -e "/bin/" -e "/obj/"
```

Expected: **no output** (exit code 1 from grep is fine — it means nothing matched).

- [ ] **Step 6: Build the solution**

Run:

```bash
cd /Users/marcduiker/dev/diagrid-labs/ai-agent-tracks-instruqt/MAF/PrDigest
dotnet build PrDigest.sln
```

Expected: `Build succeeded` with 0 errors. (There is no failing-test-first step here: the change is a removal plus a manually-toggled `FailFast` line, which has no automatable unit test. The build + existing suite are the regression guard.)

- [ ] **Step 7: Run the full test suite**

Run:

```bash
cd /Users/marcduiker/dev/diagrid-labs/ai-agent-tracks-instruqt/MAF/PrDigest
dotnet test PrDigest.sln
```

Expected: all tests pass. The suite no longer contains `CrashGateTests`; the remaining test files (`AgentCallLedgerTests`, `DigestMarkdownWriterTests`, `DigestRankerTests`, `GitHubDataReaderTests`, `PrMetricsTests`, `PrToolsTests`, `RiskModelTests`) compile and pass.

- [ ] **Step 8: Commit**

```bash
cd /Users/marcduiker/dev/diagrid-labs/ai-agent-tracks-instruqt
git add MAF/PrDigest/PrDigest.ApiService/Activities/RecordAgentCallActivity.cs \
        MAF/PrDigest/PrDigest.AppHost/AppHost.cs
git rm --cached MAF/PrDigest/PrDigest.ApiService/Demo/CrashGate.cs MAF/PrDigest/PrDigest.Tests/CrashGateTests.cs 2>/dev/null; true
git commit -m "Replace PrDigest crash gate with a one-line durability toggle

Delete the CRASH_AFTER_AGENT_CALLS env var, the CrashGate class + its tests,
the static call counter, and the marker file. RecordAgentCallActivity is now a
pure ledger recorder carrying one commented-out FailFast toggle gated on the
3rd PR of the run (#9893), tripped before the ledger append.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

(Steps 1–4 already staged the deletions/edits; `git add`/`git rm --cached` here just make sure everything is staged before commit.)

---

### Task 2: Rewrite the RUNBOOK durability section

**Files:**
- Modify: `MAF/PrDigest/RUNBOOK.md` — the "Crash-and-Resume Verification" section (currently lines ~199–311) and the crash-marker mention in "Output Location" (currently line ~348).

**Interfaces:**
- Consumes: nothing (documentation only).
- Produces: instructions that match Task 1's behavior — uncomment `RecordAgentCallActivity.cs`'s toggle line → run → crash → comment out → run → resume.

- [ ] **Step 1: Replace the "Crash-and-Resume Verification" section**

Replace everything from the `## Crash-and-Resume Verification` heading up to (but **not** including) the `## Observability: Traces` heading with:

````markdown
## Crash-and-Resume Verification

This is the durability demo: the workflow is interrupted mid-run by a **real process crash**, and on restart it resumes from durable Valkey state — **without re-running the `PrAnalyzer` agent (LLM) calls that already completed.** An append-only *agent-call ledger* makes this provable instead of something you take on faith.

### How it works

- **Simulated crash — one line you toggle by hand.** `RecordAgentCallActivity.cs` contains a single commented-out line that hard-crashes the process (via `Environment.FailFast`) while the 3rd PR of the run is being recorded. You uncomment it for the first run, then comment it back out for the resume run. There is no environment variable, counter, or marker file — *you* are the switch.
- **Why the 3rd PR:** the run analyses the first 7 PRs from `data/dapr/dapr/prs`, sorted ascending: `9719, 9855, 9893, 9974, 10053, 10054, 10093`. The gate targets `#9893` (the 3rd), so the crash lands squarely mid-fan-out. It trips *before* the ledger append, so `#9893` is recorded only on the resumed run and never duplicated.
- **The agent-call ledger:** every executed agent call appends one line to `agent-calls.log` — `<timestamp>\tPR #<number>\t<title>`. Recording happens inside a *checkpointed workflow activity*, so on resume a completed record is replayed from durable history and is **not** re-appended. The finished ledger therefore contains each PR exactly once, with a visible time gap at the moment of restart.

The ledger is written to the digest output directory (`DIGEST_OUTPUT_DIR`, or a `digest-out` folder in the parent of the API service's working directory if unset). Set `DIGEST_OUTPUT_DIR` to a known path so you can find it easily.

### Step 1: Arm the crash — uncomment one line

Open `PrDigest.ApiService/Activities/RecordAgentCallActivity.cs` and **uncomment** the demo line inside `RunAsync`:

```csharp
if (record.Number == 9893) Environment.FailFast("Simulated crash — demonstrating durable resume.");
```

Save the file.

### Step 2: Launch

Set the output directory in the shell that launches the AppHost, then run:

**PowerShell (Windows):**

```powershell
$env:DIGEST_OUTPUT_DIR = "$PWD\digest-out"
aspire run
```

**bash (macOS/Linux):**

```bash
export DIGEST_OUTPUT_DIR="$PWD/digest-out"
aspire run
```

### Step 3: Start a run

```bash
curl -X POST "http://localhost:5090/start" -H "Content-Type: application/json" -d '{
  "id": "run-crash",
  "repo": "dapr/dapr",
  "maxPrs": 7
}'
```

### Step 4: Watch it crash

The API process terminates **by itself** while recording PR #9893. In the console (or the `pr-digest` logs in the Aspire dashboard) you will see the agent calls that finished first, then the process dies — for example:

```
🤖 Analyzing PR #9719 with the PrAnalyzer agent
📒 Recorded agent call for PR #9719.
📒 Recorded agent call for PR #9855.
```

Inspect the ledger so far — because the crash trips *before* #9893 is appended, it holds only the calls that completed first (the fan-out is concurrent, so the exact count varies slightly):

```bash
cat "$DIGEST_OUTPUT_DIR/agent-calls.log"
```

### Step 5: Disarm and restart — comment the line out

Re-open `PrDigest.ApiService/Activities/RecordAgentCallActivity.cs` and **comment out** the line again:

```csharp
// if (record.Number == 9893) Environment.FailFast("Simulated crash — demonstrating durable resume.");
```

Save, then relaunch:

**PowerShell (Windows):**

```powershell
aspire run
```

**bash (macOS/Linux):**

```bash
aspire run
```

Aspire reconnects to the same Valkey container (its data volume persists across restarts), the workflow engine rehydrates instance `run-crash`, and it resumes automatically — you do **not** call `/resume` (that is only for workflows suspended via `/pause`).

### Step 6: Poll until completed

```bash
endpoint="http://localhost:5090"
while true; do
  runtime=$(curl -s "$endpoint/status/run-crash" | jq -r '.RuntimeStatus')
  echo "Status: $runtime"
  [ "$runtime" = "Completed" ] && break
  sleep 2
done
```

### Verification — durability, proven

Inspect the finished ledger:

```bash
cat "$DIGEST_OUTPUT_DIR/agent-calls.log"
```

Confirm:

1. **Exactly 7 lines — one per PR, no duplicate PR numbers.** The agent calls that completed before the crash were *not* re-run; their results came from durable history.
2. **A clear timestamp gap** between the pre-crash lines and the rest — the wall-clock cost of the crash + restart, sitting inside a single logical workflow run.
3. The resumed console shows `🤖 Analyzing PR #...` only for PRs that had not finished — already-analyzed PRs stay silent (replay-safe logging suppresses replayed log lines).
4. `pr-digest.md` contains all 7 PRs ranked, with no gaps.

A quick scripted check (bash):

```bash
total=$(grep -c . "$DIGEST_OUTPUT_DIR/agent-calls.log")
unique=$(cut -f2 "$DIGEST_OUTPUT_DIR/agent-calls.log" | sort -u | grep -c .)
echo "lines=$total unique-PRs=$unique"   # expect both = 7
```
````

- [ ] **Step 2: Fix the crash-marker mention in "Output Location"**

In the "Output Location" section, replace this sentence:

```markdown
The `pr-digest.md` file will then be written to that directory. The durability-demo artifacts — `agent-calls.log` (the agent-call ledger) and `agent-calls.crash-marker` (the one-shot crash sentinel) — are written to the **same** directory.
```

with:

```markdown
The `pr-digest.md` file will then be written to that directory. The durability-demo artifact — `agent-calls.log` (the agent-call ledger) — is written to the **same** directory.
```

- [ ] **Step 3: Confirm no lingering RUNBOOK references**

Run:

```bash
cd /Users/marcduiker/dev/diagrid-labs/ai-agent-tracks-instruqt/MAF/PrDigest
grep -n -e "CRASH_AFTER_AGENT_CALLS" -e "crash-marker" -e "crash gate" -e "Arm the crash gate" RUNBOOK.md
```

Expected: **no output**.

- [ ] **Step 4: Commit**

```bash
cd /Users/marcduiker/dev/diagrid-labs/ai-agent-tracks-instruqt
git add MAF/PrDigest/RUNBOOK.md
git commit -m "Update RUNBOOK for the one-line durability toggle

Rewrite the Crash-and-Resume section to drive the demo by uncommenting a
single FailFast line in RecordAgentCallActivity.cs (crash on the 3rd PR,
#9893) instead of the CRASH_AFTER_AGENT_CALLS env var, and drop the
crash-marker references.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- Delete env var / `CrashGate` / counter / marker → Task 1 Steps 1–4. ✓
- `RecordAgentCallActivity` becomes pure recorder + one commented toggle before append → Task 1 Step 1. ✓
- Gate on `record.Number == 9893` (3rd of `9719, 9855, 9893, 9974, 10053, 10054, 10093`) → Task 1 Step 1 + Global Constraints. ✓
- Ship commented-out → Task 1 Step 1 (line begins `//`). ✓
- Delete `CrashGateTests.cs` → Task 1 Step 2. ✓
- Remove `AppHost.cs` env wiring → Task 1 Step 3. ✓
- Rewrite RUNBOOK durability + output-location → Task 2. ✓
- Delete stale local marker → Task 1 Step 4. ✓
- Verification (build, test, manual walkthrough) → Task 1 Steps 5–7, Task 2 Steps 1/3. ✓

**Placeholder scan:** No TBD/TODO/"handle edge cases"/vague steps — every code and doc change shows full content. ✓

**Type consistency:** `RecordAgentCallActivity : WorkflowActivity<AgentCallRecord, bool>`, `LogRecorded(ILogger, int)`, `AgentCallLedger.Append(int, string, DateTime)`, `record.Number`/`record.Title` all match the existing code and the spec. ✓

**TDD note:** This change is a removal plus a human-toggled `Environment.FailFast` line; there is no runtime behavior to assert in an automated unit test. The regression guard is the green build + existing suite (Task 1 Steps 6–7) and the manual RUNBOOK walkthrough (Task 2), which is the honest verification for this kind of change.
