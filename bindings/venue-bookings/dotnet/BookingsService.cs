using System.Text;
using System.Text.Json;
using Dapr.Client;

namespace VenueBookings;

/// <summary>
/// Saves and queries venue bookings through a single Dapr output binding to PostgreSQL.
///
/// There is only one binding here, bindings.postgresql, which is output-only. Dapr has no
/// "input binding" for Postgres: an input binding is something that triggers your app (like
/// a Cron schedule), and Postgres has no mechanism for that. Both methods below call the
/// same binding, just with a different operation.
/// </summary>
public class BookingsService
{
    private const string BindingName = "postgres-binding";

    private readonly DaprClient _daprClient;

    public BookingsService(DaprClient daprClient)
    {
        _daprClient = daprClient;
    }

    /// <summary>Save a booking with the binding's "exec" operation (an INSERT).</summary>
    public async Task<string?> SaveBookingAsync(string venue, string eventDate)
    {
        var request = new BindingRequest(BindingName, "exec");
        request.Metadata["sql"] = "INSERT INTO bookings (venue, event_date) VALUES ($1, $2)";
        request.Metadata["params"] = JsonSerializer.Serialize(new[] { venue, eventDate });

        var response = await _daprClient.InvokeBindingAsync(request);
        return response.Metadata.TryGetValue("rows-affected", out var rowsAffected) ? rowsAffected : null;
    }

    /// <summary>Read every booking back with the same binding's "query" operation (a SELECT).</summary>
    public async Task<List<Booking>> ListBookingsAsync()
    {
        var request = new BindingRequest(BindingName, "query");
        request.Metadata["sql"] = "SELECT id, venue, event_date FROM bookings ORDER BY id";
        request.Metadata["params"] = "[]";

        var response = await _daprClient.InvokeBindingAsync(request);
        var json = Encoding.UTF8.GetString(response.Data.Span);
        var rows = string.IsNullOrEmpty(json)
            ? new List<List<JsonElement>>()
            : JsonSerializer.Deserialize<List<List<JsonElement>>>(json) ?? new List<List<JsonElement>>();

        return rows
            .Select(row => new Booking(row[1].GetString()!, row[2].GetString()!) { Id = row[0].GetInt32() })
            .ToList();
    }
}

public record Booking(string Venue, string EventDate)
{
    public int Id { get; init; }
}
