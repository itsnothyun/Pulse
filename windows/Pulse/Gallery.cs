using System;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Media.Animation;

namespace PulseApp;

/// <summary>A line of text in the pixel font, as an element.</summary>
sealed class PixelLabel : FrameworkElement
{
    readonly string text;
    readonly double scale;
    public Brush Brush { get; set; } = Ink.Dim;

    public PixelLabel(string text, double scale = 1) { this.text = text.ToUpperInvariant(); this.scale = scale; RenderOptions.SetEdgeMode(this, EdgeMode.Aliased); }
    protected override Size MeasureOverride(Size available) => new(PixelFont.Width(text, scale), 7 * scale);
    protected override void OnRender(DrawingContext dc) => PixelFont.Draw(dc, text, 0, 0, scale, Brush);
}

/// <summary>
/// Pick a view the way you'd pick a phone widget: every view, live and at its true relative size.
/// Click one to switch; Esc or a click elsewhere closes.
/// </summary>
sealed class Gallery : Window
{
    const double Preview = 0.5;
    readonly Sampler sampler;
    readonly Action<WidgetSize> pick;
    readonly PulseView[] previews;
    readonly Action refresh;
    bool closing;

    public Gallery(Sampler sampler, WidgetSize current, Action<WidgetSize> pick)
    {
        this.sampler = sampler;
        this.pick = pick;
        Title = "Pulse views";
        WindowStyle = WindowStyle.None;
        AllowsTransparency = true;
        Background = Brushes.Transparent;
        ResizeMode = ResizeMode.NoResize;
        ShowInTaskbar = false;
        Topmost = true;
        SizeToContent = SizeToContent.WidthAndHeight;
        WindowStartupLocation = WindowStartupLocation.Manual;
        UseLayoutRounding = true;

        FrameworkElement Tile(WidgetSize size)
        {
            var v = new PulseView(sampler) { Size = size, IsHitTestVisible = false, LayoutTransform = new ScaleTransform(Preview, Preview) };
            var card = new Border
            {
                Child = v, CornerRadius = new CornerRadius(14 * Preview + 4), Padding = new Thickness(4),
                BorderThickness = new Thickness(1.5), Background = Brushes.Transparent,
                BorderBrush = size == current ? Ink.Mid : Brushes.Transparent,
                RenderTransformOrigin = new Point(0.5, 0.5), RenderTransform = new ScaleTransform(1, 1),
            };
            var label = new PixelLabel(size.Title()) { Brush = size == current ? Ink.On : Ink.Dim, Margin = new Thickness(6, 8, 0, 0), HorizontalAlignment = HorizontalAlignment.Left };
            var tile = new StackPanel { Margin = new Thickness(8), Cursor = Cursors.Hand, Background = Brushes.Transparent, Children = { card, label } };
            tile.MouseEnter += (_, _) => { Lift(card, 1.025); if (size != current) card.BorderBrush = Ink.Line; };
            tile.MouseLeave += (_, _) => { Lift(card, 1); if (size != current) card.BorderBrush = Brushes.Transparent; };
            tile.MouseLeftButtonUp += (_, _) => Choose(size);
            return tile;
        }

        var order = new[] { WidgetSize.Full, WidgetSize.Claude, WidgetSize.Landscape, WidgetSize.Compact, WidgetSize.Mini };
        var tiles = new FrameworkElement[order.Length];
        for (int i = 0; i < order.Length; i++) tiles[i] = Tile(order[i]);
        previews = new PulseView[order.Length];
        for (int i = 0; i < order.Length; i++) previews[i] = (PulseView)((Border)((StackPanel)tiles[i]).Children[0]).Child;

        // Full and Claude stand tall on the left; the wide and short views stack on the right.
        var right = new StackPanel { Children = { tiles[2], tiles[3], tiles[4] } };
        var row = new StackPanel { Orientation = Orientation.Horizontal, Children = { tiles[0], tiles[1], right } };
        var head = new DockPanel { Margin = new Thickness(8, 0, 8, 6), LastChildFill = false };
        head.Children.Add(new PixelLabel("Choose a view", 2) { Brush = Ink.On });
        var hint = new PixelLabel("Esc to close") { VerticalAlignment = VerticalAlignment.Center };
        DockPanel.SetDock(hint, Dock.Right);
        head.Children.Add(hint);

        Content = new Border
        {
            Background = Ink.Bg, BorderBrush = Ink.Alpha(Ink.On, 0.16), BorderThickness = new Thickness(1),
            CornerRadius = new CornerRadius(18), Padding = new Thickness(16, 18, 16, 12),
            Child = new StackPanel { Children = { head, row } },
            RenderTransformOrigin = new Point(0.5, 0.5), RenderTransform = new ScaleTransform(0.97, 0.97),
        };

        refresh = () => { foreach (var p in previews) { p.InvalidateMeasure(); p.InvalidateVisual(); } };
        sampler.Updated += refresh;
        Closed += (_, _) => sampler.Updated -= refresh;
        Deactivated += (_, _) => Dismiss();
        KeyDown += (_, e) => { if (e.Key == Key.Escape) Dismiss(); };
        Opacity = 0;
        Loaded += (_, _) =>
        {
            CenterOnWork();
            var ease = new QuarticEase { EasingMode = EasingMode.EaseOut };
            BeginAnimation(OpacityProperty, new DoubleAnimation(1, TimeSpan.FromMilliseconds(180)) { EasingFunction = ease });
            var grow = new DoubleAnimation(1, TimeSpan.FromMilliseconds(220)) { EasingFunction = ease };
            var st = (ScaleTransform)((Border)Content).RenderTransform;
            st.BeginAnimation(ScaleTransform.ScaleXProperty, grow);
            st.BeginAnimation(ScaleTransform.ScaleYProperty, grow);
            Activate();
        };
    }

    void CenterOnWork()
    {
        var wa = Owner is WidgetWindow w ? w.WorkArea() : SystemParameters.WorkArea;
        Left = wa.Left + (wa.Width - ActualWidth) / 2;
        Top = wa.Top + (wa.Height - ActualHeight) / 2;
    }

    static void Lift(FrameworkElement card, double to)
    {
        var st = (ScaleTransform)card.RenderTransform;
        var a = new DoubleAnimation(to, TimeSpan.FromMilliseconds(140)) { EasingFunction = new QuadraticEase { EasingMode = EasingMode.EaseOut } };
        st.BeginAnimation(ScaleTransform.ScaleXProperty, a);
        st.BeginAnimation(ScaleTransform.ScaleYProperty, a);
    }

    void Choose(WidgetSize size)
    {
        Dismiss();
        pick(size);
    }

    void Dismiss()
    {
        if (closing) return;
        closing = true;
        var fade = new DoubleAnimation(0, TimeSpan.FromMilliseconds(120));
        fade.Completed += (_, _) => Close();
        BeginAnimation(OpacityProperty, fade);
    }
}
