using PrDigest.ApiService.Models;

namespace PrDigest.ApiService.Digest;

public static class DigestRanker
{
    public static IReadOnlyList<RankedPr> Rank(IReadOnlyList<PrResult> results) =>
        results
            .OrderByDescending(r => r.Risk.Score)
            .ThenByDescending(r => r.Metrics.TotalChanges)
            .ThenBy(r => r.Number)
            .Select((r, i) => new RankedPr(i + 1, r))
            .ToList();
}
