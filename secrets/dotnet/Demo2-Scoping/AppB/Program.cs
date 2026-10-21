using System.Text.RegularExpressions;
using Dapr;
using Dapr.Client;
using Grpc.Core;

const string SecretStore = "secretstore";

var builder = WebApplication.CreateBuilder(args);
builder.Services.AddSingleton(new DaprClientBuilder().Build());

var app = builder.Build();

// AppA and AppB have exactly the same code. Only the sidecar next to each of them is configured
// differently, and that decides which secrets each one may read.
app.MapGet("/secret/{name}", async (string name, DaprClient daprClient) =>
{
    try
    {
        var secret = await daprClient.GetSecretAsync(SecretStore, name);
        return secret.TryGetValue(name, out var value)
            ? Results.Json(new { name, value })
            : Results.Json(new { name, error = "INTERNAL" }, statusCode: 500);
    }
    catch (DaprException ex) when (ex.InnerException is RpcException rpc)
    {
        var (status, error) = Describe(rpc);
        return Results.Json(new { name, error }, statusCode: status);
    }
});

app.Run();

// Show the failure instead of hiding it: a refusal by Dapr (for example by secret scoping)
// is a 403 with the gRPC status name, anything else is a 500.
static (int Status, string Error) Describe(RpcException rpc)
{
    var status = rpc.StatusCode == StatusCode.PermissionDenied ? 403 : 500;
    // "PermissionDenied" -> "PERMISSION_DENIED"
    var error = Regex.Replace(rpc.StatusCode.ToString(), "(?<=[a-z])(?=[A-Z])", "_").ToUpperInvariant();
    return (status, error);
}
