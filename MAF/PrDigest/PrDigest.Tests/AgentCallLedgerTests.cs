using PrDigest.ApiService.Demo;
using Xunit;

namespace PrDigest.Tests;

// The ledger is the inspectable, durable proof that each PR's (expensive) agent call
// executed exactly once across a crash/restart: one line per call, never duplicated.
public class AgentCallLedgerTests : IDisposable
{
    private readonly string _dir =
        Path.Combine(Path.GetTempPath(), "prdigest-ledger-tests", Guid.NewGuid().ToString("n"));

    public void Dispose()
    {
        if (Directory.Exists(_dir))
            Directory.Delete(_dir, recursive: true);
    }

    [Fact]
    public void ReadEntries_on_missing_file_returns_empty()
    {
        var ledger = new AgentCallLedger(_dir);
        Assert.Empty(ledger.ReadEntries());
    }

    [Fact]
    public void Append_then_read_roundtrips_a_single_entry()
    {
        var ledger = new AgentCallLedger(_dir);
        var ts = new DateTime(2026, 6, 29, 12, 0, 1, DateTimeKind.Utc);

        ledger.Append(203, "Add retry policy", ts);

        var entry = Assert.Single(ledger.ReadEntries());
        Assert.Equal(203, entry.PrNumber);
        Assert.Equal("Add retry policy", entry.Title);
        Assert.Equal(ts, entry.TimestampUtc);
    }

    [Fact]
    public void ReadEntries_preserves_append_order()
    {
        var ledger = new AgentCallLedger(_dir);
        var ts = new DateTime(2026, 6, 29, 12, 0, 0, DateTimeKind.Utc);
        ledger.Append(207, "c", ts);
        ledger.Append(201, "a", ts);
        ledger.Append(205, "b", ts);

        Assert.Equal(new[] { 207, 201, 205 }, ledger.ReadEntries().Select(e => e.PrNumber));
    }

    [Fact]
    public void Append_sanitizes_tabs_and_newlines_so_one_call_stays_one_entry()
    {
        var ledger = new AgentCallLedger(_dir);
        var ts = new DateTime(2026, 6, 29, 12, 0, 0, DateTimeKind.Utc);

        ledger.Append(42, "title with\ttab and\nnewline", ts);

        var entry = Assert.Single(ledger.ReadEntries());
        Assert.Equal(42, entry.PrNumber);
        Assert.DoesNotContain('\t', entry.Title);
        Assert.DoesNotContain('\n', entry.Title);
    }

    [Fact]
    public void ReadEntries_skips_a_torn_line_left_by_a_crash_mid_append()
    {
        Directory.CreateDirectory(_dir);
        var path = Path.Combine(_dir, "agent-calls.log");
        // A valid line, then a half-written one as if the process was killed mid-append.
        File.WriteAllText(path,
            "2026-06-29T12:00:00.0000000Z\t201\tValid entry" + Environment.NewLine +
            "2026-06-29T12:00:01.000");

        var entry = Assert.Single(new AgentCallLedger(_dir).ReadEntries());
        Assert.Equal(201, entry.PrNumber);
    }

    [Fact]
    public void Concurrent_appends_do_not_corrupt_or_drop_lines()
    {
        var ledger = new AgentCallLedger(_dir);
        var ts = new DateTime(2026, 6, 29, 12, 0, 0, DateTimeKind.Utc);

        Parallel.For(0, 50, i => ledger.Append(i, $"pr-{i}", ts));

        var numbers = ledger.ReadEntries().Select(e => e.PrNumber).OrderBy(n => n).ToList();
        Assert.Equal(Enumerable.Range(0, 50), numbers);
    }
}
