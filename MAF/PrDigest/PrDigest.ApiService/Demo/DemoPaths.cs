namespace PrDigest.ApiService.Demo;

// Single source of truth for where demo artifacts land, so the digest, the agent-call
// ledger, and the crash marker always co-locate (the lab's check steps look here).
public static class DemoPaths
{
    public static string OutputDirectory() =>
        Environment.GetEnvironmentVariable("DIGEST_OUTPUT_DIR")
        ?? Path.Combine(Directory.GetParent(Directory.GetCurrentDirectory())!.FullName, "digest-out");
}
