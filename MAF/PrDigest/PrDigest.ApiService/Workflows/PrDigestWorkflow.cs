using Dapr.Workflow;
using Diagrid.AI.Microsoft.AgentFramework.Abstractions;
using Diagrid.AI.Microsoft.AgentFramework.Runtime;
using PrDigest.ApiService.Activities;
using PrDigest.ApiService.Agents;
using PrDigest.ApiService.Digest;
using PrDigest.ApiService.Models;
using PrDigest.ApiService.Risk;

namespace PrDigest.ApiService.Workflows;

public sealed partial class PrDigestWorkflow : Workflow<PrDigestInput, PrDigestOutput>
{
    public override async Task<PrDigestOutput> RunAsync(WorkflowContext context, PrDigestInput input)
    {
        var logger = context.CreateReplaySafeLogger<PrDigestWorkflow>();
        LogStart(logger, context.InstanceId, input.Repo, input.MaxPrs);

        var prs = await context.CallActivityAsync<IReadOnlyList<PrListItem>>(
            nameof(ListOpenPullRequestsActivity), input.MaxPrs);

        var analyzer = context.GetAgent(AgentNames.PrAnalyzer);

        // Durable fan-out: one checkpointed agent call per PR.
        var analysisTasks = prs.Select(pr => AnalyzeOneAsync(context, analyzer, pr, logger)).ToList();
        var results = await Task.WhenAll(analysisTasks);

        // Deterministic fan-in.
        var ranked = DigestRanker.Rank(results);

        var summarizer = context.GetAgent(AgentNames.Summarize);
        var header = await context.RunAgentAndDeserializeAsync<DigestHeader>(
            agent: summarizer,
            logger: logger,
            message: BuildHeadlinePrompt(ranked));
        var headline = header?.Headline ?? "Digest summary unavailable.";

        var path = await context.CallActivityAsync<string>(
            nameof(WriteDigestActivity), new WriteDigestInput(input.Repo, headline, ranked));

        LogDone(logger, context.InstanceId, results.Length, path);
        return new PrDigestOutput(input.Repo, results.Length, path, headline);
    }

    private static async Task<PrResult> AnalyzeOneAsync(
        WorkflowContext context, IDaprAIAgent analyzer, PrListItem pr, ILogger logger)
    {
        var risk = RiskModel.Score(pr.Metrics);

        // The analyzer runs on a small local model that can mis-format the GetPullRequest
        // tool call. A single faulted agent call must not fail the whole fan-out, so degrade
        // this one PR (Degraded: true) instead of letting the exception propagate through
        // Task.WhenAll. Deterministic metrics and risk are still reported.
        PrAnalysis? analysis;
        try
        {
            analysis = await context.RunAgentAndDeserializeAsync<PrAnalysis>(
                agent: analyzer,
                logger: logger,
                message: $"Analyze pull request #{pr.Number}. Call GetPullRequest with arguments {{\"number\": {pr.Number}}} once, " +
                         "then return strict JSON {\"summary\": string, \"linkedIssue\": string|null, \"riskRationale\": string}.");
        }
        catch (Exception ex)
        {
            LogAnalysisDegraded(logger, pr.Number, ex.Message);
            analysis = null;
        }

        return analysis is null
            ? new PrResult(pr.Number, pr.Title, pr.Metrics, risk, Analysis: null, Degraded: true)
            : new PrResult(pr.Number, pr.Title, pr.Metrics, risk, analysis, Degraded: false);
    }

    private static string BuildHeadlinePrompt(IReadOnlyList<RankedPr> ranked)
    {
        var top = ranked.Take(5).Select(r =>
            $"[rank={r.Rank} pr=#{r.Result.Number} title=\"{r.Result.Title}\" risk={r.Result.Risk.Score} " +
            $"flags={string.Join("/", r.Result.Risk.Flags)}]");
        return "Top pull requests: " + string.Join(" ", top) +
               " Write a 2-3 sentence headline. Return strict JSON: {\"headline\": string}.";
    }

    [LoggerMessage(LogLevel.Information, "Starting PR digest {InstanceId} for {Repo} (max {MaxPrs})")]
    static partial void LogStart(ILogger logger, string instanceId, string repo, int maxPrs);

    [LoggerMessage(LogLevel.Information, "Completed PR digest {InstanceId}: {Count} PRs -> {Path}")]
    static partial void LogDone(ILogger logger, string instanceId, int count, string path);

    [LoggerMessage(LogLevel.Warning, "Analysis degraded for PR #{Number}: {Reason}")]
    static partial void LogAnalysisDegraded(ILogger logger, int number, string reason);
}
