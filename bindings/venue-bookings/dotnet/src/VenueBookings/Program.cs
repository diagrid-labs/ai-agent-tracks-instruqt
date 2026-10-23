using System.Text.Json;
using Dapr;
using Microsoft.AspNetCore.Diagnostics;
using VenueBookings;

var builder = WebApplication.CreateBuilder(args);
builder.Services.AddDaprClient();
builder.Services.AddScoped<BookingsService>();
builder.Services.ConfigureHttpJsonOptions(options =>
    options.SerializerOptions.PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower);

var port = Environment.GetEnvironmentVariable("APP_PORT") ?? "8006";
builder.WebHost.UseUrls($"http://0.0.0.0:{port}");
var app = builder.Build();

app.UseExceptionHandler(handler => handler.Run(async context =>
{
    var error = context.Features.Get<IExceptionHandlerFeature>()?.Error;
    var bindingFailed = error is DaprException;
    await Results.Problem(
        statusCode: bindingFailed ? StatusCodes.Status503ServiceUnavailable : StatusCodes.Status500InternalServerError,
        detail: bindingFailed
            ? "Postgres binding request failed. Check the Dapr sidecar and database."
            : "The booking request could not be processed.")
        .ExecuteAsync(context);
}));

app.MapPost("/bookings", async (BookingRequest request, BookingsService bookings, ILogger<Program> logger) =>
{
    var rowsAffected = await bookings.SaveBookingAsync(request.Venue, request.EventDate);
    logger.LogInformation("Inserted booking for {Venue} on {EventDate}", request.Venue, request.EventDate);
    return Results.Ok(new { Status = "saved", RowsAffected = rowsAffected });
});

app.MapGet("/bookings", async (BookingsService bookings, ILogger<Program> logger) =>
{
    var result = await bookings.ListBookingsAsync();
    logger.LogInformation("Queried {Count} booking(s)", result.Count);
    return Results.Ok(new { Bookings = result });
});

app.Run();
