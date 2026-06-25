using Microsoft.Extensions.AI;
using PrDigest.ApiService.Data;
using PrDigest.ApiService.Tools;
using Xunit;

namespace PrDigest.Tests;

public class PrToolsTests
{
    private static PrTools Tools(int maxPatch = 600) =>
        new(new GitHubDataReader(Path.Combine(AppContext.BaseDirectory, "fixtures", "data", "dapr", "dapr")),
            maxBodyChars: 800, maxPatchChars: maxPatch, maxFiles: 15);

    [Fact]
    public void Returns_pr_with_computed_metrics()
    {
        var result = Tools().GetPullRequest(101);
        Assert.Equal(101, result.Number);
        Assert.Equal(2, result.Files.Count);
        Assert.True(result.Metrics.HasTests);
        Assert.Equal(45, result.Metrics.LinkedIssue);
    }

    [Fact]
    public void Truncates_long_patches()
    {
        var result = Tools(maxPatch: 5).GetPullRequest(101);
        Assert.All(result.Files, f => Assert.True(f.Patch.Length <= 5 + "…[truncated]".Length));
        Assert.Contains(result.Files, f => f.Patch.EndsWith("…[truncated]"));
    }

    // The tool's metadata is the schema the model sees. A small model (llama3.2:3b)
    // copies nouns from the description into argument names, so the description must not
    // contain words that read like parameters (e.g. "snapshot"), and the single integer
    // parameter must be named and described so the model emits {"number": <n>}.
    [Fact]
    public void Tool_exposes_a_single_int_parameter_named_number()
    {
        var function = AIFunctionFactory.Create(Tools().GetPullRequest);
        var schema = function.JsonSchema;

        var properties = schema.GetProperty("properties");
        Assert.True(properties.TryGetProperty("number", out _), "Tool parameter must be named 'number'.");
        Assert.Single(properties.EnumerateObject());

        var required = schema.GetProperty("required").EnumerateArray().Select(e => e.GetString());
        Assert.Contains("number", required);
    }

    [Fact]
    public void Tool_description_does_not_leak_words_the_model_mistakes_for_parameters()
    {
        var function = AIFunctionFactory.Create(Tools().GetPullRequest);
        Assert.DoesNotContain("snapshot", function.Description, StringComparison.OrdinalIgnoreCase);
    }
}
