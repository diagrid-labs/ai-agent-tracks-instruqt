using Dapr.Client;

var builder = WebApplication.CreateBuilder(args);
// One DaprClient for the app's lifetime: it holds the gRPC connection to the sidecar.
builder.Services.AddSingleton(new DaprClientBuilder().Build());
builder.Services.AddSingleton<ShipDb>();
builder.Services.AddSingleton<StartupGate>();
builder.Services.AddHostedService<StartupClear>();

var app = builder.Build();

// Input binding: the beacon-ping cron component makes the sidecar call this plain HTTP endpoint
// every 5 seconds. The path is the component name. No Dapr attribute needed.
app.MapPost("/beacon-ping", async Task<IResult> (DaprClient daprClient, ShipDb shipDb, StartupGate gate,
    ILogger<Program> logger) =>
{
    await gate.WaitAsync();

    Ping ping;
    try
    {
        // Service invocation: call the "ping" method of the app with ID subspace-beacon. The
        // sidecar finds the app by its ID, so there is no host or port in this code.
#pragma warning disable CS0618 // the SDK marks InvokeMethodAsync obsolete; it is still the simplest way to show the concept
        ping = await daprClient.InvokeMethodAsync<Ping>(HttpMethod.Get, "subspace-beacon", "ping");
#pragma warning restore CS0618
    }
    catch (Exception)
    {
        // The beacon may still be starting. Answer 200 anyway, so the sidecar does not log a
        // binding error on every tick; the next tick tries again.
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
