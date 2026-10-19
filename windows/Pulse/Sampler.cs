using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using System.Windows.Threading;

namespace PulseApp;

/// <summary>Collects every metric. Cheap probes run on the UI thread each second; slow ones on the thread pool.</summary>
sealed class Sampler
{
    public double Cpu;
    public double[] Cores = Array.Empty<double>();
    public double MemUsed, MemTotal = 1, DiskUsed, DiskTotal = 1;
    public string DiskName = "C:";
    public double? Temp, TempMax, Gpu;
    public double NetIn, NetOut;
    public double CommitUsed, CommitTotal;
    public int Procs, Threads;
    public (int Pct, bool Charging, bool Ac)? Battery;
    public ClaudeStats Claude = new();
    public List<TopProc> Top = new();
    TopMode? topMode;
    bool topBusy;
    readonly TopProbe topProbe = new();

    /// <summary>Which top-process list is open under CPU or MEM, if any.</summary>
    public TopMode? TopMode
    {
        get => topMode;
        set { topMode = value; Top = new(); RefreshTop(); Updated?.Invoke(); }
    }

    void RefreshTop()
    {
        if (topMode is not { } m || topBusy) return;
        topBusy = true;
        Task.Run(() => topProbe.Read(m)).ContinueWith(r => dispatcher.BeginInvoke(() =>
        {
            topBusy = false;
            if (r.IsCompletedSuccessfully && topMode == m) { Top = r.Result; Updated?.Invoke(); }
        }));
    }

    /// <summary>Synchronous read for --snapshot (two passes, so CPU has a delta).</summary>
    public void TopSync(TopMode m)
    {
        topMode = m;
        topProbe.Read(m);
        System.Threading.Thread.Sleep(500);
        Top = topProbe.Read(m);
    }
    public string Clock = "";
    public bool Tick;
    public readonly Dictionary<string, List<double>> Hist = new();

    public event Action? Updated;

    readonly Dispatcher dispatcher = Dispatcher.CurrentDispatcher;
    readonly DispatcherTimer? timer;
    readonly Thermals thermals = new();
    readonly GpuProbe gpu = new();
    readonly ClaudeUsage claude = new();
    (long Idle, long Kernel, long User)[] prevCpu;
    (long In, long Out) prevNet;
    DateTime prevNetTime = DateTime.UtcNow;
    bool probeBusy, claudeBusy;
    int n;

    public Sampler(bool start = true)
    {
        prevCpu = Probes.CpuTimes();
        prevNet = Probes.NetBytes();
        Sample();
        if (start)
            timer = new DispatcherTimer(TimeSpan.FromSeconds(1), DispatcherPriority.Background, (_, _) => Sample(), dispatcher);
    }

    public List<double> History(string key) => Hist.TryGetValue(key, out var l) ? l : new List<double>();

    void Push(string key, double v)
    {
        if (!Hist.TryGetValue(key, out var l)) Hist[key] = l = new List<double>();
        l.Add(Math.Clamp(v, 0, 1));
        if (l.Count > 40) l.RemoveAt(0);
    }

