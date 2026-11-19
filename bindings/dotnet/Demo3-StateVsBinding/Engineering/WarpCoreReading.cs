using System.Globalization;

// One warp core reading. The property order is the JSON key order.
record WarpCoreReading(string ReadingId, double Stardate, int CoreTempK, double PlasmaFlow)
{
    // Log lines use fixed decimals and the invariant culture, so every language prints the same text.
    public string ToLogLine() => string.Create(CultureInfo.InvariantCulture,
        $"engineering warp-core scan {ReadingId} stardate={Stardate:0.0} coreTempK={CoreTempK} plasmaFlow={PlasmaFlow:0.00}");
}

// Creates readings with a per-process counter, so the first one is wc-0001.
static class ReadingFactory
{
    private static int _counter;

    public static WarpCoreReading CreateReading()
    {
        var number = Interlocked.Increment(ref _counter);
        // Stardate: 78000.0 at 2026-01-01T00:00:00Z, one unit per hour after that.
        var unixSeconds = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
        var stardate = Math.Round(78000.0 + (unixSeconds - 1767225600) / 3600.0, 1);
        return new WarpCoreReading(
            $"wc-{number:D4}",
            stardate,
            Random.Shared.Next(850, 951),
            Random.Shared.Next(70, 101) / 100.0);
    }
}
