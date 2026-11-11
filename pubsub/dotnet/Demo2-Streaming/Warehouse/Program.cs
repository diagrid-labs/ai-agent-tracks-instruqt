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
        // pushes each message down the stream and waits up to 10 seconds for the response
        // before it redelivers.
        var options = new DaprSubscriptionOptions(
            new MessageHandlingPolicy(TimeSpan.FromSeconds(10), TopicResponseAction.Retry));

        await using var subscription = await client.SubscribeAsync("pubsub", "orders", options, HandleAsync, stoppingToken);

        // Keep the stream open until shutdown.
        await Task.Delay(Timeout.Infinite, stoppingToken).ConfigureAwait(ConfigureAwaitOptions.SuppressThrowing);
    }

    Task<TopicResponseAction> HandleAsync(TopicMessage message, CancellationToken cancellationToken)
    {
        // The message holds the CloudEvent data as raw bytes of JSON.
        using var json = JsonDocument.Parse(message.Data);
        logger.LogInformation("warehouse received order {OrderId}", json.RootElement.GetProperty("orderId").GetString());
        // This demo always acknowledges: Success tells Dapr the message is done.
        return Task.FromResult(TopicResponseAction.Success);
    }
}
