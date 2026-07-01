using CommunityToolkit.Aspire.Hosting.Dapr;

var builder = DistributedApplication.CreateBuilder(args);

// Aspire owns the Valkey container life cycle (started/stopped with the run).
// Port 16379 is pinned to match the hardcoded redisHost in resources/statestore.yaml.
// The password is supplied as a secret parameter and must match redisPassword in that file.
var statePassword = builder.AddParameter("cache-password", "state-store-123", secret: true);
var stateStore = builder
    .AddValkey("statestore", 16379, statePassword)
    .WithContainerName("pr-digest-state")
    .WithDataVolume("pr-digest-state-data");

// The PR JSON fixtures live under the `data` folder inside MAF/PrDigest (one level above
// this AppHost project). Pass the base data dir as an absolute path so discovery never
// depends on the working directory Aspire assigns — and never falls back to the repo-root data.
var dataDir = Path.GetFullPath(Path.Combine(builder.AppHostDirectory, "..", "data"));

builder.AddProject<Projects.PrDigest_ApiService>("pr-digest")
    .WithReference(stateStore)
    .WaitFor(stateStore)
    .WithEnvironment("DATA_DIR", dataDir)
    // Repo org/name selector; resolves to <DATA_DIR>/dapr/dapr.
    .WithEnvironment("REPO", "dapr/dapr")
    // Durability demo: when this is a positive integer, the API hard-crashes after that many
    // PrAnalyzer agent calls (once), so the crash-and-resume lab fires at the same point every
    // run. Unset/0 means never crash (normal runs). Arm it with `export CRASH_AFTER_AGENT_CALLS=3`
    // before `aspire run`.
    .WithEnvironment("CRASH_AFTER_AGENT_CALLS",
        Environment.GetEnvironmentVariable("CRASH_AFTER_AGENT_CALLS") ?? "0")
    // Pin the API's HTTP endpoint to a fixed host port so the RUNBOOK URLs are stable.
    .WithEndpoint("http", endpoint => endpoint.Port = 5090)
    .WithDaprSidecar(new DaprSidecarOptions
    {
        AppId = "pr-digest",
        ResourcesPaths = ["resources"]
    });

builder.Build().Run();
