using System;
using System.Linq;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Animation;
using System.Windows.Shapes;

namespace PulseApp;

/// <summary>
/// The subtle loops — header scanner, live pulse, CRT sweep — as retained WPF animations on a
/// transparent overlay, so the pixel view itself only repaints when data changes.
/// </summary>
sealed class Loops
{
    public readonly Canvas Canvas = new() { IsHitTestVisible = false, ClipToBounds = true };

    readonly PulseView view;
    readonly bool motion = SystemParameters.ClientAreaAnimation;
    readonly Canvas scanner = new() { Width = 38, Height = 3 };
    readonly Rectangle[] heads = new Rectangle[3];
    readonly Rectangle pip = new() { Width = 4, Height = 4, Fill = Ink.On };
    readonly Rectangle sweep = new() { Height = 80 };
    readonly TranslateTransform sweepMove = new();
    bool? hot;
    double sweepHeight = -1;

    public Loops(PulseView view)
    {
        this.view = view;
        RenderOptions.SetEdgeMode(Canvas, EdgeMode.Aliased);

        for (int i = 0; i < 8; i++)                     // dim track
        {
            var d = new Rectangle { Width = 3, Height = 3, Fill = Ink.Alpha(Ink.On, 0.12) };
            Canvas.SetLeft(d, i * 5);
            scanner.Children.Add(d);
        }
        double[] alphas = { 0.25, 0.5, 0.9 };            // trail first, head last (on top)
        for (int k = 0; k < 3; k++)
        {
            heads[k] = new Rectangle { Width = 3, Height = 3, Fill = Ink.Alpha(Ink.On, alphas[k]), RenderTransform = new TranslateTransform() };
            scanner.Children.Add(heads[k]);
        }
        Canvas.Children.Add(scanner);

        if (motion)
        {
            var a = new DoubleAnimation(0.3, 1, TimeSpan.FromSeconds(1.3))
            { AutoReverse = true, RepeatBehavior = RepeatBehavior.Forever, EasingFunction = new SineEase { EasingMode = EasingMode.EaseInOut } };
            pip.BeginAnimation(UIElement.OpacityProperty, a);

            var g = new LinearGradientBrush { StartPoint = new Point(0.5, 0), EndPoint = new Point(0.5, 1) };
            g.GradientStops.Add(new GradientStop(Color.FromArgb(0, 255, 255, 255), 0));
            g.GradientStops.Add(new GradientStop(Color.FromArgb(10, 255, 255, 255), 0.5));
            g.GradientStops.Add(new GradientStop(Color.FromArgb(0, 255, 255, 255), 1));
            g.Freeze();
            sweep.Fill = g;
            sweep.Width = PulseView.W;
            sweep.RenderTransform = sweepMove;
            Canvas.Children.Add(sweep);
        }
        pip.Visibility = Visibility.Collapsed;
        Canvas.Children.Add(pip);

        view.LayoutChanged += Sync;
    }

    public void Sync()
    {
        Canvas.SetLeft(scanner, view.ScannerPos.X);
        Canvas.SetTop(scanner, view.ScannerPos.Y);
        if (view.PipPos is { } p)
        {
            Canvas.SetLeft(pip, p.X); Canvas.SetTop(pip, p.Y);
            pip.Visibility = Visibility.Visible;
        }
        else pip.Visibility = Visibility.Collapsed;

        double h = view.ActualHeight;
        if (h > 0 && Math.Abs(h - sweepHeight) > 0.5)
        {
            sweepHeight = h;
            Canvas.Clip = new RectangleGeometry(new Rect(0, 0, PulseView.W, h), PulseView.Radius, PulseView.Radius);
            if (motion)
                sweepMove.BeginAnimation(TranslateTransform.YProperty,
                    new DoubleAnimation(-80, h, TimeSpan.FromSeconds(9)) { RepeatBehavior = RepeatBehavior.Forever });
        }

        if (hot != view.Hot) { hot = view.Hot; StartScanner(view.Hot); }
    }

    void StartScanner(bool fast)
    {
        var positions = Enumerable.Range(0, 8).Concat(Enumerable.Range(1, 6).Reverse()).Select(i => i * 5.0).ToArray();
        double beat = fast ? 0.07 : 0.16;
        for (int k = 0; k < 3; k++)
        {
            var move = (TranslateTransform)heads[k].RenderTransform;
            if (!motion) { move.X = k == 2 ? 10 : -100; continue; }
            int lag = 2 - k;                               // trail runs `lag` steps behind the head
            var a = new DoubleAnimationUsingKeyFrames { Duration = TimeSpan.FromSeconds(beat * positions.Length), RepeatBehavior = RepeatBehavior.Forever };
            for (int i = 0; i < positions.Length; i++)
                a.KeyFrames.Add(new DiscreteDoubleKeyFrame(positions[(i - lag + positions.Length) % positions.Length], KeyTime.FromTimeSpan(TimeSpan.FromSeconds(i * beat))));
            move.BeginAnimation(TranslateTransform.XProperty, a);
        }
    }
}
