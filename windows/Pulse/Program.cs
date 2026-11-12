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
            return Snapshot(args[i + 1], args.Contains("--mini") ? WidgetSize.Mini : args.Contains("--compact") ? WidgetSize.Compact
                : args.Contains("--landscape") ? WidgetSize.Landscape : args.Contains("--claude") ? WidgetSize.Claude : WidgetSize.Full,
                args.Contains("--demo"), top, args.Contains("--open"));
        }

        using var single = new Mutex(true, "Pulse.Widget.SingleInstance", out bool first);
        if (!first) return 0;                     // already running

        var app = new Application { ShutdownMode = ShutdownMode.OnMainWindowClose };
        // a widget that vanishes is worse than one that skips a frame: log UI errors and keep running
        app.DispatcherUnhandledException += (_, e) => { Log(e.Exception); e.Handled = true; };
        return app.Run(new WidgetWindow());
    }

    static void Log(Exception ex)
    {
        try
        {
            var dir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "Pulse");
            Directory.CreateDirectory(dir);
            File.AppendAllText(Path.Combine(dir, "crash.log"), $"{DateTime.Now:yyyy-MM-dd HH:mm:ss} {ex}\n\n");
        }
        catch { }
    }

    /// <summary>Renders the widget to a PNG without opening a window (debug aid, used by CI).</summary>
    static int Snapshot(string path, WidgetSize size, bool demo, TopMode? top, bool open)
    {
        var s = new Sampler(start: false);
        if (demo) { if (top is { } dm) s.TopSync(dm); s.LoadDemo(); }
        else
        {
            for (int k = 0; k < 15; k++) { Thread.Sleep(100); s.Sample(); }
            s.ProbeSync();
            if (top is { } m) s.TopSync(m);
        }
        // tooltips and menus use real WPF text: lay a line out so a broken font/culture setup fails here, not on hover
        var probe = new System.Windows.Controls.TextBlock { Text = "3,421,887,102 tokens", FontFamily = new FontFamily("Cascadia Mono, Consolas") };
        probe.Measure(new Size(double.PositiveInfinity, double.PositiveInfinity));

        var v = new PulseView(s) { Size = size, ClaudeOpen = open };
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
