using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Controls.Primitives;
using System.Windows.Input;
using System.Windows.Interop;
using System.Windows.Media;
using System.Windows.Media.Animation;
using System.Windows.Media.Imaging;
using System.Windows.Threading;

namespace PulseApp;

/// <summary>Borderless, draggable desktop widget.</summary>
sealed class WidgetWindow : Window
{
    /// <summary>Snap points for scaling; whole steps keep the pixel font crisp.</summary>
    static readonly double[] Scales = { 1, 1.25, 1.5, 1.75, 2 };
    static readonly double[] Opacities = { 1, 0.85, 0.7, 0.5 };
    static readonly Duration MorphTime = TimeSpan.FromMilliseconds(280);
    const double Grip = 14, SnapMargin = 12, SnapReach = 28;
    const int HotkeyId = 1;

    readonly Settings settings = Settings.Load();
    readonly Sampler sampler;
    readonly PulseView view;
    readonly Grid root = new(), panel = new();                  // panel = view + loops, the part that morphs
    readonly Image ghost = new() { IsHitTestVisible = false, Stretch = Stretch.Fill, VerticalAlignment = VerticalAlignment.Top };
    readonly ScaleTransform zoom = new();
    readonly bool motion = SystemParameters.ClientAreaAnimation;
    readonly Tray tray;
    readonly Alerts alerts;
    readonly ToolTip tip = new()
    {
        Placement = PlacementMode.Mouse, HasDropShadow = false, Background = Ink.Bg, Foreground = Ink.On,
        BorderBrush = Ink.Alpha(Ink.On, 0.22), BorderThickness = new Thickness(1), Padding = new Thickness(8, 5, 8, 5),
        FontFamily = new FontFamily("Cascadia Mono, Consolas"), FontSize = 11.5,
    };
    readonly DispatcherTimer tipDelay = new() { Interval = TimeSpan.FromMilliseconds(350) };
    string? tipText;
    bool morphing, resizing, resizeFromLeft, clickThrough;
    double resizeX, resizeScale, resizeWidth;

    public WidgetWindow()
    {
        Title = "Pulse";
        WindowStyle = WindowStyle.None;
        AllowsTransparency = true;
        Background = Brushes.Transparent;
        ResizeMode = ResizeMode.NoResize;
        ShowInTaskbar = false;
        SizeToContent = SizeToContent.WidthAndHeight;
        Topmost = settings.OnTop;
        UseLayoutRounding = true;

        sampler = new Sampler { LimitsEnabled = settings.Limits };
        view = new PulseView(sampler) { Size = settings.WidgetSize, ClaudeOpen = settings.ClaudeOpen };
        var loops = new Loops(view);
        zoom.ScaleX = zoom.ScaleY = Math.Clamp(settings.Scale, Scales[0], Scales[^1]);
        panel.LayoutTransform = zoom;
        panel.VerticalAlignment = VerticalAlignment.Top;
        panel.HorizontalAlignment = HorizontalAlignment.Left;
        panel.Children.Add(view);
        panel.Children.Add(loops.Canvas);
        root.Children.Add(panel);
        root.Children.Add(ghost);
        Content = root;
        Opacity = 0;

        tray = new Tray(ToggleShown, OpenGallery, () => SetClickThrough(!clickThrough), () => SetAlerts(!settings.Alerts), Close);
        alerts = new Alerts(tray.Notify) { Enabled = settings.Alerts };
        sampler.Updated += () => { view.InvalidateMeasure(); view.InvalidateVisual(); alerts.Check(sampler); };

        ContextMenu = BuildMenu();
        MouseLeftButtonDown += OnMouseDown;
        MouseMove += OnMouseMove;
        MouseLeave += (_, _) => ShowTip(null);
        MouseLeftButtonUp += (_, _) => EndResize();
        LostMouseCapture += (_, _) => EndResize();
        MouseWheel += OnWheel;
        tipDelay.Tick += (_, _) => { tipDelay.Stop(); OpenTip(); };
        SourceInitialized += (_, _) => { HideFromAltTab(); RegisterHotkey(); };
        Loaded += (_, _) => { Place(); FadeTo(settings.Opacity, 350); SyncTray(); };
        Closing += (_, _) => { SavePosition(); tray.Dispose(); };
        SizeChanged += (_, e) =>
        {
            // right-hand widgets grow and shrink leftward, so the edge you placed stays put
            if (!IsLoaded || e.PreviousSize.Width == 0) return;
            var wa = WorkArea();
            if (Left + e.PreviousSize.Width / 2 > wa.Left + wa.Width / 2) Left += e.PreviousSize.Width - e.NewSize.Width;
        };
        Microsoft.Win32.SystemEvents.DisplaySettingsChanged += (_, _) => Dispatcher.BeginInvoke(() => Place(), DispatcherPriority.Background);
    }

