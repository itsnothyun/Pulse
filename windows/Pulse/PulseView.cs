using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.Windows;
using System.Windows.Media;

namespace PulseApp;

static class F
{
    static readonly CultureInfo C = CultureInfo.InvariantCulture;
    public static string Pct(double v) => $"{Math.Round(v * 100)}%";
    public static string Gib(double b) => (b / 1073741824).ToString("0.0", C);
    public static string Size(double b) =>
        b >= 1e12 ? (b / 1e12).ToString("0.0", C) + "T" : b >= 1e9 ? (b / 1e9).ToString("0", C) + "G" : (b / 1e6).ToString("0", C) + "M";
    public static string Rate(double b) =>
        b >= 1e9 ? (b / 1e9).ToString("0.0", C) + "G" : b >= 1e6 ? (b / 1e6).ToString("0.0", C) + "M"
        : b >= 1e3 ? (b / 1e3).ToString("0", C) + "K" : b.ToString("0", C) + "B";
    public static string Tok(double v) =>
        v >= 1e9 ? (v / 1e9).ToString("0.00", C) + "B" : v >= 1e6 ? (v / 1e6).ToString("0.0", C) + "M"
        : v >= 1e3 ? (v / 1e3).ToString("0", C) + "K" : v.ToString("0", C);
    public static string Uptime()
    {
        long s = Environment.TickCount64 / 1000;
        long d = s / 86400, h = s % 86400 / 3600, m = s % 3600 / 60;
        return d > 0 ? $"UP {d}D {h}H" : $"UP {h}H {m}M";
    }
}

/// <summary>Bars tween only when they gain or lose a segment, so idle frames cost nothing.</summary>
sealed class Tweens
{
    readonly record struct T(double From, double To, double Start);
    readonly Dictionary<string, T> map = new();
    readonly Stopwatch clock = Stopwatch.StartNew();
    const double Dur = 0.45;
    public bool Active { get; private set; }

    public void BeginFrame() => Active = false;

    public double Get(string key, double target, int segments)
    {
        double now = clock.Elapsed.TotalSeconds;
        if (!map.TryGetValue(key, out var t)) { map[key] = new T(target, target, now - Dur); return target; }
        if (target != t.To)
        {
            double cur = Eval(t, now);
            t = Seg(cur, segments) != Seg(target, segments) ? new T(cur, target, now) : new T(target, target, now - Dur);
            map[key] = t;
        }
        if (now - t.Start < Dur) Active = true;
        return Eval(t, now);
    }

    static double Eval(T t, double now)
    {
        double p = Math.Clamp((now - t.Start) / Dur, 0, 1);
        p = 1 - Math.Pow(1 - p, 3);
        return t.From + (t.To - t.From) * p;
    }

    static int Seg(double v, int n) => (int)(Math.Clamp(v, 0, 1) * n * 2);
}

/// <summary>The whole widget, drawn as pixel rectangles. The same pass measures layout (dc == null).</summary>
sealed class PulseView : FrameworkElement
{
    public const double W = 320, Pad = 18, Radius = 14;
    const double Inner = W - Pad * 2;

    readonly Sampler s;
    readonly Tweens tw = new();
    bool compact, renderHooked;
    double lastHeight;

    public PulseView(Sampler sampler)
    {
        s = sampler;
        RenderOptions.SetEdgeMode(this, EdgeMode.Aliased);
        SnapsToDevicePixels = true;
        UseLayoutRounding = true;
    }

    public bool Compact
    {
        get => compact;
        set { compact = value; InvalidateMeasure(); InvalidateVisual(); }
    }

    /// <summary>Where the overlay loops should sit (set during layout).</summary>
    public Point ScannerPos { get; private set; }
    public Point? PipPos { get; private set; }
    public bool Hot => (s.Temp ?? 0) >= 85;
    public double HeaderBottom => Pad + 14 + 6;

