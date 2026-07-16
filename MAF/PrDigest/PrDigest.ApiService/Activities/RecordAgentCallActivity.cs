using Dapr.Workflow;
using PrDigest.ApiService.Demo;
using PrDigest.ApiService.Models;

namespace PrDigest.ApiService.Activities;

// Durably records that one PrAnalyzer agent call executed, by appending to the agent-call
// ledger. Because this runs as a checkpointed workflow activity, a completed record is
// replayed from history (not re-executed) after a crash — so the ledger ends up with each
// PR exactly once, proving the expensive LLM calls were never repeated on resume.
public sealed partial class RecordAgentCallActivity(ILogger<RecordAgentCallActivity> logger)
    : WorkflowActivity<AgentCallRecord, bool>
{
    public override Task<bool> RunAsync(WorkflowActivityContext context, AgentCallRecord record)
    {
        var outputDir = DemoPaths.OutputDirectory();
        var ledger = new AgentCallLedger(outputDir);

        // 💥 DURABILITY DEMO — leave the `if` statement uncommented for a first run to simulate a
        // crash partway through the fan-out (once a couple of agent calls have been recorded), then
        // comment it out and run again: the workflow rehydrates from durable Valkey state and
        // finishes WITHOUT repeating the agent calls already recorded below.
        if (ledger.CountEntries() >= 2) Environment.FailFast("Simulated crash — demonstrating durable resume.");

        ledger.Append(record.Number, record.Title, DateTime.UtcNow);
        LogRecorded(logger, record.Number);
        return Task.FromResult(true);
    }

    [LoggerMessage(LogLevel.Information, "📒 Recorded agent call for PR #{Number}.")]
    static partial void LogRecorded(ILogger logger, int number);
}
