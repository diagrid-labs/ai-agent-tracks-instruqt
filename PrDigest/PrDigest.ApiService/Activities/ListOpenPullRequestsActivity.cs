using Dapr.Workflow;
using PrDigest.ApiService.Data;
using PrDigest.ApiService.Models;
using PrDigest.ApiService.Risk;

namespace PrDigest.ApiService.Activities;

public sealed partial class ListOpenPullRequestsActivity(
    GitHubDataReader reader,
    ILogger<ListOpenPullRequestsActivity> logger)
    : WorkflowActivity<int, IReadOnlyList<PrListItem>>
{
    public override Task<IReadOnlyList<PrListItem>> RunAsync(WorkflowActivityContext context, int maxPrs)
    {
        var numbers = reader.ListPullRequestNumbers(maxPrs);
        LogListing(logger, numbers.Count);

        IReadOnlyList<PrListItem> items = numbers
            .Select(n =>
            {
                var pr = reader.GetPullRequest(n);
                return new PrListItem(pr.Number, pr.Title, PrMetricsCalculator.Compute(pr));
            })
            .ToList();

        return Task.FromResult(items);
    }

    [LoggerMessage(LogLevel.Information, "Listing {Count} pull requests for digest")]
    static partial void LogListing(ILogger logger, int count);
}
