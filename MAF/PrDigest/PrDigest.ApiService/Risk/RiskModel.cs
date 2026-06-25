using PrDigest.ApiService.Models;

namespace PrDigest.ApiService.Risk;

public static class RiskModel
{
    public const int ManyFilesThreshold = 10;
    public const int LargeDiffThreshold = 500;

    public static RiskAssessment Score(PrMetrics m)
    {
        var flags = new List<string>();
        var score = 0;

        if (m.FileCount > ManyFilesThreshold) { flags.Add("many-files"); score += 3; }
        if (m.TotalChanges > LargeDiffThreshold) { flags.Add("large-diff"); score += 3; }
        if (!m.HasTests) { flags.Add("no-tests"); score += 2; }
        if (m.LinkedIssue is null) { flags.Add("no-linked-issue"); score += 1; }

        return new RiskAssessment(score, flags);
    }
}
