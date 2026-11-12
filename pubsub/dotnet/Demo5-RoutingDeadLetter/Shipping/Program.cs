using System.Text.Json;
using CloudNative.CloudEvents;
using CloudNative.CloudEvents.SystemTextJson;

var builder = WebApplication.CreateBuilder(args);
// The CloudEvents JSON format from the open CloudEvents SDK, shared by every request.
builder.Services.AddSingleton<CloudEventFormatter, JsonEventFormatter>();
var app = builder.Build();

// There is no Dapr code here. The routes are wired only by resources/subscription-orders.yaml
// and resources/subscription-dead-letter.yaml: Dapr picks /orders/express or /orders/standard
// from the order's priority, and POSTs dead-lettered messages to /orders/dead.
app.MapPost("/orders/express", (HttpRequest request, CloudEventFormatter formatter, ILogger<Program> logger) =>
    Handle(request, "express", formatter, logger));

app.MapPost("/orders/standard", (HttpRequest request, CloudEventFormatter formatter, ILogger<Program> logger) =>
    Handle(request, "standard", formatter, logger));

// Dapr forwards the original CloudEvent to orders-dead once the retries are used up,
// so the order is in "data" here too.
app.MapPost("/orders/dead", async Task<IResult> (HttpRequest request, CloudEventFormatter formatter,
    ILogger<Program> logger) =>
{
    var (orderId, _) = await ReadOrder(request, formatter);
    if (orderId is null)
    {
        return Dropped(logger);
    }
    logger.LogInformation("shipping dead-lettered order {OrderId}", orderId);
    return TypedResults.Ok(new { status = "SUCCESS" });
});

app.Run();

static async Task<IResult> Handle(HttpRequest request, string route, CloudEventFormatter formatter,
    ILogger logger)
{
    var (orderId, item) = await ReadOrder(request, formatter);
    if (orderId is null)
    {
        return Dropped(logger);
    }
    if (item == "poison")
    {
        logger.LogWarning("shipping rejected order {OrderId}", orderId);
        // A 500 with RETRY makes Dapr redeliver per resources/resiliency.yaml, then dead-letter.
        return TypedResults.Json(new { status = "RETRY" }, statusCode: 500);
    }
    logger.LogInformation("shipping {Route} order {OrderId}", route, orderId);
    // SUCCESS tells Dapr the message is handled, so it is not redelivered.
    return TypedResults.Ok(new { status = "SUCCESS" });
}

// DROP, not RETRY: an event without an order id will not parse any better on a redelivery.
static IResult Dropped(ILogger logger)
{
    logger.LogWarning("shipping dropped unreadable event");
    return TypedResults.Ok(new { status = "DROP" });
}

// Reads data.orderId and data.item from the CloudEvent body; orderId is null if unreadable.
static async Task<(string? OrderId, string? Item)> ReadOrder(HttpRequest request, CloudEventFormatter formatter)
{
    try
    {
        // Dapr delivers a standard CloudEvent, so the open CloudEvents SDK can read it with no
        // Dapr dependency. Dapr uses structured mode: the whole event is the JSON body.
        var cloudEvent = await formatter.DecodeStructuredModeMessageAsync(request.Body, null, null);
        // The order is in the event's data, which the JSON format hands over as a JsonElement.
        if (cloudEvent.Data is not JsonElement { ValueKind: JsonValueKind.Object } data
            || !data.TryGetProperty("orderId", out var id) || id.ValueKind != JsonValueKind.String)
        {
            return (null, null);
        }
        var item = data.TryGetProperty("item", out var i) && i.ValueKind == JsonValueKind.String
            ? i.GetString() : null;
        return (id.GetString(), item);
    }
    catch (Exception e) when (e is JsonException or ArgumentException)
    {
        // Not JSON (JsonException), or JSON that is not a valid CloudEvent (ArgumentException).
        return (null, null);
    }
}
