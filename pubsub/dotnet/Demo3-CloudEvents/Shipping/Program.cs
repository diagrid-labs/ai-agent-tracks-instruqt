using System.Text;
using System.Text.Json;
using CloudNative.CloudEvents;
using CloudNative.CloudEvents.SystemTextJson;

var builder = WebApplication.CreateBuilder(args);
// The CloudEvents JSON format from the open CloudEvents SDK, shared by every request.
builder.Services.AddSingleton<CloudEventFormatter, JsonEventFormatter>();
var app = builder.Build();

// There is no Dapr code here and no UseCloudEvents(): both routes receive exactly the bytes
// Dapr sends, and the app logs them untouched. The subscriptions live in resources/*.yaml.

// /orders is a normal subscription: the body is a CloudEvent envelope with the order in "data".
app.MapPost("/orders", async (HttpRequest request, CloudEventFormatter formatter, ILogger<Program> logger,
    CancellationToken cancellationToken) =>
{
    // leaveOpen: the request body stream belongs to ASP.NET Core, not to this reader.
    using var reader = new StreamReader(request.Body, leaveOpen: true);
    var body = await reader.ReadToEndAsync(cancellationToken);
    logger.LogInformation("shipping received with envelope: {Body}", body);
    try
    {
        // Dapr delivers a standard CloudEvent, so the open CloudEvents SDK can read it with no
        // Dapr dependency. Dapr uses structured mode: the whole event is the JSON body.
        var cloudEvent = formatter.DecodeStructuredModeMessage(Encoding.UTF8.GetBytes(body), null, null);
        logger.LogInformation("shipping parsed CloudEvent id={Id} type={Type} source={Source}",
            cloudEvent.Id, cloudEvent.Type, cloudEvent.Source);
    }
    catch (Exception e) when (e is JsonException or ArgumentException)
    {
        // Not a CloudEvent: the raw line above already shows what arrived.
    }
    // SUCCESS tells Dapr the message is handled, so it is not redelivered.
    return TypedResults.Ok(new { status = "SUCCESS" });
});

// /orders-raw receives what the publisher put on the topic: the order itself, no envelope.
// It is not a CloudEvent, so there is nothing for the CloudEvents SDK to read.
app.MapPost("/orders-raw", async (HttpRequest request, ILogger<Program> logger, CancellationToken cancellationToken) =>
{
    using var reader = new StreamReader(request.Body, leaveOpen: true);
    logger.LogInformation("shipping received raw: {Body}", await reader.ReadToEndAsync(cancellationToken));
    return TypedResults.Ok(new { status = "SUCCESS" });
});

app.Run();
