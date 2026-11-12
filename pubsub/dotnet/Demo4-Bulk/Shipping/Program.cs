using System.Text.Json;

var app = WebApplication.CreateBuilder(args).Build();

// There is no Dapr code here and no UseCloudEvents(): the route is wired only by
// resources/subscription-bulk.yaml, and Dapr POSTs a batch of messages as one request.
app.MapPost("/orders/bulk", async Task<IResult> (HttpRequest request, ILogger<Program> logger,
    CancellationToken cancellationToken) =>
{
    // The body is {"entries": [{"entryId", "event", ...}, ...], ...}: one entry per message.
    try
    {
        using var doc = await JsonDocument.ParseAsync(request.Body, cancellationToken: cancellationToken);
        if (doc.RootElement.ValueKind != JsonValueKind.Object
            || !doc.RootElement.TryGetProperty("entries", out var entries)
            || entries.ValueKind != JsonValueKind.Array)
        {
            return TypedResults.BadRequest(new { error = "INVALID_BULK_REQUEST" });
        }
        return TypedResults.Ok(new { statuses = Handle(entries, logger) });
    }
    catch (JsonException)
    {
        // Not a bulk envelope at all: a non-2xx answer makes Dapr treat the delivery as failed.
        return TypedResults.BadRequest(new { error = "INVALID_BULK_REQUEST" });
    }
});

app.Run();

// Bulk subscriptions are acknowledged per entry: Dapr redelivers only the entries that
// are not SUCCESS.
static List<BulkEntryStatus> Handle(JsonElement entries, ILogger logger)
{
    var ids = new List<string>();
    var statuses = new List<BulkEntryStatus>();
    foreach (var entry in entries.EnumerateArray())
    {
        var entryId = entry.ValueKind == JsonValueKind.Object
            && entry.TryGetProperty("entryId", out var e) && e.ValueKind == JsonValueKind.String
            ? e.GetString()! : "";
        var orderId = ReadOrderId(entry);
        if (orderId is null)
        {
            // DROP, not RETRY: a malformed entry will not parse any better on a redelivery.
            logger.LogWarning("shipping dropped unreadable entry {EntryId}", entryId);
            statuses.Add(new BulkEntryStatus(entryId, "DROP"));
            continue;
        }
        ids.Add(orderId);
        statuses.Add(new BulkEntryStatus(entryId, "SUCCESS"));
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
    try
    {
        // "event" is the CloudEvent; depending on the content type it is an object or a JSON string.
        using var parsed = evt.ValueKind == JsonValueKind.String ? JsonDocument.Parse(evt.GetString()!) : null;
        var cloudEvent = parsed?.RootElement ?? evt;
        return cloudEvent.ValueKind == JsonValueKind.Object
            && cloudEvent.TryGetProperty("data", out var data) && data.ValueKind == JsonValueKind.Object
            && data.TryGetProperty("orderId", out var id) && id.ValueKind == JsonValueKind.String
            ? id.GetString() : null;
    }
    catch (JsonException)
    {
        return null;
    }
}

// One answer per entry, serialized as {"entryId": ..., "status": ...}.
record BulkEntryStatus(string EntryId, string Status);
