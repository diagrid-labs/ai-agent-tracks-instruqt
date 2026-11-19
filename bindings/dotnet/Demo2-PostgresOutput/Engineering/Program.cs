using System.Text.Json;
using System.Text.RegularExpressions;
using Dapr.Client;

var builder = WebApplication.CreateBuilder(args);
// One DaprClient for the app's lifetime: it holds the gRPC connection to the sidecar.
builder.Services.AddSingleton(new DaprClientBuilder().Build());
builder.Services.AddSingleton<ShipDb>();
builder.Services.AddSingleton<StartupGate>();
builder.Services.AddHostedService<StartupClear>();

var app = builder.Build();

// An input binding needs no Dapr code at all: the sidecar calls a plain HTTP endpoint whose
// path is the component name (warp-core-scan). No attribute needed.
app.MapPost("/warp-core-scan", async Task<IResult> (ShipDb shipDb, StartupGate gate, ILogger<Program> logger) =>
{
    await gate.WaitAsync();
    var reading = ReadingFactory.CreateReading();
    logger.LogInformation("{Line}", reading.ToLogLine());
    try
    {
        // Output binding: call the component named ship-db with the "exec" operation. The SQL
        // goes in metadata.sql, its values in metadata.params as a JSON array for $1..$4.
        await shipDb.ExecAsync(Sql.InsertReading,
            reading.ReadingId, reading.Stardate, reading.CoreTempK, reading.PlasmaFlow);
        logger.LogInformation("engineering stored reading {ReadingId} in warp_core_readings", reading.ReadingId);
        return TypedResults.Ok();
    }
    catch (Exception ex)
    {
        logger.LogWarning("engineering binding call failed: {Error}", ex.Message);
        return TypedResults.Json(new { error = "BINDING_FAILED" }, statusCode: 500);
    }
});

// A second cron binding drives the clean-up. It is an "exec" again: the delete changes data
// and returns no rows.
app.MapPost("/purge-old-readings", async Task<IResult> (ShipDb shipDb, StartupGate gate, ILogger<Program> logger) =>
{
    await gate.WaitAsync();
    try
    {
        await shipDb.ExecAsync(Sql.PurgeReadings);
        logger.LogInformation("engineering purged old readings");
        return TypedResults.Ok();
    }
    catch (Exception ex)
    {
        logger.LogWarning("engineering binding call failed: {Error}", ex.Message);
        return TypedResults.Json(new { error = "BINDING_FAILED" }, statusCode: 500);
    }
});

app.MapGet("/readings", async Task<IResult> (HttpRequest request, ShipDb shipDb, StartupGate gate,
    ILogger<Program> logger) =>
{
    // Missing minTemp means 0. A present but malformed one (empty, 9.5, abc, too long) is a 400.
    var minTemp = 0;
    if (request.Query.TryGetValue("minTemp", out var raw))
    {
        if (!Regex.IsMatch(raw.ToString(), @"^-?[0-9]{1,6}\z"))
        {
            return TypedResults.BadRequest(new { error = "INVALID_MIN_TEMP" });
        }
        minTemp = int.Parse(raw.ToString());
    }

    await gate.WaitAsync();
    try
    {
        // Output binding again, with the "query" operation: it returns rows. Each row is an
        // array whose values follow the SELECT list, so we map them by position.
        var rows = await shipDb.QueryAsync(Sql.SelectReadings, minTemp);
        var readings = rows.EnumerateArray().Select(row => new
        {
            readingId = row[0].GetString(),
            stardate = row[1].GetDouble(),
            coreTempK = row[2].GetInt32(),
            plasmaFlow = row[3].GetDouble(),
            recordedAt = row[4].GetString(),
        }).ToList();
        return TypedResults.Json(readings);
    }
    catch (Exception ex)
    {
        logger.LogWarning("engineering binding call failed: {Error}", ex.Message);
        return TypedResults.Json(new { error = "BINDING_FAILED" }, statusCode: 500);
    }
});

app.Run();