    public event Action? LayoutChanged;

    protected override Size MeasureOverride(Size available) => new(W, Paint(null));

    protected override void OnRender(DrawingContext dc)
    {
        tw.BeginFrame();
        double h = Paint(dc);
        if (Math.Abs(h - lastHeight) > 0.5) { lastHeight = h; InvalidateMeasure(); }
        LayoutChanged?.Invoke();
        if (tw.Active && !renderHooked) { CompositionTarget.Rendering += OnFrame; renderHooked = true; }
        else if (!tw.Active && renderHooked) { CompositionTarget.Rendering -= OnFrame; renderHooked = false; }
    }

    void OnFrame(object? sender, EventArgs e) => InvalidateVisual();

    // ---------- drawing primitives ----------

    static void Rect(DrawingContext? dc, Brush b, double x, double y, double w, double h)
    {
        if (dc != null && w > 0 && h > 0) dc.DrawRectangle(b, null, new Rect(x, y, w, h));
    }

    static void Text(DrawingContext? dc, string t, double x, double y, double scale, Brush b) => PixelFont.Draw(dc, t, x, y, scale, b);
    static void TextR(DrawingContext? dc, string t, double right, double y, double scale, Brush b) => PixelFont.DrawRight(dc, t, right, y, scale, b);

    static void DottedRule(DrawingContext? dc, double x, double y, double w)
    {
        if (dc == null) return;
        var g = new StreamGeometry();
        using (var c = g.Open()) for (double i = 0; i < w; i += 4) PixelFont.AddRect(c, x + i, y, 2, 1);
        g.Freeze();
        dc.DrawGeometry(Ink.Line, null, g);
    }

    void Bar(DrawingContext? dc, string key, double x, double y, double w, double h, double value, int segments = 28, bool blink = false)
    {
        if (dc == null) return;
        double v = tw.Get(key, Math.Clamp(value, 0, 1), segments);
        const double gap = 2;
        double sw = Math.Floor((w - gap * (segments - 1)) / segments);
        double exact = v * segments;
        int lit = (int)exact;
        double partial = exact - lit;
        for (int i = 0; i < segments; i++)
        {
            Brush c = i < lit ? Ink.On : Ink.Off;
            if (i == lit && partial > 0.15) c = Ink.Dim;           // leading half-lit pixel
            if (blink && i == Math.Max(lit - 1, 0)) c = Ink.Off;
            Rect(dc, c, x + i * (sw + gap), y, sw, h);
        }
    }

    static void Sparkline(DrawingContext? dc, double x, double y, List<double> data, int columns = 18, double height = 18)
    {
        if (dc == null) return;
        const double cw = 2, gap = 1, px = 2;
        int count = Math.Min(columns, data.Count);
        double start = x + (columns - count) * (cw + gap);
        int levels = (int)(height / px);
        for (int i = 0; i < columns; i++) Rect(dc, Ink.Off, x + i * (cw + gap), y + height - 1, cw, 1);
        for (int i = 0; i < count; i++)
        {
            double v = data[data.Count - count + i];
            int hgt = Math.Max(1, (int)Math.Round(Math.Clamp(v, 0, 1) * levels));
            double age = (i + 1) / (double)count;
            double cx = start + i * (cw + gap);
            for (int l = 0; l < hgt; l++)
            {
                bool top = l == hgt - 1;
                var b = top ? Ink.Alpha(Ink.On, 0.35 + 0.65 * age) : Ink.Alpha(Ink.Dim, 0.12 + 0.3 * age);
                Rect(dc, b, cx, y + height - (l + 1) * px, cw, px - 0.5);
            }
        }
    }

