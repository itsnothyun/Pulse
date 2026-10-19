using System;
using System.IO;
using System.Text.Json;
using Microsoft.Win32;

namespace PulseApp;

sealed class Settings
{
    public double? Left { get; set; }
    public double? Top { get; set; }
    public string Size { get; set; } = "";
    public bool Compact { get; set; }          // pre-1.1 setting, read once for migration

    public WidgetSize WidgetSize
    {
        get => Enum.TryParse<WidgetSize>(Size, true, out var s) ? s : Compact ? WidgetSize.Compact : WidgetSize.Full;
        set { Size = value.ToString(); Compact = false; }
    }
    public bool OnTop { get; set; } = true;

    static string FilePath => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "Pulse", "settings.json");

    public static Settings Load()
    {
        try { return JsonSerializer.Deserialize<Settings>(File.ReadAllText(FilePath)) ?? new Settings(); }
        catch { return new Settings(); }
    }

    public void Save()
    {
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(FilePath)!);
            File.WriteAllText(FilePath, JsonSerializer.Serialize(this));
        }
        catch { }
    }

    const string RunKey = @"Software\Microsoft\Windows\CurrentVersion\Run";

    public static bool LaunchAtLogin
    {
        get
        {
            using var k = Registry.CurrentUser.OpenSubKey(RunKey);
            return k?.GetValue("Pulse") is string;
        }
        set
        {
            using var k = Registry.CurrentUser.CreateSubKey(RunKey);
            if (value && Environment.ProcessPath is { } exe) k.SetValue("Pulse", $"\"{exe}\"");
            else k.DeleteValue("Pulse", false);
        }
    }
}
