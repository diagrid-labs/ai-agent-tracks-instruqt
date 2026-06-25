# Reliable PR Digests with Microsoft Agent Framework + Dapr Workflow — Design

**Date:** 2026-06-24
**Status:** Approved (design); ready for implementation planning
**Scope:** Application code only. The Instruqt track (challenges, sandbox/VM image, Ollama
pre-pull, GitHub data-collection script) is **out of scope** for this spec.

## 1. Summary

A .NET demo app where a maintainer drowning in open pull requests gets a **ranked daily
digest** (`pr-digest.md`). A Dapr Workflow fans out over a batch of open PRs; for each PR a
**Microsoft Agent Framework (MAF)** agent summarizes the change, detects a linked issue, and
reasons about risk. Results fan in — sorted deterministically by a computed risk score, topped
with a short LLM-written headline — into a single markdown digest.

The teaching message: **MAF does the per-PR reasoning; Dapr Workflow makes the batch reliable** —
durable fan-out/fan-in that survives a crash and resumes from the next unprocessed PR, with
retry/backoff on flaky local-model calls.

## 2. Stack & decisions

| Concern | Decision |
| --- | --- |
| Orchestrator | **.NET Aspire** (AppHost + ServiceDefaults + ApiService) |
| Dapr runtime | **Dapr OSS** — self-hosted sidecar via Aspire's Dapr integration (`.WithDaprSidecar`), **not** Diagrid Catalyst |
| Workflow state store | **Valkey**, run as a container whose life cycle is **managed by Aspire** (`AddValkey`); the Dapr state store component points at it |
| Agent glue | `Diagrid.AI.Microsoft.AgentFramework` package (`AddDaprAgents`, `WithAgent`, `context.GetAgent`, `RunAgentAndDeserializeAsync<T>`) — works against Dapr OSS Workflow; only the AppHost hosting package differs from the sample |
| LLM provider | **Ollama local** (`llama3.2:3b`) via an OpenAI-compatible `IChatClient` at `http://localhost:11434/v1` |
| Fan-in | **Hybrid:** deterministic sort by computed risk score + one small summarize agent for a 2–3 sentence headline |
| Crash demo | **Manual kill only** — no deliberate crash code in the app |
| Output | `pr-digest.md` — ranked PRs with one-line summaries, linked-issue status, risk flags |

### Reference

- Based on Track 1 of `dapr-university-instruqt/docs/github-agent-tracks-ideas.md`.
- Patterns adapted from the sample `catalyst-aspire-maf/EnterpriseDiagnosticsMAF` (the Catalyst
  AppHost wiring is the one part deliberately replaced with Dapr OSS).

### Known risk

A 3B local model can struggle with strict-JSON structured output. Mitigations are designed in:
all *ranking-critical* numbers are computed deterministically in code (not by the model); the
model only produces prose (summary, headline) and a coarse risk rationale; malformed model
output is retried and then degraded gracefully (§6).

## 3. Project layout

```
PrDigest.sln
├─ PrDigest.AppHost            // Aspire: ApiService + Dapr sidecar + Valkey state store + Ollama
├─ PrDigest.ServiceDefaults    // OpenTelemetry / health (Aspire template)
└─ PrDigest.ApiService         // workflow, MAF agents, tools, reader, endpoints
   ├─ Program.cs               // IChatClient(Ollama), AddDaprAgents, WithAgent x2, endpoints
   ├─ Workflows/PrDigestWorkflow.cs
   ├─ Activities/ListOpenPullRequestsActivity.cs
   ├─ Activities/WriteDigestActivity.cs
   ├─ Agents/AgentNames.cs + AgentInstructions
   ├─ Tools/PrTools.cs         // GetPullRequest(number) AIFunction
   ├─ Data/GitHubDataReader.cs // local JSON → DTOs + deterministic metrics
   └─ Models/*.cs              // DTOs, workflow IO, JSON source-gen context
```

### AppHost wiring (the delta from the sample)

```csharp
var builder = DistributedApplication.CreateBuilder(args);

// Aspire owns the Valkey container life cycle (start/stop with the app run).
var stateStore = builder.AddValkey("statestore");

builder.AddProject<Projects.PrDigest_ApiService>("pr-digest")
    .WithReference(stateStore)
    .WaitFor(stateStore)
    .WithDaprSidecar(new DaprSidecarOptions
    {
        AppId = "pr-digest",
        ResourcesPaths = ["resources"]   // Dapr component YAML for the Valkey state store
    });

builder.Build().Run();
```