    static void CoreGrid(DrawingContext? dc, double x, double y, double w, double[] cores)
    {
        if (dc == null || cores.Length == 0) return;
        const double gap = 4, px = 2, lg = 1, height = 15;
        const int levels = 5;
        double cw = Math.Floor((w - gap * (cores.Length - 1)) / cores.Length);
        for (int i = 0; i < cores.Length; i++)
        {
            int lit = (int)Math.Ceiling(Math.Clamp(cores[i], 0, 1) * levels);
            for (int l = 0; l < levels; l++)
                Rect(dc, l < lit ? Ink.On : Ink.Off, x + i * (cw + gap), y + height - (l + 1) * (px + lg), cw, px);
        }
    }

    static void WeekChart(DrawingContext? dc, double x, double y, double w, double[] days, int today)
    {
        if (dc == null) return;
        const double gap = 4, px = 2, lg = 1, chartH = 24;
        const int levels = 8;
        double cw = Math.Floor((w - gap * 6) / 7);
        double peak = 1;
        foreach (var d in days) peak = Math.Max(peak, d);
        for (int i = 0; i < 7; i++)
        {
            int lit = days[i] > 0 ? Math.Max(1, (int)Math.Ceiling(days[i] / peak * levels)) : 0;
            for (int l = 0; l < levels; l++)
            {
                Brush c = l < lit ? (i == today ? Ink.On : Ink.Alpha(Ink.Mid, 0.75)) : (i > today ? Ink.Alpha(Ink.Off, 0.5) : Ink.Off);
                Rect(dc, c, x + i * (cw + gap), y + chartH - (l + 1) * (px + lg), cw, px);
            }
            var label = "MTWTFSS"[i].ToString();
            Text(dc, label, x + i * (cw + gap) + (cw - 5) / 2, y + chartH + 4, 1, i == today ? Ink.On : Ink.Dim);
        }
    }

    // ---------- layout ----------

    string TempState(double t) => s.Temp == null ? "NO SENSOR" : t < 50 ? "COOL" : t < 70 ? "WARM" : t < 85 ? "HOT" : "CRITICAL";

    double Paint(DrawingContext? dc)
    {
        double h = compact ? PaintCompact(null) : PaintFull(null);
        if (dc == null) return h;

        var shape = new RectangleGeometry(new Rect(0, 0, W, h), Radius, Radius);
        dc.PushClip(shape);
        dc.DrawRectangle(Ink.Bg, null, new Rect(0, 0, W, h));
        var lines = new StreamGeometry();                         // faint static scanlines
        using (var c = lines.Open()) for (double y = 0; y < h; y += 3) PixelFont.AddRect(c, 0, y, W, 1);
        lines.Freeze();
        dc.DrawGeometry(Ink.Alpha(Ink.On, 0.02), null, lines);
        if (compact) PaintCompact(dc); else PaintFull(dc);
        dc.Pop();
        dc.DrawRoundedRectangle(null, new Pen(Ink.Alpha(Ink.On, 0.16), 1), new Rect(0.5, 0.5, W - 1, h - 1), Radius, Radius);
        return h;
    }

    double Header(DrawingContext? dc, double y)
    {
        Text(dc, "PULSE", Pad, y, 2, Ink.On);
        ScannerPos = new Point(Pad + PixelFont.Width("PULSE", 2) + 8, y + 5.5);
        string toggle = compact ? "+" : "-";
        TextR(dc, toggle, W - Pad, y + 1.75, 1.5, Ink.Dim);
        TextR(dc, s.Clock, W - Pad - PixelFont.Width(toggle, 1.5) - 8, y + 1.75, 1.5, Ink.Mid);
        return y + 14;
    }

    double Rule(DrawingContext? dc, double y, double gap = 14)
    {
        y += gap;
        DottedRule(dc, Pad, y, Inner);
        return y + 1 + gap;
    }

    double Hero(DrawingContext? dc, double y, string label, string detail, string value, List<double> hist)
    {
        Text(dc, label, Pad, y, 2, Ink.On);
        Text(dc, detail, Pad, y + 19, 1, Ink.Dim);
        TextR(dc, value, W - Pad, y + 2.5, 3, Ink.On);
        Sparkline(dc, W - Pad - 70 - 10 - 53, y + 4, hist);
        return y + 26 + 8;
    }

