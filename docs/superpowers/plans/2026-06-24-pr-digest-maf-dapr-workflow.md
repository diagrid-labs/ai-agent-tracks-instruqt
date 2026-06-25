# Reliable PR Digests (MAF + Dapr Workflow) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a .NET Aspire app where a Dapr Workflow fans out over a batch of open PRs, runs a Microsoft Agent Framework (MAF) agent per PR, and fans in to a ranked `pr-digest.md`.

**Architecture:** Deterministic logic (metrics, risk scoring, ranking, markdown rendering) lives in pure, unit-tested classes. A Dapr Workflow orchestrates the durable fan-out/fan-in as thin glue: an activity lists PRs, MAF agent calls analyze each PR (each an independently checkpointed durable step), code ranks the results, a summarize agent writes a headline, and an activity writes the file. Aspire owns the app, the Dapr OSS sidecar, a Valkey state store container, and (optionally) Ollama.

**Tech Stack:** .NET 10 / C#, .NET Aspire (AppHost + ServiceDefaults), Dapr OSS Workflow (`Dapr.Workflow`), `Diagrid.AI.Microsoft.AgentFramework` (MAF-in-workflow glue), `Microsoft.Extensions.AI` `IChatClient` over Ollama (`llama3.2:3b`), Valkey, xUnit.

## Global Constraints

- **Git:** Do NOT run `git add`, `git commit`, `git push`, or any state-changing git command. The user manages git manually. Each task ends with a build/test checkpoint, not a commit.
- **Target framework:** `net10.0` for all projects.
- **C# project conventions (copied from the sample):** `ImplicitUsings=enable`, `Nullable=enable`.
- **Pinned package versions:** `Diagrid.AI.Microsoft.AgentFramework` = `1.0.9`, `Dapr.Workflow` = `1.18.4`, `Microsoft.Extensions.AI.OpenAI` = `10.4.1`, `OpenAI` = `2.9.1`, `Aspire.Hosting.Valkey` = `13.4.6`. Aspire AppHost SDK = `Aspire.AppHost.Sdk/13.4.6`.
- **Unpinned packages** (`CommunityToolkit.Aspire.Hosting.Dapr`, xUnit packages): add with `dotnet add package` so the latest compatible version is restored; record the resolved version in the `.csproj`.
- **LLM provider:** Ollama, model `llama3.2:3b`, via an OpenAI-compatible `IChatClient` at `OLLAMA_BASE_URL` (default `http://localhost:11434/v1`). The OpenAI client requires a non-empty API key string which Ollama ignores.
- **Single configured repo dir:** the data location is one app setting, `REPO_DIR` (default `data/dapr/dapr`). The reader (tool + list activity) uses it; the workflow input also carries it for reporting. They must match.
- **Determinism rule:** the workflow orchestrator body performs NO I/O and NO `DateTime.Now`/`Random`/`Guid.NewGuid`. All I/O happens in activities or the MAF tool; all LLM calls happen inside `RunAgentAndDeserializeAsync` durable steps.
- **JSON contract for agent output:** agents emit prose only (`summary`, `linkedIssue`, `riskRationale` / `headline`). All risk numbers are computed in code, never by the model.

---

## File Structure

```
PrDigest.sln
├─ PrDigest.AppHost/                         Aspire orchestrator
│  ├─ PrDigest.AppHost.csproj
│  ├─ AppHost.cs                             AddValkey + AddProject + WithDaprSidecar
│  └─ resources/
│     └─ statestore.yaml                     Dapr state store -> Valkey
├─ PrDigest.ServiceDefaults/                 Aspire template (OpenTelemetry/health)
│  ├─ PrDigest.ServiceDefaults.csproj
│  └─ Extensions.cs
├─ PrDigest.ApiService/
│  ├─ PrDigest.ApiService.csproj
│  ├─ Program.cs                             IChatClient(Ollama), AddDaprAgents, endpoints
│  ├─ Models/PrModels.cs                     DTOs + workflow IO
│  ├─ Models/PrDigestJsonContext.cs          JSON source-gen context
│  ├─ Data/GitHubDataReader.cs               local JSON -> PullRequest DTOs
│  ├─ Risk/PrMetrics.cs                      compute metrics from a PullRequest (pure)
│  ├─ Risk/RiskModel.cs                      score + flags from metrics (pure)
│  ├─ Digest/DigestRanker.cs                 sort PrResult -> RankedPr (pure)
│  ├─ Digest/DigestMarkdownWriter.cs         render markdown (pure)
│  ├─ Tools/PrTools.cs                       GetPullRequest AIFunction (truncates)
│  ├─ Activities/ListOpenPullRequestsActivity.cs
│  ├─ Activities/WriteDigestActivity.cs
│  ├─ Agents/AgentNames.cs
│  ├─ Agents/AgentInstructions.cs
│  └─ Workflows/PrDigestWorkflow.cs
├─ PrDigest.Tests/
│  ├─ PrDigest.Tests.csproj
│  ├─ fixtures/data/dapr/dapr/prs/*.json     committed test PRs
│  ├─ GitHubDataReaderTests.cs
│  ├─ PrMetricsTests.cs
│  ├─ RiskModelTests.cs
│  ├─ PrToolsTests.cs
│  ├─ DigestRankerTests.cs
│  └─ DigestMarkdownWriterTests.cs
└─ data/dapr/dapr/prs/*.json                 runtime fixture snapshot (Task 13)
```

---

## Task 1: Solution & project scaffold

**Files:**
- Create: `PrDigest.sln`, `PrDigest.AppHost/`, `PrDigest.ServiceDefaults/`, `PrDigest.ApiService/`, `PrDigest.Tests/` (and their `.csproj`)

**Interfaces:**
- Produces: a buildable solution with project references wired. No code symbols yet.

- [ ] **Step 1: Generate the Aspire solution scaffold**

Run from the repo root (`C:\dev\diagrid-labs\ai-agent-tracks-instruqt`):

```powershell
dotnet new aspire --name PrDigest --output PrDigest
```

This creates `PrDigest/PrDigest.AppHost`, `PrDigest/PrDigest.ServiceDefaults`, and `PrDigest.sln`. Work inside the `PrDigest/` folder from here on (all paths below are relative to it).

- [ ] **Step 2: Add the ApiService (web) project and the test project**

```powershell
cd PrDigest
dotnet new web --name PrDigest.ApiService --output PrDigest.ApiService
dotnet new xunit --name PrDigest.Tests --output PrDigest.Tests
dotnet sln add PrDigest.ApiService/PrDigest.ApiService.csproj
dotnet sln add PrDigest.Tests/PrDigest.Tests.csproj
```

- [ ] **Step 3: Wire project references**

```powershell
dotnet add PrDigest.ApiService reference PrDigest.ServiceDefaults
dotnet add PrDigest.AppHost reference PrDigest.ApiService
dotnet add PrDigest.Tests reference PrDigest.ApiService
```

- [ ] **Step 4: Set target framework + conventions on every project**

In each of the four `.csproj` files, ensure the `<PropertyGroup>` contains:

```xml
<TargetFramework>net10.0</TargetFramework>
<ImplicitUsings>enable</ImplicitUsings>
<Nullable>enable</Nullable>
```

(The Aspire/xUnit templates may already set these; confirm and fix if not.)

Also pin the Aspire AppHost SDK in `PrDigest.AppHost/PrDigest.AppHost.csproj` to `13.4.6`:

```xml
<Project Sdk="Aspire.AppHost.Sdk/13.4.6">
```

(Adjust the version the template generated to `13.4.6`.)

- [ ] **Step 5: Build to verify the scaffold compiles**

Run: `dotnet build`
Expected: `Build succeeded` with 0 errors.

- [ ] **Step 6: Checkpoint** — scaffold builds. (Do not commit; the user manages git.)

---

## Task 2: Domain models & JSON source-gen context

**Files:**
- Create: `PrDigest.ApiService/Models/PrModels.cs`
- Create: `PrDigest.ApiService/Models/PrDigestJsonContext.cs`

