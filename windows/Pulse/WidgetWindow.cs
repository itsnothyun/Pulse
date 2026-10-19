using System;
using System.Diagnostics;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Interop;

namespace PulseApp;

/// <summary>Borderless, draggable desktop widget.</summary>
sealed class WidgetWindow : Window
{
    readonly Settings settings = Settings.Load();
    readonly Sampler sampler;
    readonly PulseView view;

    public WidgetWindow()
    {
        Title = "Pulse";
        WindowStyle = WindowStyle.None;
        AllowsTransparency = true;
        Background = System.Windows.Media.Brushes.Transparent;
        ResizeMode = ResizeMode.NoResize;
        ShowInTaskbar = false;
        SizeToContent = SizeToContent.WidthAndHeight;
        Topmost = settings.OnTop;
        UseLayoutRounding = true;

        sampler = new Sampler();
        view = new PulseView(sampler) { Size = settings.WidgetSize };
        var loops = new Loops(view);
        var root = new Grid();
        root.Children.Add(view);
        root.Children.Add(loops.Canvas);
        Content = root;
        Opacity = 0;

        sampler.Updated += () => { view.InvalidateMeasure(); view.InvalidateVisual(); };
        ContextMenu = BuildMenu();
        MouseLeftButtonDown += OnMouseDown;
        SourceInitialized += (_, _) => HideFromAltTab();
        Loaded += (_, _) =>
        {
            Place();
            BeginAnimation(OpacityProperty, new System.Windows.Media.Animation.DoubleAnimation(0, 1, TimeSpan.FromMilliseconds(350)));
        };
        Closing += (_, _) => SavePosition();
        SizeChanged += (_, e) =>
        {
            // right-hand widgets grow and shrink leftward, so the edge you placed stays put
            if (!IsLoaded || e.PreviousSize.Width == 0) return;
            var wa = SystemParameters.WorkArea;
            if (Left + e.PreviousSize.Width / 2 > wa.Left + wa.Width / 2) Left += e.PreviousSize.Width - e.NewSize.Width;
        };
    }

    void Place()
    {
        var vs = new Rect(SystemParameters.VirtualScreenLeft, SystemParameters.VirtualScreenTop,
                          SystemParameters.VirtualScreenWidth, SystemParameters.VirtualScreenHeight);
        if (settings.Left is { } l && settings.Top is { } t && vs.Contains(new Point(l + 40, t + 20)))
        {
            Left = l; Top = t;
        }
        else
        {
            var wa = SystemParameters.WorkArea;
            Left = wa.Right - ActualWidth - 24;
            Top = wa.Top + 24;
        }
    }

    void SavePosition()
    {
        settings.Left = Left; settings.Top = Top;
        settings.Save();
    }

    void OnMouseDown(object sender, MouseButtonEventArgs e)
    {
        var inHeader = e.GetPosition(view).Y < view.HeaderBottom;
        double l = Left, t = Top;
        try { DragMove(); } catch (InvalidOperationException) { }
        if (Math.Abs(Left - l) > 2 || Math.Abs(Top - t) > 2) SavePosition();
        else if (inHeader) SetSize(view.Size.Next());   // a click (not a drag) on the header changes size
    }

    readonly System.Collections.Generic.Dictionary<WidgetSize, MenuItem> sizeItems = new();

    void SetSize(WidgetSize size)
    {
        view.Size = size;
        settings.WidgetSize = size;
        settings.Save();
        foreach (var (s, item) in sizeItems) item.IsChecked = s == size;
    }

    ContextMenu BuildMenu()
    {
        var menu = new ContextMenu();
        var sizeMenu = new MenuItem { Header = "Size" };
        foreach (var s in new[] { WidgetSize.Full, WidgetSize.Compact, WidgetSize.Mini })
        {
            var item = new MenuItem { Header = s.ToString(), IsCheckable = true, IsChecked = s == settings.WidgetSize };
            item.Click += (_, _) => SetSize(s);
            sizeItems[s] = item;
            sizeMenu.Items.Add(item);
        }
        var onTop = new MenuItem { Header = "Always on Top", IsCheckable = true, IsChecked = settings.OnTop };
        onTop.Click += (_, _) => { Topmost = settings.OnTop = onTop.IsChecked; settings.Save(); };
        var login = new MenuItem { Header = "Launch at Login", IsCheckable = true, IsChecked = Settings.LaunchAtLogin };
        login.Click += (_, _) =>
        {
            try { Settings.LaunchAtLogin = login.IsChecked; } catch { login.IsChecked = Settings.LaunchAtLogin; }
        };
        var taskmgr = new MenuItem { Header = "Open Task Manager" };
        taskmgr.Click += (_, _) =>
        {
            try { Process.Start(new ProcessStartInfo("taskmgr.exe") { UseShellExecute = true }); } catch { }
        };
        var quit = new MenuItem { Header = "Quit Pulse" };
        quit.Click += (_, _) => Close();
        menu.Items.Add(sizeMenu);
        menu.Items.Add(onTop);
        menu.Items.Add(login);
        menu.Items.Add(new Separator());
        menu.Items.Add(taskmgr);
        menu.Items.Add(quit);
        return menu;
    }

    /// <summary>Tool-window style keeps the widget out of Alt+Tab and the taskbar.</summary>
    void HideFromAltTab()
    {
        var hwnd = new WindowInteropHelper(this).Handle;
        long ex = Native.GetWindowLongPtr(hwnd, Native.GWL_EXSTYLE).ToInt64();
        ex = (ex | Native.WS_EX_TOOLWINDOW) & ~(long)Native.WS_EX_APPWINDOW;
        Native.SetWindowLongPtr(hwnd, Native.GWL_EXSTYLE, new IntPtr(ex));
    }
}
