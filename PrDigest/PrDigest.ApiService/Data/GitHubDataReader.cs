using System.Text.Json;
using PrDigest.ApiService.Models;

namespace PrDigest.ApiService.Data;

public sealed class GitHubDataReader(string repoDir)
{
    private static readonly JsonSerializerOptions Options = new(JsonSerializerDefaults.Web);

    private string PrsDir => Path.Combine(repoDir, "prs");

    public IReadOnlyList<int> ListPullRequestNumbers(int max)
    {
        if (!Directory.Exists(PrsDir))
            return [];

        return Directory.EnumerateFiles(PrsDir, "*.json")
            .Select(p => Path.GetFileNameWithoutExtension(p))
            .Where(n => int.TryParse(n, out _))
            .Select(int.Parse)
            .OrderBy(n => n)
            .Take(max)
            .ToList();
    }

    public PullRequest GetPullRequest(int number)
    {
        var path = Path.Combine(PrsDir, $"{number}.json");
        if (!File.Exists(path))
            throw new FileNotFoundException($"PR {number} not found at {path}", path);

        var json = File.ReadAllText(path);
        return JsonSerializer.Deserialize<PullRequest>(json, Options)
            ?? throw new InvalidOperationException($"PR {number} JSON deserialized to null.");
    }
}
