using System.ClientModel;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.AI;
using Dapr.Workflow;
using Diagrid.AI.Microsoft.AgentFramework.Hosting;
using OpenAI;
using PrDigest.ApiService.Activities;
using PrDigest.ApiService.Agents;
using PrDigest.ApiService.Data;
using PrDigest.ApiService.Models;
using PrDigest.ApiService.Tools;
using PrDigest.ApiService.Workflows;

const string Model = "llama3.2:3b";

var builder = WebApplication.CreateBuilder(args);
builder.AddServiceDefaults();

var repoDir = Environment.GetEnvironmentVariable("REPO_DIR") ?? "data/dapr/dapr";
var ollamaBase = Environment.GetEnvironmentVariable("OLLAMA_BASE_URL") ?? "http://localhost:11434/v1";

builder.Services.AddSingleton(new GitHubDataReader(repoDir));

// OpenAI-compatible client pointed at Ollama. Ollama ignores the API key but the client requires one.
builder.Services.AddSingleton<IChatClient>(_ =>
    new OpenAIClient(
            new ApiKeyCredential("ollama"),
            new OpenAIClientOptions { Endpoint = new Uri(ollamaBase) })
        .GetChatClient(Model)
        .AsIChatClient());

builder.Services.AddSingleton(sp => new PrTools(sp.GetRequiredService<GitHubDataReader>()));

builder.Services.AddDaprAgents(
        opt => opt.AddContext(() => PrDigestJsonContext.Default),
        opt =>
        {
            opt.RegisterWorkflow<PrDigestWorkflow>();
            opt.RegisterActivity<ListOpenPullRequestsActivity>();
            opt.RegisterActivity<WriteDigestActivity>();
        })
    .WithAgent(sp =>
    {
        AITool[] tools = [AIFunctionFactory.Create(sp.GetRequiredService<PrTools>().GetPullRequest)];
        return sp.GetRequiredService<IChatClient>()
            .AsAIAgent(instructions: AgentInstructions.PrAnalyzer, name: AgentNames.PrAnalyzer, tools: tools);
    })
    .WithAgent(sp => sp.GetRequiredService<IChatClient>()
        .AsAIAgent(instructions: AgentInstructions.Summarize, name: AgentNames.Summarize));

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
