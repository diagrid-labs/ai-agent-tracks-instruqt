# PrDigest Runbook

A reproducible manual verification guide for the PrDigest .NET Aspire + Dapr Workflow application.

## Prerequisites

### Docker

Docker must be running. The Aspire AppHost manages a Valkey container on host port 16379. Verify:

```powershell
docker ps
```

### Ollama

Ollama must be running with the `llama3.2:3b` model available locally.

**Verify Ollama is running:**

```powershell
curl http://localhost:11434/v1/models
```

Expected: a JSON response listing available models.

**Ensure the model is available:**

```powershell
ollama list
```

If `llama3.2:3b` is not listed, pull it:

```powershell
ollama pull llama3.2:3b
```

### .NET SDK

.NET 10 SDK must be installed:

```powershell
dotnet --version
```

Expected: version 10.0.x or higher.

### Data Directory

The application reads PR data from `PrDigest/data/dapr/dapr/prs/`. Seven PR JSON fixtures (201.json–207.json) are included with varied risk signals to make the ranked digest interesting.

## Starting the Application

From the repo root (`C:\dev\diagrid-labs\ai-agent-tracks-instruqt`), launch the Aspire AppHost:

```powershell
dotnet run --project PrDigest/PrDigest.AppHost
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

```powershell
$endpoint = "http://localhost:5090"  # Fixed API port (pinned in the AppHost)

$body = @{
  id       = "run-1"
  repoDir  = "data/dapr/dapr"
  maxPrs   = 7
} | ConvertTo-Json

curl -X POST "$endpoint/start" -H "Content-Type: application/json" -d $body
```

Expected response:

```json
{
  "instanceId": "run-1"
}
```

### Poll Status

Poll the `/status/<instanceId>` endpoint until the digest workflow completes:

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

Expected: the status eventually becomes `Completed` with an `Output` field containing:

```json
{
  "repoDir": "data/dapr/dapr",
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

This section demonstrates that durable state in Valkey allows the workflow to resume after an interruption without re-analyzing completed PRs.

### Step 1: Start a Fresh Run

```powershell
$endpoint = "http://localhost:5090"

$body = @{
  id       = "run-2"
  repoDir  = "data/dapr/dapr"
  maxPrs   = 7
} | ConvertTo-Json

curl -X POST "$endpoint/start" -H "Content-Type: application/json" -d $body
```

### Step 2: Wait for Partial Completion

Poll `/status/run-2` and wait for it to show `Running`:

```powershell
while ($true) {
  $status = curl -s "$endpoint/status/run-2" | ConvertFrom-Json
  Write-Host "Status: $($status.RuntimeStatus)"
  
  if ($status.RuntimeStatus -eq "Running") {
    Write-Host "Workflow is running. Killing AppHost now..."
    break
  }
  
  Start-Sleep -Seconds 1
}
```

### Step 3: Kill the AppHost

In the terminal running `dotnet run`, press **Ctrl+C** to stop the application abruptly. This simulates a process crash mid-workflow.

### Step 4: Restart the AppHost

Rerun the same command:

```powershell
dotnet run --project PrDigest/PrDigest.AppHost
```

Wait for the Aspire dashboard to appear and resources to reach `Running` (about 10–15 seconds).

### Step 5: Poll Status for Completion

```powershell
$endpoint = "http://localhost:5090"  # Fixed API port (same across restarts)

while ($true) {
  $status = curl -s "$endpoint/status/run-2" | ConvertFrom-Json
  Write-Host "Status: $($status.RuntimeStatus)"
  
  if ($status.RuntimeStatus -eq "Completed") {
    Write-Host "Resumed and completed. Output: $($status.Output | ConvertTo-Json -Depth 10)"
    break
  }
  
  Start-Sleep -Seconds 2
}
```

Expected: the workflow resumes from where it stopped and eventually completes. The durable state in Valkey (keyed by instance ID "run-2") persists the analysis results for PRs already processed, so only the remaining PRs are analyzed.

### Verification

To confirm that completed PRs were not re-run:

1. Before the kill, capture the console output and note which PRs had started analysis.
2. After the restart and resume, verify that the first N completed PRs do not appear again in the logs (no duplicate "analyzing PR X" messages).
3. Open the final `pr-digest.md` and confirm all 7 PRs are ranked (no gaps due to incomplete runs).

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

By default, `pr-digest.md` is written to the **current working directory** of the `PrDigest.ApiService` process. If you need it elsewhere, set the `DIGEST_OUTPUT_DIR` environment variable before running the Aspire AppHost:

```powershell
$env:DIGEST_OUTPUT_DIR = "C:\path\to\output"
dotnet run --project PrDigest/PrDigest.AppHost
```

The `pr-digest.md` file will then be written to that directory.

## Notes

- **Data snapshot:** The 7 PR JSON fixtures (201–207) are a static out-of-band snapshot collected from a Dapr repository configuration. They simulate realistic PRs with varied risk signals but are not live GitHub data.
- **LLM model:** The application uses `llama3.2:3b`, a small local model run via Ollama. AI-generated summaries in the digest are illustrative and reflect the capabilities of this local model; they are not production-grade analyses.
- **Durable state:** The Valkey state store (managed by Aspire) persists all workflow progress, enabling crash-and-resume semantics. A new workflow instance with the same ID will resume from where the previous one was interrupted.

## Troubleshooting

**Ollama connection refused:**

Ensure Ollama is running (`ollama serve` in a separate terminal) and the endpoint is reachable:

```powershell
curl http://localhost:11434/v1/models
```

**Valkey connection refused:**

Verify Docker is running and the Aspire-managed Valkey container is healthy:

```powershell
docker ps | grep valkey
```

**Endpoint not found:**

The `pr-digest` resource may still be starting. Check the Aspire dashboard for its status. If it remains in a non-Running state, check logs in the dashboard for errors.

**Workflow never completes:**

Check the Aspire dashboard Traces for errors in activities. Confirm Ollama is responsive (see above). The AI analysis step is the longest; it may take 1–2 minutes per PR with a small model.
