using Dapr;

var app = WebApplication.CreateBuilder(args).Build();

// Unwraps the CloudEvent so handlers receive the order itself, not the envelope.
app.UseCloudEvents();
// Serves /dapr/subscribe, the endpoint Dapr calls at startup to learn this app's
// subscriptions. That is what makes the subscription programmatic.
app.MapSubscribeHandler();

app.MapPost("/orders", (Order order, ILogger<Program> logger) =>
{
    logger.LogInformation("invoicing received order {OrderId}", order.OrderId);
    return Results.Ok();
})
// The subscription lives in code: pub/sub component `pubsub`, topic `orders`.
.WithTopic("pubsub", "orders");

app.Run();

record Order(string OrderId, string Item, int Quantity, string Priority);
