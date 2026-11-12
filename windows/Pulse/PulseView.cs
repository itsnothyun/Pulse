using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.Linq;
using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Animation;

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
    public static string Usd(double v) =>
        v < 100 ? "$" + v.ToString("0.00", C) : v < 10000 ? "$" + v.ToString("0", C) : "$" + (v / 1e3).ToString("0.0", C) + "K";
    public static string Mem(double b) => b >= 1e9 ? (b / 1e9).ToString("0.0", C) + "G" : (b / 1e6).ToString("0", C) + "M";
    public static string Countdown(double s)
    {
        int m = (int)Math.Ceiling(s / 60), h = m / 60;
        return h > 0 ? $"{h}H {m % 60}M" : $"{m}M";
    }
    /// <summary>Text in the pixel font: unknown characters become spaces, anything past <paramref name="max"/> is cut.</summary>
    public static string Glyphs(string n, int max)
    {
        var chars = n.ToUpperInvariant().Select(c => PixelFont.Has(c) ? c : ' ').Take(max).ToArray();
        return new string(chars);
    }
    /// <summary>Process names in the pixel font: unknown characters become spaces.</summary>
    public static string ProcName(string n) => Glyphs(n, 20);
    public static double Now => DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() / 1000.0;
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
    const double Settled = double.NegativeInfinity;   // a tween that isn't moving (now - start can't round under Dur)
    public bool Active { get; private set; }

    public void BeginFrame() => Active = false;

    public double Get(string key, double target, int segments)
    {
        double now = clock.Elapsed.TotalSeconds;
        if (!map.TryGetValue(key, out var t)) { map[key] = new T(target, target, Settled); return target; }
        if (target != t.To)
        {
            double cur = Eval(t, now);
            t = Seg(cur, segments) != Seg(target, segments) ? new T(cur, target, now) : new T(target, target, Settled);
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

/// <summary>
/// The views, like a phone widget's sizes: everything, everything side by side, Claude only, the four big numbers,
/// one quiet line. Clicking the header steps through them in this order.
/// </summary>
enum WidgetSize { Full, Landscape, Claude, Compact, Mini }

static class WidgetSizeExt
{
    public static WidgetSize Next(this WidgetSize s) => (WidgetSize)(((int)s + 1) % 5);
    public static string Title(this WidgetSize s) => s switch
    {
        WidgetSize.Full => "Full", WidgetSize.Landscape => "Landscape", WidgetSize.Claude => "Claude",
        WidgetSize.Compact => "Compact", _ => "Mini",
    };
}

/// <summary>The whole widget, drawn as pixel rectangles. The same pass measures layout (dc == null).</summary>
sealed class PulseView : FrameworkElement
{
    public const double FullW = 320, LandW = 660, Pad = 18;
    const double W = FullW, Inner = W - Pad * 2;
    const double Col = (LandW - Pad * 2 - 24) / 2;                // landscape column width
    const double MiniH = 29, MiniValueW = 4 * 6 * 1.5 - 1.5;    // value slots sized for "100%"

    readonly Sampler s;
    readonly Tweens tw = new();
    WidgetSize size;
    bool renderHooked;
    double lastHeight;

    public PulseView(Sampler sampler)
    {
        s = sampler;
        RenderOptions.SetEdgeMode(this, EdgeMode.Aliased);
        SnapsToDevicePixels = true;
        UseLayoutRounding = true;
    }

    public WidgetSize Size
    {
        get => size;
        set { size = value; InvalidateMeasure(); InvalidateVisual(); }
    }

    bool compact => size == WidgetSize.Compact;
    public bool IsMini => size == WidgetSize.Mini;
    public double Radius => IsMini ? 10 : 14;
    public double PanelWidth => WidthOf(size);
    public static double WidthOf(WidgetSize s) => s == WidgetSize.Mini ? MiniWidth : s == WidgetSize.Landscape ? LandW : FullW;

    /// <summary>The Claude breakdown (by model, project, account) under the Claude section; always open in the Claude view.</summary>
    public bool ClaudeOpen { get; set; }
    bool BreakdownShown => size == WidgetSize.Claude || ClaudeOpen;

    readonly List<(System.Windows.Rect R, string Text)> tips = new();

    /// <summary>The exact value under a point, for the hover tooltip.</summary>
    public string? TipAt(Point p)
    {
        for (int i = tips.Count - 1; i >= 0; i--) if (tips[i].R.Contains(p)) return tips[i].Text;
        return null;
    }

    void Tip(DrawingContext? dc, double x, double y, double w, double h, string text)
    {
        if (dc != null) tips.Add((new System.Windows.Rect(x - 3, y - 3, w + 6, h + 6), text));
    }
    static double MiniWidth => 12 + 4 + 3 * 12 + 3 * (PixelFont.Width("CPU", 1) + 5 + MiniValueW) + 12;

    /// <summary>Where the overlay loops should sit (set during layout).</summary>
    public Point ScannerPos { get; private set; }
    public Point? PipPos { get; private set; }
    public bool Hot => (s.Temp ?? 0) >= 85;
    public double HeaderBottom => IsMini ? MiniH : Pad + 14 + 6;

    public event Action? LayoutChanged;

    /// <summary>Vertical extent of the CPU and MEM rows in Full size; a click there opens the top-process list.</summary>
    (double Top, double Bottom) cpuRow, memRow;
    System.Windows.Rect claudeArea = System.Windows.Rect.Empty;

    /// <summary>A click on the Claude section (Full and Landscape) opens or closes its breakdown.</summary>
    public bool ClaudeAt(Point p) => (size == WidgetSize.Full || size == WidgetSize.Landscape) && claudeArea.Contains(p);

    public TopMode? RowAt(double y) =>
        size != WidgetSize.Full ? null
        : y >= cpuRow.Top && y <= cpuRow.Bottom ? PulseApp.TopMode.Cpu
        : y >= memRow.Top && y <= memRow.Bottom ? PulseApp.TopMode.Mem : null;

    double TopList(DrawingContext? dc, double y, TopMode mode)
    {
        y += 14;
        for (int i = 0; i < 3; i++)
        {
            double ry = y + i * 13;
            Text(dc, (i + 1).ToString(), Pad, ry, 1, Ink.Dim);
            if (i < s.Top.Count)
            {
                var p = s.Top[i];
                Text(dc, F.ProcName(p.Name), Pad + 14, ry, 1, Ink.Mid);
                TextR(dc, mode == PulseApp.TopMode.Cpu ? $"{Math.Round(p.Value)}%" : F.Mem(p.Value), W - Pad, ry, 1, Ink.On);
            }
            else Text(dc, i == 0 ? "READING" : "-", Pad + 14, ry, 1, Ink.Off);
        }
        return y + 2 * 13 + 7;
    }

    protected override System.Windows.Size MeasureOverride(System.Windows.Size available) => new(PanelWidth, Paint(null));

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

    /// <summary>
    /// Soft pastel spectrum that drifts across the text on a slow loop. The compositor runs the animation,
    /// so the view never repaints for it; with reduced motion it holds still.
    /// </summary>
    static readonly Brush Rainbow = MakeRainbow();

    static Brush MakeRainbow()
    {
        const double period = 64;                                  // px per full spectrum: a 5-letter word shows about half
        var b = new LinearGradientBrush
        {
            MappingMode = BrushMappingMode.Absolute, SpreadMethod = GradientSpreadMethod.Repeat,
            StartPoint = new Point(0, 0), EndPoint = new Point(period, 0),
        };
        string[] hues = { "#F2A7BC", "#F2C7A0", "#DCE6A3", "#A8E0C8", "#A6C8F0", "#C6AEF0", "#F2A7BC" };
        for (int i = 0; i < hues.Length; i++)
            b.GradientStops.Add(new GradientStop((Color)ColorConverter.ConvertFromString(hues[i]), i / (double)(hues.Length - 1)));
        var move = new TranslateTransform();
        b.Transform = move;
        if (SystemParameters.ClientAreaAnimation)
            move.BeginAnimation(TranslateTransform.XProperty, new DoubleAnimation(0, period, TimeSpan.FromSeconds(7)) { RepeatBehavior = RepeatBehavior.Forever });
        return b;
    }

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
        double h = Body(null);
        if (dc == null) return h;
        tips.Clear();
        double w = PanelWidth, r = Radius;

        var shape = new RectangleGeometry(new Rect(0, 0, w, h), r, r);
        dc.PushClip(shape);
        dc.DrawRectangle(Ink.Bg, null, new Rect(0, 0, w, h));
        var lines = new StreamGeometry();                         // faint static scanlines
        using (var c = lines.Open()) for (double y = 0; y < h; y += 3) PixelFont.AddRect(c, 0, y, w, 1);
        lines.Freeze();
        dc.DrawGeometry(Ink.Alpha(Ink.On, 0.02), null, lines);
        Body(dc);
        dc.Pop();
        dc.DrawRoundedRectangle(null, new Pen(Ink.Alpha(Ink.On, 0.16), 1), new Rect(0.5, 0.5, w - 1, h - 1), r, r);
        return h;
    }

    double Body(DrawingContext? dc) => size switch
    {
        WidgetSize.Landscape => PaintLandscape(dc),
        WidgetSize.Claude => PaintClaude(dc),
        WidgetSize.Compact => PaintCompact(dc),
        WidgetSize.Mini => PaintMini(dc),
        _ => PaintFull(dc),
    };

    /// <summary>One quiet line: no scanner, no sweep. Only a running-hot temperature blinks.</summary>
    double PaintMini(DrawingContext? dc)
    {
        PipPos = null;
        ScannerPos = new Point(-100, -100);
        double t = s.Temp ?? 0, x = 12, y = (MiniH - 10.5) / 2;
        Rect(dc, Ink.Alpha(Ink.On, 0.85), x, (MiniH - 4) / 2, 4, 4);
        x += 4 + 12;
        (string Label, string Value, bool Blink, string Tip)[] items =
        {
            ("CPU", F.Pct(s.Cpu), false, CpuTip),
            ("MEM", F.Pct(s.MemUsed / s.MemTotal), false, MemTip),
            ("TMP", s.Temp == null ? "N/A" : $"{Math.Round(t)}°", Hot, TempTip),
        };
        foreach (var it in items)
        {
            double x0 = x;
            Text(dc, it.Label, x, y + 1.75, 1, Ink.Dim);
            x += PixelFont.Width(it.Label, 1) + 5;
            TextR(dc, it.Value, x + MiniValueW, y, 1.5, it.Blink && s.Tick ? Ink.Off : Ink.On);   // fixed slot: digits never shift the window
            x += MiniValueW + 12;
            Tip(dc, x0, y, x - 12 - x0, 10.5, it.Tip);
        }
        return MiniH;
    }

    double Header(DrawingContext? dc, double y, double width = W)
    {
        Text(dc, "PULSE", Pad, y, 2, Ink.On);
        ScannerPos = new Point(Pad + PixelFont.Width("PULSE", 2) + 8, y + 5.5);
        string toggle = size == WidgetSize.Compact ? "+" : "-";
        TextR(dc, toggle, width - Pad, y + 1.75, 1.5, Ink.Dim);
        TextR(dc, s.Clock, width - Pad - PixelFont.Width(toggle, 1.5) - 8, y + 1.75, 1.5, Ink.Mid);
        Tip(dc, width - Pad - 70, y, 70, 14, $"{size.Title()} view · click the header for the next one");
        return y + 14;
    }

    double Rule(DrawingContext? dc, double y, double gap = 14, double width = Inner)
    {
        y += gap;
        DottedRule(dc, Pad, y, width);
        return y + 1 + gap;
    }

    double Hero(DrawingContext? dc, double y, string label, string detail, string value, List<double> hist, string tip)
    {
        Text(dc, label, Pad, y, 2, Ink.On);
        Text(dc, detail, Pad, y + 19, 1, Ink.Dim);
        TextR(dc, value, W - Pad, y + 2.5, 3, Ink.On);
        Sparkline(dc, W - Pad - 70 - 10 - 53, y + 4, hist);
        Tip(dc, Pad, y, Inner, 26, tip);
        return y + 26 + 8;
    }

    double Tile(DrawingContext? dc, double x, double y, double w, string label, string value, string? sub, double? bar, string key, string tip)
    {
        const double h = 62;
        if (dc != null) dc.DrawRectangle(null, new Pen(Ink.Line, 1), new Rect(x + 0.5, y + 0.5, w - 1, h - 1));
        Text(dc, label, x + 10, y + 10, 1, Ink.Dim);
        Text(dc, value, x + 10, y + 24, 2, Ink.On);
        if (bar is { } b) Bar(dc, key, x + 10, y + 45, Math.Min(w - 20, 16 * 7), 5, b, 16);
        else if (sub != null) Text(dc, sub, x + 10, y + 45, 1, Ink.Mid);
        Tip(dc, x, y, w, h, tip);
        return h;
    }

    // ---------- exact values for the hover tooltip ----------

    string CpuTip => $"CPU {s.Cpu * 100:0.0}% across {s.Cores.Length} cores · {s.Procs:N0} processes";
    string MemTip => $"Memory {s.MemUsed / 1073741824:0.00} GB used of {s.MemTotal / 1073741824:0.00} GB ({s.MemUsed / s.MemTotal * 100:0.0}%)";
    string TempTip => s.Temp is { } t ? $"Temperature {t:0.0}°C" + (s.TempMax is { } m ? $" · hottest sensor {m:0.0}°C" : "") : "No temperature sensor found";
    string DiskTip => $"{s.DiskName} {(s.DiskTotal - s.DiskUsed) / 1e9:0.0} GB free of {s.DiskTotal / 1e9:0.0} GB";
    string GpuTip => s.Gpu is { } g ? $"GPU {g * 100:0.0}% busy" : "No GPU counters";
    string NetTip => $"Download {s.NetIn / 1e3:N1} KB/s · upload {s.NetOut / 1e3:N1} KB/s";
    string CommitTip => $"Commit charge {s.CommitUsed / 1e9:0.00} GB of {s.CommitTotal / 1e9:0.00} GB";
    string PowerTip => s.Battery is { } b ? $"Battery {b.Pct}% · {(b.Charging ? "charging" : b.Ac ? "plugged in" : "on battery")}" : "Mains power, no battery";
    static string Exact(double tokens) => $"{tokens:N0} tokens";
    static string Clock(double unix) => DateTimeOffset.FromUnixTimeMilliseconds((long)(unix * 1000)).ToLocalTime().ToString("ddd HH:mm", CultureInfo.InvariantCulture);

    // ---------- views ----------

    double PaintFull(DrawingContext? dc)
    {
        double y = Header(dc, Pad);
        y = Rule(dc, y);

        double memF = s.MemUsed / s.MemTotal, diskF = s.DiskUsed / s.DiskTotal;
        double t = s.Temp ?? 0, tempF = (t - 30) / 70;

        double y0 = y;
        y = Hero(dc, y, "CPU", $"{s.Cores.Length} CORES · {s.Procs} PROCS", F.Pct(s.Cpu), s.History("cpu"), CpuTip);
        CoreGrid(dc, Pad, y, Inner, s.Cores);
        y += 15;
        cpuRow = (y0 - 7, y + 7);
        if (s.TopMode == PulseApp.TopMode.Cpu) y = TopList(dc, y, PulseApp.TopMode.Cpu);
        y = Rule(dc, y);

        y0 = y;
        y = Hero(dc, y, "MEM", $"{F.Gib(s.MemUsed)} / {F.Gib(s.MemTotal)} GB", F.Pct(memF), s.History("mem"), MemTip);
        Bar(dc, "mem", Pad, y, Inner, 8, memF);
        y += 8;
        memRow = (y0 - 7, y + 7);
        if (s.TopMode == PulseApp.TopMode.Mem) y = TopList(dc, y, PulseApp.TopMode.Mem);
        y = Rule(dc, y);

        string tDetail = s.TempMax is { } mx ? $"{TempState(t)} · PEAK {Math.Round(mx)}°" : TempState(t);
        y = Hero(dc, y, "TMP", tDetail, s.Temp == null ? "N/A" : $"{Math.Round(t)}°", s.History("tmp"), TempTip);
        Bar(dc, "tmp", Pad, y, Inner, 8, tempF, blink: Hot && s.Tick);
        y = Rule(dc, y + 8);

        y = Hero(dc, y, "DSK", $"{s.DiskName} {F.Size(s.DiskTotal - s.DiskUsed)} FREE OF {F.Size(s.DiskTotal)}", F.Pct(diskF), s.History("dsk"), DiskTip);
        Bar(dc, "dsk", Pad, y, Inner, 8, diskF);
        y += 8 + 14;

        double tw2 = (Inner - 8) / 2;
        Tile(dc, Pad, y, tw2, "GPU", s.Gpu == null ? "N/A" : F.Pct(s.Gpu.Value), null, s.Gpu ?? 0, "gpu", GpuTip);
        Tile(dc, Pad + tw2 + 8, y, tw2, "NETWORK", $"↓{F.Rate(s.NetIn)}/S", $"↑{F.Rate(s.NetOut)}/S", null, "net", NetTip);
        y += 62 + 8;
        Tile(dc, Pad, y, tw2, "COMMIT", F.Size(s.CommitUsed), s.CommitTotal > 0 ? $"OF {F.Size(s.CommitTotal)}" : "-", null, "commit", CommitTip);
        if (s.Battery is { } bat)
            Tile(dc, Pad + tw2 + 8, y, tw2, "POWER", $"{bat.Pct}%", bat.Charging ? "⚡ CHARGING" : bat.Ac ? "AC POWER" : "ON BATTERY", null, "pwr", PowerTip);
        else
            Tile(dc, Pad + tw2 + 8, y, tw2, "POWER", "AC", "NO BATTERY", null, "pwr", PowerTip);
        y += 62;

        y = Rule(dc, y);
        y = ClaudeSection(dc, Pad, y, Inner);
        y = Rule(dc, y);

        Footer(dc, y, W);
        return y + 7 + Pad;
    }

    void Footer(DrawingContext? dc, double y, double width)
    {
        Text(dc, $"{s.Threads} THREADS", Pad, y, 1, Ink.Dim);
        TextR(dc, F.Uptime(), width - Pad, y, 1, Ink.Dim);
    }

    /// <summary>System on the left, Claude on the right: for a wide spot like the top of a screen.</summary>
    double PaintLandscape(DrawingContext? dc)
    {
        double y = Header(dc, Pad, LandW);
        y = Rule(dc, y, 14, LandW - Pad * 2);
        double top = y, rx = Pad + Col + 24;

        double t = s.Temp ?? 0;
        (string Label, string Detail, string Value, double Frac, string Key, bool Blink, string Tip)[] rows =
        {
            ("CPU", $"{s.Cores.Length} CORES · {s.Procs} PROCS", F.Pct(s.Cpu), s.Cpu, "l-cpu", false, CpuTip),
            ("MEM", $"{F.Gib(s.MemUsed)} / {F.Gib(s.MemTotal)} GB", F.Pct(s.MemUsed / s.MemTotal), s.MemUsed / s.MemTotal, "l-mem", false, MemTip),
            ("TMP", s.TempMax is { } mx ? $"{TempState(t)} · PEAK {Math.Round(mx)}°" : TempState(t), s.Temp == null ? "N/A" : $"{Math.Round(t)}°", (t - 30) / 70, "l-tmp", Hot && s.Tick, TempTip),
            ("DSK", $"{s.DiskName} {F.Size(s.DiskTotal - s.DiskUsed)} FREE", F.Pct(s.DiskUsed / s.DiskTotal), s.DiskUsed / s.DiskTotal, "l-dsk", false, DiskTip),
        };
        double ly = top;
        foreach (var r in rows)
        {
            Text(dc, r.Label, Pad, ly, 2, Ink.On);
            Text(dc, r.Detail, Pad + 46, ly + 3.5, 1, Ink.Dim);
            TextR(dc, r.Value, Pad + Col, ly, 2, Ink.On);
            Bar(dc, r.Key, Pad, ly + 21, Col, 5, r.Frac, 28, r.Blink);
            Tip(dc, Pad, ly, Col, 26, r.Tip);
            ly += 26 + 16;
        }

        double cw = (Col - 2 * 8) / 3;
        (string Label, string Value, string Tip)[] small =
        {
            ("GPU", s.Gpu == null ? "N/A" : F.Pct(s.Gpu.Value), GpuTip),
            ("NETWORK", $"↓{F.Rate(s.NetIn)}/S", NetTip),
            ("POWER", s.Battery is { } b ? $"{b.Pct}%" : "AC", PowerTip),
        };
        for (int i = 0; i < small.Length; i++)
        {
            double x = Pad + i * (cw + 8);
            Text(dc, small[i].Label, x, ly, 1, Ink.Dim);
            Text(dc, small[i].Value, x, ly + 12, 1.5, Ink.On);
            Tip(dc, x, ly, cw, 23, small[i].Tip);
        }
        ly += 23;

        double ry = ClaudeSection(dc, rx, top, Col);
        double bottom = Math.Max(ly, ry);
        VerticalRule(dc, Pad + Col + 12, top, bottom - top);

        y = Rule(dc, bottom, 14, LandW - Pad * 2);
        Footer(dc, y, LandW);
        return y + 7 + Pad;
    }

    static void VerticalRule(DrawingContext? dc, double x, double y, double h)
    {
        if (dc == null) return;
        var g = new StreamGeometry();
        using (var c = g.Open()) for (double i = 0; i < h; i += 4) PixelFont.AddRect(c, x, y + i, 1, 2);
        g.Freeze();
        dc.DrawGeometry(Ink.Line, null, g);
    }

    /// <summary>Claude only: the account, limits, this week and where the tokens went.</summary>
    double PaintClaude(DrawingContext? dc)
    {
        double y = Header(dc, Pad);
        y = Rule(dc, y);
        y = ClaudeSection(dc, Pad, y, Inner);
        y = Rule(dc, y);
        Text(dc, $"{s.Claude.Calls} CALLS · {s.Claude.Sessions} SESSIONS", Pad, y, 1, Ink.Dim);
        TextR(dc, F.Uptime(), W - Pad, y, 1, Ink.Dim);
        return y + 7 + Pad;
    }

    double ClaudeSection(DrawingContext? dc, double x, double y, double w)
    {
        var c = s.Claude;
        double right = x + w, top = y;
        Text(dc, "CLAUDE CODE", x, y, 2, Ink.On);
        PipPos = null;
        if (c.Live > 0)
        {
            string live = $"{c.Live} LIVE";
            TextR(dc, live, right, y + 3.5, 1, Ink.Mid);
            PipPos = new Point(right - PixelFont.Width(live, 1) - 6 - 4, y + 5);
            Tip(dc, right - 60, y, 60, 14, $"{c.Live} session{(c.Live == 1 ? "" : "s")} active in the last 5 minutes");
        }
        else TextR(dc, c.Ready ? "IDLE" : "SCANNING", right, y + 3.5, 1, Ink.Dim);
        y += 14 + 12;

        if (c.Email != null)
        {
            string plan = c.Plan == null ? "" : F.Glyphs(c.Plan, 12).Trim();
            double planW = plan.Length > 0 ? PixelFont.Width(plan, 1) + 12 : 0;
            Text(dc, F.Glyphs(c.Email, (int)((w - planW) / 6)), x, y, 1, Ink.Mid);
            if (plan.Length > 0) TextR(dc, plan, right, y, 1, plan == "ULTRA" ? Rainbow : Ink.Dim);
            Tip(dc, x, y, w, 7, $"Signed in as {c.Email}" + (c.Plan != null ? $" · {c.Plan} plan" : "") + " · follows /login");
            y += 7 + 12;
        }

        Text(dc, F.Tok(c.Week), x, y, 3, Ink.On);
        Text(dc, "TOKENS THIS WEEK", x, y + 28, 1, Ink.Dim);
        Tip(dc, x, y, w - 124, 35, $"{Exact(c.Week)} this week (all accounts on this PC)");
        WeekChart(dc, right - 112, y, 112, c.Days, c.TodayIndex);
        Tip(dc, right - 112, y, 112, 35, string.Join(" · ", c.Days.Select((d, i) => $"{"MTWTFSS"[i]} {F.Tok(d)}")));
        y += 35 + 12;

        double left = Math.Max(c.BlockEnd - F.Now, 0);
        double cw = (w - 3 * 8) / 4;
        (string, string, string)[] stats =
        {
            ("TODAY", F.Tok(c.Today), $"{Exact(c.Today)} today"),
            ("5H BLOCK", F.Tok(left > 0 ? c.Block : 0), left > 0 ? $"{Exact(c.Block)} in the current 5-hour block" : "No 5-hour block open"),
            ("EST. COST", F.Usd(c.Cost), $"${c.Cost:N2} at API list prices (plans are billed differently)"),
            ("SESSIONS", c.Sessions.ToString(), $"{c.Sessions} sessions this week"),
        };
        for (int i = 0; i < stats.Length; i++)
        {
            Text(dc, stats[i].Item1, x + i * (cw + 8), y, 1, Ink.Dim);
            Text(dc, stats[i].Item2, x + i * (cw + 8), y + 12, 1.5, Ink.On);
            Tip(dc, x + i * (cw + 8), y, cw, 23, stats[i].Item3);
        }
        y += 23 + 12;

        var l = s.Limits;
        if (l.Ready && (l.Five != null || l.Week != null))
        {
            if (l.Five is { } five) y = LimitRow(dc, x, y, w, "5H LIMIT", five, l.FiveReset, "l5", "5-hour limit");
            if (l.Week is { } wk) y = LimitRow(dc, x, y, w, "WEEK LIMIT", wk, l.WeekReset, "lw", "Weekly limit");
            y += 4;
        }

        Text(dc, $"IN {F.Tok(c.Input + c.CacheWrite)} · OUT {F.Tok(c.Output)} · CACHED {F.Tok(c.CacheRead)}", x, y, 1, Ink.Dim);
        TextR(dc, $"{c.Calls} CALLS", right, y, 1, Ink.Dim);
        Tip(dc, x, y, w, 7, $"Input {c.Input + c.CacheWrite:N0} · output {c.Output:N0} · cache reads {c.CacheRead:N0} · {c.Calls:N0} API calls");
        y += 7 + 12;

        Text(dc, left > 0 ? $"RESETS IN {F.Countdown(left)}" : "NO 5H BLOCK OPEN", x, y, 1, left > 0 ? Ink.Mid : Ink.Dim);
        Bar(dc, "block", right - 118, y + 2, 118, 3, left > 0 ? 1 - left / (5 * 3600) : 0, 20);
        if (left > 0) Tip(dc, x, y, w, 7, $"Local 5-hour block ends {Clock(c.BlockEnd)}");
        y += 7;

        if (BreakdownShown) y = Breakdown(dc, x, y, w);
        claudeArea = new System.Windows.Rect(x, top - 7, w, y - top + 14);
        if (size != WidgetSize.Claude)
            Tip(dc, x, top, 120, 14, ClaudeOpen ? "Click to hide the breakdown" : "Click for tokens by model, project and account");
        return y;
    }

    double LimitRow(DrawingContext? dc, double x, double y, double w, string label, double used, double reset, string key, string name)
    {
        const double labelW = 66, pctW = 30;
        Text(dc, label, x, y, 1, Ink.Dim);
        Bar(dc, key, x + labelW, y + 1, w - labelW - pctW - 8, 5, used, 24);
        TextR(dc, F.Pct(used), x + w, y, 1, used >= 0.9 ? Ink.On : Ink.Mid);
        Tip(dc, x, y, w, 7, $"{name} {used * 100:0.#}% used" + (reset > 0 ? $" · resets {Clock(reset)}" : " · no window open"));
        return y + 7 + 9;
    }

    double Breakdown(DrawingContext? dc, double x, double y, double w)
    {
        var c = s.Claude;
        double total = Math.Max(c.Week, 1), right = x + w;
        (string Title, List<Slice> Items)[] groups = { ("BY MODEL", c.ByModel), ("BY PROJECT", c.ByProject), ("BY ACCOUNT", c.ByAccount) };
        foreach (var (title, items) in groups)
        {
            y += 14;
            DottedRule(dc, x, y, w);
            y += 1 + 10;
            Text(dc, title, x, y, 1, Ink.Dim);
            y += 7 + 7;
            if (items.Count == 0) { Text(dc, "-", x, y, 1, Ink.Off); y += 7; continue; }
            int n = Math.Min(3, items.Count);
            for (int i = 0; i < n; i++)
            {
                var it = items[i];
                string amount = $"{F.Tok(it.Tokens)} · {Math.Round(it.Tokens / total * 100)}%";
                double amountW = PixelFont.Width(amount, 1);
                Bar(dc, $"bd-{title}-{i}", x, y + 11, w, 2, it.Tokens / total, 28);
                Text(dc, F.Glyphs(it.Name, (int)((w - amountW - 12) / 6)), x, y, 1, Ink.Mid);
                TextR(dc, amount, right, y, 1, Ink.On);
                Tip(dc, x, y, w, 10, $"{it.Name}: {Exact(it.Tokens)} · ${it.Cost:N2} est.");
                y += 7 + 12;
            }
            if (items.Count > n) { Text(dc, $"+{items.Count - n} MORE", x, y, 1, Ink.Dim); y += 7 + 4; }
            y -= 4;
        }
        return y;
    }

    double PaintCompact(DrawingContext? dc)
    {
        double y = Header(dc, Pad);
        y = Rule(dc, y, 12);

        double t = s.Temp ?? 0;
        (string Label, double Frac, string Value, string Key, string Tip)[] items =
        {
            ("CPU", s.Cpu, F.Pct(s.Cpu), "c-cpu", CpuTip),
            ("MEM", s.MemUsed / s.MemTotal, F.Pct(s.MemUsed / s.MemTotal), "c-mem", MemTip),
            ("TMP", (t - 30) / 70, s.Temp == null ? "N/A" : $"{Math.Round(t)}°", "c-tmp", TempTip),
            ("DSK", s.DiskUsed / s.DiskTotal, F.Pct(s.DiskUsed / s.DiskTotal), "c-dsk", DiskTip),
        };
        double cw = (Inner - 3 * 12) / 4;
        for (int i = 0; i < items.Length; i++)
        {
            double x = Pad + i * (cw + 12);
            Text(dc, items[i].Label, x, y, 1, Ink.Dim);
            Text(dc, items[i].Value, x, y + 13, 2, Ink.On);
            Bar(dc, items[i].Key, x, y + 33, cw, 4, items[i].Frac, 8, items[i].Label == "TMP" && Hot && s.Tick);
            Tip(dc, x, y, cw, 37, items[i].Tip);
        }
        y += 37;
        y = Rule(dc, y, 12);

        double tx = Pad;
        PipPos = null;
        if (s.Claude.Live > 0) { PipPos = new Point(Pad, y + 1.5); tx += 10; }
        double left = s.Claude.BlockEnd - F.Now;
        Text(dc, $"CLAUDE {F.Tok(s.Claude.Week)} · ~{F.Usd(s.Claude.Cost)}", tx, y, 1, Ink.Mid);
        Tip(dc, Pad, y, Inner / 2, 7, $"{Exact(s.Claude.Week)} this week · ${s.Claude.Cost:N2} at API list prices");
        var l = s.Limits;
        string limitText = string.Join(" · ", new[] { l.Five is { } f5 ? $"5H {F.Pct(f5)}" : null, l.Week is { } wk ? $"WK {F.Pct(wk)}" : null }.Where(v => v != null));
        string rightText = limitText.Length > 0 ? limitText
                         : left > 0 ? $"RESETS {F.Countdown(left)}" : $"TODAY {F.Tok(s.Claude.Today)}";
        TextR(dc, rightText, W - Pad, y, 1, Ink.Dim);
        if (limitText.Length > 0) Tip(dc, W - Pad - 100, y, 100, 7, $"Plan limits used: {limitText.Replace("WK", "week")}");
        return y + 7 + Pad;
    }
}
