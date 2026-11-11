using System.Text.Json;
using System.Text.RegularExpressions;
using Dapr;
using Dapr.Client;
using Grpc.Core;

const string PubSub = "pubsub";
const string Topic = "orders";

var builder = WebApplication.CreateBuilder(args);
builder.Services.AddSingleton(new DaprClientBuilder().Build());

var app = builder.Build();

app.MapPost("/orders", async (HttpRequest request, DaprClient daprClient, ILogger<Program> logger) =>
{
    var order = await ReadOrder(request);
    if (order is null)
    {
        return Results.Json(new { error = "INVALID_ORDER" }, statusCode: 400);
    }

    try
    {
        // The app only knows the pub/sub component's name and the topic, never the broker
        // behind them. Dapr wraps the order in a CloudEvent and sends it to every subscriber.
        await daprClient.PublishEventAsync(PubSub, Topic, order);
        logger.LogInformation("order-api published {OrderId} to {Topic}", order.OrderId, Topic);
        return Results.Json(new { orderId = order.OrderId, topic = Topic });
    }
    catch (DaprException ex) when (ex.InnerException is RpcException rpc)
    {
        // Show the failure instead of hiding it: the gRPC status name tells the caller why
        // Dapr rejected the publish (for example ERR_PUBSUB_NOT_FOUND maps to NOT_FOUND).
        // "NotFound" -> "NOT_FOUND"
        var error = Regex.Replace(rpc.StatusCode.ToString(), "(?<=[a-z])(?=[A-Z])", "_").ToUpperInvariant();
        return Results.Json(new { orderId = order.OrderId, error }, statusCode: 500);
    }
});

app.Run();

// Returns null unless the body is a JSON object with all four Order fields.
static async Task<Order?> ReadOrder(HttpRequest request)
{
    try
    {
        using var doc = await JsonDocument.ParseAsync(request.Body);
        var root = doc.RootElement;
        // Every field must be present and of the right JSON type; TryGetInt32 and GetString
        // throw on the wrong type, so check the kind first.
        if (root.ValueKind != JsonValueKind.Object
            || !root.TryGetProperty("orderId", out var orderId) || orderId.ValueKind != JsonValueKind.String
            || !root.TryGetProperty("item", out var item) || item.ValueKind != JsonValueKind.String
            || !root.TryGetProperty("quantity", out var quantity) || quantity.ValueKind != JsonValueKind.Number
            || !quantity.TryGetInt32(out var qty)
            || !root.TryGetProperty("priority", out var priority) || priority.ValueKind != JsonValueKind.String)
        {
            return null;
        }
        return new Order(orderId.GetString()!, item.GetString()!, qty, priority.GetString()!);
    }
    catch (JsonException)
    {
        return null;
    }
}

record Order(string OrderId, string Item, int Quantity, string Priority);
