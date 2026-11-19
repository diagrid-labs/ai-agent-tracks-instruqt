using System.Globalization;

// The beacon is a plain HTTP app: no Dapr SDK, no Dapr code. Engineering calls it through
// service invocation, and the Dapr sidecar next to this app delivers the request here.
var app = WebApplication.Create(args);

// Signal strength walks through a fixed sequence, then stays at the last value. The counter
// is per process, so restarting the beacon restarts the sequence.
int[] sequence = [12, 27, 45, 63, 81, 94];
var calls = 0;

app.MapGet("/ping", (ILogger<Program> logger) =>
{
    var index = Math.Min(Interlocked.Increment(ref calls), sequence.Length) - 1;
    var signalStrength = sequence[index];
    var message = signalStrength switch
    {
        < 40 => "static",
        < 80 => "signal acquired",
        _ => "channel open",
    };
    // Stardate: 78000.0 at 2026-01-01T00:00:00Z, one unit per hour after that.
    var unixSeconds = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
    var stardate = Math.Round(78000.0 + (unixSeconds - 1767225600) / 3600.0, 1);

    logger.LogInformation("subspace-beacon answered ping signalStrength={SignalStrength}", signalStrength);
    return new Ping("relay-theta-9", signalStrength, message, stardate);
});

app.Run();

// The property order is the JSON key order.
record Ping(string BeaconId, int SignalStrength, string Message, double Stardate);