    // ---------- monitors and positions ----------

    /// <summary>The work area of the monitor the widget is on, in WPF units.</summary>
    public Rect WorkArea()
    {
        var hwnd = new WindowInteropHelper(this).Handle;
        if (hwnd == IntPtr.Zero) return SystemParameters.WorkArea;
        var wa = System.Windows.Forms.Screen.FromHandle(hwnd).WorkingArea;
        var dpi = VisualTreeHelper.GetDpi(this);
        return new Rect(wa.Left / dpi.DpiScaleX, wa.Top / dpi.DpiScaleY, wa.Width / dpi.DpiScaleX, wa.Height / dpi.DpiScaleY);
    }

    bool RightAnchored
    {
        get { var wa = WorkArea(); return Left + ActualWidth / 2 > wa.Left + wa.Width / 2; }
    }

    /// <summary>Positions are remembered per view and per monitor arrangement, so docking or undocking a laptop puts each view back where it lived.</summary>
    static string Layout() =>
        string.Join(";", System.Windows.Forms.Screen.AllScreens.OrderBy(s => s.Bounds.Left).ThenBy(s => s.Bounds.Top)
                                                   .Select(s => $"{s.Bounds.Left},{s.Bounds.Top},{s.Bounds.Width}x{s.Bounds.Height}"));

    static string Key(WidgetSize size) => $"{Layout()}|{size}";

    Point? Saved(WidgetSize size)
    {
        if (!settings.Positions.TryGetValue(Key(size), out var p) || p.Length < 2) return null;
        var vs = new Rect(SystemParameters.VirtualScreenLeft, SystemParameters.VirtualScreenTop,
                          SystemParameters.VirtualScreenWidth, SystemParameters.VirtualScreenHeight);
        return vs.Contains(new Point(p[0] + 40, p[1] + 20)) ? new Point(p[0], p[1]) : null;
    }

    void Place()
    {
        if (Saved(view.Size) is { } p) { Left = p.X; Top = p.Y; return; }
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
        if (!IsLoaded) return;
        settings.Left = Left; settings.Top = Top;
        settings.Positions[Key(view.Size)] = new[] { Left, Top };
        settings.Save();
    }

    /// <summary>After a drag, a widget dropped near an edge or corner of its monitor glides onto it.</summary>
    void Snap()
    {
        var wa = WorkArea();
        double l = Left, t = Top, w = ActualWidth, h = ActualHeight;
        if (Math.Abs(l - (wa.Left + SnapMargin)) < SnapReach) l = wa.Left + SnapMargin;
        else if (Math.Abs(wa.Right - SnapMargin - (l + w)) < SnapReach) l = wa.Right - SnapMargin - w;
        else if (Math.Abs(l + w / 2 - (wa.Left + wa.Width / 2)) < SnapReach / 2) l = wa.Left + (wa.Width - w) / 2;
        if (Math.Abs(t - (wa.Top + SnapMargin)) < SnapReach) t = wa.Top + SnapMargin;
        else if (Math.Abs(wa.Bottom - SnapMargin - (t + h)) < SnapReach) t = wa.Bottom - SnapMargin - h;
        if (l == Left && t == Top) { SavePosition(); return; }
        Glide(l, t, SavePosition);
    }

    void Glide(double l, double t, Action? done = null)
    {
        if (!motion) { Left = l; Top = t; done?.Invoke(); return; }
        var ease = new QuarticEase { EasingMode = EasingMode.EaseOut };
        var dur = TimeSpan.FromMilliseconds(220);
        var ax = new DoubleAnimation(Left, l, dur) { EasingFunction = ease, FillBehavior = FillBehavior.Stop };
        var ay = new DoubleAnimation(Top, t, dur) { EasingFunction = ease, FillBehavior = FillBehavior.Stop };
        ay.Completed += (_, _) => { Left = l; Top = t; done?.Invoke(); };
        BeginAnimation(LeftProperty, ax);
        BeginAnimation(TopProperty, ay);
    }

