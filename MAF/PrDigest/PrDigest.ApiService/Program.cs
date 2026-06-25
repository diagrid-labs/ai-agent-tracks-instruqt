using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.AI;
using Dapr.Workflow;
using Diagrid.AI.Microsoft.AgentFramework.Hosting;
using PrDigest.ApiService.Activities;
using PrDigest.ApiService.Agents;
using PrDigest.ApiService.Data;
using PrDigest.ApiService.Models;
using PrDigest.ApiService.Tools;
using PrDigest.ApiService.Workflows;

var builder = WebApplication.CreateBuilder(args);
builder.AddServiceDefaults();

// Base data directory: the `data` folder inside MAF/PrDigest. The AppHost supplies an
// absolute DATA_DIR; the fallback resolves it relative to the app content root so a
// standalone `dotnet run` from the project folder still finds it — never the repo-root data.
var dataDir = Environment.GetEnvironmentVariable("DATA_DIR")
    ?? Path.Combine(builder.Environment.ContentRootPath, "..", "data");
// Repo is an org/name selector (e.g. "dapr/dapr") that picks the subfolder under data.
var repo = Environment.GetEnvironmentVariable("REPO") ?? "dapr/dapr";
string[] repoPath = [dataDir, .. repo.Split('/', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)];
var repoDataDir = Path.GetFullPath(Path.Combine(repoPath));

builder.Services.AddSingleton(new GitHubDataReader(repoDataDir));

// The model and Ollama endpoint are owned by the Dapr conversation component
// (AppHost/resources/conversation-ollama.yaml); the agents talk to Ollama through
// the sidecar's conversation API rather than a directly-constructed chat client.
var prTools = new PrTools(new GitHubDataReader(repoDataDir));
AITool[] analyzerTools = [AIFunctionFactory.Create(prTools.GetPullRequest)];

builder.Services.AddDaprAgents(
        opt => opt.AddContext(() => PrDigestJsonContext.Default),
        opt =>
        {
            opt.RegisterWorkflow<PrDigestWorkflow>();
            opt.RegisterActivity<ListOpenPullRequestsActivity>();
            opt.RegisterActivity<WriteDigestActivity>();
        })
    .WithAgent(
        agentName: AgentNames.PrAnalyzer,
        conversationComponentName: "conversation-ollama",
        instructions: AgentInstructions.PrAnalyzer,
        tools: analyzerTools,
        serviceLifetime: ServiceLifetime.Singleton)
    .WithAgent(
        agentName: AgentNames.Summarize,
        conversationComponentName: "conversation-ollama",
        instructions: AgentInstructions.Summarize,
        serviceLifetime: ServiceLifetime.Singleton);

var app = builder.Build();

app.MapPost("/start", async (
    [FromServices] DaprWorkflowClient workflowClient,
    [FromBody] PrDigestInput input) =>
{
    var instanceId = await workflowClient.ScheduleNewWorkflowAsync(
        name: nameof(PrDigestWorkflow), instanceId: input.Id, input: input);
    return Results.Ok(new { instanceId });
});

app.MapGet("/status/{instanceId}", async (
    [FromRoute] string instanceId,
    [FromServices] DaprWorkflowClient workflowClient) =>
{
    var state = await workflowClient.GetWorkflowStateAsync(instanceId);
    if (state is null || !state.Exists)
        return Results.NotFound($"Workflow instance '{instanceId}' not found.");

    var output = state.ReadOutputAs<PrDigestOutput>();
    return Results.Ok(new { state, output });
});

app.MapPost("pause/{instanceId}", async (
    [FromRoute] string instanceId, [FromServices] DaprWorkflowClient c) =>
{ await c.SuspendWorkflowAsync(instanceId); return Results.Accepted(); });

app.MapPost("resume/{instanceId}", async (
    [FromRoute] string instanceId, [FromServices] DaprWorkflowClient c) =>
{ await c.ResumeWorkflowAsync(instanceId); return Results.Accepted(); });

app.MapPost("terminate/{instanceId}", async (
    [FromRoute] string instanceId, [FromServices] DaprWorkflowClient c) =>
{ await c.TerminateWorkflowAsync(instanceId); return Results.Accepted(); });

app.MapDefaultEndpoints();
app.Run();