    public void Sample()
    {
        Tick = !Tick;
        Clock = DateTime.Now.ToString("HH:mm");

        // CPU from per-core tick deltas (kernel time includes idle on Windows)
        var t = Probes.CpuTimes();
        if (t.Length == prevCpu.Length && t.Length > 0)
        {
            double busyAll = 0, totAll = 0;
            Cores = t.Select((c, i) =>
            {
                double idle = c.Idle - prevCpu[i].Idle;
                double total = (c.Kernel - prevCpu[i].Kernel) + (c.User - prevCpu[i].User);
                double busy = total - idle;
                busyAll += busy; totAll += total;
                return total > 0 ? Math.Clamp(busy / total, 0, 1) : 0;
            }).ToArray();
            Cpu = totAll > 0 ? Math.Clamp(busyAll / totAll, 0, 1) : 0;
        }
        prevCpu = t;
        Push("cpu", Cpu);

        if (Probes.Memory() is { } m) { MemUsed = m.Used; MemTotal = m.Total; }
        Push("mem", MemUsed / MemTotal);

        if (n % 5 == 0 && Probes.Disk() is { } d) { DiskUsed = d.Used; DiskTotal = d.Total; DiskName = d.Name; }
        Push("dsk", DiskUsed / DiskTotal);

        // WMI + performance counters are slow; keep them off the UI thread.
        if (n % 3 == 0 && !probeBusy)
        {
            probeBusy = true;
            bool readGpu = n % 2 == 0;
            Task.Run(() => (thermals.Read(), readGpu ? gpu.Read() : null)).ContinueWith(r =>
                dispatcher.BeginInvoke(() =>
                {
                    probeBusy = false;
                    if (r.IsCompletedSuccessfully)
                    {
                        var (th, g) = r.Result;
                        if (th is { } v) { Temp = v.Value; TempMax = v.Max; }
                        if (readGpu) Gpu = g;
                    }
                }));
        }
        if (Temp is { } tc) Push("tmp", (tc - 30) / 70);
        Push("gpu", Gpu ?? 0);

        var net = Probes.NetBytes();
        var now = DateTime.UtcNow;
        double dt = Math.Max((now - prevNetTime).TotalSeconds, 0.1);
        NetIn = Math.Max(net.In - prevNet.In, 0) / dt;
        NetOut = Math.Max(net.Out - prevNet.Out, 0) / dt;
        prevNet = net; prevNetTime = now;
        Push("net", Math.Log10(Math.Max(NetIn, 1)) / 8);

        if (n % 5 == 0 && Probes.PerfInfo() is { } p)
        {
            CommitUsed = p.CommitUsed; CommitTotal = p.CommitLimit; Procs = p.Procs; Threads = p.Threads;
        }
        if (n % 10 == 0) Battery = Probes.Battery();

        if (n % 20 == 0 && !claudeBusy)
        {
            claudeBusy = true;
            Task.Run(claude.Scan).ContinueWith(r => dispatcher.BeginInvoke(() =>
            {
                claudeBusy = false;
                if (r.IsCompletedSuccessfully) { Claude = r.Result; Updated?.Invoke(); }
            }));
        }

        if (n % 2 == 0) RefreshTop();

        n++;
        Updated?.Invoke();
    }

    /// <summary>Synchronous version of the background probes, for --snapshot.</summary>
    public void ProbeSync()
    {
        if (thermals.Read() is { } v) { Temp = v.Value; TempMax = v.Max; }
        Gpu = gpu.Read();
        Claude = claude.Scan();
    }

    /// <summary>Plausible fake numbers for screenshots (--demo), so no real usage is published.</summary>
    public void LoadDemo()
    {
        var rnd = new Random(7);
        double Wave(int i, double b, double a) => Math.Clamp(b + a * Math.Sin(i / 4.0) + (rnd.NextDouble() - 0.5) * a, 0, 1);
        Hist.Clear();
        for (int i = 0; i < 40; i++)
        {
            Push("cpu", Wave(i, 0.32, 0.18)); Push("mem", Wave(i, 0.62, 0.03)); Push("dsk", 0.58);
            Push("tmp", Wave(i, 0.27, 0.06)); Push("gpu", Wave(i, 0.2, 0.15)); Push("net", Wave(i, 0.6, 0.15));
        }
        Cpu = 0.34; Cores = new[] { 0.62, 0.48, 0.41, 0.35, 0.22, 0.18, 0.12, 0.08 };
        MemUsed = 10.4 * 1073741824; MemTotal = 16.0 * 1073741824;
        DiskUsed = 287e9; DiskTotal = 494e9; DiskName = "C:";
        Temp = 48; TempMax = 55; Gpu = 0.21;
        NetIn = 1.84e6; NetOut = 212e3;
        CommitUsed = 14.2e9; CommitTotal = 24.0e9; Procs = 241; Threads = 3120;
        Battery = (86, true, true);
        Clock = "09:41";
        if (topMode == PulseApp.TopMode.Cpu) Top = new() { new TopProc("Code", 61), new TopProc("chrome", 23), new TopProc("dwm", 14) };
        if (topMode == PulseApp.TopMode.Mem) Top = new() { new TopProc("Code", 3.1e9), new TopProc("chrome", 1.8e9), new TopProc("claude", 0.9e9) };
        Claude = new ClaudeStats
        {
            Ready = true, Week = 412.6e6, Today = 58.3e6, Block = 31.9e6, Output = 2.41e6, Cost = 184.2,
            BlockEnd = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() / 1000.0 + 2 * 3600 + 14 * 60 + 30,
            Input = 9.8e6, CacheRead = 400.4e6, Sessions = 9, Live = 1, Calls = 3184, TodayIndex = 3,
            Days = new[] { 88e6, 102e6, 164e6, 58.3e6, 0, 0, 0 },
        };
    }
}