    double Tile(DrawingContext? dc, double x, double y, double w, string label, string value, string? sub, double? bar, string key)
    {
        const double h = 62;
        if (dc != null) dc.DrawRectangle(null, new Pen(Ink.Line, 1), new Rect(x + 0.5, y + 0.5, w - 1, h - 1));
        Text(dc, label, x + 10, y + 10, 1, Ink.Dim);
        Text(dc, value, x + 10, y + 24, 2, Ink.On);
        if (bar is { } b) Bar(dc, key, x + 10, y + 45, Math.Min(w - 20, 16 * 7), 5, b, 16);
        else if (sub != null) Text(dc, sub, x + 10, y + 45, 1, Ink.Mid);
        return h;
    }

    double PaintFull(DrawingContext? dc)
    {
        double y = Header(dc, Pad);
        y = Rule(dc, y);

        double memF = s.MemUsed / s.MemTotal, diskF = s.DiskUsed / s.DiskTotal;
        double t = s.Temp ?? 0, tempF = (t - 30) / 70;

        y = Hero(dc, y, "CPU", $"{s.Cores.Length} CORES · {s.Procs} PROCS", F.Pct(s.Cpu), s.History("cpu"));
        CoreGrid(dc, Pad, y, Inner, s.Cores);
        y = Rule(dc, y + 15);

        y = Hero(dc, y, "MEM", $"{F.Gib(s.MemUsed)} / {F.Gib(s.MemTotal)} GB", F.Pct(memF), s.History("mem"));
        Bar(dc, "mem", Pad, y, Inner, 8, memF);
        y = Rule(dc, y + 8);

        string tDetail = s.TempMax is { } mx ? $"{TempState(t)} · PEAK {Math.Round(mx)}°" : TempState(t);
        y = Hero(dc, y, "TMP", tDetail, s.Temp == null ? "N/A" : $"{Math.Round(t)}°", s.History("tmp"));
        Bar(dc, "tmp", Pad, y, Inner, 8, tempF, blink: Hot && s.Tick);
        y = Rule(dc, y + 8);

        y = Hero(dc, y, "DSK", $"{s.DiskName} {F.Size(s.DiskTotal - s.DiskUsed)} FREE OF {F.Size(s.DiskTotal)}", F.Pct(diskF), s.History("dsk"));
        Bar(dc, "dsk", Pad, y, Inner, 8, diskF);
        y += 8 + 14;

        double tw2 = (Inner - 8) / 2;
        Tile(dc, Pad, y, tw2, "GPU", s.Gpu == null ? "N/A" : F.Pct(s.Gpu.Value), null, s.Gpu ?? 0, "gpu");
        Tile(dc, Pad + tw2 + 8, y, tw2, "NETWORK", $"↓{F.Rate(s.NetIn)}/S", $"↑{F.Rate(s.NetOut)}/S", null, "net");
        y += 62 + 8;
        Tile(dc, Pad, y, tw2, "COMMIT", F.Size(s.CommitUsed), s.CommitTotal > 0 ? $"OF {F.Size(s.CommitTotal)}" : "-", null, "commit");
        if (s.Battery is { } bat)
            Tile(dc, Pad + tw2 + 8, y, tw2, "POWER", $"{bat.Pct}%", bat.Charging ? "⚡ CHARGING" : bat.Ac ? "AC POWER" : "ON BATTERY", null, "pwr");
        else
            Tile(dc, Pad + tw2 + 8, y, tw2, "POWER", "AC", "NO BATTERY", null, "pwr");
        y += 62;

        y = Rule(dc, y);
        y = ClaudeSection(dc, y);
        y = Rule(dc, y);

        Text(dc, $"{s.Threads} THREADS", Pad, y, 1, Ink.Dim);
        TextR(dc, F.Uptime(), W - Pad, y, 1, Ink.Dim);
        return y + 7 + Pad;
    }

