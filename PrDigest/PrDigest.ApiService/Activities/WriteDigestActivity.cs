using Dapr.Workflow;
using PrDigest.ApiService.Digest;
using PrDigest.ApiService.Models;

namespace PrDigest.ApiService.Activities;

public sealed partial class WriteDigestActivity(ILogger<WriteDigestActivity> logger)
    : WorkflowActivity<WriteDigestInput, string>
{
    public override async Task<string> RunAsync(WorkflowActivityContext context, WriteDigestInput input)
    {
        var outputDir = Environment.GetEnvironmentVariable("DIGEST_OUTPUT_DIR") ?? Directory.GetCurrentDirectory();
        var path = Path.Combine(outputDir, "pr-digest.md");

        var markdown = DigestMarkdownWriter.Render(input.RepoDir, input.Headline, input.Ranked);
        await File.WriteAllTextAsync(path, markdown);

        LogWrote(logger, path, input.Ranked.Count);
        return path;
    }

    [LoggerMessage(LogLevel.Information, "Wrote digest to {Path} with {Count} PRs")]
    static partial void LogWrote(ILogger logger, string path, int count);
}
