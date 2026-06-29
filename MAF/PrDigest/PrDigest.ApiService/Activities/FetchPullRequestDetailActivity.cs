using Dapr.Workflow;
using PrDigest.ApiService.Data;
using PrDigest.ApiService.Tools;

namespace PrDigest.ApiService.Activities;

// Fetches one PR's body, truncated diffs, and computed metrics from the on-disk
// snapshot. This is deterministic local I/O: it used to be an LLM tool, but OpenAI
// rejects the orphaned tool-result messages the experimental Dapr conversation API
// produces, so the fetch now happens here and the result is fed into the analyzer
// prompt — letting the analyzer make a single, tool-free agent call.
public sealed partial class FetchPullRequestDetailActivity(
    GitHubDataReader reader,
    ILogger<FetchPullRequestDetailActivity> logger)
    : WorkflowActivity<int, PrToolResult>
{
    public override Task<PrToolResult> RunAsync(WorkflowActivityContext context, int number)
    {
        LogFetching(logger, number);
        var detail = new PrTools(reader).GetPullRequest(number);
        return Task.FromResult(detail);
    }

    [LoggerMessage(LogLevel.Information, "🔎 Fetching detail for PR #{Number}")]
    static partial void LogFetching(ILogger logger, int number);
}
