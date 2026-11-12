using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;

namespace PulseApp;

/// <summary>One line of a breakdown: who or what spent the tokens.</summary>
sealed record Slice(string Name, double Tokens, double Cost);

sealed class ClaudeStats
{
    public double Week, Input, Output, CacheWrite, CacheRead, Today;
    public double Cost;                  // estimated USD at API list prices
    public double Block, BlockEnd;       // tokens in the current 5-hour block, and when it resets (unix s, 0 = none)
    public int Sessions, Live, Calls, TodayIndex;
    public double[] Days = new double[7];
    public bool Ready;
    public string? Email, Plan;          // the account Claude Code is signed in with (null = API key or signed out)
    public List<Slice> ByModel = new(), ByProject = new(), ByAccount = new();   // this week, largest first
}

/// <summary>
/// Incremental tally of this week's tokens across every Claude Code session on this machine
/// (transcripts in ~/.claude/projects). Each pass reads only bytes appended since the last pass;
/// API calls are de-duplicated by message + request id.
/// </summary>
sealed class ClaudeUsage
{
    readonly record struct Event(double Ts, double Input, double Output, double Cw, double Cr, double Cost, string Session, string Model, string Project);

    /// <summary>
    /// Estimated API list price in USD per million tokens: input, output, cache write, cache read.
    /// First match wins; unknown models count as free. Edit when prices change.
    /// </summary>
    static readonly (string Model, double[] Price)[] Prices =
    {
        ("fable", new[] { 10, 50, 12.5, 1 }),
        ("opus-5", new[] { 4, 20, 5, 0.4 }), ("opus-4-5", new[] { 5, 25, 6.25, 0.5 }), ("opus", new[] { 15, 75, 18.75, 1.5 }),
        ("sonnet-5", new[] { 2, 10, 2.5, 0.1 }), ("sonnet", new[] { 3, 15, 3.75, 0.3 }),
        ("haiku-5", new[] { 0.1, 0.5, 0.125, 0.01 }), ("haiku-4", new[] { 1, 5, 1.25, 0.1 }), ("haiku", new[] { 0.8, 4, 1, 0.08 }),
    };
    static readonly double[] Free = { 0, 0, 0, 0 };

    static double[] Price(string model)
    {
        foreach (var (m, p) in Prices) if (model.Contains(m, StringComparison.Ordinal)) return p;
        return Free;
    }

    readonly Dictionary<string, long> offsets = new();
    readonly HashSet<string> seen = new();
    readonly List<Event> events = new();
    readonly object gate = new();
    double weekStart;

    static ReadOnlySpan<byte> UsageKey => "\"usage\":{"u8;
    static ReadOnlySpan<byte> TsKey => "\"timestamp\":\""u8;
    static ReadOnlySpan<byte> IdKey => "\"id\":\"msg_"u8;
    static ReadOnlySpan<byte> ReqKey => "\"requestId\":\""u8;
    static ReadOnlySpan<byte> SessionKey => "\"sessionId\":\""u8;
    static ReadOnlySpan<byte> ModelKey => "\"model\":\""u8;
    static ReadOnlySpan<byte> CwdKey => "\"cwd\":\""u8;

    static string Family(string model) =>
        model.Contains("fable") ? "FABLE" : model.Contains("opus") ? "OPUS" : model.Contains("sonnet") ? "SONNET"
        : model.Contains("haiku") ? "HAIKU" : "OTHER";

    /// <summary>Project name: the last folder of the session's working directory, else the transcript folder.</summary>
    static string ProjectName(string? cwd, string fallback)
    {
        if (cwd != null)
        {
            var parts = cwd.Split(new[] { '\\', '/' }, StringSplitOptions.RemoveEmptyEntries);
            if (parts.Length > 0) return parts[^1];
        }
        return fallback;
    }

