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

// The state store component name, from resources/statestore.yaml.
const string StateStore = "statestore";
static string StateKey(string readingId) => $"reading-{readingId}";

// An input binding needs no Dapr code at all: the sidecar calls a plain HTTP endpoint whose
// path is the component name (warp-core-scan). No attribute needed.
app.MapPost("/warp-core-scan", async Task<IResult> (DaprClient daprClient, ShipDb shipDb, StartupGate gate,
    ILogger<Program> logger) =>
{
    await gate.WaitAsync();
    var reading = ReadingFactory.CreateReading();
    logger.LogInformation("{Line}", reading.ToLogLine());
    try
    {
        // The same reading is written twice, through two different Dapr APIs.
        //
        // 1. State API: Dapr owns the table. We hand over a key and a value, Dapr decides how
        //    to store it (a `state` table with key, JSON value, etag and timestamps). There
        //    is no schema and no SQL in our code, and the call is portable: swap the
        //    statestore component for Redis or Cosmos DB and this line stays the same. The
        //    API also gives us ETags, TTL and transactions for free.
        var key = StateKey(reading.ReadingId);
        //    The contentType metadata tells the store the bytes are JSON, so the `state` table
        //    holds a real JSON object (readable in psql) instead of an opaque base64 string.
        await daprClient.SaveStateAsync(StateStore, key, reading,
            metadata: new Dictionary<string, string> { ["contentType"] = "application/json" });
        logger.LogInformation("engineering saved reading {ReadingId} to statestore (key={Key})", reading.ReadingId, key);

        // 2. Output binding: we own the table. We wrote the schema and we write the SQL, so we
        //    can filter, sort and delete in bulk (see GET /readings). The price is that this
        //    code is tied to Postgres: swapping the ship-db component for another store breaks it.
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

// State API read: one reading by key. Get-by-key is all the State API offers for lookups;
// "all readings above 900 K" needs a query, which is what GET /readings does with SQL.
app.MapGet("/state/{readingId}", async Task<IResult> (string readingId, DaprClient daprClient, StartupGate gate,
    ILogger<Program> logger) =>
{
    await gate.WaitAsync();
    try
    {
        var reading = await daprClient.GetStateAsync<WarpCoreReading?>(StateStore, StateKey(readingId));
        // A key that was never saved comes back as null, not as an error.
        return reading is null
            ? TypedResults.Json(new { error = "NOT_FOUND" }, statusCode: 404)
            : TypedResults.Json(reading);
    }
    catch (Exception ex)
    {
        logger.LogWarning("engineering binding call failed: {Error}", ex.Message);
        return TypedResults.Json(new { error = "BINDING_FAILED" }, statusCode: 500);
    }
});

// Binding read, with SQL: the filter and the ordering are ours. The State API cannot do this
// against the reading values without a store-specific query.
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