    // ---------- fading, morphing ----------

    void FadeTo(double to, double ms, Action? done = null)
    {
        if (!motion) { BeginAnimation(OpacityProperty, null); Opacity = to; done?.Invoke(); return; }
        var a = new DoubleAnimation(to, TimeSpan.FromMilliseconds(ms)) { EasingFunction = new QuadraticEase { EasingMode = EasingMode.EaseOut } };
        if (done != null) a.Completed += (_, _) => done();
        BeginAnimation(OpacityProperty, a);
    }

    /// <summary>
    /// Applies a change that alters the widget's size and morphs the outline from the old shape to the new one:
    /// the window briefly holds the larger of the two, a rounded clip eases between them and the old frame fades out.
    /// </summary>
    void Morph(Action change, bool crossfade = true)
    {
        EndMorph();
        ShowTip(null);
        if (!IsLoaded || !motion)
        {
            change();
            view.InvalidateMeasure();
            Dispatcher.BeginInvoke(SavePosition, DispatcherPriority.Background);
            return;
        }

        double oldW = panel.ActualWidth, oldH = panel.ActualHeight, oldScale = zoom.ScaleX, oldR = view.Radius * oldScale;
        if (crossfade && oldW > 0 && oldH > 0)
        {
            var dpi = VisualTreeHelper.GetDpi(root);
            var bmp = new RenderTargetBitmap((int)Math.Ceiling(oldW * dpi.DpiScaleX), (int)Math.Ceiling(oldH * dpi.DpiScaleY),
                                             dpi.PixelsPerInchX, dpi.PixelsPerInchY, PixelFormats.Pbgra32);
            bmp.Render(root);
            ghost.Source = bmp; ghost.Width = oldW; ghost.Height = oldH;
        }
        bool right = RightAnchored;
        panel.HorizontalAlignment = ghost.HorizontalAlignment = right ? HorizontalAlignment.Right : HorizontalAlignment.Left;

        change();
        view.InvalidateMeasure();
        panel.Measure(new Size(double.PositiveInfinity, double.PositiveInfinity));
        double newW = panel.DesiredSize.Width, newH = panel.DesiredSize.Height, newR = view.Radius * zoom.ScaleX;
        double w = Math.Max(oldW, newW), h = Math.Max(oldH, newH);

        morphing = true;
        SizeToContent = SizeToContent.Manual;
        Width = w; Height = h;                                  // SizeChanged keeps a right-hand widget's right edge put

        double X(double cw) => right ? w - cw : 0;
        var ease = new QuarticEase { EasingMode = EasingMode.EaseOut };
        var clip = new RectangleGeometry(new Rect(X(oldW), 0, oldW, oldH), oldR, oldR);
        root.Clip = clip;
        var shape = new RectAnimation(new Rect(X(newW), 0, newW, newH), MorphTime) { EasingFunction = ease };
        shape.Completed += (_, _) => { if (root.Clip == clip) EndMorph(); };
        clip.BeginAnimation(RectangleGeometry.RectProperty, shape);
        clip.BeginAnimation(RectangleGeometry.RadiusXProperty, new DoubleAnimation(newR, MorphTime) { EasingFunction = ease });
        clip.BeginAnimation(RectangleGeometry.RadiusYProperty, new DoubleAnimation(newR, MorphTime) { EasingFunction = ease });

        if (ghost.Source != null)
            ghost.BeginAnimation(OpacityProperty, new DoubleAnimation(1, 0, TimeSpan.FromMilliseconds(200)) { EasingFunction = new QuadraticEase { EasingMode = EasingMode.EaseOut } });
        if (oldScale != zoom.ScaleX)                             // content starts at its old size and grows into the new one
        {
            var grow = new ScaleTransform(oldScale / zoom.ScaleX, oldScale / zoom.ScaleX);
            panel.RenderTransformOrigin = new Point(right ? 1 : 0, 0);
            panel.RenderTransform = grow;
            var a = new DoubleAnimation(1, MorphTime) { EasingFunction = ease };
            grow.BeginAnimation(ScaleTransform.ScaleXProperty, a);
            grow.BeginAnimation(ScaleTransform.ScaleYProperty, a);
        }
    }

