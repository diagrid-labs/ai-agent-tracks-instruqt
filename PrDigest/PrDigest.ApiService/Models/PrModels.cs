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
