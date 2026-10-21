using Dapr.Client;

const string SecretStore = "secretstore";

var builder = WebApplication.CreateBuilder(args);
builder.Services.AddSingleton(new DaprClientBuilder().Build());

var app = builder.Build();

app.MapGet("/secret/{name}", async (string name, DaprClient daprClient) =>
{
    // The app only knows the secret store's name, never where the secrets really live.
    var secret = await daprClient.GetSecretAsync(SecretStore, name);
    return new { name, value = secret[name] };
});

app.Run();
