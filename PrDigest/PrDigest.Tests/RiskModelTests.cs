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
