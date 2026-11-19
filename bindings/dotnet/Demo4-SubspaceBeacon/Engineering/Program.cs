using Dapr.Client;
using Microsoft.AspNetCore.Mvc;

var builder = WebApplication.CreateBuilder(args);
// One DaprClient for the app's lifetime: it holds the gRPC connection to the sidecar.
builder.Services.AddSingleton(new DaprClientBuilder().Build());
// Service invocation client: an HttpClient whose requests go through the Dapr sidecar, which
// resolves the target by app ID. One instance for the app's lifetime, not one per tick.
builder.Services.AddKeyedSingleton("subspace-beacon", (_, _) => DaprClient.CreateInvokeHttpClient("subspace-beacon"));
builder.Services.AddSingleton<ShipDb>();
builder.Services.AddSingleton<StartupGate>();
builder.Services.AddHostedService<StartupClear>();

var app = builder.Build();

// Input binding: the beacon-ping cron component makes the sidecar call this plain HTTP endpoint
// every 5 seconds. The path is the component name. No Dapr attribute needed.
app.MapPost("/beacon-ping", async Task<IResult> ([FromKeyedServices("subspace-beacon")] HttpClient beacon, ShipDb shipDb,
    StartupGate gate, ILogger<Program> logger) =>
{
    await gate.WaitAsync();

    Ping ping;
    try
    {
        // Service invocation: this HttpClient goes through the Dapr sidecar, which finds the app
        // with ID subspace-beacon. The URL is just the method name "ping"; there is no host or
        // port of the beacon in this code.
        ping = await beacon.GetFromJsonAsync<Ping>("ping")
            ?? throw new InvalidOperationException("empty answer from subspace-beacon");
    }
    catch (Exception)
    {
        // The beacon may still be starting, so an unreachable beacon is expected: we log it and move on.
        // Answering 200 is deliberate: a 500 would change nothing, because cron ticks are never retried;
        // the next tick simply tries again.
        logger.LogWarning("engineering beacon unreachable");
        return TypedResults.Ok();
    }

    try
    {
        // Output binding: call the component named ship-db with the "exec" operation. The SQL
        // goes in metadata.sql, its values in metadata.params as a JSON array for $1..$4.
        await shipDb.ExecAsync(Sql.InsertPing, ping.BeaconId, ping.SignalStrength, ping.Message, ping.Stardate);
        logger.LogInformation("engineering pinged {BeaconId} signalStrength={SignalStrength} message=\"{Message}\"",
            ping.BeaconId, ping.SignalStrength, ping.Message);
    }
    catch (Exception ex)
    {
        logger.LogWarning("engineering binding call failed: {Error}", ex.Message);
    }
    return TypedResults.Ok();
});

app.MapGet("/comms/status", async Task<IResult> (ShipDb shipDb, StartupGate gate, ILogger<Program> logger) =>
{
    await gate.WaitAsync();
    try
    {
        // Output binding with the "query" operation. Each row is an array whose values follow
        // the SELECT list, so we read the signal by position.
        var rows = await shipDb.QueryAsync(Sql.LastPings);
        var signals = rows.EnumerateArray().Select(row => row[0].GetInt32()).ToList();
        var established = signals.Count == 3 && signals.All(signal => signal >= 40);
        // The newest row is first (ORDER BY id DESC). No rows means null.
        int? last = signals.Count > 0 ? signals[0] : null;
        return TypedResults.Json(new CommsStatus(established ? "ESTABLISHED" : "SEARCHING", last));
    }
    catch (Exception ex)
    {
        logger.LogWarning("engineering binding call failed: {Error}", ex.Message);
        return TypedResults.Json(new { error = "BINDING_FAILED" }, statusCode: 500);
    }
});

app.Run();

// What the beacon answers. The property order is the JSON key order.
record Ping(string BeaconId, int SignalStrength, string Message, double Stardate);

record CommsStatus(string Status, int? LastSignalStrength);
