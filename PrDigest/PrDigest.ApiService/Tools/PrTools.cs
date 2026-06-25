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
