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
