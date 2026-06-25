using CommunityToolkit.Aspire.Hosting.Dapr;

var builder = DistributedApplication.CreateBuilder(args);

// Aspire owns the Valkey container life cycle (started/stopped with the run).
// Port 16379 is pinned to match the hardcoded redisHost in resources/statestore.yaml.
var stateStore = builder.AddValkey("statestore", port: 16379);

builder.AddProject<Projects.PrDigest_ApiService>("pr-digest")
    .WithReference(stateStore)
    .WaitFor(stateStore)
    // Pin the API's HTTP endpoint to a fixed host port so the RUNBOOK URLs are stable.
    .WithEndpoint("http", endpoint => endpoint.Port = 5090)
    .WithDaprSidecar(new DaprSidecarOptions
    {
        AppId = "pr-digest",
        ResourcesPaths = ["resources"]
    });

builder.Build().Run();
