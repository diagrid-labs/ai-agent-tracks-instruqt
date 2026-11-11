using System.Text.Json;

var app = WebApplication.CreateBuilder(args).Build();

// There is no Dapr code here and no UseCloudEvents(): the route is wired only by
// resources/subscription-bulk.yaml, and Dapr POSTs a batch of messages as one request.
app.MapPost("/orders/bulk", async (HttpRequest request, ILogger<Program> logger) =>
{
    // The body is {"entries": [{"entryId", "event", ...}, ...], ...}: one entry per message.
    JsonElement entries;
    try
    {
        using var doc = await JsonDocument.ParseAsync(request.Body);
        if (doc.RootElement.ValueKind != JsonValueKind.Object
            || !doc.RootElement.TryGetProperty("entries", out entries)
            || entries.ValueKind != JsonValueKind.Array)
        {
            return Results.Json(new { error = "INVALID_BULK_REQUEST" }, statusCode: 400);
        }
        return Results.Json(new { statuses = Handle(entries, logger) });
    }
    catch (JsonException)
    {
        // Not a bulk envelope at all: a non-2xx answer makes Dapr treat the delivery as failed.
        return Results.Json(new { error = "INVALID_BULK_REQUEST" }, statusCode: 400);
    }
});

app.Run();

// Bulk subscriptions are acknowledged per entry: Dapr redelivers only the entries that
// are not SUCCESS.
static List<object> Handle(JsonElement entries, ILogger logger)
{
    var ids = new List<string>();
    var statuses = new List<object>();
    foreach (var entry in entries.EnumerateArray())
    {
        var entryId = entry.ValueKind == JsonValueKind.Object
            && entry.TryGetProperty("entryId", out var e) && e.ValueKind == JsonValueKind.String
            ? e.GetString()! : "";
        var orderId = ReadOrderId(entry);
        if (orderId is null)
        {
            // DROP, not RETRY: a malformed entry will not parse any better on a redelivery.
            logger.LogInformation("shipping dropped unreadable entry {EntryId}", entryId);
            statuses.Add(new { entryId, status = "DROP" });
            continue;
        }
        ids.Add(orderId);
        statuses.Add(new { entryId, status = "SUCCESS" });
    }
    logger.LogInformation("shipping received batch of {Count} orders: {Ids}", ids.Count, string.Join(",", ids));
    return statuses;
}

// Returns the order id from entry.event.data.orderId, or null if the entry is unreadable.
static string? ReadOrderId(JsonElement entry)
{
    if (entry.ValueKind != JsonValueKind.Object || !entry.TryGetProperty("event", out var evt))
    {
        return null;
    }
    JsonDocument? parsed = null;
    try
    {
        // "event" is the CloudEvent; depending on the content type it is an object or a JSON string.
        if (evt.ValueKind == JsonValueKind.String)
        {
            parsed = JsonDocument.Parse(evt.GetString()!);
            evt = parsed.RootElement;
        }
        return evt.ValueKind == JsonValueKind.Object
            && evt.TryGetProperty("data", out var data) && data.ValueKind == JsonValueKind.Object
            && data.TryGetProperty("orderId", out var id) && id.ValueKind == JsonValueKind.String
            ? id.GetString() : null;
    }
    catch (JsonException)
    {
        return null;
    }
    finally
    {
        parsed?.Dispose();
    }
}
