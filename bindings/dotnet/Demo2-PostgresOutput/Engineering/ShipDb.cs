using System.Text.Json;
using Dapr.Client;

// The SQL the engineering app runs. Every value goes through $1, $2... placeholders, never
// through string concatenation.
static class Sql
{
    public const string ClearReadings = "DELETE FROM warp_core_readings";

    public const string InsertReading =
        "INSERT INTO warp_core_readings (reading_id, stardate, core_temp_k, plasma_flow) VALUES ($1, $2, $3, $4)";

    // The casts and to_char keep the binding's JSON simple: plain numbers and a plain string,
    // nothing the app has to decode from a database type.
    public const string SelectReadings =
        "SELECT reading_id, stardate::float8, core_temp_k, plasma_flow::float8, " +
        "to_char(recorded_at AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"') " +
        "FROM warp_core_readings WHERE core_temp_k >= $1 ORDER BY recorded_at DESC, reading_id DESC LIMIT 20";

    public const string PurgeReadings = "DELETE FROM warp_core_readings WHERE recorded_at < now() - interval '1 minute'";
}

// Thin wrapper around the ship-db output binding. The app only knows the component name
// "ship-db", never that PostgreSQL is behind it.
class ShipDb(DaprClient daprClient)
{
    private const string Binding = "ship-db";

    // "exec" runs a statement that changes data (INSERT, DELETE) and returns no rows.
    public Task<BindingResponse> ExecAsync(string sql, params object[] args) =>
        InvokeAsync("exec", sql, args);

    // "query" runs a SELECT. The binding answers with a JSON array of arrays: one inner array
    // per row, values in the order of the SELECT list, so callers read them by position.
    public async Task<JsonElement> QueryAsync(string sql, params object[] args)
    {
        var response = await InvokeAsync("query", sql, args);
        return JsonSerializer.Deserialize<JsonElement>(response.Data.Span);
    }

    private Task<BindingResponse> InvokeAsync(string operation, string sql, object[] args)
    {
        // The binding name and the operation say where and what; the SQL and its parameters
        // travel as request metadata. "params" is a JSON array in a string, matching $1, $2...
        var request = new BindingRequest(Binding, operation);
        request.Metadata["sql"] = sql;
        if (args.Length > 0)
        {
            request.Metadata["params"] = JsonSerializer.Serialize(args);
        }
        return daprClient.InvokeBindingAsync(request);
    }
}

// Opens once the startup clear is done. Cron ticks and GET requests wait on it, so a reading
// stored by an early tick is never wiped by the clear.
class StartupGate
{
    private readonly TaskCompletionSource _open = new(TaskCreationOptions.RunContinuationsAsynchronously);

    public Task WaitAsync() => _open.Task;

    public void Open() => _open.TrySetResult();
}

// Runs once at startup: waits for the sidecar, clears the table, then opens the gate.
class StartupClear(DaprClient daprClient, ShipDb shipDb, StartupGate gate, ILogger<StartupClear> logger)
    : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        try
        {
            // The sidecar starts alongside the app; binding calls only work once it is up.
            await daprClient.WaitForSidecarAsync(stoppingToken);
            // Each run starts with an empty table, so readings from an earlier run (or another
            // language) never show up. The app does this itself because Postgres outlives it.
            await shipDb.ExecAsync(Sql.ClearReadings);
            logger.LogInformation("engineering cleared warp_core_readings for a fresh run");
        }
        catch (Exception ex) when (ex is not OperationCanceledException)
        {
            logger.LogWarning("engineering could not clear warp_core_readings: {Error}", ex.Message);
        }
        finally
        {
            gate.Open();
        }
    }
}
