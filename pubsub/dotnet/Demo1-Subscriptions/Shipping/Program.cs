using System.Text.Json;

var app = WebApplication.CreateBuilder(args).Build();

// There is no Dapr code here. The subscription lives in resources/subscription-shipping.yaml;
// Dapr POSTs each message to this route as a CloudEvent, and the app just reads the JSON.
app.MapPost("/orders", async (HttpRequest request, ILogger<Program> logger, CancellationToken cancellationToken) =>
{
    var orderId = await ReadOrderId(request, cancellationToken);
    if (orderId is null)
    {
        // DROP, not an error status: Dapr redelivers on any non-2xx answer (except 404), and an
        // unreadable event will not parse any better on a redelivery.
        logger.LogWarning("shipping dropped unreadable event");
        return TypedResults.Ok(new { status = "DROP" });
    }
    logger.LogInformation("shipping received order {OrderId}", orderId);
    // SUCCESS tells Dapr the message is handled, so it is not redelivered.
    return TypedResults.Ok(new { status = "SUCCESS" });
});

app.Run();

// Returns data.orderId from the CloudEvent body, or null if the event is unreadable.
static async Task<string?> ReadOrderId(HttpRequest request, CancellationToken cancellationToken)
{
    try
    {
        using var doc = await JsonDocument.ParseAsync(request.Body, cancellationToken: cancellationToken);
        // The order is in the CloudEvent's "data" field.
        return doc.RootElement.ValueKind == JsonValueKind.Object
            && doc.RootElement.TryGetProperty("data", out var data) && data.ValueKind == JsonValueKind.Object
            && data.TryGetProperty("orderId", out var id) && id.ValueKind == JsonValueKind.String
            ? id.GetString() : null;
    }
    catch (JsonException)
    {
        return null;
    }
}
