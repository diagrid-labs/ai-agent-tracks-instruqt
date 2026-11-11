using System.Text.Json;

var app = WebApplication.CreateBuilder(args).Build();

// There is no Dapr code here. The subscription lives in resources/subscription-shipping.yaml;
// Dapr POSTs each message to this route as a CloudEvent, and the app just reads the JSON.
app.MapPost("/orders", async (HttpRequest request, ILogger<Program> logger) =>
{
    using var doc = await JsonDocument.ParseAsync(request.Body);
    // The order is in the CloudEvent's "data" field.
    var orderId = doc.RootElement.GetProperty("data").GetProperty("orderId").GetString();
    logger.LogInformation("shipping received order {OrderId}", orderId);
    // SUCCESS tells Dapr the message is handled, so it is not redelivered.
    return Results.Json(new { status = "SUCCESS" });
});

app.Run();