**Interfaces:**
- Produces (used by nearly every later task — exact names/types):
  - `PullRequestFile(string Filename, int Additions, int Deletions, string? Patch)`
  - `PullRequest(int Number, string Title, string? Body, IReadOnlyList<PullRequestFile> Files)`
  - `PrMetrics(int FileCount, int Additions, int Deletions, bool HasTests, int? LinkedIssue)` with computed `int TotalChanges`
  - `RiskAssessment(int Score, IReadOnlyList<string> Flags)`
  - `PrListItem(int Number, string Title, PrMetrics Metrics)`
  - `PrAnalysis(string Summary, string? LinkedIssue, string RiskRationale)` (agent output)
  - `DigestHeader(string Headline)` (agent output)
  - `PrResult(int Number, string Title, PrMetrics Metrics, RiskAssessment Risk, PrAnalysis? Analysis, bool Degraded)`
  - `RankedPr(int Rank, PrResult Result)`
  - `PrDigestInput(string Id, string RepoDir, int MaxPrs)`
  - `PrDigestOutput(string RepoDir, int PrCount, string DigestPath, string Headline)`
  - `WriteDigestInput(string RepoDir, string Headline, IReadOnlyList<RankedPr> Ranked)`

- [ ] **Step 1: Create `Models/PrModels.cs`**

```csharp
using System.Text.Json.Serialization;

namespace PrDigest.ApiService.Models;

// ----- Input contract: raw PR JSON on disk (data/<owner>/<repo>/prs/<number>.json) -----
public record PullRequestFile(
    [property: JsonPropertyName("filename")] string Filename,
    [property: JsonPropertyName("additions")] int Additions,
    [property: JsonPropertyName("deletions")] int Deletions,
    [property: JsonPropertyName("patch")] string? Patch);

public record PullRequest(
    [property: JsonPropertyName("number")] int Number,
    [property: JsonPropertyName("title")] string Title,
    [property: JsonPropertyName("body")] string? Body,
    [property: JsonPropertyName("files")] IReadOnlyList<PullRequestFile> Files);

// ----- Deterministic, computed-in-code values -----
public record PrMetrics(
    int FileCount,
    int Additions,
    int Deletions,
    bool HasTests,
    int? LinkedIssue)
{
    public int TotalChanges => Additions + Deletions;
}

public record RiskAssessment(int Score, IReadOnlyList<string> Flags);

public record PrListItem(int Number, string Title, PrMetrics Metrics);

// ----- Agent outputs (prose only) -----
public record PrAnalysis(
    [property: JsonPropertyName("summary")] string Summary,
    [property: JsonPropertyName("linkedIssue")] string? LinkedIssue,
    [property: JsonPropertyName("riskRationale")] string RiskRationale);

public record DigestHeader(
    [property: JsonPropertyName("headline")] string Headline);

// ----- Carried through the workflow -----
public record PrResult(
    int Number,
    string Title,
    PrMetrics Metrics,
    RiskAssessment Risk,
    PrAnalysis? Analysis,
    bool Degraded);

public record RankedPr(int Rank, PrResult Result);

// ----- Workflow / activity IO -----
public record PrDigestInput(string Id, string RepoDir, int MaxPrs);
public record PrDigestOutput(string RepoDir, int PrCount, string DigestPath, string Headline);
public record WriteDigestInput(string RepoDir, string Headline, IReadOnlyList<RankedPr> Ranked);
```

- [ ] **Step 2: Create `Models/PrDigestJsonContext.cs`**

The MAF glue deserializes agent output via a source-gen context (mirrors the sample). Register the agent-output types.

```csharp
using System.Text.Json.Serialization;

namespace PrDigest.ApiService.Models;

[JsonSourceGenerationOptions(PropertyNameCaseInsensitive = true, PropertyNamingPolicy = JsonKnownNamingPolicy.CamelCase)]
[JsonSerializable(typeof(PrAnalysis))]
[JsonSerializable(typeof(DigestHeader))]
public partial class PrDigestJsonContext : JsonSerializerContext;
```

- [ ] **Step 3: Build to verify models compile**

Run: `dotnet build PrDigest.ApiService`
Expected: `Build succeeded`.

- [ ] **Step 4: Checkpoint** — models compile.

---

## Task 3: GitHubDataReader (read local PR JSON)

**Files:**
- Create: `PrDigest.ApiService/Data/GitHubDataReader.cs`
- Create test fixtures: `PrDigest.Tests/fixtures/data/dapr/dapr/prs/101.json`, `102.json`
- Test: `PrDigest.Tests/GitHubDataReaderTests.cs`

**Interfaces:**
- Consumes: `PullRequest`, `PullRequestFile` (Task 2).
- Produces:
  - `GitHubDataReader(string repoDir)` constructor
  - `IReadOnlyList<int> ListPullRequestNumbers(int max)` — ascending PR numbers, capped at `max`
  - `PullRequest GetPullRequest(int number)` — throws `FileNotFoundException` if missing

- [ ] **Step 1: Create the two fixture files**

`PrDigest.Tests/fixtures/data/dapr/dapr/prs/101.json`:

```json
{
  "number": 101,
  "title": "Fix retry backoff in workflow client",
  "body": "Fixes #45. Corrects exponential backoff.",
  "files": [
    { "filename": "src/Workflow/RetryPolicy.cs", "additions": 12, "deletions": 4, "patch": "@@ retry @@ small patch" },
    { "filename": "test/Workflow/RetryPolicyTests.cs", "additions": 30, "deletions": 0, "patch": "@@ tests @@ added" }
  ]
}
```

`PrDigest.Tests/fixtures/data/dapr/dapr/prs/102.json`:

```json
{
  "number": 102,
  "title": "Refactor scheduler internals",
  "body": "Large internal refactor with no linked issue.",
  "files": [
    { "filename": "src/A.cs", "additions": 400, "deletions": 200, "patch": "@@ big @@ patch" },
    { "filename": "src/B.cs", "additions": 150, "deletions": 90, "patch": "@@ big @@ patch" },
    { "filename": "src/C.cs", "additions": 80, "deletions": 10, "patch": "@@ big @@ patch" }
  ]
}
```

- [ ] **Step 2: Make the test project copy fixtures to output**

In `PrDigest.Tests/PrDigest.Tests.csproj`, inside an `<ItemGroup>`:

```xml
<None Include="fixtures/**/*.json" CopyToOutputDirectory="PreserveNewest" />
```

- [ ] **Step 3: Write the failing test**

`PrDigest.Tests/GitHubDataReaderTests.cs`:

```csharp
using PrDigest.ApiService.Data;
using Xunit;

namespace PrDigest.Tests;

public class GitHubDataReaderTests
{
    private static GitHubDataReader Reader() =>
        new(Path.Combine(AppContext.BaseDirectory, "fixtures", "data", "dapr", "dapr"));

    [Fact]
    public void ListPullRequestNumbers_returns_ascending_capped()
    {
        var numbers = Reader().ListPullRequestNumbers(max: 10);
        Assert.Equal(new[] { 101, 102 }, numbers);
    }

    [Fact]
    public void ListPullRequestNumbers_respects_max()
    {
        var numbers = Reader().ListPullRequestNumbers(max: 1);
        Assert.Equal(new[] { 101 }, numbers);
    }

    [Fact]
    public void GetPullRequest_reads_files()
    {
        var pr = Reader().GetPullRequest(102);
        Assert.Equal("Refactor scheduler internals", pr.Title);
        Assert.Equal(3, pr.Files.Count);
    }

    [Fact]
    public void GetPullRequest_missing_throws()
    {
        Assert.Throws<FileNotFoundException>(() => Reader().GetPullRequest(999));
    }
}
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `dotnet test PrDigest.Tests --filter GitHubDataReaderTests`
Expected: FAIL — `GitHubDataReader` does not exist (compile error).

- [ ] **Step 5: Implement `Data/GitHubDataReader.cs`**

```csharp
using System.Text.Json;
using PrDigest.ApiService.Models;

