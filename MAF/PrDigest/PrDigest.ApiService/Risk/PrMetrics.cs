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
