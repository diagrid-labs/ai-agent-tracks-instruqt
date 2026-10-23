using System.Text.Json;
using Dapr.Client;

namespace VenueBookings;

public class BookingsService(DaprClient daprClient)
{
    private const string BindingName = "postgres-binding";

    public async Task<string?> SaveBookingAsync(string venue, string eventDate)
    {
        var request = new BindingRequest(BindingName, "exec");
        request.Metadata["sql"] = "INSERT INTO bookings (venue, event_date) VALUES ($1, $2)";
        request.Metadata["params"] = JsonSerializer.Serialize(new[] { venue, eventDate });

        var response = await daprClient.InvokeBindingAsync(request);
        return response.Metadata.TryGetValue("rows-affected", out var rowsAffected) ? rowsAffected : null;
    }

    public async Task<List<Booking>> ListBookingsAsync()
    {
        var request = new BindingRequest(BindingName, "query");
        request.Metadata["sql"] = "SELECT id, venue, event_date::text FROM bookings ORDER BY id";
        request.Metadata["params"] = "[]";

        var response = await daprClient.InvokeBindingAsync(request);
        var rows = response.Data.IsEmpty
            ? []
            : JsonSerializer.Deserialize<List<List<JsonElement>>>(response.Data.Span) ?? [];

        return rows.Select(row => new Booking(
            row[0].GetInt32(), row[1].GetString()!, row[2].GetString()!)).ToList();
    }
}
