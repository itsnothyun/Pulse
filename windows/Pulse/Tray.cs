using System;
using Forms = System.Windows.Forms;

namespace PulseApp;

/// <summary>
/// Tray icon: brings the widget back when it's hidden or click-through, and carries the alerts
/// (Windows shows its balloons as ordinary notifications).
/// </summary>
sealed class Tray : IDisposable
{
    readonly Forms.NotifyIcon icon = new() { Text = "Pulse", Visible = true };
    readonly Forms.ToolStripMenuItem shown = new("Show Pulse") { CheckOnClick = false };
    readonly Forms.ToolStripMenuItem through = new("Click-through   Ctrl+Alt+P");
    readonly Forms.ToolStripMenuItem alerts = new("Alerts");

    public Tray(Action toggleShown, Action views, Action toggleThrough, Action toggleAlerts, Action quit)
    {
        try { icon.Icon = System.Drawing.Icon.ExtractAssociatedIcon(Environment.ProcessPath!); } catch { icon.Icon = System.Drawing.SystemIcons.Application; }
        shown.Click += (_, _) => toggleShown();
        through.Click += (_, _) => toggleThrough();
        alerts.Click += (_, _) => toggleAlerts();
        var menu = new Forms.ContextMenuStrip();
        menu.Items.Add(shown);
        menu.Items.Add(new Forms.ToolStripMenuItem("Choose View…", null, (_, _) => views()));
        menu.Items.Add(through);
        menu.Items.Add(alerts);
        menu.Items.Add(new Forms.ToolStripSeparator());
        menu.Items.Add(new Forms.ToolStripMenuItem("Quit Pulse", null, (_, _) => quit()));
        icon.ContextMenuStrip = menu;
        icon.MouseClick += (_, e) => { if (e.Button == Forms.MouseButtons.Left) toggleShown(); };
    }

    public void Sync(bool isShown, bool clickThrough, bool alertsOn)
    {
        shown.Checked = isShown;
        through.Checked = clickThrough;
        alerts.Checked = alertsOn;
        icon.Text = clickThrough ? "Pulse · click-through (Ctrl+Alt+P)" : "Pulse";
    }

    public void Notify(string title, string text) => icon.ShowBalloonTip(6000, title, text, Forms.ToolTipIcon.None);

    public void Dispose()
    {
        icon.Visible = false;
        icon.Dispose();
    }
}