namespace PrDigest.ApiService.Data;

public sealed class GitHubDataReader(string repoDir)
{
    private static readonly JsonSerializerOptions Options = new(JsonSerializerDefaults.Web);

    private string PrsDir => Path.Combine(repoDir, "prs");

    public IReadOnlyList<int> ListPullRequestNumbers(int max)
    {
        if (!Directory.Exists(PrsDir))
            return [];

        return Directory.EnumerateFiles(PrsDir, "*.json")
            .Select(p => Path.GetFileNameWithoutExtension(p))
            .Where(n => int.TryParse(n, out _))
            .Select(int.Parse)
            .OrderBy(n => n)
            .Take(max)
            .ToList();
    }

    public PullRequest GetPullRequest(int number)
    {
        var path = Path.Combine(PrsDir, $"{number}.json");
        if (!File.Exists(path))
            throw new FileNotFoundException($"PR {number} not found at {path}", path);

        var json = File.ReadAllText(path);
        return JsonSerializer.Deserialize<PullRequest>(json, Options)
            ?? throw new InvalidOperationException($"PR {number} JSON deserialized to null.");
    }
}
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `dotnet test PrDigest.Tests --filter GitHubDataReaderTests`
Expected: PASS (4 tests).

- [ ] **Step 7: Checkpoint** — reader works against fixtures.

---

## Task 4: PrMetrics (compute deterministic metrics)

**Files:**
- Create: `PrDigest.ApiService/Risk/PrMetrics.cs` (static computer; the record itself is in `Models`)
- Test: `PrDigest.Tests/PrMetricsTests.cs`

**Interfaces:**
- Consumes: `PullRequest`, `PrMetrics` (Task 2).
- Produces: `static PrMetrics PrMetricsCalculator.Compute(PullRequest pr)`.
  - `HasTests` = any file whose path (case-insensitive) contains `test` or `spec`.
  - `LinkedIssue` = first integer N from regex `#(\d+)` or `(fixes|closes|resolves)\s+#(\d+)` in `Body`; `null` if none.

- [ ] **Step 1: Write the failing test**

`PrDigest.Tests/PrMetricsTests.cs`:

```csharp
using PrDigest.ApiService.Models;
using PrDigest.ApiService.Risk;
using Xunit;

namespace PrDigest.Tests;

public class PrMetricsTests
{
    private static PullRequest Pr(string? body, params PullRequestFile[] files) =>
        new(1, "t", body, files);

    [Fact]
    public void Counts_files_and_lines()
    {
        var m = PrMetricsCalculator.Compute(Pr(null,
            new("a.cs", 10, 5, null),
            new("b.cs", 2, 1, null)));
        Assert.Equal(2, m.FileCount);
        Assert.Equal(12, m.Additions);
        Assert.Equal(6, m.Deletions);
        Assert.Equal(18, m.TotalChanges);
    }

    [Fact]
    public void Detects_tests_by_filename()
    {
        var withTests = PrMetricsCalculator.Compute(Pr(null, new("src/FooTests.cs", 1, 0, null)));
        var noTests = PrMetricsCalculator.Compute(Pr(null, new("src/Foo.cs", 1, 0, null)));
        Assert.True(withTests.HasTests);
        Assert.False(noTests.HasTests);
    }

    [Theory]
    [InlineData("Fixes #45 now", 45)]
    [InlineData("see #7 for context", 7)]
    [InlineData("no reference here", null)]
    [InlineData(null, null)]
    public void Detects_linked_issue(string? body, int? expected)
    {
        Assert.Equal(expected, PrMetricsCalculator.Compute(Pr(body, new("a.cs", 1, 0, null))).LinkedIssue);
    }
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `dotnet test PrDigest.Tests --filter PrMetricsTests`
Expected: FAIL — `PrMetricsCalculator` does not exist.

- [ ] **Step 3: Implement `Risk/PrMetrics.cs`**

```csharp
using System.Text.RegularExpressions;
using PrDigest.ApiService.Models;

namespace PrDigest.ApiService.Risk;

public static partial class PrMetricsCalculator
{
    [GeneratedRegex(@"#(\d+)", RegexOptions.IgnoreCase)]
    private static partial Regex IssueRegex();

    public static PrMetrics Compute(PullRequest pr)
    {
        var fileCount = pr.Files.Count;
        var additions = pr.Files.Sum(f => f.Additions);
        var deletions = pr.Files.Sum(f => f.Deletions);
        var hasTests = pr.Files.Any(f =>
            f.Filename.Contains("test", StringComparison.OrdinalIgnoreCase) ||
            f.Filename.Contains("spec", StringComparison.OrdinalIgnoreCase));

        int? linkedIssue = null;
        if (!string.IsNullOrWhiteSpace(pr.Body))
        {
            var match = IssueRegex().Match(pr.Body);
            if (match.Success && int.TryParse(match.Groups[1].Value, out var n))
                linkedIssue = n;
        }

        return new PrMetrics(fileCount, additions, deletions, hasTests, linkedIssue);
    }
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `dotnet test PrDigest.Tests --filter PrMetricsTests`
Expected: PASS (6 cases).

- [ ] **Step 5: Checkpoint** — metric computation verified.

---

## Task 5: RiskModel (score + flags)

**Files:**
- Create: `PrDigest.ApiService/Risk/RiskModel.cs`
- Test: `PrDigest.Tests/RiskModelTests.cs`

**Interfaces:**
- Consumes: `PrMetrics`, `RiskAssessment` (Task 2).
- Produces: `static RiskAssessment RiskModel.Score(PrMetrics m)`.
  - Constants: `ManyFilesThreshold = 10`, `LargeDiffThreshold = 500`.
  - Flags + weights: `"many-files"` (files > 10) → 3; `"large-diff"` (TotalChanges > 500) → 3; `"no-tests"` (!HasTests) → 2; `"no-linked-issue"` (LinkedIssue is null) → 1.
  - `Score` = sum of triggered weights (0–9). `Flags` in the fixed order above.

- [ ] **Step 1: Write the failing test**

`PrDigest.Tests/RiskModelTests.cs`:

```csharp
using PrDigest.ApiService.Models;
using PrDigest.ApiService.Risk;
using Xunit;

namespace PrDigest.Tests;

public class RiskModelTests
{
    [Fact]
    public void Low_risk_pr_with_tests_and_linked_issue_scores_zero()
    {
        var m = new PrMetrics(FileCount: 2, Additions: 10, Deletions: 5, HasTests: true, LinkedIssue: 45);
        var r = RiskModel.Score(m);
        Assert.Equal(0, r.Score);
        Assert.Empty(r.Flags);
    }

    [Fact]
    public void No_tests_and_no_linked_issue_flags_and_scores()
    {
        var m = new PrMetrics(FileCount: 2, Additions: 10, Deletions: 5, HasTests: false, LinkedIssue: null);
        var r = RiskModel.Score(m);
        Assert.Equal(3, r.Score); // no-tests(2) + no-linked-issue(1)
        Assert.Equal(new[] { "no-tests", "no-linked-issue" }, r.Flags);
    }

    [Fact]
    public void All_signals_trigger_max_score_and_ordered_flags()
    {
        var m = new PrMetrics(FileCount: 11, Additions: 400, Deletions: 200, HasTests: false, LinkedIssue: null);
        var r = RiskModel.Score(m);
        Assert.Equal(9, r.Score);
        Assert.Equal(new[] { "many-files", "large-diff", "no-tests", "no-linked-issue" }, r.Flags);
    }
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `dotnet test PrDigest.Tests --filter RiskModelTests`
Expected: FAIL — `RiskModel` does not exist.

- [ ] **Step 3: Implement `Risk/RiskModel.cs`**

```csharp
using PrDigest.ApiService.Models;

namespace PrDigest.ApiService.Risk;

public static class RiskModel
{
    public const int ManyFilesThreshold = 10;
    public const int LargeDiffThreshold = 500;