    void EndMorph()
    {
        if (!morphing) return;
        morphing = false;
        root.Clip = null;
        ghost.BeginAnimation(OpacityProperty, null);
        ghost.Source = null;
        panel.RenderTransform = Transform.Identity;
        panel.HorizontalAlignment = ghost.HorizontalAlignment = HorizontalAlignment.Left;
        SizeToContent = SizeToContent.WidthAndHeight;
        Dispatcher.BeginInvoke(SavePosition, DispatcherPriority.Background);
    }

    /// <summary>Switching to a view that lives somewhere else: fade out here, reappear there.</summary>
    void Hop(Action change, Point to)
    {
        EndMorph();
        ShowTip(null);
        FadeTo(0, 130, () =>
        {
            change();
            view.InvalidateMeasure();
            UpdateLayout();
            Left = to.X; Top = to.Y;
            if (motion)
            {
                var pop = new ScaleTransform(0.97, 0.97);
                panel.RenderTransformOrigin = new Point(0.5, 0);
                panel.RenderTransform = pop;
                var a = new DoubleAnimation(1, TimeSpan.FromMilliseconds(240)) { EasingFunction = new QuarticEase { EasingMode = EasingMode.EaseOut } };
                a.Completed += (_, _) => panel.RenderTransform = Transform.Identity;
                pop.BeginAnimation(ScaleTransform.ScaleXProperty, a);
                pop.BeginAnimation(ScaleTransform.ScaleYProperty, a);
            }
            FadeTo(settings.Opacity, 220);
        });
    }

    // ---------- views ----------

    readonly Dictionary<WidgetSize, MenuItem> sizeItems = new();

    void SetSize(WidgetSize size)
    {
        if (size == view.Size) return;
        SavePosition();                                        // the view we're leaving keeps its spot
        void Apply()
        {
            if (size != WidgetSize.Full) sampler.TopMode = null;
            view.Size = size;
        }
        // a right-hand widget morphing in place keeps its right edge, so that's where "here" will be
        double here = RightAnchored ? Left + ActualWidth - PulseView.WidthOf(size) * zoom.ScaleX : Left;
        if (Saved(size) is { } p && (Math.Abs(p.X - here) > 4 || Math.Abs(p.Y - Top) > 4)) Hop(Apply, p);
        else Morph(Apply);
        settings.WidgetSize = size;
        settings.Save();
        foreach (var (s, item) in sizeItems) item.IsChecked = s == size;
    }

    Gallery? gallery;

    void OpenGallery()
    {
        if (!IsVisible) ToggleShown();
        if (gallery != null) { gallery.Activate(); return; }
        gallery = new Gallery(sampler, view.Size, SetSize) { Owner = this };
        gallery.Closed += (_, _) => gallery = null;
        gallery.Show();
    }

    // ---------- scale ----------

    readonly Dictionary<double, MenuItem> scaleItems = new();

    void SetScale(double scale, bool save = true)
    {
        zoom.ScaleX = zoom.ScaleY = scale;
        if (!save) return;
        settings.Scale = scale;
        settings.Save();
        foreach (var (s, item) in scaleItems) item.IsChecked = s == scale;
    }

    static double Nearest(double scale)
    {
        double best = Scales[0];
        foreach (var s in Scales) if (Math.Abs(s - scale) < Math.Abs(best - scale)) best = s;
        return best;
    }

    void ScaleTo(double scale)
    {
        if (scale != zoom.ScaleX || scale != settings.Scale) Morph(() => SetScale(scale), crossfade: false);
    }

    /// <summary>Ctrl + wheel steps through the scales.</summary>
    void OnWheel(object sender, MouseWheelEventArgs e)
    {
        if ((Keyboard.Modifiers & ModifierKeys.Control) == 0 || resizing) return;
        int i = Array.IndexOf(Scales, Nearest(zoom.ScaleX)) + Math.Sign(e.Delta);
        ScaleTo(Scales[Math.Clamp(i, 0, Scales.Length - 1)]);
        e.Handled = true;
    }

    // ---------- mouse ----------

    /// <summary>The bottom corner away from the anchored edge is a resize grip.</summary>
    bool InGrip(Point p) => p.Y >= ActualHeight - Grip && (RightAnchored ? p.X <= Grip : p.X >= ActualWidth - Grip);

