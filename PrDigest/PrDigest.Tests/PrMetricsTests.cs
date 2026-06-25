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
            new PullRequestFile("a.cs", 10, 5, null),
            new PullRequestFile("b.cs", 2, 1, null)));
        Assert.Equal(2, m.FileCount);
        Assert.Equal(12, m.Additions);
        Assert.Equal(6, m.Deletions);
        Assert.Equal(18, m.TotalChanges);
    }

    [Fact]
    public void Detects_tests_by_filename()
    {
        var withTests = PrMetricsCalculator.Compute(Pr(null, new PullRequestFile("src/FooTests.cs", 1, 0, null)));
        var noTests = PrMetricsCalculator.Compute(Pr(null, new PullRequestFile("src/Foo.cs", 1, 0, null)));
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
        Assert.Equal(expected, PrMetricsCalculator.Compute(Pr(body, new PullRequestFile("a.cs", 1, 0, null))).LinkedIssue);
    }
}