`PrDigest.AppHost/resources/` holds the Dapr **workflow state store** component
(`state.redis`/Valkey-compatible) pointing at the Aspire-managed **Valkey** container — so the
durable workflow state lives in Valkey and Aspire starts/stops it alongside the run. Ollama is
reached as an external endpoint (default `http://localhost:11434`); optionally modeled as an
Aspire resource. No `AddCatalystProject`, no `WithCatalyst`.

> The exact connection wiring (whether the component reads the Valkey host from an Aspire-injected
> connection string / env var, or a static `localhost:6379` for the local demo) is confirmed
> during implementation; either way Aspire manages the container.

### ApiService registration (shape; mirrors the sample)

```csharp
const string Model = "llama3.2:3b";
var ollamaBase = Environment.GetEnvironmentVariable("OLLAMA_BASE_URL") ?? "http://localhost:11434/v1";

builder.Services.AddSingleton<IChatClient>(_ =>
    new OpenAIClient(new ApiKeyCredential("ollama"),
        new OpenAIClientOptions { Endpoint = new Uri(ollamaBase) })
        .GetChatClient(Model).AsIChatClient());

AITool[] prTools = [AIFunctionFactory.Create(PrTools.GetPullRequest)];

builder.Services.AddDaprAgents(
        opt => opt.AddContext(() => PrDigestJsonContext.Default),
        opt => {
            opt.RegisterWorkflow<PrDigestWorkflow>();
            opt.RegisterActivity<ListOpenPullRequestsActivity>();
            opt.RegisterActivity<WriteDigestActivity>();
        })
    .WithAgent(sp => sp.GetRequiredService<IChatClient>()
        .AsAIAgent(instructions: AgentInstructions.PrAnalyzer, name: AgentNames.PrAnalyzer, tools: prTools))
    .WithAgent(sp => sp.GetRequiredService<IChatClient>()
        .AsAIAgent(instructions: AgentInstructions.Summarize, name: AgentNames.Summarize));
```

> Exact `IChatClient`-over-Ollama construction is to be confirmed during implementation
> (OpenAI-compatible client pointed at Ollama's `/v1`; an API key is required by the client
> but ignored by Ollama). If the OpenAI client rejects the dummy key, fall back to a dedicated
> Ollama `IChatClient` provider package.

## 4. Workflow & data flow

```
START  input: { Id, RepoDir = "data/dapr/dapr", MaxPrs = 30 }
  │
  ├─ Activity: ListOpenPullRequestsActivity      (I/O) reads RepoDir/prs/*.json
  │     → returns [ { number, title, metrics } ... ]  (lightweight; no full diffs)
  │
  ├─ FAN-OUT  foreach number → Task ; await Task.WhenAll
  │     RunAgentAndDeserializeAsync<PrAnalysis>(prAnalyzerAgent, prompt(number))
  │        agent calls tool GetPullRequest(number) → truncated files/diff/body + metrics
  │        agent emits strict JSON: { summary, linkedIssue, riskRationale }
  │     ← each call is an independently checkpointed durable step (resume boundary)
  │
  ├─ FAN-IN (deterministic, in orchestrator)
  │     combine each PrAnalysis with its code-computed riskScore ; sort desc by riskScore
  │
  ├─ RunAgentAndDeserializeAsync<DigestHeader>(summarizeAgent, topN(ranked))
  │        emits { headline }   // 2–3 sentence top-line
  │
  └─ Activity: WriteDigestActivity               (I/O) writes pr-digest.md → returns path
END  output: { repoDir, prCount, digestPath, headline }
```

**Determinism rule:** the orchestrator body performs **no I/O**. All filesystem reads happen in
activities (`ListOpenPullRequestsActivity`) or in the agent's MAF tool (`GetPullRequest`); all
LLM calls happen inside `RunAgentAndDeserializeAsync` durable steps. The deterministic sort
operates only on data already returned into workflow history. This is what makes per-PR resume
correct.

## 5. Components

