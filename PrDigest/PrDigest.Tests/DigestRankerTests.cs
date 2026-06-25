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
