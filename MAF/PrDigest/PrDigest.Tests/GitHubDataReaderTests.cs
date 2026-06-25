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
