using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Management;
using System.Net.NetworkInformation;
using System.Runtime.InteropServices;

namespace PulseApp;

static class Native
{
    [StructLayout(LayoutKind.Sequential)]
    public struct MEMORYSTATUSEX
    {
        public uint dwLength, dwMemoryLoad;
        public ulong ullTotalPhys, ullAvailPhys, ullTotalPageFile, ullAvailPageFile, ullTotalVirtual, ullAvailVirtual, ullAvailExtendedVirtual;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct SYSTEM_POWER_STATUS
    {
        public byte ACLineStatus, BatteryFlag, BatteryLifePercent, SystemStatusFlag;
        public int BatteryLifeTime, BatteryFullLifeTime;
    }

    /// <summary>SYSTEM_PROCESSOR_PERFORMANCE_INFORMATION (one per logical CPU).</summary>
    [StructLayout(LayoutKind.Sequential)]
    public struct SPPI
    {
        public long IdleTime, KernelTime, UserTime, Reserved1a, Reserved1b;
        public uint Reserved2;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct PERFORMANCE_INFORMATION
    {
        public uint cb;
        public UIntPtr CommitTotal, CommitLimit, CommitPeak, PhysicalTotal, PhysicalAvailable,
                       SystemCache, KernelTotal, KernelPaged, KernelNonpaged, PageSize;
        public uint HandleCount, ProcessCount, ThreadCount;
    }

    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern bool GlobalMemoryStatusEx(ref MEMORYSTATUSEX m);

    [DllImport("kernel32.dll")]
    public static extern bool GetSystemPowerStatus(out SYSTEM_POWER_STATUS s);

    [DllImport("ntdll.dll")]
    public static extern int NtQuerySystemInformation(int infoClass, IntPtr info, int length, out int returnLength);

    [DllImport("psapi.dll", SetLastError = true)]
    public static extern bool GetPerformanceInfo(out PERFORMANCE_INFORMATION pi, int size);

    public const int GWL_EXSTYLE = -20, WS_EX_TOOLWINDOW = 0x80, WS_EX_APPWINDOW = 0x40000;

    [DllImport("user32.dll", EntryPoint = "GetWindowLongPtrW")]
    public static extern IntPtr GetWindowLongPtr(IntPtr hWnd, int index);

    [DllImport("user32.dll", EntryPoint = "SetWindowLongPtrW")]
    public static extern IntPtr SetWindowLongPtr(IntPtr hWnd, int index, IntPtr value);
}

static class Probes
{
    /// <summary>Cumulative (idle, kernel incl. idle, user) 100ns ticks per logical CPU.</summary>
    public static (long Idle, long Kernel, long User)[] CpuTimes()
    {
        int n = Environment.ProcessorCount, size = Marshal.SizeOf<Native.SPPI>();
        IntPtr buf = Marshal.AllocHGlobal(size * n);
        try
        {
            if (Native.NtQuerySystemInformation(8, buf, size * n, out int ret) != 0) return Array.Empty<(long, long, long)>();
            var r = new (long, long, long)[ret / size];
            for (int i = 0; i < r.Length; i++)
            {
                var p = Marshal.PtrToStructure<Native.SPPI>(buf + i * size);
                r[i] = (p.IdleTime, p.KernelTime, p.UserTime);
            }
            return r;
        }
        finally { Marshal.FreeHGlobal(buf); }
    }

    public static (double Used, double Total)? Memory()
    {
        var m = new Native.MEMORYSTATUSEX { dwLength = (uint)Marshal.SizeOf<Native.MEMORYSTATUSEX>() };
        if (!Native.GlobalMemoryStatusEx(ref m)) return null;
        return (m.ullTotalPhys - m.ullAvailPhys, m.ullTotalPhys);
    }

    public static (double Used, double Total, string Name)? Disk()
    {
        try
        {
            var root = System.IO.Path.GetPathRoot(Environment.SystemDirectory) ?? "C:\\";
            var d = new System.IO.DriveInfo(root);
            return (d.TotalSize - d.AvailableFreeSpace, d.TotalSize, root.TrimEnd('\\'));
        }
        catch { return null; }
    }

