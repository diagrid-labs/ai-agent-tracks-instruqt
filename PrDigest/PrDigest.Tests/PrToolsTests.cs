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
