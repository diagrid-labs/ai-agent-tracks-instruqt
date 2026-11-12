using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;
using Dapr;
using Dapr.Client;
using Grpc.Core;

const string PubSub = "pubsub";
const string Topic = "orders";

var builder = WebApplication.CreateBuilder(args);
// One DaprClient for the app's lifetime: it holds the gRPC connection to the sidecar.
builder.Services.AddSingleton(new DaprClientBuilder().Build());

var app = builder.Build();

app.MapPost("/orders", async Task<IResult> (HttpRequest request, DaprClient daprClient, ILogger<Program> logger,
    CancellationToken cancellationToken) =>
{
    var order = await ReadOrder(request, cancellationToken);
    if (order is null)
    {
        return TypedResults.BadRequest(new { error = "INVALID_ORDER" });
    }

    try
    {
        // The app only knows the pub/sub component's name and the topic, never the broker
        // behind them. Dapr wraps the order in a CloudEvent and sends it to every subscriber.
        // No request token: a publish cancelled on disconnect may or may not have happened.
        await daprClient.PublishEventAsync(PubSub, Topic, order);
        logger.LogInformation("order-api published {OrderId} to {Topic}", order.OrderId, Topic);
        return TypedResults.Ok(new { orderId = order.OrderId, topic = Topic });
    }
    catch (DaprException ex) when (ex.InnerException is RpcException rpc)
    {
        return TypedResults.Json(new { orderId = order.OrderId, error = ErrorName(rpc) }, statusCode: 500);
    }
});

app.MapPost("/orders/bulk", async Task<IResult> (string? count, string? prefix, DaprClient daprClient,
    ILogger<Program> logger) =>
{
    // count binds as a string, not int?: with int? the framework would answer "abc" with its
    // own 400 before this code runs, and the body would not be INVALID_COUNT.
    // count must be a whole number from 1 to 100 in plain ASCII digits ("+5" and "1.5" are not);
    // surrounding whitespace is ignored.
    var digits = count?.Trim();
    if (string.IsNullOrEmpty(digits) || !digits.All(char.IsAsciiDigit)
        || !int.TryParse(digits, out var n) || n is < 1 or > 100)
    {
        return TypedResults.BadRequest(new { error = "INVALID_COUNT" });
    }
    var idPrefix = string.IsNullOrEmpty(prefix) ? "o" : prefix;
    var orders = Enumerable.Range(1, n)
        .Select(i => new Order($"{idPrefix}-{i}", "coffee-beans", 1, "standard"))
        .ToList();

    try
    {
        // One call publishes all orders. Dapr still wraps each one in its own CloudEvent.
        // A bulk publish can succeed for some entries and fail for others, so the response
        // lists the entries that failed instead of throwing for them.
        // No request token: a publish cancelled on disconnect may or may not have happened.
        var result = await daprClient.BulkPublishEventAsync(PubSub, Topic, orders);
        var failed = result.FailedEntries.Count;
        logger.LogInformation("order-api bulk published {Sent} orders to {Topic}, {Failed} failed", n, Topic, failed);
        return TypedResults.Ok(new { sent = n, failed });
    }
    catch (DaprException ex) when (ex.InnerException is RpcException rpc)
    {
        // There is no single order to name here, so the error body has no orderId.
        return TypedResults.Json(new { error = ErrorName(rpc) }, statusCode: 500);
    }
});

app.Run();

// Show the failure instead of hiding it: the gRPC status name tells the caller why
// Dapr rejected the publish (for example ERR_PUBSUB_NOT_FOUND maps to NOT_FOUND).
// "NotFound" -> "NOT_FOUND"
static string ErrorName(RpcException rpc) =>
    Regex.Replace(rpc.StatusCode.ToString(), "(?<=[a-z])(?=[A-Z])", "_").ToUpperInvariant();

// Returns null unless the body is exactly one JSON object with all four Order fields.
static async Task<Order?> ReadOrder(HttpRequest request, CancellationToken cancellationToken)
{
    try
    {
        return await JsonSerializer.DeserializeAsync<Order>(request.Body, Order.Strict, cancellationToken);
    }
    catch (JsonException)
    {
        return null;
    }
}

record Order(string OrderId, string Item, int Quantity, string Priority)
{
    // camelCase names as in the web defaults, but nothing lenient: a missing or null field,
    // a wrong JSON type (such as "2" for quantity), a differently cased name or trailing
    // content after the object makes the read fail.
    public static readonly JsonSerializerOptions Strict = new(JsonSerializerDefaults.Web)
    {
        PropertyNameCaseInsensitive = false,
        NumberHandling = JsonNumberHandling.Strict,
        RespectNullableAnnotations = true,
        RespectRequiredConstructorParameters = true,
    };
}
