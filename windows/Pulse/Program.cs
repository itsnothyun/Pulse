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
            return Snapshot(args[i + 1], args.Contains("--compact"), args.Contains("--demo"));

        using var single = new Mutex(true, "Pulse.Widget.SingleInstance", out bool first);
        if (!first) return 0;                     // already running

        var app = new Application { ShutdownMode = ShutdownMode.OnMainWindowClose };
        return app.Run(new WidgetWindow());
    }

    /// <summary>Renders the widget to a PNG without opening a window (debug aid, used by CI).</summary>
    static int Snapshot(string path, bool compact, bool demo)
    {
        var s = new Sampler(start: false);
        if (demo) s.LoadDemo();
        else
        {
            for (int k = 0; k < 15; k++) { Thread.Sleep(100); s.Sample(); }
            s.ProbeSync();
        }
        var v = new PulseView(s) { Compact = compact };
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
