using System;
using System.Globalization;
using System.IO;
using System.Net.Http;
using System.Text.Json;
using System.Threading.Tasks;

namespace PulseApp;

/// <summary>How much of the plan's rolling limits is used (0–1), and when each window resets (unix s, 0 = no window open).</summary>
sealed class PlanLimits
{
    public double? Five, Week;
    public double FiveReset, WeekReset;
    public bool Ready;
}

/// <summary>
/// Reads the same numbers as Claude Code's /usage, with the token Claude Code keeps in .credentials.json.
/// Read-only: Pulse never refreshes the token, so an expired one just means "no data until Claude Code runs again".
/// </summary>
sealed class LimitsProbe
{
    static readonly HttpClient Http = new() { Timeout = TimeSpan.FromSeconds(10) };

    static string CredentialsFile()
    {
        var cfg = Environment.GetEnvironmentVariable("CLAUDE_CONFIG_DIR");
        var baseDir = string.IsNullOrEmpty(cfg)
            ? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".claude")
            : cfg;
        return Path.Combine(baseDir, ".credentials.json");
    }

    static string? Token()
    {
        try
        {
            using var doc = JsonDocument.Parse(File.ReadAllText(CredentialsFile()));
            if (!doc.RootElement.TryGetProperty("claudeAiOauth", out var o)) return null;
            if (o.TryGetProperty("expiresAt", out var exp) && exp.ValueKind == JsonValueKind.Number &&
                exp.GetDouble() < DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()) return null;
            return o.TryGetProperty("accessToken", out var t) ? t.GetString() : null;
        }
        catch { return null; }
    }

    static (double? Used, double Reset) Window(JsonElement root, string name)
    {
        if (!root.TryGetProperty(name, out var w) || w.ValueKind != JsonValueKind.Object) return (null, 0);
        double? used = w.TryGetProperty("utilization", out var u) && u.ValueKind == JsonValueKind.Number ? u.GetDouble() / 100 : null;
        double reset = w.TryGetProperty("resets_at", out var r) && r.ValueKind == JsonValueKind.String &&
                       DateTimeOffset.TryParse(r.GetString(), CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal, out var d)
                       ? d.ToUnixTimeMilliseconds() / 1000.0 : 0;
        return (used, reset);
    }

    /// <summary>Null when signed out, offline, or the endpoint changed; callers keep the last good reading.</summary>
    public async Task<PlanLimits?> Read()
    {
        var token = Token();
        if (token == null) return null;
        try
        {
            using var req = new HttpRequestMessage(HttpMethod.Get, "https://api.anthropic.com/api/oauth/usage");
            req.Headers.Add("Authorization", "Bearer " + token);
            req.Headers.Add("anthropic-beta", "oauth-2025-04-20");
            req.Headers.Add("User-Agent", "Pulse");
            using var res = await Http.SendAsync(req);
            if (!res.IsSuccessStatusCode) return null;
            using var doc = JsonDocument.Parse(await res.Content.ReadAsStringAsync());
            var five = Window(doc.RootElement, "five_hour");
            var week = Window(doc.RootElement, "seven_day");
            return new PlanLimits { Ready = true, Five = five.Used, FiveReset = five.Reset, Week = week.Used, WeekReset = week.Reset };
        }
        catch { return null; }
    }
}
