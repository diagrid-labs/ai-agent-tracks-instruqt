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
        return Results.Json(new { orderId = order.OrderId, error = ErrorName(rpc) }, statusCode: 500);
    }
});

app.MapPost("/orders/bulk", async (string? count, string? prefix, DaprClient daprClient, ILogger<Program> logger) =>
{
    // count must be a whole number from 1 to 100.
    if (!int.TryParse(count, out var n) || n < 1 || n > 100)
    {
        return Results.Json(new { error = "INVALID_COUNT" }, statusCode: 400);
    }
    var orders = Enumerable.Range(1, n)
        .Select(i => new Order($"{(string.IsNullOrEmpty(prefix) ? "o" : prefix)}-{i}", "coffee-beans", 1, "standard"))
        .ToList();

    try
    {
        // One call publishes all orders. Dapr still wraps each one in its own CloudEvent.
        // A bulk publish can succeed for some entries and fail for others, so the response
        // lists the entries that failed instead of throwing for them.
        var result = await daprClient.BulkPublishEventAsync(PubSub, Topic, orders);
        var failed = result.FailedEntries.Count;
        logger.LogInformation("order-api bulk published {Sent} orders to {Topic}, {Failed} failed", n, Topic, failed);
        return Results.Json(new { sent = n, failed });
    }
    catch (DaprException ex) when (ex.InnerException is RpcException rpc)
    {
        // There is no single order to name here, so the error body has no orderId.
        return Results.Json(new { error = ErrorName(rpc) }, statusCode: 500);
    }
});

app.Run();

// Show the failure instead of hiding it: the gRPC status name tells the caller why
// Dapr rejected the publish (for example ERR_PUBSUB_NOT_FOUND maps to NOT_FOUND).
// "NotFound" -> "NOT_FOUND"
static string ErrorName(RpcException rpc) =>
    Regex.Replace(rpc.StatusCode.ToString(), "(?<=[a-z])(?=[A-Z])", "_").ToUpperInvariant();

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
