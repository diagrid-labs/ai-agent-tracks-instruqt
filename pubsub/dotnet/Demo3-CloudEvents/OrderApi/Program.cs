using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;
using Dapr;
using Dapr.Client;
using Grpc.Core;

const string PubSub = "pubsub";

var builder = WebApplication.CreateBuilder(args);
// One DaprClient for the app's lifetime: it holds the gRPC connection to the sidecar.
builder.Services.AddSingleton(new DaprClientBuilder().Build());

var app = builder.Build();

app.MapPost("/orders", (HttpRequest request, DaprClient daprClient, ILogger<Program> logger,
    CancellationToken cancellationToken) =>
    // Dapr wraps the order in a CloudEvent: an envelope with id, source, type and the order in "data".
    Publish(request, daprClient, logger, "orders", metadata: [], cancellationToken));

app.MapPost("/orders/raw", (HttpRequest request, DaprClient daprClient, ILogger<Program> logger,
    CancellationToken cancellationToken) =>
    // The rawPayload publish metadata tells Dapr not to add the envelope: the order itself is
    // the message on the topic. The subscription needs no rawPayload of its own (see subscription-orders-raw.yaml).
    Publish(request, daprClient, logger, "orders-raw", metadata: new() { ["rawPayload"] = "true" }, cancellationToken));

app.Run();

static async Task<IResult> Publish(HttpRequest request, DaprClient daprClient, ILogger<Program> logger,
    string topic, Dictionary<string, string> metadata, CancellationToken cancellationToken)
{
    var order = await ReadOrder(request, cancellationToken);
    if (order is null)
    {
        return TypedResults.BadRequest(new { error = "INVALID_ORDER" });
    }

    try
    {
        // The app only knows the pub/sub component's name and the topic, never the broker
        // behind them. The metadata decides whether Dapr wraps the order in a CloudEvent.
        // No request token: a publish cancelled on disconnect may or may not have happened.
        await daprClient.PublishEventAsync(PubSub, topic, order, metadata);
        logger.LogInformation("order-api published {OrderId} to {Topic}", order.OrderId, topic);
        return TypedResults.Ok(new { orderId = order.OrderId, topic });
    }
    catch (DaprException ex) when (ex.InnerException is RpcException rpc)
    {
        return TypedResults.Json(new { orderId = order.OrderId, error = ErrorName(rpc) }, statusCode: 500);
    }
}

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