    void OnMouseMove(object sender, MouseEventArgs e)
    {
        var p = e.GetPosition(this);
        if (!resizing)
        {
            bool grip = !morphing && InGrip(p);
            Cursor = grip ? (RightAnchored ? Cursors.SizeNESW : Cursors.SizeNWSE) : null;
            ShowTip(grip || morphing || e.LeftButton == MouseButtonState.Pressed ? null : view.TipAt(e.GetPosition(view)));
            return;
        }
        double dx = (PointToScreen(p).X - resizeX) / VisualTreeHelper.GetDpi(this).DpiScaleX;
        if (resizeFromLeft) dx = -dx;
        SetScale(Math.Clamp(resizeScale * (resizeWidth + dx) / resizeWidth, Scales[0] * 0.9, Scales[^1] * 1.05), save: false);
    }

    void EndResize()
    {
        if (!resizing) return;
        resizing = false;
        ReleaseMouseCapture();
        Cursor = null;
        ScaleTo(Nearest(zoom.ScaleX));                         // ease onto the closest snap point
    }

    void OnMouseDown(object sender, MouseButtonEventArgs e)
    {
        ShowTip(null);
        var at = e.GetPosition(this);
        if (!morphing && InGrip(at))
        {
            resizing = true;
            resizeFromLeft = RightAnchored;
            resizeX = PointToScreen(at).X;
            resizeScale = zoom.ScaleX;
            resizeWidth = ActualWidth;
            CaptureMouse();
            e.Handled = true;
            return;
        }
        var pv = e.GetPosition(view);
        bool inHeader = pv.Y < view.HeaderBottom;
        var row = view.RowAt(pv.Y);
        bool claude = view.ClaudeAt(pv);
        double l = Left, t = Top;
        try { DragMove(); } catch (InvalidOperationException) { }
        if (Math.Abs(Left - l) > 2 || Math.Abs(Top - t) > 2) Snap();
        else if (inHeader) SetSize(view.Size.Next());   // a click (not a drag) on the header changes view
        else if (row is { } r) Morph(() => sampler.TopMode = sampler.TopMode == r ? null : r);   // on CPU or MEM: top processes
        else if (claude) Morph(() => { view.ClaudeOpen = !view.ClaudeOpen; settings.ClaudeOpen = view.ClaudeOpen; settings.Save(); });
    }

    // ---------- tooltip ----------

    void ShowTip(string? text)
    {
        if (text == tipText) return;
        tipText = text;
        tip.IsOpen = false;
        tipDelay.Stop();
        if (text != null) tipDelay.Start();
    }

    void OpenTip()
    {
        if (tipText == null || !IsMouseOver) return;
        tip.Content = tipText;
        tip.PlacementTarget = this;
        tip.IsOpen = true;
    }

    // ---------- click-through, opacity, alerts, tray ----------

    void SetClickThrough(bool on)
    {
        clickThrough = on;
        var hwnd = new WindowInteropHelper(this).Handle;
        long ex = Native.GetWindowLongPtr(hwnd, Native.GWL_EXSTYLE).ToInt64();
        ex = on ? ex | WS_EX_TRANSPARENT : ex & ~WS_EX_TRANSPARENT;
        Native.SetWindowLongPtr(hwnd, Native.GWL_EXSTYLE, new IntPtr(ex));
        if (on) { ShowTip(null); tray.Notify("Click-through on", "Clicks now pass through Pulse. Press Ctrl+Alt+P or use the tray icon to turn it off."); }
        if (throughItem != null) throughItem.IsChecked = on;
        SyncTray();
    }

    void SetOpacity(double o)
    {
        settings.Opacity = o;
        settings.Save();
        FadeTo(o, 200);
        foreach (var (v, item) in opacityItems) item.IsChecked = v == o;
    }

    void SetAlerts(bool on)
    {
        settings.Alerts = alerts.Enabled = on;
        settings.Save();
        if (alertsItem != null) alertsItem.IsChecked = on;
        SyncTray();
    }

    void ToggleShown()
    {
        if (IsVisible) FadeTo(0, 150, Hide);
        else { Show(); FadeTo(settings.Opacity, 250); }
        Dispatcher.BeginInvoke(SyncTray, DispatcherPriority.Background);
    }