    public static RiskAssessment Score(PrMetrics m)
    {
        var flags = new List<string>();
        var score = 0;

        if (m.FileCount > ManyFilesThreshold) { flags.Add("many-files"); score += 3; }
        if (m.TotalChanges > LargeDiffThreshold) { flags.Add("large-diff"); score += 3; }
        if (!m.HasTests) { flags.Add("no-tests"); score += 2; }
        if (m.LinkedIssue is null) { flags.Add("no-linked-issue"); score += 1; }

        return new RiskAssessment(score, flags);
    }
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `dotnet test PrDigest.Tests --filter RiskModelTests`
Expected: PASS (3 tests).

- [ ] **Step 5: Checkpoint** — risk scoring verified.

---

## Task 6: PrTools.GetPullRequest (MAF tool with truncation)

**Files:**
- Create: `PrDigest.ApiService/Tools/PrTools.cs`
- Test: `PrDigest.Tests/PrToolsTests.cs`

**Interfaces:**
- Consumes: `GitHubDataReader` (Task 3), `PrMetricsCalculator` (Task 4), `PullRequest` (Task 2).
- Produces:
  - `PrTools(GitHubDataReader reader, int maxBodyChars = 800, int maxPatchChars = 600, int maxFiles = 15)`
  - `[Description(...)] PrToolResult GetPullRequest(int number)` — instance method registered via `AIFunctionFactory.Create`.
  - `record PrToolResult(int Number, string Title, string Body, IReadOnlyList<PrFileSummary> Files, PrMetrics Metrics)`
  - `record PrFileSummary(string Filename, int Additions, int Deletions, string Patch)`
  - Truncation: `Body` cut to `maxBodyChars`, each `Patch` cut to `maxPatchChars` (append `"…[truncated]"` when cut), at most `maxFiles` files returned.

- [ ] **Step 1: Write the failing test**

`PrDigest.Tests/PrToolsTests.cs`:

```csharp
using PrDigest.ApiService.Data;
using PrDigest.ApiService.Tools;
using Xunit;

namespace PrDigest.Tests;

public class PrToolsTests
{
    private static PrTools Tools(int maxPatch = 600) =>
        new(new GitHubDataReader(Path.Combine(AppContext.BaseDirectory, "fixtures", "data", "dapr", "dapr")),
            maxBodyChars: 800, maxPatchChars: maxPatch, maxFiles: 15);

    [Fact]
    public void Returns_pr_with_computed_metrics()
    {
        var result = Tools().GetPullRequest(101);
        Assert.Equal(101, result.Number);
        Assert.Equal(2, result.Files.Count);
        Assert.True(result.Metrics.HasTests);
        Assert.Equal(45, result.Metrics.LinkedIssue);
    }

    [Fact]
    public void Truncates_long_patches()
    {
        var result = Tools(maxPatch: 5).GetPullRequest(101);
        Assert.All(result.Files, f => Assert.True(f.Patch.Length <= 5 + "…[truncated]".Length));
        Assert.Contains(result.Files, f => f.Patch.EndsWith("…[truncated]"));
    }
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `dotnet test PrDigest.Tests --filter PrToolsTests`
Expected: FAIL — `PrTools` does not exist.

- [ ] **Step 3: Implement `Tools/PrTools.cs`**

```csharp
using System.ComponentModel;
using PrDigest.ApiService.Data;
using PrDigest.ApiService.Models;
using PrDigest.ApiService.Risk;

namespace PrDigest.ApiService.Tools;

public record PrFileSummary(string Filename, int Additions, int Deletions, string Patch);

public record PrToolResult(
    int Number,
    string Title,
    string Body,
    IReadOnlyList<PrFileSummary> Files,
    PrMetrics Metrics);

public sealed class PrTools(
    GitHubDataReader reader,
    int maxBodyChars = 800,
    int maxPatchChars = 600,
    int maxFiles = 15)
{
    private const string TruncatedMarker = "…[truncated]";

    [Description("Fetches one pull request's files, diff, and body from the local data snapshot. Returns truncated content plus computed metrics. Call once per PR number.")]
    public PrToolResult GetPullRequest(int number)
    {
        var pr = reader.GetPullRequest(number);
        var metrics = PrMetricsCalculator.Compute(pr);

        var files = pr.Files
            .Take(maxFiles)
            .Select(f => new PrFileSummary(
                f.Filename, f.Additions, f.Deletions, Truncate(f.Patch ?? string.Empty, maxPatchChars)))
            .ToList();

        return new PrToolResult(pr.Number, pr.Title, Truncate(pr.Body ?? string.Empty, maxBodyChars), files, metrics);
    }

    private static string Truncate(string value, int max) =>
        value.Length <= max ? value : value[..max] + TruncatedMarker;
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `dotnet test PrDigest.Tests --filter PrToolsTests`
Expected: PASS (2 tests).

- [ ] **Step 5: Checkpoint** — tool + truncation verified.

---

## Task 7: DigestRanker (deterministic sort)

**Files:**
- Create: `PrDigest.ApiService/Digest/DigestRanker.cs`
- Test: `PrDigest.Tests/DigestRankerTests.cs`

**Interfaces:**
- Consumes: `PrResult`, `RankedPr` (Task 2).
- Produces: `static IReadOnlyList<RankedPr> DigestRanker.Rank(IReadOnlyList<PrResult> results)`.
  - Sort: `Risk.Score` desc, then `Metrics.TotalChanges` desc, then `Number` asc (fully deterministic).
  - `Rank` assigned 1..n in sorted order.

- [ ] **Step 1: Write the failing test**

`PrDigest.Tests/DigestRankerTests.cs`:

```csharp
using PrDigest.ApiService.Digest;
using PrDigest.ApiService.Models;
using Xunit;

namespace PrDigest.Tests;

public class DigestRankerTests
{
    private static PrResult Result(int number, int score, int totalChanges)
    {
        var metrics = new PrMetrics(FileCount: 1, Additions: totalChanges, Deletions: 0, HasTests: true, LinkedIssue: 1);
        return new PrResult(number, $"PR {number}", metrics, new RiskAssessment(score, []), null, Degraded: true);
    }

    [Fact]
    public void Sorts_by_score_then_changes_then_number()
    {
        var ranked = DigestRanker.Rank([
            Result(number: 1, score: 2, totalChanges: 10),
            Result(number: 2, score: 5, totalChanges: 10),
            Result(number: 3, score: 5, totalChanges: 99),
        ]);

        Assert.Equal(new[] { 3, 2, 1 }, ranked.Select(r => r.Result.Number));
        Assert.Equal(new[] { 1, 2, 3 }, ranked.Select(r => r.Rank));
    }
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `dotnet test PrDigest.Tests --filter DigestRankerTests`
Expected: FAIL — `DigestRanker` does not exist.

- [ ] **Step 3: Implement `Digest/DigestRanker.cs`**

```csharp
using PrDigest.ApiService.Models;

namespace PrDigest.ApiService.Digest;

public static class DigestRanker
{
    public static IReadOnlyList<RankedPr> Rank(IReadOnlyList<PrResult> results) =>
        results
            .OrderByDescending(r => r.Risk.Score)
            .ThenByDescending(r => r.Metrics.TotalChanges)
            .ThenBy(r => r.Number)
            .Select((r, i) => new RankedPr(i + 1, r))
            .ToList();
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `dotnet test PrDigest.Tests --filter DigestRankerTests`
Expected: PASS.

- [ ] **Step 5: Checkpoint** — ranking verified.

---

## Task 8: DigestMarkdownWriter (render markdown)

**Files:**
- Create: `PrDigest.ApiService/Digest/DigestMarkdownWriter.cs`
- Test: `PrDigest.Tests/DigestMarkdownWriterTests.cs`

**Interfaces:**
- Consumes: `RankedPr`, `PrResult`, `PrAnalysis`, `PrMetrics`, `RiskAssessment` (Task 2).
- Produces: `static string DigestMarkdownWriter.Render(string repoDir, string headline, IReadOnlyList<RankedPr> ranked)`.
  - Output: `# PR Digest — {repoDir}` title, a `> {headline}` blockquote, then a markdown table with columns `Rank | PR | Summary | Linked issue | Risk | Flags`.
  - Normal row: PR `#{Number} {Title}`, `Analysis.Summary`, linked issue `#{Metrics.LinkedIssue}` or `—`, `Risk.Score`, comma-joined `Risk.Flags` (or `—`).
  - Degraded row (`Degraded == true`): Summary cell = `_analysis unavailable_`.

- [ ] **Step 1: Write the failing test**

`PrDigest.Tests/DigestMarkdownWriterTests.cs`:

```csharp
using PrDigest.ApiService.Digest;
using PrDigest.ApiService.Models;
using Xunit;

namespace PrDigest.Tests;

public class DigestMarkdownWriterTests
{
    [Fact]
    public void Renders_header_normal_and_degraded_rows()
    {
        var normal = new PrResult(
            101, "Fix retry backoff",
            new PrMetrics(2, 42, 4, HasTests: true, LinkedIssue: 45),
            new RiskAssessment(1, new[] { "no-linked-issue" }),
            new PrAnalysis("Corrects backoff math.", "#45", "Low blast radius."),
            Degraded: false);

        var degraded = new PrResult(
            102, "Refactor scheduler",
            new PrMetrics(3, 600, 300, HasTests: false, LinkedIssue: null),
            new RiskAssessment(6, new[] { "large-diff", "no-tests" }),
            Analysis: null, Degraded: true);

        var md = DigestMarkdownWriter.Render("data/dapr/dapr", "Two PRs need attention.",
            [new RankedPr(1, degraded), new RankedPr(2, normal)]);

        Assert.Contains("# PR Digest — data/dapr/dapr", md);
        Assert.Contains("> Two PRs need attention.", md);
        Assert.Contains("| Rank | PR | Summary | Linked issue | Risk | Flags |", md);
        Assert.Contains("Corrects backoff math.", md);
        Assert.Contains("#45", md);
        Assert.Contains("_analysis unavailable_", md);
        Assert.Contains("large-diff, no-tests", md);
    }
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `dotnet test PrDigest.Tests --filter DigestMarkdownWriterTests`
Expected: FAIL — `DigestMarkdownWriter` does not exist.

- [ ] **Step 3: Implement `Digest/DigestMarkdownWriter.cs`**

```csharp
using System.Text;
using PrDigest.ApiService.Models;

namespace PrDigest.ApiService.Digest;

public static class DigestMarkdownWriter
{
    public static string Render(string repoDir, string headline, IReadOnlyList<RankedPr> ranked)
    {
        var sb = new StringBuilder();
        sb.AppendLine($"# PR Digest — {repoDir}");
        sb.AppendLine();
        sb.AppendLine($"> {headline}");
        sb.AppendLine();
        sb.AppendLine("| Rank | PR | Summary | Linked issue | Risk | Flags |");
        sb.AppendLine("|---|---|---|---|---|---|");

        foreach (var entry in ranked)
        {
            var r = entry.Result;
            var pr = $"#{r.Number} {r.Title}";
            var summary = r.Degraded ? "_analysis unavailable_" : Clean(r.Analysis!.Summary);
            var linked = r.Metrics.LinkedIssue is { } n ? $"#{n}" : "—";
            var flags = r.Risk.Flags.Count > 0 ? string.Join(", ", r.Risk.Flags) : "—";
            sb.AppendLine($"| {entry.Rank} | {Clean(pr)} | {summary} | {linked} | {r.Risk.Score} | {flags} |");
        }

        return sb.ToString();
    }

    // Keep cell content single-line and pipe-safe.
    private static string Clean(string value) =>
        value.Replace("|", "\\|").ReplaceLineEndings(" ").Trim();
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `dotnet test PrDigest.Tests --filter DigestMarkdownWriterTests`
Expected: PASS.

- [ ] **Step 5: Run the full test suite (regression check)**

Run: `dotnet test`
Expected: PASS — all tests from Tasks 3–8 green.

- [ ] **Step 6: Checkpoint** — all pure logic verified.

---

## Task 9: Activities (list PRs, write digest)

**Files:**
- Create: `PrDigest.ApiService/Activities/ListOpenPullRequestsActivity.cs`
- Create: `PrDigest.ApiService/Activities/WriteDigestActivity.cs`

**Interfaces:**
- Consumes: `GitHubDataReader` (Task 3), `PrMetricsCalculator` (Task 4), `DigestMarkdownWriter` (Task 8), `PrListItem`, `WriteDigestInput` (Task 2).
- Produces (called by the workflow in Task 11):
  - `ListOpenPullRequestsActivity` : `WorkflowActivity<int, IReadOnlyList<PrListItem>>` — input is `maxPrs`.
  - `WriteDigestActivity` : `WorkflowActivity<WriteDigestInput, string>` — returns the written file path.
  - `WriteDigestActivity` writes to `{DIGEST_OUTPUT_DIR or current dir}/pr-digest.md`.

> These activities are thin glue over already-tested pure code, so they are verified by build now and by the integration runbook in Task 13 (not by isolated unit tests — they depend on `WorkflowActivityContext` and DI-injected services).

- [ ] **Step 1: Implement `Activities/ListOpenPullRequestsActivity.cs`**

```csharp
using Dapr.Workflow;
using PrDigest.ApiService.Data;
using PrDigest.ApiService.Models;
using PrDigest.ApiService.Risk;

namespace PrDigest.ApiService.Activities;

public sealed partial class ListOpenPullRequestsActivity(
    GitHubDataReader reader,
    ILogger<ListOpenPullRequestsActivity> logger)
    : WorkflowActivity<int, IReadOnlyList<PrListItem>>
{
    public override Task<IReadOnlyList<PrListItem>> RunAsync(WorkflowActivityContext context, int maxPrs)
    {
        var numbers = reader.ListPullRequestNumbers(maxPrs);
        LogListing(logger, numbers.Count);

        IReadOnlyList<PrListItem> items = numbers
            .Select(n =>
            {
                var pr = reader.GetPullRequest(n);
                return new PrListItem(pr.Number, pr.Title, PrMetricsCalculator.Compute(pr));
            })
            .ToList();

        return Task.FromResult(items);
    }

    [LoggerMessage(LogLevel.Information, "Listing {Count} pull requests for digest")]
    static partial void LogListing(ILogger logger, int count);
}
```

- [ ] **Step 2: Implement `Activities/WriteDigestActivity.cs`**

```csharp
using Dapr.Workflow;
using PrDigest.ApiService.Digest;
using PrDigest.ApiService.Models;

namespace PrDigest.ApiService.Activities;

public sealed partial class WriteDigestActivity(ILogger<WriteDigestActivity> logger)
    : WorkflowActivity<WriteDigestInput, string>
{
    public override async Task<string> RunAsync(WorkflowActivityContext context, WriteDigestInput input)
    {
        var outputDir = Environment.GetEnvironmentVariable("DIGEST_OUTPUT_DIR") ?? Directory.GetCurrentDirectory();
        var path = Path.Combine(outputDir, "pr-digest.md");

        var markdown = DigestMarkdownWriter.Render(input.RepoDir, input.Headline, input.Ranked);
        await File.WriteAllTextAsync(path, markdown);

        LogWrote(logger, path, input.Ranked.Count);
        return path;
    }

    [LoggerMessage(LogLevel.Information, "Wrote digest to {Path} with {Count} PRs")]
    static partial void LogWrote(ILogger logger, string path, int count);
}
```

- [ ] **Step 3: Build to verify activities compile**

Run: `dotnet build PrDigest.ApiService`
Expected: `Build succeeded`.

- [ ] **Step 4: Checkpoint** — activities compile.

---

## Task 10: Agents (names + instructions) and DI registration

**Files:**
- Create: `PrDigest.ApiService/Agents/AgentNames.cs`
- Create: `PrDigest.ApiService/Agents/AgentInstructions.cs`
- Modify: `PrDigest.ApiService/PrDigest.ApiService.csproj` (packages)
- Modify: `PrDigest.ApiService/Program.cs`

**Interfaces:**
- Consumes: `PrTools` (Task 6), `PrDigestJsonContext` (Task 2), `GitHubDataReader` (Task 3), activities (Task 9), `PrDigestWorkflow` (forward ref — Task 11), `IChatClient`.
- Produces:
  - `AgentNames.PrAnalyzer` = `"PrAnalyzerAgent"`, `AgentNames.Summarize` = `"SummarizeAgent"`.
  - `AgentInstructions.PrAnalyzer`, `AgentInstructions.Summarize` (string constants).
  - Registered DI: `GitHubDataReader` (bound to `REPO_DIR`), `IChatClient` (Ollama), `AddDaprAgents(...)` with both agents, both activities, and the workflow; HTTP endpoints `/start`, `/status/{id}`, `/pause|resume|terminate/{id}`.

- [ ] **Step 1: Add the required packages to `PrDigest.ApiService.csproj`**

```powershell
dotnet add PrDigest.ApiService package Diagrid.AI.Microsoft.AgentFramework --version 1.0.9
dotnet add PrDigest.ApiService package Dapr.Workflow --version 1.18.4
dotnet add PrDigest.ApiService package Microsoft.Extensions.AI.OpenAI --version 10.4.1
dotnet add PrDigest.ApiService package OpenAI --version 2.9.1
```

Then add to the `<PropertyGroup>` in that csproj (the sample suppresses this preview warning):

```xml
<NoWarn>$(NoWarn);DAPR_CONVERSATION</NoWarn>
```

- [ ] **Step 2: Create `Agents/AgentNames.cs`**

```csharp
namespace PrDigest.ApiService.Agents;

internal static class AgentNames
{
    public const string PrAnalyzer = "PrAnalyzerAgent";
    public const string Summarize = "SummarizeAgent";
}
```

- [ ] **Step 3: Create `Agents/AgentInstructions.cs`**

```csharp
namespace PrDigest.ApiService.Agents;

internal static class AgentInstructions
{
    public const string PrAnalyzer =
        "You are a pull-request analyst for an open-source maintainer. " +
        "When given a PR number, call the GetPullRequest tool exactly once to fetch its files, diff, and body. " +
        "Write a one-sentence plain-English summary of what the change does. " +
        "From the tool's metrics, state the linked issue as \"#<number>\" if metrics.linkedIssue is present, otherwise null. " +
        "Write a one-sentence risk rationale referring to the metrics (file count, total changes, whether tests are present, whether an issue is linked). " +
        "Do NOT invent or compute a numeric risk score — that is handled elsewhere. " +
        "Always respond with strict JSON only — no prose, no code fences. " +
        "Schema: {\"summary\": string, \"linkedIssue\": string|null, \"riskRationale\": string}.";

    public const string Summarize =
        "You are a maintainer's digest editor. " +
        "Given the top-ranked pull requests for a repository (each with rank, title, risk score, and flags), " +
        "write a 2-3 sentence headline that tells the maintainer where to focus first. Lead with the highest-risk PRs. " +
        "Always respond with strict JSON only — no prose, no code fences. " +
        "Schema: {\"headline\": string}.";
}
```

- [ ] **Step 4: Replace `Program.cs` with the wiring**

```csharp
using System.ClientModel;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.AI;
using Dapr.Workflow;
using Diagrid.AI.Microsoft.AgentFramework.Hosting;
using OpenAI;
using PrDigest.ApiService.Activities;
using PrDigest.ApiService.Agents;
using PrDigest.ApiService.Data;
using PrDigest.ApiService.Models;
using PrDigest.ApiService.Tools;
using PrDigest.ApiService.Workflows;

const string Model = "llama3.2:3b";

var builder = WebApplication.CreateBuilder(args);
builder.AddServiceDefaults();

var repoDir = Environment.GetEnvironmentVariable("REPO_DIR") ?? "data/dapr/dapr";
var ollamaBase = Environment.GetEnvironmentVariable("OLLAMA_BASE_URL") ?? "http://localhost:11434/v1";

builder.Services.AddSingleton(new GitHubDataReader(repoDir));

// OpenAI-compatible client pointed at Ollama. Ollama ignores the API key but the client requires one.
builder.Services.AddSingleton<IChatClient>(_ =>
    new OpenAIClient(
            new ApiKeyCredential("ollama"),
            new OpenAIClientOptions { Endpoint = new Uri(ollamaBase) })
        .GetChatClient(Model)
        .AsIChatClient());

builder.Services.AddSingleton(sp => new PrTools(sp.GetRequiredService<GitHubDataReader>()));

builder.Services.AddDaprAgents(
        opt => opt.AddContext(() => PrDigestJsonContext.Default),
        opt =>
        {
            opt.RegisterWorkflow<PrDigestWorkflow>();
            opt.RegisterActivity<ListOpenPullRequestsActivity>();
            opt.RegisterActivity<WriteDigestActivity>();
        })
    .WithAgent(sp =>
    {
        AITool[] tools = [AIFunctionFactory.Create(sp.GetRequiredService<PrTools>().GetPullRequest)];
        return sp.GetRequiredService<IChatClient>()
            .AsAIAgent(instructions: AgentInstructions.PrAnalyzer, name: AgentNames.PrAnalyzer, tools: tools);
    })
    .WithAgent(sp => sp.GetRequiredService<IChatClient>()
        .AsAIAgent(instructions: AgentInstructions.Summarize, name: AgentNames.Summarize));

var app = builder.Build();

app.MapPost("/start", async (
    [FromServices] DaprWorkflowClient workflowClient,
    [FromBody] PrDigestInput input) =>
{
    var instanceId = await workflowClient.ScheduleNewWorkflowAsync(
        name: nameof(PrDigestWorkflow), instanceId: input.Id, input: input);
    return Results.Ok(new { instanceId });
});

app.MapGet("/status/{instanceId}", async (
    [FromRoute] string instanceId,
    [FromServices] DaprWorkflowClient workflowClient) =>
{
    var state = await workflowClient.GetWorkflowStateAsync(instanceId);
    if (state is null || !state.Exists)
        return Results.NotFound($"Workflow instance '{instanceId}' not found.");

    var output = state.ReadOutputAs<PrDigestOutput>();
    return Results.Ok(new { state, output });
});

app.MapPost("pause/{instanceId}", async (
    [FromRoute] string instanceId, [FromServices] DaprWorkflowClient c) =>
{ await c.SuspendWorkflowAsync(instanceId); return Results.Accepted(); });

app.MapPost("resume/{instanceId}", async (
    [FromRoute] string instanceId, [FromServices] DaprWorkflowClient c) =>
{ await c.ResumeWorkflowAsync(instanceId); return Results.Accepted(); });

app.MapPost("terminate/{instanceId}", async (
    [FromRoute] string instanceId, [FromServices] DaprWorkflowClient c) =>
{ await c.TerminateWorkflowAsync(instanceId); return Results.Accepted(); });

app.MapDefaultEndpoints();
app.Run();
```

> **Confirm during build:** the exact namespaces `Diagrid.AI.Microsoft.AgentFramework.Hosting` (for `AddDaprAgents`/`WithAgent`/`AsAIAgent`) and the `OpenAIClient(ApiKeyCredential, OpenAIClientOptions)` constructor. These mirror the sample (`EnterpriseDiagnosticsMAF/Program.cs`) and the OpenAI v2 SDK. If `AsIChatClient`/`AsAIAgent` resolve from different namespaces in `1.0.9`, fix the `using` and keep the call shapes.

- [ ] **Step 5: Build to verify wiring compiles**

Run: `dotnet build PrDigest.ApiService`
Expected: `Build succeeded`. (The workflow type referenced here is created in Task 11; if doing tasks strictly in order, expect a single "PrDigestWorkflow not found" error here and resolve it after Task 11. Recommended: implement Task 11 before this build step, or stub the workflow class first.)

- [ ] **Step 6: Checkpoint** — agents + DI wiring in place.

---

## Task 11: PrDigestWorkflow orchestrator

**Files:**
- Create: `PrDigest.ApiService/Workflows/PrDigestWorkflow.cs`

**Interfaces:**
- Consumes: `PrDigestInput`/`PrDigestOutput`/`PrListItem`/`PrResult`/`PrAnalysis`/`DigestHeader`/`WriteDigestInput` (Task 2), `RiskModel` (Task 5), `DigestRanker` (Task 7), `AgentNames` (Task 10), activities (Task 9), and the MAF glue extensions `context.GetAgent` / `context.RunAgentAndDeserializeAsync<T>` (from `Diagrid.AI.Microsoft.AgentFramework.Runtime`, per the sample).
- Produces: `PrDigestWorkflow : Workflow<PrDigestInput, PrDigestOutput>` registered in Task 10.

- [ ] **Step 1: Implement `Workflows/PrDigestWorkflow.cs`**

```csharp
using Dapr.Workflow;
using Diagrid.AI.Microsoft.AgentFramework.Runtime;
using PrDigest.ApiService.Activities;
using PrDigest.ApiService.Agents;
using PrDigest.ApiService.Digest;
using PrDigest.ApiService.Models;
using PrDigest.ApiService.Risk;

namespace PrDigest.ApiService.Workflows;

public sealed partial class PrDigestWorkflow : Workflow<PrDigestInput, PrDigestOutput>
{
    public override async Task<PrDigestOutput> RunAsync(WorkflowContext context, PrDigestInput input)
    {
        var logger = context.CreateReplaySafeLogger<PrDigestWorkflow>();
        LogStart(logger, context.InstanceId, input.RepoDir, input.MaxPrs);

        var prs = await context.CallActivityAsync<IReadOnlyList<PrListItem>>(
            nameof(ListOpenPullRequestsActivity), input.MaxPrs);

        var analyzer = context.GetAgent(AgentNames.PrAnalyzer);

        // Durable fan-out: one checkpointed agent call per PR.
        var analysisTasks = prs.Select(pr => AnalyzeOneAsync(context, analyzer, pr, logger)).ToList();
        var results = await Task.WhenAll(analysisTasks);

        // Deterministic fan-in.
        var ranked = DigestRanker.Rank(results);

        var summarizer = context.GetAgent(AgentNames.Summarize);
        var header = await context.RunAgentAndDeserializeAsync<DigestHeader>(
            agent: summarizer, message: BuildHeadlinePrompt(ranked), logger: logger);
        var headline = header?.Headline ?? "Digest summary unavailable.";

        var path = await context.CallActivityAsync<string>(
            nameof(WriteDigestActivity), new WriteDigestInput(input.RepoDir, headline, ranked));

        LogDone(logger, context.InstanceId, results.Length, path);
        return new PrDigestOutput(input.RepoDir, results.Length, path, headline);
    }

    private static async Task<PrResult> AnalyzeOneAsync(
        WorkflowContext context, object analyzer, PrListItem pr, ILogger logger)
    {
        var risk = RiskModel.Score(pr.Metrics);

        var analysis = await context.RunAgentAndDeserializeAsync<PrAnalysis>(
            agent: analyzer,
            message: $"Analyze pull request #{pr.Number}. Call GetPullRequest({pr.Number}) once, then return strict JSON " +
                     "{\"summary\": string, \"linkedIssue\": string|null, \"riskRationale\": string}.",
            logger: logger);

        return analysis is null
            ? new PrResult(pr.Number, pr.Title, pr.Metrics, risk, Analysis: null, Degraded: true)
            : new PrResult(pr.Number, pr.Title, pr.Metrics, risk, analysis, Degraded: false);
    }

    private static string BuildHeadlinePrompt(IReadOnlyList<RankedPr> ranked)
    {
        var top = ranked.Take(5).Select(r =>
            $"[rank={r.Rank} pr=#{r.Result.Number} title=\"{r.Result.Title}\" risk={r.Result.Risk.Score} " +
            $"flags={string.Join("/", r.Result.Risk.Flags)}]");
        return "Top pull requests: " + string.Join(" ", top) +
               " Write a 2-3 sentence headline. Return strict JSON: {\"headline\": string}.";
    }

    [LoggerMessage(LogLevel.Information, "Starting PR digest {InstanceId} for {RepoDir} (max {MaxPrs})")]
    static partial void LogStart(ILogger logger, string instanceId, string repoDir, int maxPrs);

    [LoggerMessage(LogLevel.Information, "Completed PR digest {InstanceId}: {Count} PRs -> {Path}")]
    static partial void LogDone(ILogger logger, string instanceId, int count, string path);
}
```

> **Confirm during build:** the `analyzer`/`summarizer` static type returned by `context.GetAgent(...)` (typed as `object` above to avoid guessing). Once the build resolves it, replace `object` with the real type and pass agents directly. Also confirm `RunAgentAndDeserializeAsync` accepts a retry/options overload; if it does, wrap both agent calls with a `WorkflowTaskOptions { RetryPolicy = ... }` (3 attempts, exponential backoff) per the spec's resiliency requirement. If no such overload exists in `1.0.9`, leave the calls as-is (graceful-degradation on null already covers a failed analysis) and note it.

- [ ] **Step 2: Build the whole solution**

Run: `dotnet build`
Expected: `Build succeeded`. Fix any namespace/type mismatches surfaced by the two "confirm during build" notes (Tasks 10 & 11).

- [ ] **Step 3: Run the full test suite (regression)**

Run: `dotnet test`
Expected: PASS — pure-logic tests still green.

- [ ] **Step 4: Checkpoint** — full solution compiles, unit tests pass.

---

## Task 12: AppHost wiring (Valkey + Dapr sidecar) and Dapr component

**Files:**
- Modify: `PrDigest.AppHost/PrDigest.AppHost.csproj` (packages + copy component to output)
- Modify: `PrDigest.AppHost/AppHost.cs`
- Create: `PrDigest.AppHost/resources/statestore.yaml`

**Interfaces:**
- Consumes: `Projects.PrDigest_ApiService` (Aspire-generated), the `pr-digest` Dapr app id, the `statestore` component.
- Produces: a runnable Aspire app graph (ApiService + Dapr sidecar + Valkey).

- [ ] **Step 1: Add the Aspire hosting packages**

```powershell
dotnet add PrDigest.AppHost package CommunityToolkit.Aspire.Hosting.Dapr
dotnet add PrDigest.AppHost package Aspire.Hosting.Valkey --version 13.4.6
```

Pin `Aspire.Hosting.Valkey` to `13.4.6` (Global Constraints). Record the resolved `CommunityToolkit.Aspire.Hosting.Dapr` version in the csproj.

- [ ] **Step 2: Replace `AppHost.cs`**

```csharp
using CommunityToolkit.Aspire.Hosting.Dapr;

var builder = DistributedApplication.CreateBuilder(args);

// Aspire owns the Valkey container life cycle (started/stopped with the run).
// Host port pinned to 16379 to match the redisHost in resources/statestore.yaml.
var stateStore = builder.AddValkey("statestore", port: 16379);

builder.AddProject<Projects.PrDigest_ApiService>("pr-digest")
    .WithReference(stateStore)
    .WaitFor(stateStore)
    // Pin the API's HTTP endpoint to a fixed host port so the RUNBOOK URLs are stable.
    .WithEndpoint("http", endpoint => endpoint.Port = 5090)
    .WithDaprSidecar(new DaprSidecarOptions
    {
        AppId = "pr-digest",
         ResourcesPaths = ["resources"]
    });

builder.Build().Run();
```

> **Confirm during build:** the `WithDaprSidecar` option property names in the installed `CommunityToolkit.Aspire.Hosting.Dapr` version (`AppId`, `ResourcesPaths`) and the `AddValkey` signature. Adjust to the resolved API; the intent (Aspire-managed Valkey + a Dapr sidecar pointed at the local `resources` folder) is fixed. `ResourcesPaths` is resolved relative to the AppHost project directory, so `["resources"]` points at `PrDigest.AppHost/resources`. The `.WithEndpoint("http", endpoint => endpoint.Port = 5090)` call pins the API's reachable HTTP port to `5090` (so the RUNBOOK URLs are stable); it modifies the existing launch-profile `http` endpoint rather than adding a new one.

- [ ] **Step 3: Create the Dapr state store component `PrDigest.AppHost/resources/statestore.yaml`**

```yaml
apiVersion: dapr.io/v1alpha1
kind: Component
metadata:
  name: statestore
spec:
  type: state.redis
  version: v1
  metadata:
    - name: redisHost
      value: localhost:16379
    - name: redisPassword
      value: ""
    - name: actorStateStore
      value: "true"
```

> Valkey is Redis-protocol compatible, so `state.redis` works. `actorStateStore: "true"` is required for Dapr Workflow. `redisHost` must match the Aspire-pinned Valkey host port (`16379` in Step 2); keep these two in sync.

- [ ] **Step 4: Copy the resources folder to the AppHost output**

In `PrDigest.AppHost.csproj`, inside an `<ItemGroup>`:

```xml
<None Include="resources/**/*.yaml" CopyToOutputDirectory="PreserveNewest" />
```

- [ ] **Step 5: Build the solution**

Run: `dotnet build`
Expected: `Build succeeded`.

- [ ] **Step 6: Checkpoint** — Aspire graph + component compile.

---

## Task 13: Runtime fixtures + integration & crash-resume runbook

**Files:**
- Create: `PrDigest/data/dapr/dapr/prs/*.json` (a small runtime snapshot — at least 6–8 PRs so a mid-batch kill is observable)
- Create: `PrDigest/RUNBOOK.md`

**Interfaces:**
- Consumes: the whole app.
- Produces: a reproducible manual verification of the digest + the crash-and-resume payoff.

- [ ] **Step 1: Create a runtime data snapshot**

Create `PrDigest/data/dapr/dapr/prs/` and add 6–8 PR JSON files following the input contract (same shape as the Task 3 fixtures), varying the signals so ranking is visible: some with tests + linked issue (low risk), some with many files / large diffs / no tests / no linked issue (high risk). Ensure the ApiService runs from a working directory where `REPO_DIR` (`data/dapr/dapr`) resolves — set `DIGEST_OUTPUT_DIR` if you want the `pr-digest.md` written somewhere specific.

- [ ] **Step 2: Verify Ollama is available**

Run: `ollama list`
Expected: `llama3.2:3b` present. If not: `ollama pull llama3.2:3b`. Confirm the endpoint responds:
Run: `curl http://localhost:11434/v1/models`
Expected: JSON listing models.

- [ ] **Step 3: Run the app via Aspire**

Run: `dotnet run --project PrDigest.AppHost`
Expected: the Aspire dashboard URL prints; in the dashboard, `statestore` (Valkey), the `pr-digest` app, and its Dapr sidecar all reach Running.

- [ ] **Step 4: Start a digest run**

The `pr-digest` API is pinned to the fixed port `5090` (see Task 12 AppHost), so:

```powershell
curl -X POST http://localhost:5090/start -H "Content-Type: application/json" -d '{ "id": "run-1", "repoDir": "data/dapr/dapr", "maxPrs": 8 }'
```

Expected: `{ "instanceId": "run-1" }`. Poll status:

```powershell
curl http://localhost:5090/status/run-1
```

Expected: eventually `RuntimeStatus: Completed` with an `output` containing `digestPath` and `headline`. Open `pr-digest.md` and confirm a ranked table with summaries, linked-issue column, risk scores, and flags.

- [ ] **Step 5: Crash-and-resume verification (the payoff)**

1. Start a fresh run: `POST /start` with `{ "id": "run-2", "repoDir": "data/dapr/dapr", "maxPrs": 8 }`.
2. While `/status/run-2` shows `Running` (a few PRs analyzed but not all), **kill the AppHost** (Ctrl-C in the `dotnet run` terminal, or stop the `pr-digest` process).
3. Restart: `dotnet run --project PrDigest.AppHost`.
4. Poll `/status/run-2`.

Expected: the workflow resumes and reaches `Completed` **without re-analyzing already-completed PRs** — the durable state persisted in Valkey lets it continue from the next unprocessed PR rather than restarting. Compare the per-PR log lines before and after the kill to confirm completed PRs are not re-run.

- [ ] **Step 6: Observe traces**

In the Aspire dashboard, open the Traces view for the `pr-digest` resource and confirm spans for the activity calls and per-PR agent steps are visible across the run (and the resume).

- [ ] **Step 7: Write `RUNBOOK.md`**

Capture Steps 2–6 (prereqs, start command, status polling, the crash-resume procedure, where `pr-digest.md` lands, how to read the trace) as a short runbook so the demo is reproducible.

- [ ] **Step 8: Checkpoint** — end-to-end digest works and survives a mid-batch kill.

---

## Self-Review

**Spec coverage:**
- Stack (.NET Aspire + Dapr OSS sidecar, not Catalyst) → Tasks 1, 12. ✔
- Valkey state store managed by Aspire → Task 12 (`AddValkey` + component). ✔
- MAF glue (`AddDaprAgents`/`WithAgent`/`GetAgent`/`RunAgentAndDeserializeAsync`) → Tasks 10, 11. ✔
- Ollama `IChatClient` (`llama3.2:3b`) → Task 10. ✔
- Workflow fan-out (durable per-PR) / deterministic fan-in / summarize agent / markdown writer → Tasks 7, 8, 9, 11. ✔
- `GitHubDataReader` + risk model + tool truncation → Tasks 3, 4, 5, 6. ✔
- Determinism rule (no I/O in orchestrator; reads in activities/tool) → Tasks 9, 11. ✔
- Graceful degradation on malformed JSON (null → degraded entry) → Tasks 8, 11. ✔
- Resiliency retry on agent calls → Task 11 (flagged as version-dependent overload; degradation covers the gap). ✔ (partial — see note)
- Endpoints (`/start`,`/status`,`/pause`,`/resume`,`/terminate`) → Task 10. ✔
- Input data contract / default `data/dapr/dapr` → Tasks 2, 3, 13. ✔
- Output `pr-digest.md` → Tasks 8, 9, 13. ✔
- Crash-and-resume (manual kill) → Task 13. ✔
- Testing (reader/metrics/risk/ranker/writer/tool unit tests; workflow/activities via integration) → Tasks 3–8, 13. ✔

**Type consistency:** `PullRequest`, `PrMetrics` (with `TotalChanges`), `RiskAssessment`, `PrListItem`, `PrAnalysis`, `DigestHeader`, `PrResult`, `RankedPr`, `WriteDigestInput`, `PrDigestInput/Output` are defined once in Task 2 and consumed with matching shapes in Tasks 3–11. `PrMetricsCalculator.Compute`, `RiskModel.Score`, `DigestRanker.Rank`, `DigestMarkdownWriter.Render`, `PrTools.GetPullRequest`, `GitHubDataReader.ListPullRequestNumbers/GetPullRequest` names are consistent across producer and consumer tasks. ✔

**Known version-dependent confirmations (flagged inline, not placeholders):** exact MAF namespaces and the `GetAgent` return type (Task 11), the `RunAgentAndDeserializeAsync` retry overload (Task 11), the OpenAI-over-Ollama client constructor (Task 10), and the `CommunityToolkit.Aspire.Hosting.Dapr` / `AddValkey` API surface (Task 12). Each has a fixed intent and a stated fallback; resolve against the restored package versions during the relevant task's build step.

**Build-order note:** Task 10's `Program.cs` references `PrDigestWorkflow` from Task 11. Implement Task 11 before Task 10's final build step (or stub the workflow), as called out in Task 10 Step 5.
