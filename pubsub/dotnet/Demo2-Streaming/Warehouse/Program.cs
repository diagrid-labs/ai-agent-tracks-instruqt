using System.Text.Json;
using Dapr.Messaging.PublishSubscribe;
using Dapr.Messaging.PublishSubscribe.Extensions;

// A generic host, not a web host: warehouse has no HTTP server and no appPort, so the
// sidecar never calls it. The app calls the sidecar instead.
var builder = Host.CreateApplicationBuilder(args);

// Registers DaprPublishSubscribeClient, which opens streaming subscriptions to the sidecar.
builder.Services.AddDaprPubSubClient();
builder.Services.AddHostedService<OrderStreamService>();

builder.Build().Run();

// BackgroundService keeps the app alive until the host gets SIGTERM.
class OrderStreamService(DaprPublishSubscribeClient client, ILogger<OrderStreamService> logger) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        // The app opens the stream itself: pub/sub component `pubsub`, topic `orders`. Dapr
        // pushes each message down the stream and waits for the app's answer.
        // The handling policy is applied by the SDK, not by Dapr: the SDK cancels the handler's
        // token after 10 seconds, and answers Retry (Dapr redelivers) if it cannot send the
        // handler's own answer.
        var options = new DaprSubscriptionOptions(
            new MessageHandlingPolicy(TimeSpan.FromSeconds(10), TopicResponseAction.Retry));

        await using var subscription = await client.SubscribeAsync("pubsub", "orders", options, HandleAsync, stoppingToken);

        // Keep the stream open until shutdown.
        await Task.Delay(Timeout.Infinite, stoppingToken).ConfigureAwait(ConfigureAwaitOptions.SuppressThrowing);
    }

    Task<TopicResponseAction> HandleAsync(TopicMessage message, CancellationToken cancellationToken)
    {
        var orderId = ReadOrderId(message.Data);
        if (orderId is null)
        {
            logger.LogWarning("warehouse dropped unreadable event");
        }
        else
        {
            logger.LogInformation("warehouse received order {OrderId}", orderId);
        }
        // This demo always acknowledges: Success tells Dapr the message is done. The handler
        // never throws either, because an exception here would end the whole subscription.
        return Task.FromResult(TopicResponseAction.Success);
    }

    // The message holds the CloudEvent data as raw bytes of JSON. Returns its orderId, or
    // null if the data is not a JSON object with a string orderId.
    static string? ReadOrderId(ReadOnlyMemory<byte> data)
    {
        try
        {
            using var json = JsonDocument.Parse(data);
            return json.RootElement.ValueKind == JsonValueKind.Object
                && json.RootElement.TryGetProperty("orderId", out var id) && id.ValueKind == JsonValueKind.String
                ? id.GetString() : null;
        }
        catch (JsonException)
        {
            return null;
        }
    }
}
