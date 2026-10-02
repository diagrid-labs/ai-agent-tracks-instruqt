using System.Text;
using Dapr.Client;
using Moq;
using VenueBookings;
using Xunit;

namespace VenueBookings.Tests;

/// <summary>
/// Unit tests for BookingsService, with DaprClient mocked out. These don't need a running
/// Dapr sidecar or Postgres: they only assert that each method calls the binding with the
/// right operation and SQL, and parses the response the way the binding actually shapes it.
/// </summary>
public class BookingsServiceTests
{
    [Fact]
    public async Task SaveBookingAsync_UsesExecOperation()
    {
        BindingRequest? captured = null;
        var mockClient = new Mock<DaprClient>();
        mockClient
            .Setup(c => c.InvokeBindingAsync(It.IsAny<BindingRequest>(), It.IsAny<CancellationToken>()))
            .Callback<BindingRequest, CancellationToken>((req, _) => captured = req)
            .ReturnsAsync((BindingRequest req, CancellationToken _) => new BindingResponse(
                req,
                ReadOnlyMemory<byte>.Empty,
                new Dictionary<string, string> { ["rows-affected"] = "1" }));

        var service = new BookingsService(mockClient.Object);
        var rowsAffected = await service.SaveBookingAsync("Grand Ballroom", "2026-03-15");

        Assert.Equal("1", rowsAffected);
        Assert.NotNull(captured);
        Assert.Equal("postgres-binding", captured!.BindingName);
        Assert.Equal("exec", captured.Operation);
        Assert.Contains("INSERT INTO bookings", captured.Metadata["sql"]);
        Assert.Contains("Grand Ballroom", captured.Metadata["params"]);
    }

    [Fact]
    public async Task ListBookingsAsync_UsesQueryOperation()
    {
        var data = Encoding.UTF8.GetBytes("[[1,\"Grand Ballroom\",\"2026-03-15\"]]");
        BindingRequest? captured = null;
        var mockClient = new Mock<DaprClient>();
        mockClient
            .Setup(c => c.InvokeBindingAsync(It.IsAny<BindingRequest>(), It.IsAny<CancellationToken>()))
            .Callback<BindingRequest, CancellationToken>((req, _) => captured = req)
            .ReturnsAsync((BindingRequest req, CancellationToken _) => new BindingResponse(
                req,
                data,
                new Dictionary<string, string>()));

        var service = new BookingsService(mockClient.Object);
        var bookings = await service.ListBookingsAsync();

        Assert.Single(bookings);
        Assert.Equal("Grand Ballroom", bookings[0].Venue);
        Assert.Equal("2026-03-15", bookings[0].EventDate);
        Assert.NotNull(captured);
        Assert.Equal("query", captured!.Operation);
        Assert.Contains("SELECT", captured.Metadata["sql"]);
    }

    [Fact]
    public async Task ListBookingsAsync_HandlesEmptyResult()
    {
        var mockClient = new Mock<DaprClient>();
        mockClient
            .Setup(c => c.InvokeBindingAsync(It.IsAny<BindingRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync((BindingRequest req, CancellationToken _) => new BindingResponse(
                req,
                ReadOnlyMemory<byte>.Empty,
                new Dictionary<string, string>()));

        var service = new BookingsService(mockClient.Object);
        var bookings = await service.ListBookingsAsync();

        Assert.Empty(bookings);
    }
}