    void SyncTray() => tray.Sync(IsVisible, clickThrough, settings.Alerts);

    const long WS_EX_TRANSPARENT = 0x20;

    [DllImport("user32.dll")] static extern bool RegisterHotKey(IntPtr hWnd, int id, uint modifiers, uint vk);

    /// <summary>Ctrl+Alt+P toggles click-through — the way back when the widget ignores the mouse.</summary>
    void RegisterHotkey()
    {
        var src = HwndSource.FromHwnd(new WindowInteropHelper(this).Handle);
        src?.AddHook((IntPtr h, int msg, IntPtr w, IntPtr l, ref bool handled) =>
        {
            if (msg == 0x0312 && w.ToInt32() == HotkeyId) { SetClickThrough(!clickThrough); handled = true; }
            return IntPtr.Zero;
        });
        RegisterHotKey(new WindowInteropHelper(this).Handle, HotkeyId, 0x0001 | 0x0002 | 0x4000, 0x50);   // Alt | Ctrl | NoRepeat, 'P'
    }

    // ---------- menu ----------

    readonly Dictionary<double, MenuItem> opacityItems = new();
    MenuItem? throughItem, alertsItem;

    ContextMenu BuildMenu()
    {
        var menu = new ContextMenu();
        menu.Opened += (_, _) => ShowTip(null);

        var viewMenu = new MenuItem { Header = "View" };
        foreach (var s in Enum.GetValues<WidgetSize>())
        {
            var item = new MenuItem { Header = s.Title(), IsCheckable = true, IsChecked = s == settings.WidgetSize };
            item.Click += (_, _) => SetSize(s);
            sizeItems[s] = item;
            viewMenu.Items.Add(item);
        }
        viewMenu.Items.Add(new Separator());
        var choose = new MenuItem { Header = "Choose View…" };
        choose.Click += (_, _) => OpenGallery();
        viewMenu.Items.Add(choose);

        var scaleMenu = new MenuItem { Header = "Scale" };
        foreach (var s in Scales)
        {
            var item = new MenuItem { Header = $"{s * 100:0}%", IsCheckable = true, IsChecked = s == zoom.ScaleX };
            item.Click += (_, _) => ScaleTo(s);
            scaleItems[s] = item;
            scaleMenu.Items.Add(item);
        }

        var opacityMenu = new MenuItem { Header = "Opacity" };
        foreach (var o in Opacities)
        {
            var item = new MenuItem { Header = $"{o * 100:0}%", IsCheckable = true, IsChecked = Math.Abs(o - settings.Opacity) < 0.01 };
            item.Click += (_, _) => SetOpacity(o);
            opacityItems[o] = item;
            opacityMenu.Items.Add(item);
        }

        var onTop = new MenuItem { Header = "Always on Top", IsCheckable = true, IsChecked = settings.OnTop };
        onTop.Click += (_, _) => { Topmost = settings.OnTop = onTop.IsChecked; settings.Save(); };
        throughItem = new MenuItem { Header = "Click-through", InputGestureText = "Ctrl+Alt+P", IsCheckable = true };
        throughItem.Click += (_, _) => SetClickThrough(throughItem.IsChecked);
        alertsItem = new MenuItem { Header = "Alerts", IsCheckable = true, IsChecked = settings.Alerts };
        alertsItem.Click += (_, _) => SetAlerts(alertsItem.IsChecked);
        var limits = new MenuItem { Header = "Plan Limits (online)", IsCheckable = true, IsChecked = settings.Limits };
        limits.Click += (_, _) => { settings.Limits = sampler.LimitsEnabled = limits.IsChecked; settings.Save(); };
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
        var hide = new MenuItem { Header = "Hide to Tray" };
        hide.Click += (_, _) => ToggleShown();
        var quit = new MenuItem { Header = "Quit Pulse" };
        quit.Click += (_, _) => Close();

        menu.Items.Add(viewMenu);
        menu.Items.Add(scaleMenu);
        menu.Items.Add(opacityMenu);
        menu.Items.Add(new Separator());
        menu.Items.Add(onTop);
        menu.Items.Add(throughItem);
        menu.Items.Add(alertsItem);
        menu.Items.Add(limits);
        menu.Items.Add(login);
        menu.Items.Add(new Separator());
        menu.Items.Add(taskmgr);
        menu.Items.Add(hide);
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
