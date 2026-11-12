using System.Text.Json;

var app = WebApplication.CreateBuilder(args).Build();

// There is no Dapr code here. The routes are wired only by resources/subscription-orders.yaml
// and resources/subscription-dead-letter.yaml: Dapr picks /orders/express or /orders/standard
// from the order's priority, and POSTs dead-lettered messages to /orders/dead.
app.MapPost("/orders/express", (HttpRequest request, ILogger<Program> logger, CancellationToken cancellationToken) =>
    Handle(request, "express", logger, cancellationToken));

app.MapPost("/orders/standard", (HttpRequest request, ILogger<Program> logger, CancellationToken cancellationToken) =>
    Handle(request, "standard", logger, cancellationToken));

// Dapr forwards the original CloudEvent to orders-dead once the retries are used up,
// so the order is in "data" here too.
app.MapPost("/orders/dead", async Task<IResult> (HttpRequest request, ILogger<Program> logger,
    CancellationToken cancellationToken) =>
{
    var (orderId, _) = await ReadOrder(request, cancellationToken);
    if (orderId is null)
    {
        return Dropped(logger);
    }
    logger.LogInformation("shipping dead-lettered order {OrderId}", orderId);
    return TypedResults.Ok(new { status = "SUCCESS" });
});

app.Run();

static async Task<IResult> Handle(HttpRequest request, string route, ILogger logger,
    CancellationToken cancellationToken)
{
    var (orderId, item) = await ReadOrder(request, cancellationToken);
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
static async Task<(string? OrderId, string? Item)> ReadOrder(HttpRequest request,
    CancellationToken cancellationToken)
{
    try
    {
        using var doc = await JsonDocument.ParseAsync(request.Body, cancellationToken: cancellationToken);
        if (doc.RootElement.ValueKind != JsonValueKind.Object
            || !doc.RootElement.TryGetProperty("data", out var data)
            || data.ValueKind != JsonValueKind.Object
            || !data.TryGetProperty("orderId", out var id) || id.ValueKind != JsonValueKind.String)
        {
            return (null, null);
        }
        var item = data.TryGetProperty("item", out var i) && i.ValueKind == JsonValueKind.String
            ? i.GetString() : null;
        return (id.GetString(), item);
    }
    catch (JsonException)
    {
        return (null, null);
    }
}
