using System.Text.Json;
using CloudNative.CloudEvents;
using CloudNative.CloudEvents.SystemTextJson;

var builder = WebApplication.CreateBuilder(args);
// The CloudEvents JSON format from the open CloudEvents SDK, shared by every request.
builder.Services.AddSingleton<CloudEventFormatter, JsonEventFormatter>();
var app = builder.Build();

// There is no Dapr code here. The subscription lives in resources/subscription-shipping.yaml;
// Dapr POSTs each message to this route as a CloudEvent, and the app reads it with the
// CloudEvents SDK.
app.MapPost("/orders", async (HttpRequest request, CloudEventFormatter formatter, ILogger<Program> logger) =>
{
    var orderId = await ReadOrderId(request, formatter);
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
static async Task<string?> ReadOrderId(HttpRequest request, CloudEventFormatter formatter)
{
    try
    {
        // Dapr delivers a standard CloudEvent, so the open CloudEvents SDK can read it with no
        // Dapr dependency. Dapr uses structured mode: the whole event is the JSON body.
        var cloudEvent = await formatter.DecodeStructuredModeMessageAsync(request.Body, null, null);
        // The order is in the event's data, which the JSON format hands over as a JsonElement.
        return cloudEvent.Data is JsonElement { ValueKind: JsonValueKind.Object } data
            && data.TryGetProperty("orderId", out var id) && id.ValueKind == JsonValueKind.String
            ? id.GetString() : null;
    }
    catch (Exception e) when (e is JsonException or ArgumentException)
    {
        // Not JSON (JsonException), or JSON that is not a valid CloudEvent (ArgumentException).
        return null;
    }
}