| Unit | Type | Responsibility | Depends on |
| --- | --- | --- | --- |
| `GitHubDataReader` | helper class | Deserialize `RepoDir/prs/{n}.json` → DTOs; compute metrics (file count, total additions/deletions, has-test-file heuristic, linked-issue regex over body) | filesystem |
| `PrTools.GetPullRequest(int number)` | MAF `AIFunction` (`[Description]`) | Return one PR's files/diff/body **truncated** to a char budget + computed metrics, for the analyzer agent | `GitHubDataReader` |
| `ListOpenPullRequestsActivity` | Dapr activity | Return PR numbers + lightweight metrics for fan-out | `GitHubDataReader` |
| `prAnalyzerAgent` | MAF agent | Per PR: prose summary, linked-issue confirmation, risk rationale over supplied signals | `IChatClient`, `PrTools` |
| `summarizeAgent` | MAF agent | One 2–3 sentence headline over the top-ranked analyses | `IChatClient` |
| `WriteDigestActivity` | Dapr activity | Render ranked analyses + headline → `pr-digest.md` | filesystem |

### Risk model (deterministic, in code)

`riskScore` = weighted sum of signals computed from PR data, **not** produced by the model:

- many files touched (above a threshold),
- large total diff (additions + deletions above a threshold),
- no test files in the changeset (filename heuristic, e.g. contains `test`/`spec`),
- no linked issue detected (regex for `#\d+` / `fixes|closes #\d+` in body).

The agent writes a human-readable `riskRationale`; the *score* (and therefore the ranking) is
stable regardless of model quality.

### Input data contract (read-only; produced out of band)

```
data/<owner>/<repo>/prs/<number>.json
{ "number": int, "title": string, "body": string,
  "files": [ { "filename": string, "additions": int, "deletions": int, "patch": string } ] }
```

The collector that produces these files is out of scope; the app is developed and tested against
**committed fixture JSON** of this shape. Default `RepoDir` is `data/dapr/dapr`.

## 6. Error handling & resiliency

- **Durable resume (headline payoff):** each fan-out `RunAgentAndDeserializeAsync` call is a
  checkpointed durable step. Killing the app mid-batch (Ctrl-C / kill process) and restarting
  replays workflow history — completed PR analyses are not re-run; the workflow continues from
  the next unprocessed PR. No deliberate crash code in the app.
- **Transient LLM flakiness:** agent activity calls use a `WorkflowTaskOptions` **retry policy**
  (e.g. 3 attempts, exponential backoff) so a timeout or empty/garbled model response is retried
  rather than aborting the digest. (Alternative for production: a Dapr resiliency spec YAML —
  noted, not used in the app-only scope.)
- **Malformed JSON:** `RunAgentAndDeserializeAsync<T>` returns null on unparseable output. After
  retries are exhausted, that PR becomes a **degraded** digest entry (summary = "analysis
  unavailable", risk = unknown) instead of failing the whole batch.
- **Context-window guard:** `GetPullRequest` truncates `patch`/`body` to a configured character
  budget before returning to the model (track risk #1).

### Endpoints (from the sample, via `DaprWorkflowClient`)

`POST /start` · `GET /status/{instanceId}` · `POST /pause/{id}` · `POST /resume/{id}` ·
`POST /terminate/{id}`.

## 7. Testing

- **`GitHubDataReader` + risk model** — unit tests against committed fixture JSON: metric
  extraction (file count, diff size, has-tests, linked-issue) and `riskScore` weighting. No LLM.
- **`WriteDigestActivity`** — unit test: given analyses, assert markdown structure (ranked rows,
  risk flags, linked-issue status, headline placement).
- **Workflow shape** — LLM-free test with stubbed agent calls: asserts one analysis per PR number
  and deterministic sort by score.
- **Manual / integration** — documented run: start over a 20–50 PR batch, kill mid-run, restart,
  confirm resume and inspect `pr-digest.md`; traces visible in the Aspire dashboard (OpenTelemetry).

## 8. Output artifact

`pr-digest.md` — ranked list of open PRs, each with: rank, PR number + title, one-line summary,
linked-issue status, risk flags, and risk score; topped by the LLM-written headline. Degraded
entries are clearly marked.

## 9. Out of scope

GitHub data-collection/collector script · the Instruqt track (challenges, narrative) · sandbox/VM
image and provisioning · Ollama model pre-pull · any write-back to GitHub (app is strictly
read-only and produces a local report).
