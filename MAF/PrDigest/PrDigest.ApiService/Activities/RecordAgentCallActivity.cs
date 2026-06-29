using Dapr.Workflow;
using PrDigest.ApiService.Demo;
using PrDigest.ApiService.Models;

namespace PrDigest.ApiService.Activities;

// Durably records that one PrAnalyzer agent call executed, by appending to the agent-call
// ledger. Because this runs as a checkpointed workflow activity, a completed record is
// replayed from history (not re-executed) after a crash — so the ledger ends up with each
// PR exactly once, proving the expensive LLM calls were never repeated on resume.
//
// It also hosts the deterministic crash gate: when CRASH_AFTER_AGENT_CALLS is set, the
// process is hard-killed after that many agent calls, so the durability demo crashes at the
// same point every run. The gate trips *before* the ledger append, so the PR whose call was
// in flight at the crash is recorded only once — on the restarted run.
public sealed partial class RecordAgentCallActivity(ILogger<RecordAgentCallActivity> logger)
    : WorkflowActivity<AgentCallRecord, bool>
{
    // Counts agent calls executed in THIS process. Resets to zero on restart, which is
    // exactly what we want: after a crash, completed calls replay from history without
    // re-entering this activity, so only genuinely new calls are counted.
    private static int _executedCalls;

    public override Task<bool> RunAsync(WorkflowActivityContext context, AgentCallRecord record)
    {
        var outputDir = DemoPaths.OutputDirectory();
        var count = Interlocked.Increment(ref _executedCalls);

        var threshold = ParseThreshold(Environment.GetEnvironmentVariable("CRASH_AFTER_AGENT_CALLS"));
        var gate = new CrashGate(threshold, Path.Combine(outputDir, "agent-calls.crash-marker"));
        if (gate.ShouldCrash(count))
        {
            LogCrashing(logger, count);
            // Ungraceful, immediate termination — simulates a real process crash so we can
            // prove the workflow resumes from durable Valkey state without redoing work.
            Environment.FailFast($"PrDigest durability demo: simulated crash after {count} agent call(s).");
        }

        new AgentCallLedger(outputDir).Append(record.Number, record.Title, DateTime.UtcNow);
        LogRecorded(logger, record.Number, count);
        return Task.FromResult(true);
    }

    private static int ParseThreshold(string? raw) =>
        int.TryParse(raw, out var n) && n > 0 ? n : 0;

    [LoggerMessage(LogLevel.Warning,
        "💥 CRASH GATE TRIPPED after {Count} agent call(s) — killing the process to simulate a crash.")]
    static partial void LogCrashing(ILogger logger, int count);

    [LoggerMessage(LogLevel.Information,
        "📒 Recorded agent call for PR #{Number} (call #{Count} in this process).")]
    static partial void LogRecorded(ILogger logger, int number, int count);
}
