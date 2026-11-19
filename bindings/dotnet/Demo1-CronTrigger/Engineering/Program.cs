var app = WebApplication.CreateBuilder(args).Build();

// An input binding needs no Dapr code at all: the sidecar calls a plain HTTP endpoint whose
// path is the component name (warp-core-scan). No attribute, no Dapr package.
app.MapPost("/warp-core-scan", (ILogger<Program> logger) =>
{
    var reading = ReadingFactory.CreateReading();
    logger.LogInformation("{Line}", reading.ToLogLine());
    // Any 2xx tells Dapr the tick was handled.
    return Results.Ok();
});

app.Run();
