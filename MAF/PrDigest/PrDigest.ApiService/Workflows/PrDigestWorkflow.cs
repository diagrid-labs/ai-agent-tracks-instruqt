using Dapr.Workflow;
using Diagrid.AI.Microsoft.AgentFramework.Abstractions;
using Diagrid.AI.Microsoft.AgentFramework.Runtime;
using PrDigest.ApiService.Activities;
using PrDigest.ApiService.Agents;
using PrDigest.ApiService.Digest;
using PrDigest.ApiService.Models;
using PrDigest.ApiService.Risk;
using PrDigest.ApiService.Tools;

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

        // Fetch the PR detail deterministically (local file I/O)
        var detail = await context.CallActivityAsync<PrToolResult>(
            nameof(FetchPullRequestDetailActivity), pr.Number);

        // A single faulted agent call must not fail the whole fan-out, so degrade this one
        // PR (Degraded: true) instead of letting the exception propagate through
        // Task.WhenAll. Deterministic metrics and risk are still reported.
        PrAnalysis? analysis;
        try
        {
            // Replay-safe: this prints once per PR on first execution and stays silent when
            // the workflow replays after a crash — so on resume only the not-yet-analyzed
            // PRs log, visibly demonstrating that completed agent calls are not repeated.
            LogAnalyzing(logger, pr.Number);
            analysis = await context.RunAgentAndDeserializeAsync<PrAnalysis>(
                agent: analyzer,
                logger: logger,
                message: BuildAnalysisPrompt(detail));
        }
        catch (Exception ex)
        {
            LogAnalysisDegraded(logger, pr.Number, ex.Message);
            analysis = null;
        }

        // Durably record that this PR's agent call ran. Checkpointed like any activity, so on
        // resume it replays from history (no duplicate ledger line). The activity also carries
        // the commented-out durability-demo crash toggle described in the RUNBOOK.
        await context.CallActivityAsync<bool>(
            nameof(RecordAgentCallActivity), new AgentCallRecord(pr.Number, pr.Title));

        return analysis is null
            ? new PrResult(pr.Number, pr.Title, pr.Metrics, risk, Analysis: null, Degraded: true)
            : new PrResult(pr.Number, pr.Title, pr.Metrics, risk, analysis, Degraded: false);
    }

    private static string BuildAnalysisPrompt(PrToolResult pr)
    {
        var files = string.Join("\n", pr.Files.Select(f =>
            $"- {f.Filename} (+{f.Additions}/-{f.Deletions})\n{f.Patch}"));
        var m = pr.Metrics;
        var linkedIssue = m.LinkedIssue is int li ? $"#{li}" : "null";
        return
            $"Analyze pull request #{pr.Number}: \"{pr.Title}\".\n\n" +
            $"Body:\n{pr.Body}\n\n" +
            $"Changed files ({m.FileCount}):\n{files}\n\n" +
            $"Metrics: fileCount={m.FileCount}, additions={m.Additions}, deletions={m.Deletions}, " +
            $"totalChanges={m.TotalChanges}, hasTests={m.HasTests}, linkedIssue={linkedIssue}.\n\n" +
            "Return strict JSON {\"summary\": string, \"linkedIssue\": string|null, \"riskRationale\": string}.";
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

    [LoggerMessage(LogLevel.Information, "🤖 Analyzing PR #{Number} with the PrAnalyzer agent")]
    static partial void LogAnalyzing(ILogger logger, int number);

    [LoggerMessage(LogLevel.Warning, "Analysis degraded for PR #{Number}: {Reason}")]
    static partial void LogAnalysisDegraded(ILogger logger, int number, string reason);
}
