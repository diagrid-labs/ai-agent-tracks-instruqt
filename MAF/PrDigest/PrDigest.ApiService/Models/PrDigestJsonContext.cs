using System.Text.Json.Serialization;

namespace PrDigest.ApiService.Models;

[JsonSourceGenerationOptions(PropertyNameCaseInsensitive = true, PropertyNamingPolicy = JsonKnownNamingPolicy.CamelCase)]
[JsonSerializable(typeof(PrAnalysis))]
[JsonSerializable(typeof(DigestHeader))]
public partial class PrDigestJsonContext : JsonSerializerContext;