    /// <summary>Total bytes received / sent on physical, up interfaces.</summary>
    public static (long In, long Out) NetBytes()
    {
        long i = 0, o = 0;
        try
        {
            foreach (var ni in NetworkInterface.GetAllNetworkInterfaces())
            {
                if (ni.OperationalStatus != OperationalStatus.Up) continue;
                if (ni.NetworkInterfaceType is NetworkInterfaceType.Loopback or NetworkInterfaceType.Tunnel) continue;
                if (ni.Description.Contains("Virtual", StringComparison.OrdinalIgnoreCase) ||
                    ni.Description.Contains("Hyper-V", StringComparison.OrdinalIgnoreCase)) continue;
                var s = ni.GetIPStatistics();
                i += s.BytesReceived; o += s.BytesSent;
            }
        }
        catch { }
        return (i, o);
    }

    public static (double CommitUsed, double CommitLimit, int Procs, int Threads)? PerfInfo()
    {
        if (!Native.GetPerformanceInfo(out var p, Marshal.SizeOf<Native.PERFORMANCE_INFORMATION>())) return null;
        double page = (double)p.PageSize.ToUInt64();
        return (p.CommitTotal.ToUInt64() * page, p.CommitLimit.ToUInt64() * page, (int)p.ProcessCount, (int)p.ThreadCount);
    }

    public static (int Pct, bool Charging, bool Ac)? Battery()
    {
        if (!Native.GetSystemPowerStatus(out var s)) return null;
        if ((s.BatteryFlag & 128) != 0 || s.BatteryFlag == 255 || s.BatteryLifePercent > 100) return null;   // no battery / unknown
        return (s.BatteryLifePercent, (s.BatteryFlag & 8) != 0, s.ACLineStatus == 1);
    }
}

/// <summary>
/// Temperature via ACPI thermal zones. Works without admin on most machines;
/// Windows exposes no public per-core CPU sensor API, so this is the board's thermal zone reading.
/// </summary>
sealed class Thermals
{
    bool perfFailed, wmiFailed;

    public (double Value, double Max)? Read()
    {
        var vals = new List<double>();
        if (!perfFailed)
        {
            try
            {
                using var q = new ManagementObjectSearcher(@"root\cimv2",
                    "SELECT HighPrecisionTemperature, Temperature FROM Win32_PerfFormattedData_Counters_ThermalZoneInformation");
                foreach (ManagementObject o in q.Get())
                    using (o)
                    {
                        double k = o["HighPrecisionTemperature"] is object hp && Convert.ToDouble(hp) > 0
                            ? Convert.ToDouble(hp) / 10 : Convert.ToDouble(o["Temperature"]);
                        vals.Add(k - 273.15);
                    }
            }
            catch { perfFailed = true; }
        }
        if (vals.Count == 0 && !wmiFailed)
        {
            try   // needs admin on most systems
            {
                using var q = new ManagementObjectSearcher(@"root\WMI", "SELECT CurrentTemperature FROM MSAcpi_ThermalZoneTemperature");
                foreach (ManagementObject o in q.Get())
                    using (o) vals.Add(Convert.ToDouble(o["CurrentTemperature"]) / 10 - 273.15);
            }
            catch { wmiFailed = true; }
        }
        vals.RemoveAll(v => v < 5 || v > 130);
        if (vals.Count == 0) return null;
        return (vals.Max(), vals.Max());
    }
}

/// <summary>3D engine utilisation from the "GPU Engine" performance counters (what Task Manager shows).</summary>
sealed class GpuProbe
{
    readonly List<PerformanceCounter> counters = new();
    DateTime refreshed = DateTime.MinValue;
    bool unavailable;

    public double? Read()
    {
        if (unavailable) return null;
        try
        {
            if ((DateTime.UtcNow - refreshed).TotalSeconds > 15)      // processes come and go; re-enumerate engines
            {
                foreach (var c in counters) c.Dispose();
                counters.Clear();
                var cat = new PerformanceCounterCategory("GPU Engine");
                foreach (var inst in cat.GetInstanceNames().Where(i => i.EndsWith("engtype_3D", StringComparison.Ordinal)))
                {
                    var pc = new PerformanceCounter("GPU Engine", "Utilization Percentage", inst, true);
                    pc.NextValue();
                    counters.Add(pc);
                }
                refreshed = DateTime.UtcNow;
            }
            double sum = 0;
            foreach (var pc in counters)
            {
                try { sum += pc.NextValue(); } catch { }
            }
            return Math.Clamp(sum / 100, 0, 1);
        }
        catch { unavailable = true; return null; }
    }
}
