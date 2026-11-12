using System;
using System.Collections.Generic;

namespace PulseApp;

/// <summary>
/// Decides when something is worth a notification: a sustained hot CPU or full memory, the 5-hour block
/// resetting, and plan limits crossing 80% and 95%. Each fires once, then waits out a cooldown.
/// </summary>
sealed class Alerts
{
    const double Sustain = 30, Cooldown = 15 * 60;

    readonly Action<string, string> notify;
    readonly Dictionary<string, double> lastFired = new();
    readonly HashSet<string> limitsFired = new();
    double hotSince = -1, memSince = -1, openBlockEnd;
    public bool Enabled = true;

    public Alerts(Action<string, string> notify) => this.notify = notify;

    void Fire(string key, string title, string text, double now)
    {
        if (lastFired.TryGetValue(key, out var t) && now - t < Cooldown) return;
        lastFired[key] = now;
        notify(title, text);
    }

    static bool Held(bool on, ref double since, double now)
    {
        if (!on) { since = -1; return false; }
        if (since < 0) since = now;
        return now - since >= Sustain;
    }

    public void Check(Sampler s)
    {
        if (!Enabled) return;
        double now = F.Now;

        if (Held((s.Temp ?? 0) >= 85, ref hotSince, now))
            Fire("hot", "Running hot", $"{s.Temp:0}°C for over {Sustain:0} seconds.", now);

        double mem = s.MemUsed / s.MemTotal;
        if (Held(mem >= 0.92, ref memSince, now))
            Fire("mem", "Memory almost full", $"{mem * 100:0}% of {F.Gib(s.MemTotal)} GB in use.", now);

        var c = s.Claude;
        if (c.Ready)
        {
            if (c.BlockEnd > now) openBlockEnd = c.BlockEnd;
            else if (openBlockEnd > 0 && now >= openBlockEnd)
            {
                openBlockEnd = 0;
                Fire("block", "5-hour block reset", "Your Claude Code 5-hour block has ended — a fresh one starts with your next message.", now);
            }
        }

        var l = s.Limits;
        if (!l.Ready) return;
        foreach (var (name, used, reset) in new[] { ("5-hour limit", l.Five, l.FiveReset), ("Weekly limit", l.Week, l.WeekReset) })
        {
            if (used is not { } u) continue;
            foreach (var mark in new[] { 0.95, 0.8 })
            {
                if (u < mark) continue;
                if (limitsFired.Add($"{name}|{mark}|{reset:0}"))
                {
                    string when = reset > 0 ? $" Resets {DateTimeOffset.FromUnixTimeMilliseconds((long)(reset * 1000)).ToLocalTime():ddd HH:mm}." : "";
                    notify($"{name} {u * 100:0}% used", $"{s.Claude.Email ?? "Your account"} is past {mark * 100:0}% of its {name.ToLowerInvariant()}.{when}");
                }
                break;                                          // one notice per crossing, not both marks at once
            }
        }
    }
}
