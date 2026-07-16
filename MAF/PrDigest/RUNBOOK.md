# PrDigest Runbook

A reproducible manual verification guide for the PrDigest .NET Aspire + Dapr Workflow application.

> **Shell conventions:** Commands are provided for both **PowerShell (Windows)** and **bash (macOS/Linux)**. Pick the tab that matches your platform. Where a command is identical on both platforms, only a single block is shown.
>
> The bash examples use [`jq`](https://jqlang.github.io/jq/) to parse JSON responses. Install it first if needed (`brew install jq` on macOS, `sudo apt install jq` on Debian/Ubuntu).

## Prerequisites

### Docker

Docker must be running. The Aspire AppHost manages a Valkey container on host port 16379. Verify:

```sh
docker ps
```

### OpenAI

The application uses OpenAI's `gpt-4o-mini` model through the Dapr conversation API. You need an OpenAI API key with access to chat completions.

**Get an API key:**

Create or copy a key from the [OpenAI API keys dashboard](https://platform.openai.com/api-keys).

**Add the key to the local secrets file:**

The key is read from a local Dapr secret store (`secretstores.local.file`), not committed to source control. Copy the template and fill in your key:

**PowerShell (Windows):**

```powershell
Copy-Item PrDigest.AppHost/secrets.example.json PrDigest.AppHost/secrets.json
```

**bash (macOS/Linux):**

```bash
cp PrDigest.AppHost/secrets.example.json PrDigest.AppHost/secrets.json
```

Then edit `PrDigest.AppHost/secrets.json` and set your key:

```json
{
  "openai-api-key": "sk-..."
}
```

`secrets.json` is git-ignored. The conversation component (`resources/conversation.yaml`) resolves the key via `secretKeyRef` against the `local-secret-store` component (`resources/secretstore.yaml`). The model is configured in `conversation.yaml` (`gpt-4o-mini` by default) and can be changed to any chat-capable OpenAI model.

### .NET SDK

.NET 10 SDK must be installed:

```sh
dotnet --version
```

Expected: version 10.0.x or higher.

### Data Directory

The application reads PR data from `MAF/PrDigest/data/dapr/dapr/prs/`. Ten PR JSON fixtures (9719.json–10112.json) are included with varied risk signals to make the ranked digest interesting; a `maxPrs=7` run analyses the first seven by number (`9719, 9855, 9893, 9974, 10053, 10054, 10093`).

## Starting the Application

From the MAF/PrDigest folder, launch the Aspire project.

```bash
cd MAF/PrDigest
aspire run
```

Expected output:

```
Building...
Starting...
Dashboard: http://localhost:<port>
```

Open the Aspire dashboard in a browser (the exact port will be printed).

**Confirm resource health:**

- Navigate to the Resources view in the Aspire dashboard.
- Verify that `statestore` (Valkey), `pr-digest` (the API service), and `pr-digest-dapr-sidecar` (the Dapr sidecar) all show `Running` status.
- The `pr-digest` resource exposes its HTTP endpoint at the fixed port `http://localhost:5090` (pinned in the AppHost).

## Triggering a Digest Run

From a separate terminal (while the AppHost is running), send a POST request to the `pr-digest` API at its fixed port and `/start`:

**PowerShell (Windows):**

```powershell
$endpoint = "http://localhost:5090"  # Fixed API port (pinned in the AppHost)

$body = @{
  id       = "run-1"
  repo     = "dapr/dapr"
  maxPrs   = 7
} | ConvertTo-Json

curl -X POST "$endpoint/start" -H "Content-Type: application/json" -d $body
```

**bash (macOS/Linux):**

```bash
endpoint="http://localhost:5090"  # Fixed API port (pinned in the AppHost)

curl -X POST "$endpoint/start" -H "Content-Type: application/json" -d '{
  "id": "run-1",
  "repo": "dapr/dapr",
  "maxPrs": 7
}'
```

Expected response:

```json
{
  "instanceId": "run-1"
}
```

### Poll Status

Poll the `/status/<instanceId>` endpoint until the digest workflow completes:

**PowerShell (Windows):**

```powershell
$endpoint = "http://localhost:5090"
$instanceId = "run-1"

while ($true) {
  $status = curl -s "$endpoint/status/$instanceId" | ConvertFrom-Json
  Write-Host "Status: $($status.RuntimeStatus)"

  if ($status.RuntimeStatus -eq "Completed") {
    Write-Host "Output: $($status.Output | ConvertTo-Json -Depth 10)"
    break
  }

  Start-Sleep -Seconds 2
}
```

**bash (macOS/Linux):**

```bash
endpoint="http://localhost:5090"
instanceId="run-1"

while true; do
  status=$(curl -s "$endpoint/status/$instanceId")
  runtime=$(echo "$status" | jq -r '.RuntimeStatus')
  echo "Status: $runtime"

  if [ "$runtime" = "Completed" ]; then
    echo "Output:"
    echo "$status" | jq '.Output'
    break
  fi

  sleep 2
done
```

Expected: the status eventually becomes `Completed` with an `Output` field containing:

```json
{
  "repo": "dapr/dapr",
  "prCount": 7,
  "digestPath": "<path-to-pr-digest.md>",
  "headline": "<AI-generated summary>"
}
```

### Read the Digest

Open the file at `digestPath`. It should contain a Markdown table ranking the 7 PRs by risk, with columns for:

- Rank
- PR Number
- Title
- Risk Score
- Flags (e.g., `many-files`, `large-diff`, `no-tests`, `no-linked-issue`)
- Summary (from the AI analysis)
- Linked Issue

You should see a mix of LOW (scores 0–1), MEDIUM (scores 2–4), and HIGH (scores 6+) risk PRs.

## Crash-and-Resume Verification

This is the durability demo: the workflow is interrupted mid-run by a **real process crash**, and on restart it resumes from durable Valkey state — **without re-running the `PrAnalyzer` agent (LLM) calls that already completed.** An append-only *agent-call ledger* makes this provable instead of something you take on faith.

### How it works

- **Simulated crash — one line you toggle by hand.** `RecordAgentCallActivity.cs` contains a single line that hard-crashes the process (via `Environment.FailFast`) once a couple of agent calls have already been recorded — i.e. partway through the fan-out. It ships **armed** (uncommented): the first run crashes, and you comment it out for the resume run. There is no environment variable, static counter, or marker file — the crash is driven off the ledger's own line count, and *you* are the switch.

> **Note:** because the line ships armed, a normal digest run (the "Triggering a Digest Run" section above) will also crash partway through. Comment the line out first if you just want a clean, non-crashing run.
- **Why count-based, not a fixed PR:** the 7 PRs are analysed concurrently, so which ones finish first is nondeterministic. Gating on the ledger count (`>= 2`) guarantees the crash lands mid-run with roughly two calls already banked, regardless of ordering — the crash trips *before* the third record is appended, so that in-flight PR is recorded only on the resumed run and never duplicated.
- **The agent-call ledger:** every executed agent call appends one line to `agent-calls.log` — `<timestamp>\tPR #<number>\t<title>`. Recording happens inside a *checkpointed workflow activity*, so on resume a completed record is replayed from durable history and is **not** re-appended. The finished ledger therefore contains each PR exactly once, with a visible time gap at the moment of restart.

The ledger is written to the digest output directory (`DIGEST_OUTPUT_DIR`, or a `digest-out` folder in the parent of the API service's working directory if unset). Set `DIGEST_OUTPUT_DIR` to a known path so you can find it easily.

### Step 1: Confirm the crash is armed

The demo line inside `RunAsync` of `PrDigest.ApiService/Activities/RecordAgentCallActivity.cs` ships **armed** (uncommented), so no change is needed for the first run:

```csharp
if (ledger.CountEntries() >= 2) Environment.FailFast("Simulated crash — demonstrating durable resume.");
```

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

The API process terminates **by itself** once two calls have been recorded (the third trips the crash before it is appended). In the console (or the `pr-digest` logs in the Aspire dashboard) you will see the agent calls that finished first, then the process dies — for example:

```
🤖 Analyzing PR #9719 with the PrAnalyzer agent
📒 Recorded agent call for PR #9719.
📒 Recorded agent call for PR #9855.
```

Inspect the ledger so far — it holds the ~2 calls recorded before the crash (which PRs they are depends on the concurrent fan-out):

```bash
cat "$DIGEST_OUTPUT_DIR/agent-calls.log"
```

### Step 5: Disarm and restart — comment the line out

Re-open `PrDigest.ApiService/Activities/RecordAgentCallActivity.cs` and **comment out** the line again:

```csharp
// if (ledger.CountEntries() >= 2) Environment.FailFast("Simulated crash — demonstrating durable resume.");
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

## Observability: Traces

In the Aspire dashboard:

1. Navigate to the **Traces** view.
2. Select the `pr-digest` resource.
3. You should see spans for:
   - The workflow orchestrator entry point
   - Individual activity calls for each PR (e.g., `AnalyzePrActivity`)
   - The summarize activity
   - The write-digest activity

For the crash-and-resume verification, you will see:

- Trace spans from the first run (up to the kill point).
- Additional spans from the resumed run, showing the second half of PR analysis and the completion steps.
- Compare timestamps and span IDs to confirm the resumption.

## Output Location

By default, `pr-digest.md` is written to a **`digest-out` folder in the parent of the current working directory** of the `PrDigest.ApiService` process. If you need it elsewhere, set the `DIGEST_OUTPUT_DIR` environment variable before running the Aspire AppHost:

**PowerShell (Windows):**

```powershell
$env:DIGEST_OUTPUT_DIR = "C:\path\to\output"
dotnet run --project PrDigest/PrDigest.AppHost
```

**bash (macOS/Linux):**

```bash
export DIGEST_OUTPUT_DIR="/path/to/output"
dotnet run --project PrDigest/PrDigest.AppHost
```

The `pr-digest.md` file will then be written to that directory. The durability-demo artifact — `agent-calls.log` (the agent-call ledger) — is written to the **same** directory.

## Notes

- **Data snapshot:** The 10 PR JSON fixtures (9719–10112) are a static out-of-band snapshot collected from a Dapr repository configuration. They simulate realistic PRs with varied risk signals but are not live GitHub data.
- **LLM model:** The application uses OpenAI's `gpt-4o-mini` via the Dapr conversation API. AI-generated summaries in the digest are illustrative; they are not production-grade analyses.
- **Durable state:** The Valkey state store (managed by Aspire) persists all workflow progress, enabling crash-and-resume semantics. A new workflow instance with the same ID will resume from where the previous one was interrupted.

## Troubleshooting

**OpenAI authentication or connection errors:**

Confirm `PrDigest.AppHost/secrets.json` exists and its `openai-api-key` value is a valid OpenAI API key with access to the configured model, and that the host has outbound internet access to `api.openai.com`. A missing `secrets.json` will surface as a secret-store load error for `local-secret-store`.

**Valkey connection refused:**

Verify Docker is running and the Aspire-managed Valkey container is healthy.

**PowerShell (Windows):**

```powershell
docker ps | Select-String valkey
```

**bash (macOS/Linux):**

```bash
docker ps | grep valkey
```

**Endpoint not found:**

The `pr-digest` resource may still be starting. Check the Aspire dashboard for its status. If it remains in a non-Running state, check logs in the dashboard for errors.

**Workflow never completes:**

Check the Aspire dashboard Traces for errors in activities. Confirm the OpenAI key is valid and the API is reachable (see above). The AI analysis step is the longest part of the run.
