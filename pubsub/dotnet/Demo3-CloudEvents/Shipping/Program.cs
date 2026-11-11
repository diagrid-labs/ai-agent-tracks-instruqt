var app = WebApplication.CreateBuilder(args).Build();

// There is no Dapr code here and no UseCloudEvents(): both routes receive exactly the bytes
// Dapr sends, and the app logs them untouched. The subscriptions live in resources/*.yaml.

// /orders is a normal subscription: the body is a CloudEvent envelope with the order in "data".
app.MapPost("/orders", async (HttpRequest request, ILogger<Program> logger) =>
{
    using var reader = new StreamReader(request.Body);
    logger.LogInformation("shipping received with envelope: {Body}", await reader.ReadToEndAsync());
    // SUCCESS tells Dapr the message is handled, so it is not redelivered.
    return Results.Json(new { status = "SUCCESS" });
});

// /orders-raw is a rawPayload subscription: the body is the order itself, no envelope.
app.MapPost("/orders-raw", async (HttpRequest request, ILogger<Program> logger) =>
{
    using var reader = new StreamReader(request.Body);
    logger.LogInformation("shipping received raw: {Body}", await reader.ReadToEndAsync());
    return Results.Json(new { status = "SUCCESS" });
});

app.Run();
