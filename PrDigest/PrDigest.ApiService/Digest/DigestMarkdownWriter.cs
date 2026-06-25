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
