using System;
using System.IO;
using System.Linq;
using System.Threading;
using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Imaging;

namespace PulseApp;

public static class Program
{
    [STAThread]
    public static int Main(string[] args)
    {
        int i = Array.IndexOf(args, "--snapshot");
        if (i >= 0 && i + 1 < args.Length)
        {
            int t = Array.IndexOf(args, "--top");
            TopMode? top = t >= 0 && t + 1 < args.Length ? (args[t + 1] == "mem" ? TopMode.Mem : TopMode.Cpu) : null;
            return Snapshot(args[i + 1], args.Contains("--mini") ? WidgetSize.Mini : args.Contains("--compact") ? WidgetSize.Compact : WidgetSize.Full, args.Contains("--demo"), top);
        }

        using var single = new Mutex(true, "Pulse.Widget.SingleInstance", out bool first);
        if (!first) return 0;                     // already running

        var app = new Application { ShutdownMode = ShutdownMode.OnMainWindowClose };
        return app.Run(new WidgetWindow());
    }

    /// <summary>Renders the widget to a PNG without opening a window (debug aid, used by CI).</summary>
    static int Snapshot(string path, WidgetSize size, bool demo, TopMode? top)
    {
        var s = new Sampler(start: false);
        if (demo) { if (top is { } dm) s.TopSync(dm); s.LoadDemo(); }
        else
        {
            for (int k = 0; k < 15; k++) { Thread.Sleep(100); s.Sample(); }
            s.ProbeSync();
            if (top is { } m) s.TopSync(m);
        }
        var v = new PulseView(s) { Size = size };
        v.Measure(new Size(double.PositiveInfinity, double.PositiveInfinity));
        v.Arrange(new Rect(v.DesiredSize));
        v.UpdateLayout();

        var bmp = new RenderTargetBitmap((int)(v.DesiredSize.Width * 2), (int)(v.DesiredSize.Height * 2), 192, 192, PixelFormats.Pbgra32);
        bmp.Render(v);
        var enc = new PngBitmapEncoder();
        enc.Frames.Add(BitmapFrame.Create(bmp));
        using var f = File.Create(path);
        enc.Save(f);
        return 0;
    }
}
