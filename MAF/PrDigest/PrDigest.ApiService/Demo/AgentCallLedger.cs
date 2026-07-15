using System.Globalization;

namespace PrDigest.ApiService.Demo;

public record LedgerEntry(DateTime TimestampUtc, int PrNumber, string Title);

// An append-only, human-readable record of every PrAnalyzer agent call that actually
// executed. Because the workflow records each call through a checkpointed activity, a
// completed call is replayed from durable history (never re-executed) after a crash —
// so this file shows each PR exactly once, with a visible time gap at the restart.
public sealed class AgentCallLedger(string directory)
{
    // The fan-out runs agent calls concurrently, so appends from parallel branches must
    // not interleave within a line. A process-wide lock serializes them.
    private static readonly object AppendLock = new();

    private string FilePath => Path.Combine(directory, "agent-calls.log");

    public void Append(int prNumber, string title, DateTime timestampUtc)
    {
        var line = string.Join('\t',
            timestampUtc.ToUniversalTime().ToString("o", CultureInfo.InvariantCulture),
            prNumber.ToString(CultureInfo.InvariantCulture),
            Sanitize(title));

        lock (AppendLock)
        {
            Directory.CreateDirectory(directory);
            File.AppendAllText(FilePath, line + Environment.NewLine);
        }
    }

    public IReadOnlyList<LedgerEntry> ReadEntries()
    {
        if (!File.Exists(FilePath))
            return [];

        return File.ReadAllLines(FilePath)
            .Select(TryParse)
            .OfType<LedgerEntry>()
            .ToList();
    }

    // Number of recorded calls, read under the same lock as Append so it never races with a
    // concurrent append from another fan-out branch. Used by the durability-demo crash toggle.
    public int CountEntries()
    {
        lock (AppendLock)
            return ReadEntries().Count;
    }

    // Tolerant of a torn final line left by a hard crash mid-append: malformed lines are
    // skipped rather than throwing, so the ledger stays readable after the simulated crash.
    private static LedgerEntry? TryParse(string line)
    {
        if (string.IsNullOrWhiteSpace(line))
            return null;

        var parts = line.Split('\t', 3);
        if (parts.Length < 2
            || !DateTime.TryParse(parts[0], CultureInfo.InvariantCulture, DateTimeStyles.RoundtripKind, out var ts)
            || !int.TryParse(parts[1], CultureInfo.InvariantCulture, out var number))
            return null;

        return new LedgerEntry(ts, number, parts.Length > 2 ? parts[2] : "");
    }

    private static string Sanitize(string value) =>
        value.Replace('\t', ' ').Replace('\r', ' ').Replace('\n', ' ');
}