    static string Root()
    {
        var cfg = Environment.GetEnvironmentVariable("CLAUDE_CONFIG_DIR");
        var baseDir = string.IsNullOrEmpty(cfg)
            ? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".claude")
            : cfg;
        return Path.Combine(baseDir, "projects");
    }

    /// <summary>~/.claude.json (or $CLAUDE_CONFIG_DIR/.claude.json) — rewritten by /login, so it names the current account.</summary>
    static string ConfigFile()
    {
        var cfg = Environment.GetEnvironmentVariable("CLAUDE_CONFIG_DIR");
        return string.IsNullOrEmpty(cfg)
            ? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".claude.json")
            : Path.Combine(cfg, ".claude.json");
    }

    DateTime accountStamp;
    string? email, plan;

    /// <summary>
    /// When each account was first seen signed in (unix s). Transcripts don't name the account, so tokens are
    /// credited to whoever was signed in at the time; the first account ever seen also owns the history before it.
    /// </summary>
    readonly List<(double From, string Email)> accountLog = LoadAccountLog();

    static string AccountLogPath => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "Pulse", "accounts.json");

    static List<(double, string)> LoadAccountLog()
    {
        try
        {
            using var doc = JsonDocument.Parse(File.ReadAllText(AccountLogPath));
            return doc.RootElement.EnumerateArray()
                .Select(e => (e.GetProperty("from").GetDouble(), e.GetProperty("email").GetString() ?? ""))
                .Where(e => e.Item2.Length > 0).OrderBy(e => e.Item1).ToList();
        }
        catch { return new(); }
    }

    void NoteAccount(string? current)
    {
        if (current == null || (accountLog.Count > 0 && accountLog[^1].Email == current)) return;
        accountLog.Add((accountLog.Count == 0 ? 0 : DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() / 1000.0, current));
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(AccountLogPath)!);
            File.WriteAllText(AccountLogPath, JsonSerializer.Serialize(accountLog.Select(a => new { from = a.From, email = a.Email })));
        }
        catch { }
    }

    string AccountAt(double ts)
    {
        string who = accountLog.Count > 0 ? accountLog[0].Email : "UNKNOWN";
        foreach (var (from, e) in accountLog) { if (from <= ts) who = e; else break; }
        return who;
    }

    static List<Slice> Top(IEnumerable<Event> events, Func<Event, string> key) =>
        events.GroupBy(key)
              .Select(g => new Slice(g.Key, g.Sum(e => e.Input + e.Output + e.Cw + e.Cr), g.Sum(e => e.Cost)))
              .OrderByDescending(s => s.Tokens).ToList();

    /// <summary>Re-reads the signed-in account only when the config file changes.</summary>
    void ReadAccount()
    {
        var fi = new FileInfo(ConfigFile());
        if (!fi.Exists) { email = plan = null; accountStamp = default; return; }
        if (fi.LastWriteTimeUtc == accountStamp) return;
        try
        {
            using var fs = new FileStream(fi.FullName, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete);
            using var doc = JsonDocument.Parse(fs);
            string? S(JsonElement o, string k) => o.TryGetProperty(k, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() : null;
            if (doc.RootElement.TryGetProperty("oauthAccount", out var a) && a.ValueKind == JsonValueKind.Object)
            { email = S(a, "emailAddress"); plan = S(a, "planDisplayName"); }
            else email = plan = null;
            accountStamp = fi.LastWriteTimeUtc;
        }
        catch (Exception e) when (e is IOException or JsonException or UnauthorizedAccessException) { /* mid-write — next pass */ }
    }

    public ClaudeStats Scan()
    {
        lock (gate) return ScanLocked();
    }

    ClaudeStats ScanLocked()
    {
        var now = DateTimeOffset.Now;
        int sinceMonday = ((int)now.DayOfWeek + 6) % 7;
        var monday = new DateTimeOffset(now.Date.AddDays(-sinceMonday), now.Offset);
        double ws = monday.ToUnixTimeMilliseconds() / 1000.0;
        if (ws != weekStart) { weekStart = ws; offsets.Clear(); seen.Clear(); events.Clear(); }

        int live = 0;
        var root = Root();
        if (Directory.Exists(root))
        {
            IEnumerable<string> files;
            try { files = Directory.EnumerateFiles(root, "*.jsonl", SearchOption.AllDirectories); }
            catch { files = Array.Empty<string>(); }
            foreach (var path in files)
            {
                try { live += ReadFile(path, root, ws, now); } catch { /* file vanished or locked — next pass */ }
            }
        }

        ReadAccount();
        NoteAccount(email);
        var st = new ClaudeStats
        {
            Ready = true, Live = live, Calls = events.Count, TodayIndex = sinceMonday, Email = email, Plan = plan,
            ByModel = Top(events, e => e.Model), ByProject = Top(events, e => e.Project),
            ByAccount = Top(events, e => AccountAt(e.Ts)),
        };
        double dayStart = new DateTimeOffset(now.Date, now.Offset).ToUnixTimeMilliseconds() / 1000.0;
        var sessions = new HashSet<string>();
        foreach (var e in events)
        {
            double t = e.Input + e.Output + e.Cw + e.Cr;
            st.Week += t; st.Input += e.Input; st.Output += e.Output; st.CacheWrite += e.Cw; st.CacheRead += e.Cr;
            st.Cost += e.Cost;
            if (e.Ts >= dayStart) st.Today += t;
            st.Days[Math.Clamp((int)((e.Ts - ws) / 86400), 0, 6)] += t;
            sessions.Add(e.Session);
        }
        st.Sessions = sessions.Count;

        // 5-hour blocks: one opens at the hour of the first message after the last block ran out.
        const double Five = 5 * 3600;
        double bStart = double.NegativeInfinity, bTok = 0;
        var ordered = events.Select(e => (e.Ts, T: e.Input + e.Output + e.Cw + e.Cr)).OrderBy(e => e.Ts);
        foreach (var (ts, t) in ordered)
        {
            if (ts >= bStart + Five) { bStart = Math.Floor(ts / 3600) * 3600; bTok = 0; }
            bTok += t;
        }
        if (now.ToUnixTimeMilliseconds() / 1000.0 < bStart + Five) { st.Block = bTok; st.BlockEnd = bStart + Five; }
        return st;
    }

    /// <summary>Reads new bytes of one transcript; returns 1 if it looks like a live session.</summary>
    int ReadFile(string path, string root, double ws, DateTimeOffset now)
    {
        var rel = Path.GetRelativePath(root, path);
        string folder = rel.Split(Path.DirectorySeparatorChar)[0];
        var fi = new FileInfo(path);
        var mod = new DateTimeOffset(fi.LastWriteTimeUtc).ToUnixTimeMilliseconds() / 1000.0;
        if (mod < ws) return 0;
        int live = (now - fi.LastWriteTimeUtc).TotalMinutes < 5 &&
                   !path.Contains($"{Path.DirectorySeparatorChar}subagents{Path.DirectorySeparatorChar}") ? 1 : 0;

        offsets.TryGetValue(path, out long off);
        if (fi.Length <= off) return live;

        using var fs = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete, 1 << 16);
        fs.Seek(off, SeekOrigin.Begin);
        var buf = new byte[4 << 20];                     // stream in 4 MB chunks to keep memory flat
        int have = 0;
        long consumed = 0;
        while (true)
        {
            if (have == buf.Length) Array.Resize(ref buf, buf.Length * 2);   // a single line larger than the buffer
            int n = fs.Read(buf, have, buf.Length - have);
            if (n == 0) break;
            have += n;
            int lastNl = Array.LastIndexOf(buf, (byte)'\n', have - 1);
            if (lastNl < 0) continue;
            var span = new ReadOnlySpan<byte>(buf, 0, lastNl + 1);
            while (span.Length > 0)
            {
                int nl = span.IndexOf((byte)'\n');
                Ingest(span[..nl], ws, folder);
                span = span[(nl + 1)..];
            }
            consumed += lastNl + 1;
            Buffer.BlockCopy(buf, lastNl + 1, buf, 0, have - lastNl - 1);
            have -= lastNl + 1;
        }
        offsets[path] = off + consumed;
        return live;
    }

    static string? Field(ReadOnlySpan<byte> line, ReadOnlySpan<byte> key, bool last = false)
    {
        int i = last ? line.LastIndexOf(key) : line.IndexOf(key);
        if (i < 0) return null;
        var rest = line[(i + key.Length)..];
        int end = rest.IndexOf((byte)'"');
        return end < 0 ? null : Encoding.UTF8.GetString(rest[..end]);
    }

    void Ingest(ReadOnlySpan<byte> line, double ws, string folder)
    {
        // Cheap field extraction — lines can be megabytes, so avoid parsing the whole record.
        int u = line.IndexOf(UsageKey);
        if (u < 0) return;
        var tsS = Field(line, TsKey, last: true);
        if (tsS == null || !DateTimeOffset.TryParse(tsS, CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal, out var dto)) return;
        double ts = dto.ToUnixTimeMilliseconds() / 1000.0;
        if (ts < ws) return;

        int open = u + UsageKey.Length - 1, depth = 0, close = -1;
        for (int i = open; i < line.Length; i++)
        {
            if (line[i] == (byte)'{') depth++;
            else if (line[i] == (byte)'}' && --depth == 0) { close = i; break; }
        }
        if (close < 0) return;

        var key = $"{Field(line, IdKey)}|{Field(line, ReqKey) ?? ts.ToString(CultureInfo.InvariantCulture)}";
        if (!seen.Add(key)) return;

        try
        {
            using var doc = JsonDocument.Parse(line[open..(close + 1)].ToArray());
            var r = doc.RootElement;
            double N(string k) => r.TryGetProperty(k, out var v) && v.ValueKind == JsonValueKind.Number ? v.GetDouble() : 0;
            double i = N("input_tokens"), o = N("output_tokens"), cw = N("cache_creation_input_tokens"), cr = N("cache_read_input_tokens");
            var model = Field(line, ModelKey) ?? "";
            var p = Price(model);
            events.Add(new Event(ts, i, o, cw, cr, (i * p[0] + o * p[1] + cw * p[2] + cr * p[3]) / 1e6, Field(line, SessionKey) ?? "",
                                 Family(model), ProjectName(Field(line, CwdKey), folder)));
        }
        catch (JsonException) { }
    }
}
