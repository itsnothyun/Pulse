using System;
using System.Collections.Generic;
using System.Windows;
using System.Windows.Media;

namespace PulseApp;

/// <summary>Monochrome palette shared by every view.</summary>
static class Ink
{
    static SolidColorBrush Make(byte r, byte g, byte b, double a = 1)
    {
        var br = new SolidColorBrush(Color.FromArgb((byte)Math.Round(a * 255), r, g, b));
        br.Freeze();
        return br;
    }

    public static readonly SolidColorBrush Bg = Make(9, 9, 9);
    public static readonly SolidColorBrush On = Make(242, 242, 237);
    public static readonly SolidColorBrush Mid = Make(179, 179, 173);
    public static readonly SolidColorBrush Dim = Make(117, 117, 115);
    public static readonly SolidColorBrush Off = Make(38, 38, 38);
    public static readonly SolidColorBrush Line = Make(48, 48, 48);

    static readonly Dictionary<int, SolidColorBrush> alphaCache = new();

    /// <summary>A shade of <paramref name="baseBrush"/> at the given opacity (cached in 1% steps).</summary>
    public static SolidColorBrush Alpha(SolidColorBrush baseBrush, double a)
    {
        int pct = (int)Math.Round(Math.Clamp(a, 0, 1) * 100);
        int key = (baseBrush.Color.R << 16 | baseBrush.Color.G << 8 | baseBrush.Color.B) * 128 + pct;
        if (!alphaCache.TryGetValue(key, out var br))
            alphaCache[key] = br = Make(baseBrush.Color.R, baseBrush.Color.G, baseBrush.Color.B, pct / 100.0);
        return br;
    }
}

/// <summary>5×7 bitmap font drawn as squares — no system fonts involved.</summary>
static partial class PixelFont
{
    static readonly Dictionary<(string, double), Geometry> cache = new();

    public static double Width(string s, double scale) => Math.Max(s.Length * 6 - 1, 0) * scale;

    public static void Draw(DrawingContext? dc, string text, double x, double y, double scale, Brush brush)
    {
        if (dc == null || text.Length == 0) return;
        var key = (text.ToUpperInvariant(), scale);
        if (!cache.TryGetValue(key, out var geo))
        {
            if (cache.Count > 600) cache.Clear();
            cache[key] = geo = Build(key.Item1, scale);
        }
        dc.PushTransform(new TranslateTransform(x, y));
        dc.DrawGeometry(brush, null, geo);
        dc.Pop();
    }

    public static void DrawRight(DrawingContext? dc, string text, double right, double y, double scale, Brush brush)
        => Draw(dc, text, right - Width(text, scale), y, scale, brush);

    static Geometry Build(string text, double scale)
    {
        double dot = scale >= 3 ? scale - 0.75 : scale;
        var g = new StreamGeometry { FillRule = FillRule.Nonzero };
        using (var ctx = g.Open())
        {
            for (int i = 0; i < text.Length; i++)
            {
                if (!Glyphs.TryGetValue(text[i], out var rows)) continue;
                double ox = i * 6 * scale;
                for (int r = 0; r < rows.Length; r++)
                    for (int c = 0; c < 5; c++)
                        if ((rows[r] & (0x10 >> c)) != 0)
                            AddRect(ctx, ox + c * scale, r * scale, dot, dot);
            }
        }
        g.Freeze();
        return g;
    }

    public static void AddRect(StreamGeometryContext ctx, double x, double y, double w, double h)
    {
        ctx.BeginFigure(new Point(x, y), true, true);
        ctx.LineTo(new Point(x + w, y), false, false);
        ctx.LineTo(new Point(x + w, y + h), false, false);
        ctx.LineTo(new Point(x, y + h), false, false);
    }
}