    double ClaudeSection(DrawingContext? dc, double y)
    {
        var c = s.Claude;
        Text(dc, "CLAUDE CODE", Pad, y, 2, Ink.On);
        PipPos = null;
        if (c.Live > 0)
        {
            string live = $"{c.Live} LIVE";
            TextR(dc, live, W - Pad, y + 3.5, 1, Ink.Mid);
            PipPos = new Point(W - Pad - PixelFont.Width(live, 1) - 6 - 4, y + 5);
        }
        else TextR(dc, c.Ready ? "IDLE" : "SCANNING", W - Pad, y + 3.5, 1, Ink.Dim);
        y += 14 + 12;

        Text(dc, F.Tok(c.Week), Pad, y, 3, Ink.On);
        Text(dc, "TOKENS THIS WEEK", Pad, y + 28, 1, Ink.Dim);
        WeekChart(dc, W - Pad - 112, y, 112, c.Days, c.TodayIndex);
        y += 35 + 12;

        double cw = (Inner - 3 * 8) / 4;
        (string, string)[] stats = { ("TODAY", F.Tok(c.Today)), ("LAST 5H", F.Tok(c.Window5h)), ("OUTPUT", F.Tok(c.Output)), ("SESSIONS", c.Sessions.ToString()) };
        for (int i = 0; i < stats.Length; i++)
        {
            Text(dc, stats[i].Item1, Pad + i * (cw + 8), y, 1, Ink.Dim);
            Text(dc, stats[i].Item2, Pad + i * (cw + 8), y + 12, 1.5, Ink.On);
        }
        y += 23 + 12;

        Text(dc, $"IN {F.Tok(c.Input + c.CacheWrite)} · CACHED {F.Tok(c.CacheRead)}", Pad, y, 1, Ink.Dim);
        TextR(dc, $"{c.Calls} CALLS", W - Pad, y, 1, Ink.Dim);
        return y + 7;
    }

    double PaintCompact(DrawingContext? dc)
    {
        double y = Header(dc, Pad);
        y = Rule(dc, y, 12);

        double t = s.Temp ?? 0;
        (string Label, double Frac, string Value, string Key)[] items =
        {
            ("CPU", s.Cpu, F.Pct(s.Cpu), "c-cpu"),
            ("MEM", s.MemUsed / s.MemTotal, F.Pct(s.MemUsed / s.MemTotal), "c-mem"),
            ("TMP", (t - 30) / 70, s.Temp == null ? "N/A" : $"{Math.Round(t)}°", "c-tmp"),
            ("DSK", s.DiskUsed / s.DiskTotal, F.Pct(s.DiskUsed / s.DiskTotal), "c-dsk"),
        };
        double cw = (Inner - 3 * 12) / 4;
        for (int i = 0; i < items.Length; i++)
        {
            double x = Pad + i * (cw + 12);
            Text(dc, items[i].Label, x, y, 1, Ink.Dim);
            Text(dc, items[i].Value, x, y + 13, 2, Ink.On);
            Bar(dc, items[i].Key, x, y + 33, cw, 4, items[i].Frac, 8, items[i].Label == "TMP" && Hot && s.Tick);
        }
        y += 37;
        y = Rule(dc, y, 12);

        double tx = Pad;
        PipPos = null;
        if (s.Claude.Live > 0) { PipPos = new Point(Pad, y + 1.5); tx += 10; }
        Text(dc, $"CLAUDE {F.Tok(s.Claude.Week)} WK", tx, y, 1, Ink.Mid);
        TextR(dc, $"TODAY {F.Tok(s.Claude.Today)}", W - Pad, y, 1, Ink.Dim);
        return y + 7 + Pad;
    }
}
