using System.Text.Json;

var app = WebApplication.CreateBuilder(args).Build();

// There is no Dapr code here and no UseCloudEvents(): the route is wired only by
// resources/subscription-bulk.yaml, and Dapr POSTs a batch of messages as one request.
app.MapPost("/orders/bulk", async (HttpRequest request, ILogger<Program> logger) =>
{
    using var doc = await JsonDocument.ParseAsync(request.Body);
    var ids = new List<string>();
    var statuses = new List<object>();
    // The body is {"entries": [{"entryId", "event", ...}, ...], ...}: one entry per message.
    foreach (var entry in doc.RootElement.GetProperty("entries").EnumerateArray())
    {
        var evt = entry.GetProperty("event");
        // "event" is the CloudEvent; depending on the content type it is an object or a JSON string.
        if (evt.ValueKind == JsonValueKind.String)
        {
            evt = JsonDocument.Parse(evt.GetString()!).RootElement;
        }
        ids.Add(evt.GetProperty("data").GetProperty("orderId").GetString()!);
        statuses.Add(new { entryId = entry.GetProperty("entryId").GetString(), status = "SUCCESS" });
    }
    logger.LogInformation("shipping received batch of {Count} orders: {Ids}", ids.Count, string.Join(",", ids));
    // Bulk subscriptions are acknowledged per entry: Dapr redelivers only the entries that
    // are not SUCCESS.
    return Results.Json(new { statuses });
});

app.Run();
