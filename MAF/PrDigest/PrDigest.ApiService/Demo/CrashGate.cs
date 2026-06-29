namespace PrDigest.ApiService.Demo;

// Makes the durability demo deterministic. When CRASH_AFTER_AGENT_CALLS is set, the gate
// trips once — after that many agent calls have executed — and drops a marker file so the
// restarted process (which replays completed calls from history) does not crash again.
public sealed class CrashGate(int threshold, string markerPath)
{
    public bool ShouldCrash(int countSoFar)
    {
        if (threshold <= 0)
            return false;
        if (File.Exists(markerPath))
            return false;
        if (countSoFar < threshold)
            return false;

        var dir = Path.GetDirectoryName(markerPath);
        if (!string.IsNullOrEmpty(dir))
            Directory.CreateDirectory(dir);
        File.WriteAllText(markerPath, $"Crash gate tripped after {countSoFar} agent call(s).");
        return true;
    }
}
