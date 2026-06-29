using PrDigest.ApiService.Demo;
using Xunit;

namespace PrDigest.Tests;

// The crash gate makes the durability demo deterministic: it trips exactly once, at a
// fixed point, and a persisted marker stops it tripping again after the process restarts.
public class CrashGateTests : IDisposable
{
    private readonly string _dir =
        Path.Combine(Path.GetTempPath(), "prdigest-crashgate-tests", Guid.NewGuid().ToString("n"));

    private string Marker => Path.Combine(_dir, "crash.marker");

    public void Dispose()
    {
        if (Directory.Exists(_dir))
            Directory.Delete(_dir, recursive: true);
    }

    [Fact]
    public void Disabled_when_threshold_is_zero()
    {
        var gate = new CrashGate(threshold: 0, markerPath: Marker);
        Assert.False(gate.ShouldCrash(99));
        Assert.False(File.Exists(Marker));
    }

    [Fact]
    public void Does_not_trip_below_threshold()
    {
        var gate = new CrashGate(threshold: 3, markerPath: Marker);
        Assert.False(gate.ShouldCrash(2));
        Assert.False(File.Exists(Marker));
    }

    [Fact]
    public void Trips_at_threshold_and_writes_marker()
    {
        var gate = new CrashGate(threshold: 3, markerPath: Marker);
        Assert.True(gate.ShouldCrash(3));
        Assert.True(File.Exists(Marker));
    }

    [Fact]
    public void Does_not_trip_again_after_it_has_tripped_once()
    {
        var gate = new CrashGate(threshold: 3, markerPath: Marker);
        Assert.True(gate.ShouldCrash(3));
        Assert.False(gate.ShouldCrash(4));
    }

    [Fact]
    public void Does_not_trip_when_marker_already_exists_simulating_restart()
    {
        Directory.CreateDirectory(_dir);
        File.WriteAllText(Marker, "tripped on a previous run");

        var gate = new CrashGate(threshold: 3, markerPath: Marker);
        Assert.False(gate.ShouldCrash(3));
    }
}
