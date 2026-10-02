using Dapr.Client;
using VenueBookings;

var builder = WebApplication.CreateBuilder(args);
builder.Services.AddDaprClient();
builder.Services.AddScoped<BookingsService>();

var port = Environment.GetEnvironmentVariable("APP_PORT") ?? "8006";
builder.WebHost.UseUrls($"http://0.0.0.0:{port}");

var app = builder.Build();

// Two endpoints, one Dapr binding component:
// - POST /bookings  calls the binding with operation "exec"  (INSERT a row)
// - GET  /bookings  calls the binding with operation "query" (SELECT the rows)
// See BookingsService for how each operation is invoked.

app.MapPost("/bookings", async (BookingRequestDto dto, BookingsService bookings, ILogger<Program> logger) =>
{
    var rowsAffected = await bookings.SaveBookingAsync(dto.Venue, dto.EventDate);
    logger.LogInformation(
        "Inserted booking for {Venue} on {EventDate} (rows-affected={RowsAffected})",
        dto.Venue, dto.EventDate, rowsAffected);
    return Results.Ok(new { status = "saved", rows_affected = rowsAffected });
});

app.MapGet("/bookings", async (BookingsService bookings, ILogger<Program> logger) =>
{
    var result = await bookings.ListBookingsAsync();
    logger.LogInformation("Queried {Count} booking(s)", result.Count);
    return Results.Ok(new { bookings = result });
});

app.Run();

record BookingRequestDto(string Venue, string EventDate);

// Exposed so the test project's WebApplicationFactory<Program> (if used) can find the entry point.
public partial class Program { }
