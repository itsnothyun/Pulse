// Pulse — monochrome pixel system monitor widget
import AppKit
import SwiftUI
import ServiceManagement
import IOKit
import IOKit.ps
import Darwin
import Carbon.HIToolbox
import UserNotifications

// MARK: - Palette

enum Ink {
    static let bg   = Color(red: 0.035, green: 0.035, blue: 0.035)
    static let on   = Color(red: 0.95, green: 0.95, blue: 0.93)
    static let mid  = Color(red: 0.70, green: 0.70, blue: 0.68)
    static let dim  = Color(red: 0.46, green: 0.46, blue: 0.45)
    static let off  = Color(red: 0.15, green: 0.15, blue: 0.15)
    static let line = Color(red: 0.19, green: 0.19, blue: 0.19)
}

let reduceMotion = NSWorkspace.shared.accessibilityDisplayShouldReduceMotion
var snapshotMode = false   // offscreen renders can't host AppKit layers

/// Soft pastel spectrum for the ULTRA plan label (last stop repeats the first, so it loops seamlessly).
let rainbowHex: [UInt32] = [0xF2A7BC, 0xF2C7A0, 0xDCE6A3, 0xA8E0C8, 0xA6C8F0, 0xC6AEF0, 0xF2A7BC]

func hexColor(_ h: UInt32) -> Color {
    Color(red: Double((h >> 16) & 0xFF) / 255, green: Double((h >> 8) & 0xFF) / 255, blue: Double(h & 0xFF) / 255)
}

func hexCG(_ h: UInt32) -> CGColor {
    CGColor(red: CGFloat((h >> 16) & 0xFF) / 255, green: CGFloat((h >> 8) & 0xFF) / 255, blue: CGFloat(h & 0xFF) / 255, alpha: 1)
}

// MARK: - Zoom

private struct ZoomKey: EnvironmentKey { static let defaultValue: CGFloat = 1 }

extension EnvironmentValues {
    /// Widget scale (1–2, or 0.5 in the view gallery). Every pixel measure is multiplied by it,
    /// so the font is redrawn at the new size and stays crisp.
    var zoom: CGFloat {
        get { self[ZoomKey.self] }
        set { self[ZoomKey.self] = newValue }
    }
}

// MARK: - 5x7 bitmap font

let glyphs: [Character: [UInt8]] = [
    "0": [0x0E,0x11,0x13,0x15,0x19,0x11,0x0E], "1": [0x04,0x0C,0x04,0x04,0x04,0x04,0x0E],
    "2": [0x0E,0x11,0x01,0x02,0x04,0x08,0x1F], "3": [0x1F,0x02,0x04,0x02,0x01,0x11,0x0E],
    "4": [0x02,0x06,0x0A,0x12,0x1F,0x02,0x02], "5": [0x1F,0x10,0x1E,0x01,0x01,0x11,0x0E],
    "6": [0x06,0x08,0x10,0x1E,0x11,0x11,0x0E], "7": [0x1F,0x01,0x02,0x04,0x08,0x08,0x08],
    "8": [0x0E,0x11,0x11,0x0E,0x11,0x11,0x0E], "9": [0x0E,0x11,0x11,0x0F,0x01,0x02,0x0C],
    "A": [0x0E,0x11,0x11,0x1F,0x11,0x11,0x11], "B": [0x1E,0x11,0x11,0x1E,0x11,0x11,0x1E],
    "C": [0x0E,0x11,0x10,0x10,0x10,0x11,0x0E], "D": [0x1C,0x12,0x11,0x11,0x11,0x12,0x1C],
    "E": [0x1F,0x10,0x10,0x1E,0x10,0x10,0x1F], "F": [0x1F,0x10,0x10,0x1E,0x10,0x10,0x10],
    "G": [0x0E,0x11,0x10,0x17,0x11,0x11,0x0F], "H": [0x11,0x11,0x11,0x1F,0x11,0x11,0x11],
    "I": [0x0E,0x04,0x04,0x04,0x04,0x04,0x0E], "J": [0x07,0x02,0x02,0x02,0x02,0x12,0x0C],
    "K": [0x11,0x12,0x14,0x18,0x14,0x12,0x11], "L": [0x10,0x10,0x10,0x10,0x10,0x10,0x1F],
    "M": [0x11,0x1B,0x15,0x15,0x11,0x11,0x11], "N": [0x11,0x11,0x19,0x15,0x13,0x11,0x11],
    "O": [0x0E,0x11,0x11,0x11,0x11,0x11,0x0E], "P": [0x1E,0x11,0x11,0x1E,0x10,0x10,0x10],
    "Q": [0x0E,0x11,0x11,0x11,0x15,0x12,0x0D], "R": [0x1E,0x11,0x11,0x1E,0x14,0x12,0x11],
    "S": [0x0F,0x10,0x10,0x0E,0x01,0x01,0x1E], "T": [0x1F,0x04,0x04,0x04,0x04,0x04,0x04],
    "U": [0x11,0x11,0x11,0x11,0x11,0x11,0x0E], "V": [0x11,0x11,0x11,0x11,0x11,0x0A,0x04],
    "W": [0x11,0x11,0x11,0x15,0x15,0x15,0x0A], "X": [0x11,0x11,0x0A,0x04,0x0A,0x11,0x11],
    "Y": [0x11,0x11,0x11,0x0A,0x04,0x04,0x04], "Z": [0x1F,0x01,0x02,0x04,0x08,0x10,0x1F],
    ".": [0,0,0,0,0,0x0C,0x0C], "%": [0x18,0x19,0x02,0x04,0x08,0x13,0x03],
    "/": [0,0x01,0x02,0x04,0x08,0x10,0], ":": [0,0x0C,0x0C,0,0x0C,0x0C,0],
    "°": [0x0C,0x12,0x12,0x0C,0,0,0], "-": [0,0,0,0x1F,0,0,0], " ": [0,0,0,0,0,0,0],
    ">": [0x08,0x04,0x02,0x01,0x02,0x04,0x08], "_": [0,0,0,0,0,0,0x1F],
    "+": [0,0x04,0x04,0x1F,0x04,0x04,0], "·": [0,0,0,0x04,0,0,0], "!": [0x04,0x04,0x04,0x04,0x04,0,0x04],
    "↑": [0x04,0x0E,0x15,0x04,0x04,0x04,0x04], "↓": [0x04,0x04,0x04,0x04,0x15,0x0E,0x04],
    "⚡": [0x02,0x04,0x08,0x1F,0x02,0x04,0x08],
    "$": [0x04,0x0F,0x14,0x0E,0x05,0x1E,0x04], "~": [0,0,0x08,0x15,0x02,0,0],
    "@": [0x0E,0x11,0x17,0x15,0x17,0x10,0x0E],
]

struct PixelText: View {
    let text: String
    var scale: CGFloat = 2
    var color: Color = Ink.on
    @Environment(\.zoom) var z

    static func width(_ s: String, _ scale: CGFloat) -> CGFloat { CGFloat(max(s.count * 6 - 1, 0)) * scale }

    var body: some View {
        let chars = Array(text.uppercased())
        let px = scale * z
        let dot = scale >= 3 ? (scale - 0.75) * z : px
        Canvas { ctx, _ in
            for (i, ch) in chars.enumerated() {
                guard let rows = glyphs[ch] else { continue }
                let ox = CGFloat(i * 6) * px
                for (y, row) in rows.enumerated() {
                    for x in 0..<5 where row & (0x10 >> UInt8(x)) != 0 {
                        ctx.fill(Path(CGRect(x: ox + CGFloat(x) * px, y: CGFloat(y) * px,
                                             width: dot, height: dot)), with: .color(color))
                    }
                }
            }
        }
        .frame(width: PixelText.width(text, px), height: 7 * px)
    }
}

/// Number that tweens between samples.
struct PixelNumber: View, Animatable {
    var value: Double
    let format: (Double) -> String
    var scale: CGFloat = 3
    var color: Color = Ink.on
    var animatableData: Double { get { value } set { value = newValue } }
    var body: some View { PixelText(text: format(value), scale: scale, color: color) }
}

/// Pixel text filled with the slowly drifting pastel spectrum (one 64 pt period per 7 s).
/// The drift is a Core Animation loop; snapshots and Reduce Motion get a still gradient.
struct RainbowText: View {
    let text: String
    var scale: CGFloat = 1
    @Environment(\.zoom) var z

    var body: some View {
        let px = scale * z
        let w = PixelText.width(text, px), h = 7 * px
        if snapshotMode || reduceMotion {
            LinearGradient(colors: rainbowHex.map(hexColor), startPoint: .leading, endPoint: .trailing)
                .frame(width: 64 * z, height: h)
                .frame(width: w, height: h, alignment: .leading)
                .clipped()
                .mask(alignment: .topLeading) { PixelText(text: text, scale: scale, color: .white) }
        } else {
            RainbowLayer(text: text, px: px, period: 64 * z).frame(width: w, height: h)
        }
    }
}

struct RainbowLayer: NSViewRepresentable {
    let text: String
    let px: CGFloat
    let period: CGFloat

    func makeNSView(context: Context) -> RainbowView {
        let v = RainbowView()
        v.configure(text, px, period)
        return v
    }
    func updateNSView(_ v: RainbowView, context: Context) { v.configure(text, px, period) }
    func sizeThatFits(_ p: ProposedViewSize, nsView: RainbowView, context: Context) -> CGSize? {
        CGSize(width: PixelText.width(text, px), height: 7 * px)
    }
}

/// One layer per lit pixel, each cycling through the spectrum with a phase set by its x position,
/// which reads as a gradient sliding to the right. No masks, so no coordinate-flip surprises.
final class RainbowView: NSView {
    private var key = ""
    override var isFlipped: Bool { true }
    override init(frame: NSRect) { super.init(frame: frame); wantsLayer = true }
    required init?(coder: NSCoder) { fatalError() }
    override func hitTest(_ p: NSPoint) -> NSView? { nil }

    func configure(_ text: String, _ px: CGFloat, _ period: CGFloat) {
        let k = "\(text)|\(px)|\(period)"
        guard k != key, let root = layer, px > 0, period > 0 else { return }
        key = k
        root.sublayers?.forEach { $0.removeFromSuperlayer() }
        let colors: [CGColor] = rainbowHex.reversed().map(hexCG)   // reversed: the spectrum moves rightward
        let duration = 7.0
        for (i, ch) in Array(text.uppercased()).enumerated() {
            guard let rows = glyphs[ch] else { continue }
            for (y, row) in rows.enumerated() {
                for x in 0..<5 where row & (0x10 >> UInt8(x)) != 0 {
                    let left = CGFloat(i * 6 + x) * px
                    let l = CALayer()
                    l.frame = CGRect(x: left, y: CGFloat(y) * px, width: px, height: px)
                    l.backgroundColor = colors[0]
                    let a = CAKeyframeAnimation(keyPath: "backgroundColor")
                    a.values = colors
                    a.calculationMode = .linear
                    a.duration = duration
                    a.repeatCount = .infinity
                    let phase = Double((left + px / 2) / period).truncatingRemainder(dividingBy: 1)
                    a.timeOffset = duration * (1 - phase)
                    l.add(a, forKey: "hue")
                    root.addSublayer(l)
                }
            }
        }
    }
}

// MARK: - Pixel widgets

struct PixelBar: View, Animatable {
    var value: Double          // 0...1
    var segments = 28
    var height: CGFloat = 8
    var blink = false
    @Environment(\.zoom) var z
    var animatableData: Double { get { value } set { value = newValue } }

    var body: some View {
        let gap = 2 * z
        Canvas { ctx, size in
            let sw = ((size.width - gap * CGFloat(segments - 1)) / CGFloat(segments)).rounded(.down)
            let exact = min(max(value, 0), 1) * Double(segments)
            let lit = Int(exact)
            let partial = exact - Double(lit)
            for i in 0..<segments {
                let r = CGRect(x: CGFloat(i) * (sw + gap), y: 0, width: sw, height: size.height)
                var c: Color = i < lit ? Ink.on : Ink.off
                if i == lit && partial > 0.15 { c = Ink.dim }          // leading half-lit pixel
                if blink && i == max(lit - 1, 0) { c = Ink.off }
                ctx.fill(Path(r), with: .color(c))
            }
        }
        .frame(height: height * z)
    }
}

struct Sparkline: View {
    let data: [Double]         // 0...1
    var columns = 18
    var height: CGFloat = 18
    @Environment(\.zoom) var z

    var body: some View {
        let cw = 2 * z, gap = 1 * z, px = 2 * z, base = 1 * z
        Canvas { ctx, size in
            let pts = Array(data.suffix(columns))
            let start = CGFloat(columns - pts.count) * (cw + gap)
            let levels = Int((size.height / px).rounded())
            for i in 0..<columns {                                     // baseline dots
                ctx.fill(Path(CGRect(x: CGFloat(i) * (cw + gap), y: size.height - base, width: cw, height: base)), with: .color(Ink.off))
            }
            for (i, v) in pts.enumerated() {
                let h = max(1, Int((min(max(v, 0), 1) * Double(levels)).rounded()))
                let x = start + CGFloat(i) * (cw + gap)
                let age = Double(i + 1) / Double(pts.count)
                for l in 0..<h {
                    let top = l == h - 1
                    ctx.fill(Path(CGRect(x: x, y: size.height - CGFloat(l + 1) * px, width: cw, height: px - base / 2)),
                             with: .color(top ? Ink.on.opacity(0.35 + 0.65 * age) : Ink.dim.opacity(0.12 + 0.3 * age)))
                }
            }
        }
        .frame(width: CGFloat(columns * 3 - 1) * z, height: height * z)
    }
}

/// One mini vertical meter per core.
struct CoreGrid: View {
    let cores: [Double]
    let perfCount: Int
    @Environment(\.zoom) var z

    var body: some View {
        let gap = 4 * z, px = 2 * z, lg = 1 * z
        Canvas { ctx, size in
            guard !cores.isEmpty else { return }
            let levels = 5
            let cw = ((size.width - gap * CGFloat(cores.count - 1)) / CGFloat(cores.count)).rounded(.down)
            for (i, v) in cores.enumerated() {
                let lit = Int((min(max(v, 0), 1) * Double(levels)).rounded(.up))
                let x = CGFloat(i) * (cw + gap)
                for l in 0..<levels {
                    let y = size.height - CGFloat(l + 1) * (px + lg)
                    ctx.fill(Path(CGRect(x: x, y: y, width: cw, height: px)), with: .color(l < lit ? Ink.on : Ink.off))
                }
            }
        }
        .frame(height: 15 * z)
    }
}

struct DottedRule: View {
    @Environment(\.zoom) var z
    var body: some View {
        let dash = 2 * z, step = 4 * z
        Canvas { ctx, size in
            var x: CGFloat = 0
            while x < size.width { ctx.fill(Path(CGRect(x: x, y: 0, width: dash, height: size.height)), with: .color(Ink.line)); x += step }
        }.frame(height: z)
    }
}

/// The dotted rule between the two columns of the Landscape view; fills whatever height it is given.
struct VerticalRule: View {
    @Environment(\.zoom) var z
    var body: some View {
        let dash = 2 * z, step = 4 * z
        Canvas { ctx, size in
            var y: CGFloat = 0
            while y < size.height { ctx.fill(Path(CGRect(x: 0, y: y, width: size.width, height: dash)), with: .color(Ink.line)); y += step }
        }
        .frame(width: z)
        .frame(maxHeight: .infinity)
    }
}

/// Mon–Sun token bars; today bright, past days mid, future days empty.
struct WeekChart: View {
    let days: [Double]
    let today: Int
    @Environment(\.zoom) var z
    var body: some View {
        let gap = 4 * z, px = 2 * z, lg = 1 * z
        VStack(spacing: 4 * z) {
            Canvas { ctx, size in
                let levels = 8
                let cw = ((size.width - gap * 6) / 7).rounded(.down)
                let peak = max(days.max() ?? 0, 1)
                for (i, v) in days.enumerated() {
                    let lit = v > 0 ? max(1, Int((v / peak * Double(levels)).rounded(.up))) : 0
                    for l in 0..<levels {
                        let c: Color = l < lit ? (i == today ? Ink.on : Ink.mid.opacity(0.75)) : (i > today ? Ink.off.opacity(0.5) : Ink.off)
                        ctx.fill(Path(CGRect(x: CGFloat(i) * (cw + gap), y: size.height - CGFloat(l + 1) * (px + lg), width: cw, height: px)), with: .color(c))
                    }
                }
            }
            .frame(height: 24 * z)
            HStack(spacing: 0) {
                ForEach(Array("MTWTFSS".enumerated()), id: \.offset) { i, d in
                    PixelText(text: String(d), scale: 1, color: i == today ? Ink.on : Ink.dim).frame(maxWidth: .infinity)
                }
            }
        }
    }
}

struct Stat: View {
    let label: String
    let value: String
    @Environment(\.zoom) var z
    var body: some View {
        VStack(alignment: .leading, spacing: 5 * z) {
            PixelText(text: label, scale: 1, color: Ink.dim)
            PixelText(text: value, scale: 1.5, color: Ink.on)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

// MARK: - Loop animations (subtle)

// Loops run as Core Animation layers: the render server drives them, so they cost ~0% app CPU.

private func caColor(_ white: CGFloat, _ a: CGFloat) -> CGColor { NSColor(white: white, alpha: a).cgColor }

private func loopsPaused() -> Bool { reduceMotion }

/// Live-indicator pixel (static in snapshots).
struct LivePip: View {
    @Environment(\.zoom) var z
    var body: some View {
        if snapshotMode { Rectangle().fill(Ink.on).frame(width: 4 * z, height: 4 * z) } else { Pulse(z: z).id(z) }
    }
}

/// Header scanner (static in snapshots).
struct HeaderScanner: View {
    var hot = false
    @Environment(\.zoom) var z
    var body: some View {
        if snapshotMode {
            HStack(spacing: 2 * z) {
                ForEach(0..<8, id: \.self) { i in Rectangle().fill(Ink.on.opacity(i == 2 ? 0.9 : 0.12)).frame(width: 3 * z, height: 3 * z) }
            }
        } else { Scanner(hot: hot, z: z).id(z) }
    }
}

/// Softly breathing pixel, used as a "live" indicator.
struct Pulse: NSViewRepresentable {
    var z: CGFloat = 1
    func makeNSView(context: Context) -> NSView {
        let v = NSView(); v.wantsLayer = true
        let l = CALayer(); l.frame = CGRect(x: 0, y: 0, width: 4 * z, height: 4 * z); l.backgroundColor = caColor(0.95, 1)
        v.layer?.addSublayer(l)
        if !loopsPaused() {
            let a = CABasicAnimation(keyPath: "opacity")
            a.fromValue = 0.3; a.toValue = 1; a.duration = 1.3; a.autoreverses = true; a.repeatCount = .infinity
            a.timingFunction = CAMediaTimingFunction(name: .easeInEaseOut)
            l.add(a, forKey: "pulse")
        }
        return v
    }
    func updateNSView(_ v: NSView, context: Context) {}
    func sizeThatFits(_ p: ProposedViewSize, nsView: NSView, context: Context) -> CGSize? { CGSize(width: 4 * z, height: 4 * z) }
}

/// KITT-style scanner: a pixel stepping back and forth across a dim track, with a fading trail.
struct Scanner: NSViewRepresentable {
    var hot = false
    var z: CGFloat = 1
    let n = 8
    var step: CGFloat { 5 * z }
    var dot: CGFloat { 3 * z }

    func makeNSView(context: Context) -> NSView {
        let v = NSView(); v.wantsLayer = true
        for i in 0..<n {
            let d = CALayer(); d.frame = CGRect(x: CGFloat(i) * step, y: 0, width: dot, height: dot)
            d.backgroundColor = caColor(0.95, 0.12); v.layer?.addSublayer(d)
        }
        for (k, alpha) in [(2, 0.25), (1, 0.5), (0, 0.9)] {        // trail first, head last (on top)
            let l = CALayer(); l.frame = CGRect(x: 0, y: 0, width: dot, height: dot)
            l.backgroundColor = caColor(0.95, alpha); l.anchorPoint = .zero; l.position = .zero
            l.setValue(k, forKey: "lag")
            v.layer?.addSublayer(l)
        }
        context.coordinator.layers = v.layer?.sublayers?.suffix(3).map { $0 } ?? []
        apply(context.coordinator)
        return v
    }

    func apply(_ c: Coordinator) {
        guard !loopsPaused(), c.hot != hot || c.first else { return }
        c.first = false; c.hot = hot
        let forward: [CGFloat] = (0..<n).map { CGFloat($0) * step }
        let back: [CGFloat] = (1..<(n - 1)).reversed().map { CGFloat($0) * step }
        let positions: [CGFloat] = forward + back
        let beat = hot ? 0.07 : 0.16
        for l in c.layers {
            let lag = l.value(forKey: "lag") as? Int ?? 0
            let a = CAKeyframeAnimation(keyPath: "position.x")
            a.values = positions; a.calculationMode = .discrete
            a.duration = beat * Double(positions.count); a.repeatCount = .infinity
            a.timeOffset = a.duration - Double(lag) * beat                     // trail runs `lag` steps behind the head
            l.add(a, forKey: "scan")
        }
    }

    final class Coordinator { var layers: [CALayer] = []; var hot = false; var first = true }
    func makeCoordinator() -> Coordinator { Coordinator() }
    func updateNSView(_ v: NSView, context: Context) { apply(context.coordinator) }
    func sizeThatFits(_ p: ProposedViewSize, nsView: NSView, context: Context) -> CGSize? {
        CGSize(width: CGFloat(n - 1) * step + dot, height: dot)
    }
}

/// Static scanlines plus a faint CRT band slowly sweeping down the panel.
struct CRTOverlay: View {
    var sweep = true
    @Environment(\.zoom) var z
    var body: some View {
        let line = z, pitch = 3 * z
        ZStack {
            Canvas { ctx, size in
                var y: CGFloat = 0
                while y < size.height { ctx.fill(Path(CGRect(x: 0, y: y, width: size.width, height: line)), with: .color(.white.opacity(0.022))); y += pitch }
            }
            if sweep && !reduceMotion && !snapshotMode { Sweep(band: 80 * z).id(z) }
        }
        .allowsHitTesting(false)
    }

    struct Sweep: NSViewRepresentable {
        var band: CGFloat = 80
        func makeNSView(context: Context) -> NSView { let v = SweepView(); v.bh = band; return v }
        func updateNSView(_ v: NSView, context: Context) { (v as? SweepView)?.restart() }
    }

    final class SweepView: NSView {
        let band = CAGradientLayer()
        var bh: CGFloat = 80
        var lastHeight: CGFloat = -1, lastWidth: CGFloat = -1
        override var isFlipped: Bool { true }
        override init(frame: NSRect) {
            super.init(frame: frame); wantsLayer = true
            band.colors = [caColor(1, 0), caColor(1, 0.04), caColor(1, 0)]
            band.startPoint = CGPoint(x: 0.5, y: 0); band.endPoint = CGPoint(x: 0.5, y: 1)
            layer?.addSublayer(band)
        }
        required init?(coder: NSCoder) { fatalError() }
        override func hitTest(_ p: NSPoint) -> NSView? { nil }
        override func layout() { super.layout(); restart() }
        func restart() {
            let h = bounds.height, w = bounds.width
            guard h > 0, h != lastHeight || w != lastWidth else { return }
            lastHeight = h; lastWidth = w
            CATransaction.begin(); CATransaction.setDisableActions(true)
            band.frame = CGRect(x: 0, y: -bh, width: w, height: bh)
            CATransaction.commit()
            let a = CABasicAnimation(keyPath: "position.y")
            a.fromValue = -bh / 2; a.toValue = h + bh / 2
            a.duration = 9; a.repeatCount = .infinity
            band.add(a, forKey: "sweep")
        }
    }
}

// MARK: - Temperature (Apple Silicon HID sensors)

final class Thermals: @unchecked Sendable {   // only touched from the probe queue after init
    typealias CreateFn = @convention(c) (CFAllocator?) -> UnsafeMutableRawPointer?
    typealias SetMatchingFn = @convention(c) (UnsafeMutableRawPointer, UnsafeRawPointer) -> Int32
    typealias CopyServicesFn = @convention(c) (UnsafeMutableRawPointer) -> UnsafeRawPointer?
    typealias CopyPropFn = @convention(c) (UnsafeRawPointer, UnsafeRawPointer) -> UnsafeRawPointer?
    typealias CopyEventFn = @convention(c) (UnsafeRawPointer, Int64, Int32, Int64) -> UnsafeRawPointer?
    typealias GetFloatFn = @convention(c) (UnsafeRawPointer, Int32) -> Double

    private var client: UnsafeMutableRawPointer?
    private var copyServices: CopyServicesFn?
    private var copyProp: CopyPropFn?
    private var copyEvent: CopyEventFn?
    private var getFloat: GetFloatFn?

    init() {
        guard let h = dlopen("/System/Library/Frameworks/IOKit.framework/IOKit", RTLD_NOW),
              let c = dlsym(h, "IOHIDEventSystemClientCreate"),
              let m = dlsym(h, "IOHIDEventSystemClientSetMatching"),
              let s = dlsym(h, "IOHIDEventSystemClientCopyServices"),
              let p = dlsym(h, "IOHIDServiceClientCopyProperty"),
              let e = dlsym(h, "IOHIDServiceClientCopyEvent"),
              let f = dlsym(h, "IOHIDEventGetFloatValue") else { return }
        let create = unsafeBitCast(c, to: CreateFn.self)
        let setMatching = unsafeBitCast(m, to: SetMatchingFn.self)
        copyServices = unsafeBitCast(s, to: CopyServicesFn.self)
        copyProp = unsafeBitCast(p, to: CopyPropFn.self)
        copyEvent = unsafeBitCast(e, to: CopyEventFn.self)
        getFloat = unsafeBitCast(f, to: GetFloatFn.self)
        guard let cl = create(kCFAllocatorDefault) else { return }
        let match = ["PrimaryUsagePage": 0xff00, "PrimaryUsage": 5] as CFDictionary
        _ = setMatching(cl, Unmanaged.passUnretained(match).toOpaque())
        client = cl
    }

    /// Returns (cpu average, hottest sensor) in °C.
    func read() -> (cpu: Double, max: Double)? {
        guard let client, let copyServices, let copyProp, let copyEvent, let getFloat,
              let arrPtr = copyServices(client) else { return nil }
        let services = Unmanaged<CFArray>.fromOpaque(arrPtr).takeRetainedValue()
        let key = Unmanaged.passUnretained("Product" as CFString).toOpaque()
        var cpu: [Double] = [], all: [Double] = []
        for i in 0..<CFArrayGetCount(services) {
            guard let svc = CFArrayGetValueAtIndex(services, i) else { continue }
            var name = ""
            if let np = copyProp(svc, key) {
                name = (Unmanaged<AnyObject>.fromOpaque(np).takeRetainedValue() as? String) ?? ""
            }
            guard let ev = copyEvent(svc, 15, 0, 0) else { continue }
            let t = getFloat(ev, 15 << 16)
            Unmanaged<AnyObject>.fromOpaque(ev).release()
            guard t > 5, t < 130 else { continue }
            if name.contains("battery") || name.contains("NAND") { continue }
            all.append(t)
            if name.contains("tdie") || name.contains("ACC") || name.contains("CPU") || name.contains("SOC") { cpu.append(t) }
        }
        guard !all.isEmpty else { return nil }
        let src = cpu.isEmpty ? all : cpu
        return (src.reduce(0, +) / Double(src.count), all.max()!)
    }
}

// MARK: - Probes

enum Probe {
    static func memory() -> (used: Double, total: Double)? {
        var stats = vm_statistics64()
        var count = mach_msg_type_number_t(MemoryLayout<vm_statistics64_data_t>.stride / MemoryLayout<integer_t>.stride)
        let kr = withUnsafeMutablePointer(to: &stats) {
            $0.withMemoryRebound(to: integer_t.self, capacity: Int(count)) { host_statistics64(mach_host_self(), HOST_VM_INFO64, $0, &count) }
        }
        guard kr == KERN_SUCCESS else { return nil }
        let pages = Double(stats.internal_page_count) - Double(stats.purgeable_count) + Double(stats.wire_count) + Double(stats.compressor_page_count)
        return (pages * Double(vm_kernel_page_size), Double(ProcessInfo.processInfo.physicalMemory))
    }

    static func disk() -> (used: Double, total: Double)? {
        guard let v = try? URL(fileURLWithPath: "/").resourceValues(forKeys: [.volumeTotalCapacityKey, .volumeAvailableCapacityForImportantUsageKey]),
              let total = v.volumeTotalCapacity, let free = v.volumeAvailableCapacityForImportantUsage else { return nil }
        return (Double(total) - Double(free), Double(total))
    }

    static func cpuTicks() -> [[UInt32]] {
        var n: natural_t = 0
        var info: processor_info_array_t?
        var infoCount: mach_msg_type_number_t = 0
        guard host_processor_info(mach_host_self(), PROCESSOR_CPU_LOAD_INFO, &n, &info, &infoCount) == KERN_SUCCESS, let info else { return [] }
        defer { vm_deallocate(mach_task_self_, vm_address_t(bitPattern: info), vm_size_t(Int(infoCount) * MemoryLayout<integer_t>.stride)) }
        return (0..<Int(n)).map { c in (0..<Int(CPU_STATE_MAX)).map { UInt32(bitPattern: info[c * Int(CPU_STATE_MAX) + $0]) } }
    }

    static func gpu() -> Double? {
        var it: io_iterator_t = 0
        guard IOServiceGetMatchingServices(kIOMainPortDefault, IOServiceMatching("IOAccelerator"), &it) == KERN_SUCCESS else { return nil }
        defer { IOObjectRelease(it) }
        var best: Double?
        while case let s = IOIteratorNext(it), s != 0 {
            defer { IOObjectRelease(s) }
            if let p = IORegistryEntryCreateCFProperty(s, "PerformanceStatistics" as CFString, kCFAllocatorDefault, 0)?.takeRetainedValue() as? [String: Any],
               let u = p["Device Utilization %"] as? NSNumber {
                best = max(best ?? 0, u.doubleValue / 100)
            }
        }
        return best
    }

    /// Cumulative bytes per interface (en*), 32-bit counters.
    static func netCounters() -> [String: (UInt32, UInt32)] {
        var out: [String: (UInt32, UInt32)] = [:]
        var ifap: UnsafeMutablePointer<ifaddrs>?
        guard getifaddrs(&ifap) == 0 else { return out }
        defer { freeifaddrs(ifap) }
        var p = ifap
        while let a = p {
            let i = a.pointee
            if let addr = i.ifa_addr, addr.pointee.sa_family == UInt8(AF_LINK), let d = i.ifa_data {
                let name = String(cString: i.ifa_name)
                if name.hasPrefix("en") {
                    let data = d.assumingMemoryBound(to: if_data.self).pointee
                    out[name] = (data.ifi_ibytes, data.ifi_obytes)
                }
            }
            p = i.ifa_next
        }
        return out
    }

    static func swap() -> (used: Double, total: Double) {
        var sw = xsw_usage(); var sz = MemoryLayout<xsw_usage>.size
        sysctlbyname("vm.swapusage", &sw, &sz, nil, 0)
        return (Double(sw.xsu_used), Double(sw.xsu_total))
    }

    static func battery() -> (pct: Int, charging: Bool, ac: Bool)? {
        let blob = IOPSCopyPowerSourcesInfo().takeRetainedValue()
        let list = IOPSCopyPowerSourcesList(blob).takeRetainedValue() as [CFTypeRef]
        for ps in list {
            guard let d = IOPSGetPowerSourceDescription(blob, ps)?.takeUnretainedValue() as? [String: Any],
                  let cur = d[kIOPSCurrentCapacityKey] as? Int, let mx = d[kIOPSMaxCapacityKey] as? Int, mx > 0 else { continue }
            return (cur * 100 / mx, d[kIOPSIsChargingKey] as? Bool ?? false, (d[kIOPSPowerSourceStateKey] as? String) == kIOPSACPowerValue)
        }
        return nil
    }

    /// Heaviest processes, grouped by name. `ps` is setuid, so it sees system processes too;
    /// it only runs while a list is open.
    static func top(_ mode: TopMode) -> [TopProc] {
        let p = Process(), pipe = Pipe()
        p.executableURL = URL(fileURLWithPath: "/bin/ps")
        p.arguments = ["-Aceo", "pcpu=,rss=,comm="]
        p.standardOutput = pipe; p.standardError = FileHandle.nullDevice
        guard (try? p.run()) != nil else { return [] }
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        p.waitUntilExit()
        var by: [String: (cpu: Double, mem: Double)] = [:]
        for line in String(decoding: data, as: UTF8.self).split(separator: "\n") {
            let f = line.split(separator: " ", maxSplits: 2)
            guard f.count == 3, let cpu = Double(f[0]), let rss = Double(f[1]) else { continue }
            let name = f[2].trimmingCharacters(in: .whitespaces)
            guard name != "ps" else { continue }
            by[name, default: (0, 0)].cpu += cpu
            by[name, default: (0, 0)].mem += rss * 1024
        }
        return by.map { TopProc(name: $0.key, value: mode == .cpu ? $0.value.cpu : $0.value.mem) }
            .sorted { $0.value > $1.value }.prefix(3).map { $0 }
    }

    static func load() -> Double { var l = [Double](repeating: 0, count: 3); getloadavg(&l, 3); return l[0] }
}

// MARK: - Claude Code usage (local transcripts in ~/.claude/projects)

/// One line of a breakdown: who or what spent the tokens.
struct UsageSlice {
    let name: String
    let tokens: Double
    let cost: Double
}

struct ClaudeStats {
    var week = 0.0, input = 0.0, output = 0.0, cacheWrite = 0.0, cacheRead = 0.0
    var today = 0.0
    var cost = 0.0                     // estimated USD at API list prices
    var block = 0.0, blockEnd = 0.0    // tokens in the current 5-hour block, and when it resets (0 = no block open)
    var sessions = 0, live = 0, calls = 0
    var days = [Double](repeating: 0, count: 7)
    var todayIndex = 0
    var ready = false
    var email: String?, plan: String?   // the account Claude Code is signed in with (nil = API key or signed out)
    var byModel: [UsageSlice] = []           // this week, largest first
    var byProject: [UsageSlice] = []
    var byAccount: [UsageSlice] = []
}

/// Incremental tally of this week's tokens across every Claude Code session on this Mac.
/// Each pass reads only bytes appended since the last pass; API calls are de-duplicated by message+request id.
final class ClaudeUsage {
    private struct Event {
        let ts: Double
        let input, output, cw, cr, cost: Double
        let session, model, project: String
    }

    /// Estimated API list price in USD per million tokens: input, output, cache write, cache read.
    /// First match wins; unknown models count as free. Edit when prices change.
    static let prices: [(String, [Double])] = [
        ("fable", [10, 50, 12.5, 1]),
        ("opus-5", [4, 20, 5, 0.4]), ("opus-4-5", [5, 25, 6.25, 0.5]), ("opus", [15, 75, 18.75, 1.5]),
        ("sonnet-5", [2, 10, 2.5, 0.1]), ("sonnet", [3, 15, 3.75, 0.3]),
        ("haiku-5", [0.1, 0.5, 0.125, 0.01]), ("haiku-4", [1, 5, 1.25, 0.1]), ("haiku", [0.8, 4, 1, 0.08]),
    ]
    static func price(_ model: String) -> [Double] { prices.first { model.contains($0.0) }?.1 ?? [0, 0, 0, 0] }

    static func family(_ model: String) -> String {
        model.contains("fable") ? "FABLE" : model.contains("opus") ? "OPUS" : model.contains("sonnet") ? "SONNET"
            : model.contains("haiku") ? "HAIKU" : "OTHER"
    }

    /// Project name: the last folder of the session's working directory, else the transcript folder.
    static func projectName(_ cwd: String?, _ fallback: String) -> String {
        if let cwd, let last = cwd.split(whereSeparator: { $0 == "/" || $0 == "\\" }).last { return String(last) }
        return fallback
    }

    private let q = DispatchQueue(label: "pulse.claude", qos: .utility)
    private var offsets: [String: UInt64] = [:]
    private var seen = Set<String>()
    private var events: [Event] = []
    private var weekStart = 0.0
    private let isoFrac: ISO8601DateFormatter = { let f = ISO8601DateFormatter(); f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]; return f }()
    private let iso = ISO8601DateFormatter()

    func refresh(_ done: @escaping (ClaudeStats) -> Void) {
        q.async { let s = self.scan(); DispatchQueue.main.async { done(s) } }
    }
    func scanSync() -> ClaudeStats { q.sync { scan() } }

    private var accountStamp: Date?
    private var email: String?, plan: String?

    /// Re-reads the signed-in account from ~/.claude.json (or $CLAUDE_CONFIG_DIR/.claude.json) only when it changes —
    /// /login rewrites it, so it always names the current account.
    private func readAccount() {
        let url = ProcessInfo.processInfo.environment["CLAUDE_CONFIG_DIR"].map { URL(fileURLWithPath: $0).appendingPathComponent(".claude.json") }
            ?? FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".claude.json")
        guard let mod = (try? url.resourceValues(forKeys: [.contentModificationDateKey]))?.contentModificationDate else {
            email = nil; plan = nil; accountStamp = nil; return
        }
        guard mod != accountStamp, let data = try? Data(contentsOf: url),
              let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return }   // unchanged, or mid-write
        let a = root["oauthAccount"] as? [String: Any]
        email = a?["emailAddress"] as? String; plan = a?["planDisplayName"] as? String
        accountStamp = mod
    }

    /// When each account was first seen signed in (unix s). Transcripts don't name the account, so tokens are
    /// credited to whoever was signed in at the time; the first account ever seen also owns the history before it.
    private var accountLog: [(from: Double, email: String)] = ClaudeUsage.loadAccountLog()

    private static var accountLogURL: URL {
        FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/Pulse/accounts.json")
    }

    private static func loadAccountLog() -> [(from: Double, email: String)] {
        guard let data = try? Data(contentsOf: accountLogURL),
              let arr = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]] else { return [] }
        let log: [(from: Double, email: String)] = arr.compactMap { e -> (from: Double, email: String)? in
            guard let f = (e["from"] as? NSNumber)?.doubleValue, let m = e["email"] as? String, !m.isEmpty else { return nil }
            return (from: f, email: m)
        }
        return log.sorted { $0.from < $1.from }
    }

    private func noteAccount(_ current: String?) {
        guard let current, accountLog.last?.email != current else { return }
        accountLog.append((from: accountLog.isEmpty ? 0 : Date().timeIntervalSince1970, email: current))
        let arr: [[String: Any]] = accountLog.map { ["from": $0.from, "email": $0.email] }
        let url = Self.accountLogURL
        try? FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        if let data = try? JSONSerialization.data(withJSONObject: arr) { try? data.write(to: url, options: .atomic) }
    }

    private func accountAt(_ ts: Double) -> String {
        var who = accountLog.first?.email ?? "UNKNOWN"
        for a in accountLog {
            if a.from <= ts { who = a.email } else { break }
        }
        return who
    }

    private func top(_ key: (Event) -> String) -> [UsageSlice] {
        var by: [String: (t: Double, c: Double)] = [:]
        for e in events {
            let k = key(e)
            let cur = by[k] ?? (t: 0, c: 0)
            by[k] = (t: cur.t + e.input + e.output + e.cw + e.cr, c: cur.c + e.cost)
        }
        return by.map { UsageSlice(name: $0.key, tokens: $0.value.t, cost: $0.value.c) }.sorted { $0.tokens > $1.tokens }
    }

    /// Offset just past `needle` in `hay`, searching forward (or for the last match).
    private static func find(_ hay: UnsafeRawBufferPointer, _ needle: String, last: Bool = false) -> Int? {
        guard let h = hay.baseAddress else { return nil }
        return needle.utf8CString.withUnsafeBufferPointer { nb -> Int? in
            let nlen = nb.count - 1
            var from = 0, hit: Int?
            while let m = memmem(h + from, hay.count - from, nb.baseAddress!, nlen) {
                hit = UnsafeRawPointer(m) - h + nlen
                if !last { break }
                from = hit!
            }
            return hit
        }
    }

    private static func field(_ line: UnsafeRawBufferPointer, _ key: String, last: Bool = false) -> String? {
        guard let start = find(line, key, last: last) else { return nil }
        var e = start
        while e < line.count, line[e] != UInt8(ascii: "\"") { e += 1 }
        return String(decoding: UnsafeRawBufferPointer(rebasing: line[start..<e]), as: UTF8.self)
    }

    private func ingest(_ line: UnsafeRawBufferPointer, weekStart ws: Double, folder: String) {
        guard let ur = Self.find(line, "\"usage\":{"),
              let tsS = Self.field(line, "\"timestamp\":\"", last: true),
              let ts = (isoFrac.date(from: tsS) ?? iso.date(from: tsS))?.timeIntervalSince1970, ts >= ws else { return }
        let open = ur - 1
        var depth = 0, close = open
        for i in open..<line.count {
            if line[i] == UInt8(ascii: "{") { depth += 1 } else if line[i] == UInt8(ascii: "}") { depth -= 1; if depth == 0 { close = i; break } }
        }
        let key = "\(Self.field(line, "\"id\":\"msg_") ?? "")|\(Self.field(line, "\"requestId\":\"") ?? "\(ts)")"
        guard close > open, seen.insert(key).inserted,
              let u = try? JSONSerialization.jsonObject(with: Data(UnsafeRawBufferPointer(rebasing: line[open...close]))) as? [String: Any] else { return }
        func n(_ k: String) -> Double { (u[k] as? NSNumber)?.doubleValue ?? 0 }
        let (i, o, cw, cr) = (n("input_tokens"), n("output_tokens"), n("cache_creation_input_tokens"), n("cache_read_input_tokens"))
        let model = Self.field(line, "\"model\":\"") ?? ""
        let p = Self.price(model)
        let project = Self.projectName(Self.field(line, "\"cwd\":\""), folder)
        events.append(Event(ts: ts, input: i, output: o, cw: cw, cr: cr,
                            cost: (i * p[0] + o * p[1] + cw * p[2] + cr * p[3]) / 1e6,
                            session: Self.field(line, "\"sessionId\":\"") ?? "",
                            model: Self.family(model), project: project))
    }

    private func scan() -> ClaudeStats {
        var cal = Calendar(identifier: .iso8601); cal.timeZone = .current          // weeks start Monday
        let now = Date()
        let ws = cal.dateInterval(of: .weekOfYear, for: now)?.start.timeIntervalSince1970 ?? 0
        if ws != weekStart { weekStart = ws; offsets = [:]; seen = []; events = [] }

        let base = ProcessInfo.processInfo.environment["CLAUDE_CONFIG_DIR"].map { URL(fileURLWithPath: $0) }
            ?? FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".claude")
        let root = base.appendingPathComponent("projects")
        let rootComps = root.standardizedFileURL.pathComponents
        let keys: [URLResourceKey] = [.contentModificationDateKey, .fileSizeKey]
        var live = 0
        let en = FileManager.default.enumerator(at: root, includingPropertiesForKeys: keys)
        while let url = en?.nextObject() as? URL {
            guard url.pathExtension == "jsonl", let rv = try? url.resourceValues(forKeys: Set(keys)),
                  let mod = rv.contentModificationDate, mod.timeIntervalSince1970 >= ws, let size = rv.fileSize else { continue }
            if now.timeIntervalSince(mod) < 300, !url.path.contains("/subagents/") { live += 1 }
            let off = offsets[url.path] ?? 0
            guard UInt64(size) > off, let fh = try? FileHandle(forReadingFrom: url) else { continue }
            defer { try? fh.close() }
            // the transcript's top-level folder under projects/ names the project when a line has no cwd
            let comps = url.standardizedFileURL.pathComponents
            let folder: String = comps.count > rootComps.count && Array(comps.prefix(rootComps.count)) == rootComps
                ? comps[rootComps.count] : url.deletingLastPathComponent().lastPathComponent
            try? fh.seek(toOffset: off)
            var consumed: UInt64 = 0, carry = Data()
            while true {                                   // stream in 4 MB chunks to keep memory flat
                let done: Bool = autoreleasepool {
                    guard let chunk = try? fh.read(upToCount: 4 << 20), !chunk.isEmpty else { return true }
                    var buf = carry; buf.append(chunk)
                    guard let lastNL = buf.lastIndex(of: 10) else { carry = buf; return false }
                    let n = lastNL - buf.startIndex + 1
                    buf.withUnsafeBytes { (raw: UnsafeRawBufferPointer) in
                        guard let base = raw.baseAddress else { return }
                        var p = base
                        let end = base + n
                        while p < end, let nl = memchr(p, 10, end - p) {
                            ingest(UnsafeRawBufferPointer(start: p, count: UnsafeRawPointer(nl) - p), weekStart: ws, folder: folder)
                            p = UnsafeRawPointer(nl) + 1
                        }
                    }
                    consumed += UInt64(n)
                    carry = Data(buf[(lastNL + 1)...])
                    return false
                }
                if done { break }
            }
            offsets[url.path] = off + consumed
        }

        readAccount()
        noteAccount(email)
        var st = ClaudeStats(); st.ready = true; st.live = live; st.calls = events.count
        st.email = email; st.plan = plan
        st.byModel = top { $0.model }
        st.byProject = top { $0.project }
        st.byAccount = top { self.accountAt($0.ts) }
        let dayStart = cal.startOfDay(for: now).timeIntervalSince1970
        var sessions = Set<String>()
        for e in events {
            let t = e.input + e.output + e.cw + e.cr
            st.week += t; st.input += e.input; st.output += e.output; st.cacheWrite += e.cw; st.cacheRead += e.cr
            st.cost += e.cost
            if e.ts >= dayStart { st.today += t }
            st.days[min(max(Int((e.ts - ws) / 86400), 0), 6)] += t
            sessions.insert(e.session)
        }
        st.sessions = sessions.count

        // 5-hour blocks: one opens at the hour of the first message after the last block ran out.
        var bStart = -Double.infinity, bTok = 0.0
        for (ts, t) in events.map({ ($0.ts, $0.input + $0.output + $0.cw + $0.cr) }).sorted(by: { $0.0 < $1.0 }) {
            if ts >= bStart + 5 * 3600 { bStart = (ts / 3600).rounded(.down) * 3600; bTok = 0 }
            bTok += t
        }
        if now.timeIntervalSince1970 < bStart + 5 * 3600 { st.block = bTok; st.blockEnd = bStart + 5 * 3600 }
        st.todayIndex = min(max(Int((dayStart - ws) / 86400 + 0.5), 0), 6)
        return st
    }
}

// MARK: - Plan limits (the same numbers as Claude Code's /usage)

/// How much of the plan's rolling limits is used (0–1), and when each window resets (unix s, 0 = no window open).
struct PlanLimits {
    var five: Double?
    var week: Double?
    var fiveReset = 0.0
    var weekReset = 0.0
    var ready = false
}

/// Reads the plan limits with the token Claude Code keeps in the login Keychain (or ~/.claude/.credentials.json).
/// Read-only: Pulse never refreshes the token, so an expired one just means "no data until Claude Code runs again".
enum LimitsProbe {
    static func credentialsFile() -> URL {
        let base = ProcessInfo.processInfo.environment["CLAUDE_CONFIG_DIR"].map { URL(fileURLWithPath: $0) }
            ?? FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".claude")
        return base.appendingPathComponent(".credentials.json")
    }

    /// The access token in a credentials blob, unless it has expired.
    static func token(from data: Data) -> String? {
        guard let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let o = root["claudeAiOauth"] as? [String: Any] else { return nil }
        if let exp = (o["expiresAt"] as? NSNumber)?.doubleValue, exp < Date().timeIntervalSince1970 * 1000 { return nil }
        return o["accessToken"] as? String
    }

    /// The Keychain item Claude Code writes on macOS, read through /usr/bin/security (already trusted by the item).
    static func keychain() -> Data? {
        let p = Process(), pipe = Pipe()
        p.executableURL = URL(fileURLWithPath: "/usr/bin/security")
        p.arguments = ["find-generic-password", "-s", "Claude Code-credentials", "-w"]
        p.standardOutput = pipe; p.standardError = FileHandle.nullDevice
        guard (try? p.run()) != nil else { return nil }
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        p.waitUntilExit()
        guard p.terminationStatus == 0 else { return nil }
        let s = String(decoding: data, as: UTF8.self).trimmingCharacters(in: .whitespacesAndNewlines)
        return s.isEmpty ? nil : Data(s.utf8)
    }

    static func currentToken() -> String? {
        if let d = keychain(), let t = token(from: d) { return t }
        if let d = try? Data(contentsOf: credentialsFile()) { return token(from: d) }
        return nil
    }

    static func parseDate(_ s: String) -> Double {
        let frac = ISO8601DateFormatter()
        frac.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let d = frac.date(from: s) { return d.timeIntervalSince1970 }
        let plain = ISO8601DateFormatter()
        if let d = plain.date(from: s) { return d.timeIntervalSince1970 }
        if let dot = s.firstIndex(of: ".") {                     // more fractional digits than the formatter takes
            let rest = s[s.index(after: dot)...]
            let end = rest.firstIndex(where: { !$0.isNumber }) ?? s.endIndex
            if let d = plain.date(from: String(s[..<dot]) + String(s[end...])) { return d.timeIntervalSince1970 }
        }
        return 0
    }

    static func window(_ root: [String: Any], _ name: String) -> (used: Double?, reset: Double) {
        guard let w = root[name] as? [String: Any] else { return (used: nil, reset: 0) }
        let used: Double? = (w["utilization"] as? NSNumber).map { $0.doubleValue / 100 }
        let reset: Double = (w["resets_at"] as? String).map { LimitsProbe.parseDate($0) } ?? 0
        return (used: used, reset: reset)
    }

    /// Calls back on the main queue; nil when signed out, offline, or the endpoint changed (callers keep the last reading).
    static func read(_ done: @escaping (PlanLimits?) -> Void) {
        DispatchQueue.global(qos: .utility).async {
            guard let tok = LimitsProbe.currentToken(), let url = URL(string: "https://api.anthropic.com/api/oauth/usage") else {
                DispatchQueue.main.async { done(nil) }
                return
            }
            var req = URLRequest(url: url, timeoutInterval: 10)
            req.setValue("Bearer \(tok)", forHTTPHeaderField: "Authorization")
            req.setValue("oauth-2025-04-20", forHTTPHeaderField: "anthropic-beta")
            req.setValue("Pulse", forHTTPHeaderField: "User-Agent")
            URLSession.shared.dataTask(with: req) { data, resp, _ in
                var parsed: PlanLimits?
                if let http = resp as? HTTPURLResponse, (200..<300).contains(http.statusCode), let data,
                   let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                    let f = LimitsProbe.window(root, "five_hour"), w = LimitsProbe.window(root, "seven_day")
                    parsed = PlanLimits(five: f.used, week: w.used, fiveReset: f.reset, weekReset: w.reset, ready: true)
                }
                let result = parsed
                DispatchQueue.main.async { done(result) }
            }.resume()
        }
    }
}

// MARK: - Sampler

enum TopMode { case cpu, mem }
struct TopProc { let name: String; let value: Double }

@MainActor
final class Sampler: ObservableObject {
    @Published var cpu = 0.0
    @Published var cores: [Double] = []
    @Published var memUsed = 0.0
    @Published var memTotal = 1.0
    @Published var diskUsed = 0.0
    @Published var diskTotal = 1.0
    @Published var cpuTemp: Double?
    @Published var maxTemp: Double?
    @Published var gpu: Double?
    @Published var netIn = 0.0
    @Published var netOut = 0.0
    @Published var swapUsed = 0.0
    @Published var swapTotal = 0.0
    @Published var battery: (pct: Int, charging: Bool, ac: Bool)?
    @Published var load = 0.0
    @Published var thermalState = ProcessInfo.ThermalState.nominal
    @Published var tick = false
    @Published var clock = ""
    @Published var hist: [String: [Double]] = [:]
    @Published var claude = ClaudeStats()
    @Published var limits = PlanLimits()
    @Published var top: [TopProc] = []
    @Published var topMode: TopMode? { didSet { top = []; refreshTop() } }
    /// Plan limits come from Anthropic's servers; everything else stays on this Mac.
    var limitsEnabled = true
    /// Called after every one-second sample (alerts, refitting the window).
    var onSample: (() -> Void)?
    private var topBusy = false
    let claudeUsage = ClaudeUsage()

    let perfCores = { var v: Int32 = 0; var s = 4; sysctlbyname("hw.perflevel0.logicalcpu", &v, &s, nil, 0); return Int(v) }()
    private let thermals = Thermals()
    private let probeQ = DispatchQueue(label: "pulse.probe", qos: .utility)
    private var timer: Timer?
    private var n = 0
    private var prevTicks: [[UInt32]] = []
    private var prevNet: [String: (UInt32, UInt32)] = [:]
    private var prevNetTime = Date()
    private var limitsBusy = false
    private var limitsAt = -Double.infinity
    private var limitsAccount: String?
    private let fmt: DateFormatter = { let f = DateFormatter(); f.dateFormat = "HH:mm"; return f }()

    init(start: Bool = true) {
        prevTicks = Probe.cpuTicks()
        prevNet = Probe.netCounters()
        sample()
        guard start else { return }
        timer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] _ in
            MainActor.assumeIsolated { self?.sample() }
        }
        timer?.tolerance = 0.2
    }

    func refreshTop() {
        guard let m = topMode, !topBusy else { return }
        if snapshotMode { top = Probe.top(m); return }
        topBusy = true
        probeQ.async {
            let r = Probe.top(m)
            DispatchQueue.main.async { [weak self] in
                guard let self else { return }
                topBusy = false
                if topMode == m { top = r }
            }
        }
    }

    private func push(_ key: String, _ v: Double) {
        var a = hist[key] ?? []; a.append(min(max(v, 0), 1)); if a.count > 40 { a.removeFirst() }; hist[key] = a
    }

    /// Plausible fake numbers for screenshots (--demo), so no real usage is published.
    func loadDemo() {
        var rng = SystemRandomNumberGenerator()
        func wave(_ i: Int, _ b: Double, _ a: Double) -> Double { min(max(b + a * sin(Double(i) / 4) + (Double.random(in: 0...1, using: &rng) - 0.5) * a, 0), 1) }
        hist = [:]
        for i in 0..<40 {
            push("cpu", wave(i, 0.32, 0.18)); push("mem", wave(i, 0.62, 0.03)); push("dsk", 0.58)
            push("tmp", wave(i, 0.27, 0.06)); push("gpu", wave(i, 0.2, 0.15)); push("net", wave(i, 0.6, 0.15))
        }
        cpu = 0.34; cores = [0.62, 0.48, 0.41, 0.35, 0.22, 0.18, 0.12, 0.08]
        memUsed = 10.4 * 1_073_741_824; memTotal = 16 * 1_073_741_824
        diskUsed = 287e9; diskTotal = 494e9
        cpuTemp = 48; maxTemp = 55; gpu = 0.21
        netIn = 1.84e6; netOut = 212e3
        swapUsed = 1.2e9; swapTotal = 2.1e9
        battery = (86, true, true); load = 2.4; clock = "09:41"
        let now = Date().timeIntervalSince1970
        var c = ClaudeStats()
        c.ready = true; c.week = 412.6e6; c.today = 58.3e6; c.block = 31.9e6; c.output = 2.41e6
        c.cost = 184.2; c.blockEnd = now + 2 * 3600 + 14 * 60 + 30
        c.input = 9.8e6; c.cacheRead = 400.4e6; c.sessions = 9; c.live = 1; c.calls = 3184; c.todayIndex = 3
        c.days = [88e6, 102e6, 164e6, 58.3e6, 0, 0, 0]
        c.email = "you@example.com"; c.plan = "Max"
        c.byModel = [UsageSlice(name: "OPUS", tokens: 301.2e6, cost: 151.0), UsageSlice(name: "SONNET", tokens: 96.4e6, cost: 30.1),
                     UsageSlice(name: "HAIKU", tokens: 15.0e6, cost: 3.1)]
        c.byProject = [UsageSlice(name: "pulse", tokens: 188.0e6, cost: 84.2), UsageSlice(name: "website", tokens: 131.5e6, cost: 58.9),
                       UsageSlice(name: "notes", tokens: 93.1e6, cost: 41.1)]
        c.byAccount = [UsageSlice(name: "you@example.com", tokens: 352.6e6, cost: 157.4), UsageSlice(name: "work@example.com", tokens: 60.0e6, cost: 26.8)]
        claude = c
        limits = PlanLimits(five: 0.34, week: 0.42, fiveReset: now + 2 * 3600 + 14 * 60, weekReset: now + 2 * 86400 + 3 * 3600, ready: true)
    }

    func sample() {
        tick.toggle()
        clock = fmt.string(from: Date())

        // CPU (per core, from tick deltas)
        let t = Probe.cpuTicks()
        if t.count == prevTicks.count, !t.isEmpty {
            var busyAll = 0.0, totAll = 0.0
            cores = zip(t, prevTicks).map { cur, prev in
                let d = (0..<cur.count).map { Double(cur[$0] &- prev[$0]) }
                let total = d.reduce(0, +)
                let busy = total - d[Int(CPU_STATE_IDLE)]
                busyAll += busy; totAll += total
                return total > 0 ? busy / total : 0
            }
            cpu = totAll > 0 ? busyAll / totAll : 0
        }
        prevTicks = t
        push("cpu", cpu)

        if let m = Probe.memory() { memUsed = m.used; memTotal = m.total }
        push("mem", memUsed / memTotal)

        if n % 5 == 0, let d = Probe.disk() { diskUsed = d.used; diskTotal = d.total }
        push("dsk", diskUsed / diskTotal)

        // Sensor + GPU queries block on IOKit round-trips, so they run off the main thread.
        if n % 3 == 0 {
            let readGPU = n % 2 == 0
            probeQ.async { [thermals] in
                let th = thermals.read(), g = readGPU ? Probe.gpu() : nil
                DispatchQueue.main.async { [weak self] in
                    guard let self else { return }
                    if let th { cpuTemp = th.cpu; maxTemp = th.max }
                    if readGPU { gpu = g }
                }
            }
        }
        if let c = cpuTemp { push("tmp", (c - 30) / 70) }
        push("gpu", gpu ?? 0)

        let net = Probe.netCounters(), now = Date()
        let dt = max(now.timeIntervalSince(prevNetTime), 0.1)
        var di: UInt64 = 0, dout: UInt64 = 0
        for (k, v) in net { if let p = prevNet[k] { di += UInt64(v.0 &- p.0); dout += UInt64(v.1 &- p.1) } }
        netIn = Double(di) / dt; netOut = Double(dout) / dt
        prevNet = net; prevNetTime = now
        push("net", log10(max(netIn, 1)) / 8)   // log scale up to ~100 MB/s

        if n % 5 == 0 { let s = Probe.swap(); swapUsed = s.used; swapTotal = s.total; load = Probe.load() }
        if n % 10 == 0 { battery = Probe.battery() }
        thermalState = ProcessInfo.processInfo.thermalState
        if n % 20 == 0 { claudeUsage.refresh { [weak self] in self?.claude = $0 } }

        // every 5 minutes, and straight away after a /login to another account
        let nowS = now.timeIntervalSince1970
        if limitsEnabled && !snapshotMode && !limitsBusy && claude.ready && (nowS - limitsAt > 300 || claude.email != limitsAccount) {
            limitsBusy = true
            limitsAt = nowS
            if claude.email != limitsAccount { limits = PlanLimits() }
            limitsAccount = claude.email
            LimitsProbe.read { [weak self] l in
                guard let self else { return }
                limitsBusy = false
                if let l, limitsEnabled { limits = l }
            }
        } else if !limitsEnabled && limits.ready {
            limits = PlanLimits()
        }

        if n % 2 == 0 { refreshTop() }
        n += 1
        onSample?()
    }
}

// MARK: - Formatting

enum F {
    static var now: Double { Date().timeIntervalSince1970 }
    static func pct(_ v: Double) -> String { "\(Int((v * 100).rounded()))%" }
    static func gib(_ b: Double) -> String { String(format: "%.1f", b / 1_073_741_824) }
    static func size(_ b: Double) -> String {
        b >= 1e12 ? String(format: "%.1fT", b / 1e12) : b >= 1e9 ? String(format: "%.0fG", b / 1e9) : String(format: "%.0fM", b / 1e6)
    }
    static func rate(_ b: Double) -> String {
        b >= 1e9 ? String(format: "%.1fG", b / 1e9) : b >= 1e6 ? String(format: "%.1fM", b / 1e6)
            : b >= 1e3 ? String(format: "%.0fK", b / 1e3) : String(format: "%.0fB", b)
    }
    static func tok(_ v: Double) -> String {
        v >= 1e9 ? String(format: "%.2fB", v / 1e9) : v >= 1e6 ? String(format: "%.1fM", v / 1e6)
            : v >= 1e3 ? String(format: "%.0fK", v / 1e3) : String(format: "%.0f", v)
    }
    static func usd(_ v: Double) -> String {
        v < 100 ? String(format: "$%.2f", v) : v < 10_000 ? String(format: "$%.0f", v) : String(format: "$%.1fK", v / 1e3)
    }
    static func mem(_ b: Double) -> String { b >= 1e9 ? String(format: "%.1fG", b / 1e9) : String(format: "%.0fM", b / 1e6) }
    static func countdown(_ s: Double) -> String {
        let m = Int((s / 60).rounded(.up)), h = m / 60
        return h > 0 ? "\(h)H \(m % 60)M" : "\(m)M"
    }
    /// Fixed decimals, no grouping (tooltips).
    static func dec(_ v: Double, _ digits: Int) -> String { String(format: "%.\(digits)f", v) }
    /// Grouped number with fixed decimals, like 412,600,000 (tooltips).
    static func num(_ v: Double, _ digits: Int) -> String {
        let f = NumberFormatter()
        f.numberStyle = .decimal
        f.minimumFractionDigits = digits
        f.maximumFractionDigits = digits
        return f.string(from: NSNumber(value: v)) ?? dec(v, digits)
    }
    /// Up to one decimal, trailing zero dropped (34 or 34.5).
    static func trim1(_ v: Double) -> String {
        let r = (v * 10).rounded() / 10
        return r == r.rounded() ? String(Int(r)) : String(format: "%.1f", r)
    }
    static func exact(_ tokens: Double) -> String { "\(num(tokens, 0)) tokens" }
    /// Local weekday and time of a unix timestamp, like "Fri 14:00".
    static func clock(_ unix: Double) -> String {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "EEE HH:mm"
        return f.string(from: Date(timeIntervalSince1970: unix))
    }
    /// Process names in the pixel font: reverse-DNS names keep their last part, unknown characters become spaces.
    static func procName(_ n: String) -> String {
        var s = n
        if s.filter({ $0 == "." }).count >= 2, let last = s.split(separator: ".").last { s = String(last) }
        return pixel(s, 20)
    }
    /// Text in the pixel font: unknown characters become spaces, anything past `limit` is cut.
    static func pixel(_ s: String, _ limit: Int) -> String {
        String(s.uppercased().map { glyphs[$0] != nil ? $0 : " " }.prefix(max(limit, 0)))
    }
    static func uptime() -> String {
        let s = Int(ProcessInfo.processInfo.systemUptime)
        let d = s / 86400, h = (s % 86400) / 3600, m = (s % 3600) / 60
        return d > 0 ? "UP \(d)D \(h)H" : "UP \(h)H \(m)M"
    }
    static func thermal(_ s: ProcessInfo.ThermalState) -> String {
        switch s { case .nominal: "NOMINAL"; case .fair: "FAIR"; case .serious: "SERIOUS"; case .critical: "CRITICAL"; @unknown default: "-" }
    }
}

// MARK: - Rows & tiles

let tween = Animation.easeOut(duration: 0.45)

/// Animation key that only changes when a bar gains or loses a segment.
func seg(_ v: Double, _ n: Int = 28) -> Int { Int(min(max(v, 0), 1) * Double(n) * 2) }

struct HeroRow<Meter: View>: View {
    let label: String
    let detail: String
    let value: Double                  // drives the big number
    let format: (Double) -> String
    let history: [Double]
    @ViewBuilder var meter: Meter
    @Environment(\.zoom) var z

    var body: some View {
        VStack(alignment: .leading, spacing: 8 * z) {
            HStack(alignment: .center, spacing: 10 * z) {
                VStack(alignment: .leading, spacing: 5 * z) {
                    PixelText(text: label, scale: 2)
                    PixelText(text: detail, scale: 1, color: Ink.dim)
                }
                Spacer(minLength: 0)
                Sparkline(data: history)
                PixelNumber(value: value, format: format, scale: 3)
                    .frame(width: 70 * z, alignment: .trailing)
            }
            meter
        }
    }
}

/// The three heaviest processes, shown under CPU or MEM after a click.
struct TopList: View {
    let items: [TopProc]
    let mode: TopMode
    @Environment(\.zoom) var z
    var body: some View {
        VStack(alignment: .leading, spacing: 6 * z) {
            ForEach(0..<3, id: \.self) { i in
                HStack(spacing: 8 * z) {
                    PixelText(text: "\(i + 1)", scale: 1, color: Ink.dim)
                    if i < items.count {
                        let p = items[i]
                        PixelText(text: F.procName(p.name), scale: 1, color: Ink.mid)
                        Spacer(minLength: 0)
                        PixelText(text: mode == .cpu ? "\(Int(p.value.rounded()))%" : F.mem(p.value), scale: 1)
                    } else {
                        PixelText(text: i == 0 ? "READING" : "-", scale: 1, color: Ink.off)
                        Spacer(minLength: 0)
                    }
                }
            }
        }
    }
}

struct Tile<Content: View>: View {
    let label: String
    @ViewBuilder var content: Content
    @Environment(\.zoom) var z
    var body: some View {
        VStack(alignment: .leading, spacing: 7 * z) {
            PixelText(text: label, scale: 1, color: Ink.dim)
            content
        }
        .padding(10 * z)
        .frame(maxWidth: .infinity, alignment: .leading)
        .overlay(Rectangle().strokeBorder(Ink.line, lineWidth: 1))
    }
}

// MARK: - Main view

/// Panel widths and the Landscape column, in unscaled points.
enum Metrics {
    static let fullW: CGFloat = 320, landW: CGFloat = 660, pad: CGFloat = 18
    static let inner: CGFloat = fullW - pad * 2                     // 284
    static let col: CGFloat = (landW - pad * 2 - 24) / 2            // 300
}

struct WidgetView: View {
    @ObservedObject var s: Sampler
    @ObservedObject var prefs: Prefs
    /// Set for the gallery's live previews: that view at half size, not interactive.
    var preview: WidgetSize? = nil

    var size: WidgetSize { preview ?? prefs.size }
    var z: CGFloat { preview == nil ? CGFloat(prefs.zoom) : 0.5 }
    var breakdownShown: Bool { size == .claude || prefs.claudeOpen }

    var body: some View {
        let t = s.cpuTemp ?? 0
        let hot = t >= 85 || s.thermalState == .serious || s.thermalState == .critical
        let mini = size == .mini
        let radius: CGFloat = (mini ? 10 : 14) * z
        Group {
            switch size {
            case .full: full(hot: hot).padding(Metrics.pad * z).frame(width: Metrics.fullW * z)
            case .landscape: landscape(hot: hot).padding(Metrics.pad * z).frame(width: Metrics.landW * z)
            case .claude: claudeOnly().padding(Metrics.pad * z).frame(width: Metrics.fullW * z)
            case .compact: compact(hot: hot).padding(Metrics.pad * z).frame(width: Metrics.fullW * z)
            case .mini: miniView(hot: hot)
            }
        }
        .background(Ink.bg)
        .overlay(CRTOverlay(sweep: !mini && preview == nil))
        .clipShape(RoundedRectangle(cornerRadius: radius, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: radius, style: .continuous).strokeBorder(Ink.on.opacity(0.16), lineWidth: 1))
        .contextMenu { if preview == nil { menu } }
        .environment(\.zoom, z)
    }

    @ViewBuilder var menu: some View {
        Picker("View", selection: Binding(get: { prefs.size }, set: { prefs.pickSize($0) })) {
            ForEach(WidgetSize.allCases, id: \.self) { Text($0.title).tag($0) }
        }
        Button("Choose View…") { prefs.actions?.openGallery() }
        Picker("Scale", selection: Binding(get: { nearestScale(prefs.zoom) }, set: { prefs.actions?.scaleTo($0) })) {
            ForEach(widgetScales, id: \.self) { v in Text(verbatim: "\(Int((v * 100).rounded()))%").tag(v) }
        }
        Picker("Opacity", selection: Binding(get: { prefs.opacity }, set: { prefs.actions?.setOpacity($0) })) {
            ForEach(widgetOpacities, id: \.self) { v in Text(verbatim: "\(Int((v * 100).rounded()))%").tag(v) }
        }
        Divider()
        Toggle("Always on Top", isOn: $prefs.onTop)
        Toggle("Click-through  ⌃⌥P", isOn: Binding(get: { prefs.clickThrough }, set: { prefs.actions?.setClickThrough($0) }))
        Toggle("Alerts", isOn: $prefs.alerts)
        Toggle("Plan Limits (online)", isOn: $prefs.limits)
        Toggle("Launch at Login", isOn: $prefs.launchAtLogin)
        Divider()
        Button("Open Activity Monitor") {
            NSWorkspace.shared.openApplication(at: URL(fileURLWithPath: "/System/Applications/Utilities/Activity Monitor.app"), configuration: .init())
        }
        Button("Hide Pulse") { prefs.actions?.toggleShown() }
        Button("Quit Pulse") { NSApp.terminate(nil) }
    }

    // ---------- exact values for the hover tooltips ----------

    var cpuTip: String { "CPU \(F.dec(s.cpu * 100, 1))% across \(s.cores.count) cores · load \(F.dec(s.load, 2))" }
    var memTip: String {
        "Memory \(F.dec(s.memUsed / 1_073_741_824, 2)) GB used of \(F.dec(s.memTotal / 1_073_741_824, 2)) GB (\(F.dec(s.memUsed / s.memTotal * 100, 1))%)"
    }
    var tempTip: String {
        guard let t = s.cpuTemp else { return "No temperature sensor found" }
        let peak: String = s.maxTemp.map { " · hottest sensor \(F.dec($0, 1))°C" } ?? ""
        return "Temperature \(F.dec(t, 1))°C" + peak
    }
    var diskTip: String { "Disk \(F.dec((s.diskTotal - s.diskUsed) / 1e9, 1)) GB free of \(F.dec(s.diskTotal / 1e9, 1)) GB" }
    var gpuTip: String { s.gpu.map { "GPU \(F.dec($0 * 100, 1))% busy" } ?? "No GPU counters" }
    var netTip: String { "Download \(F.num(s.netIn / 1e3, 1)) KB/s · upload \(F.num(s.netOut / 1e3, 1)) KB/s" }
    var swapTip: String {
        s.swapTotal > 0 ? "Swap \(F.dec(s.swapUsed / 1e9, 2)) GB used of \(F.dec(s.swapTotal / 1e9, 2)) GB" : "No swap in use"
    }
    var powerTip: String {
        guard let b = s.battery else { return "Mains power, no battery" }
        let state: String = b.charging ? "charging" : b.ac ? "plugged in" : "on battery"
        return "Battery \(b.pct)% · \(state)"
    }
    var headerTip: String { "\(size.title) view · click the header for the next one" }

    // ---------- shared pieces ----------

    var header: some View {
        HStack(spacing: 8 * z) {
            PixelText(text: "PULSE", scale: 2)
            HeaderScanner(hot: (s.cpuTemp ?? 0) >= 85)
            Spacer()
            PixelText(text: s.clock, scale: 1.5, color: Ink.mid)
            PixelText(text: size == .compact ? "+" : "-", scale: 1.5, color: Ink.dim)
        }
        .contentShape(Rectangle())
        .onTapGesture { prefs.pickSize(size.next) }
        .help(headerTip)
    }

    func footer(hot: Bool) -> some View {
        HStack {
            PixelText(text: "THERMAL \(F.thermal(s.thermalState))", scale: 1, color: hot ? Ink.on : Ink.dim)
            Spacer()
            PixelText(text: F.uptime(), scale: 1, color: Ink.dim)
        }
    }

    func tempState(_ t: Double) -> String {
        s.cpuTemp == nil ? "NO SENSOR" : t < 50 ? "COOL" : t < 70 ? "WARM" : t < 85 ? "HOT" : "CRITICAL"
    }

    // ---------- Full ----------

    @ViewBuilder func full(hot: Bool) -> some View {
        let memF = s.memUsed / s.memTotal, diskF = s.diskUsed / s.diskTotal
        let t = s.cpuTemp ?? 0, tempF = (t - 30) / 70
        VStack(alignment: .leading, spacing: 14 * z) {
            header
            DottedRule()
            HeroRow(label: "CPU", detail: "\(s.cores.count) CORES · LOAD \(String(format: "%.1f", s.load))",
                    value: s.cpu * 100, format: { "\(Int($0.rounded()))%" }, history: s.hist["cpu"] ?? []) {
                CoreGrid(cores: s.cores, perfCount: s.perfCores)
            }
            .contentShape(Rectangle())
            .onTapGesture { prefs.change { s.topMode = s.topMode == .cpu ? nil : .cpu } }
            .help(cpuTip)
            if s.topMode == .cpu { TopList(items: s.top, mode: .cpu) }
            DottedRule()
            HeroRow(label: "MEM", detail: "\(F.gib(s.memUsed)) / \(F.gib(s.memTotal)) GB",
                    value: memF * 100, format: { "\(Int($0.rounded()))%" }, history: s.hist["mem"] ?? []) {
                PixelBar(value: memF).animation(tween, value: seg(memF))
            }
            .contentShape(Rectangle())
            .onTapGesture { prefs.change { s.topMode = s.topMode == .mem ? nil : .mem } }
            .help(memTip)
            if s.topMode == .mem { TopList(items: s.top, mode: .mem) }
            DottedRule()
            HeroRow(label: "TMP", detail: s.maxTemp.map { "\(tempState(t)) · PEAK \(Int($0.rounded()))°" } ?? tempState(t),
                    value: t, format: { s.cpuTemp == nil ? "N/A" : "\(Int($0.rounded()))°" }, history: s.hist["tmp"] ?? []) {
                PixelBar(value: tempF, blink: hot && s.tick).animation(tween, value: seg(tempF))
            }
            .help(tempTip)
            DottedRule()
            HeroRow(label: "DSK", detail: "\(F.size(s.diskTotal - s.diskUsed)) FREE OF \(F.size(s.diskTotal))",
                    value: diskF * 100, format: { "\(Int($0.rounded()))%" }, history: s.hist["dsk"] ?? []) {
                PixelBar(value: diskF).animation(tween, value: seg(diskF))
            }
            .help(diskTip)
            tiles
            DottedRule()
            claudeSection(Metrics.inner)
            DottedRule()
            footer(hot: hot)
        }
    }

    var tiles: some View {
        Grid(horizontalSpacing: 8 * z, verticalSpacing: 8 * z) {
            GridRow {
                Tile(label: "GPU") {
                    PixelNumber(value: (s.gpu ?? 0) * 100, format: { s.gpu == nil ? "N/A" : "\(Int($0.rounded()))%" }, scale: 2)
                    PixelBar(value: s.gpu ?? 0, segments: 16, height: 5).animation(tween, value: seg(s.gpu ?? 0, 16))
                }
                .help(gpuTip)
                Tile(label: "NETWORK") {
                    PixelText(text: "↓\(F.rate(s.netIn))/S", scale: 2)
                    PixelText(text: "↑\(F.rate(s.netOut))/S", scale: 1, color: Ink.mid)
                }
                .help(netTip)
            }
            GridRow {
                Tile(label: "SWAP") {
                    PixelText(text: F.size(s.swapUsed), scale: 2)
                    PixelText(text: s.swapTotal > 0 ? "OF \(F.size(s.swapTotal))" : "NONE", scale: 1, color: Ink.mid)
                }
                .help(swapTip)
                Tile(label: "POWER") {
                    if let b = s.battery {
                        PixelText(text: "\(b.pct)%", scale: 2)
                        PixelText(text: b.charging ? "⚡ CHARGING" : b.ac ? "AC POWER" : "ON BATTERY", scale: 1, color: Ink.mid)
                    } else {
                        PixelText(text: "AC", scale: 2)
                        PixelText(text: "NO BATTERY", scale: 1, color: Ink.mid)
                    }
                }
                .help(powerTip)
            }
        }
    }

    // ---------- Landscape: system on the left, Claude on the right ----------

    @ViewBuilder func landscape(hot: Bool) -> some View {
        let t = s.cpuTemp ?? 0
        let memF = s.memUsed / s.memTotal, diskF = s.diskUsed / s.diskTotal
        let tDetail: String = s.maxTemp.map { "\(tempState(t)) · PEAK \(Int($0.rounded()))°" } ?? tempState(t)
        let rows: [(String, String, String, Double, Bool, String)] = [
            ("CPU", "\(s.cores.count) CORES · LOAD \(String(format: "%.1f", s.load))", F.pct(s.cpu), s.cpu, false, cpuTip),
            ("MEM", "\(F.gib(s.memUsed)) / \(F.gib(s.memTotal)) GB", F.pct(memF), memF, false, memTip),
            ("TMP", tDetail, s.cpuTemp == nil ? "N/A" : "\(Int(t.rounded()))°", (t - 30) / 70, hot && s.tick, tempTip),
            ("DSK", "\(F.size(s.diskTotal - s.diskUsed)) FREE", F.pct(diskF), diskF, false, diskTip),
        ]
        let small: [(String, String, String)] = [
            ("GPU", s.gpu.map { F.pct($0) } ?? "N/A", gpuTip),
            ("NETWORK", "↓\(F.rate(s.netIn))/S", netTip),
            ("POWER", s.battery.map { "\($0.pct)%" } ?? "AC", powerTip),
        ]
        let smallW = (Metrics.col - 16) / 3 * z
        VStack(alignment: .leading, spacing: 14 * z) {
            header
            DottedRule()
            HStack(alignment: .top, spacing: 0) {
                VStack(alignment: .leading, spacing: 16 * z) {
                    ForEach(rows, id: \.0) { r in
                        VStack(alignment: .leading, spacing: 7 * z) {
                            HStack(alignment: .center, spacing: 0) {
                                PixelText(text: r.0, scale: 2).frame(width: 46 * z, alignment: .leading)
                                PixelText(text: r.1, scale: 1, color: Ink.dim)
                                Spacer(minLength: 0)
                                PixelText(text: r.2, scale: 2)
                            }
                            PixelBar(value: r.3, segments: 28, height: 5, blink: r.4).animation(tween, value: seg(r.3))
                        }
                        .help(r.5)
                    }
                    HStack(alignment: .top, spacing: 8 * z) {
                        ForEach(small, id: \.0) { m in
                            VStack(alignment: .leading, spacing: 5 * z) {
                                PixelText(text: m.0, scale: 1, color: Ink.dim)
                                PixelText(text: m.1, scale: 1.5)
                            }
                            .frame(width: smallW, alignment: .leading)
                            .help(m.2)
                        }
                    }
                }
                .frame(width: Metrics.col * z, alignment: .leading)
                VerticalRule().frame(width: 24 * z)
                claudeSection(Metrics.col).frame(width: Metrics.col * z, alignment: .leading)
            }
            .fixedSize(horizontal: false, vertical: true)
            DottedRule()
            footer(hot: hot)
        }
    }

    // ---------- Claude: the account, limits, this week and where the tokens went ----------

    @ViewBuilder func claudeOnly() -> some View {
        VStack(alignment: .leading, spacing: 14 * z) {
            header
            DottedRule()
            claudeSection(Metrics.inner)
            DottedRule()
            HStack {
                PixelText(text: "\(s.claude.calls) CALLS · \(s.claude.sessions) SESSIONS", scale: 1, color: Ink.dim)
                Spacer()
                PixelText(text: F.uptime(), scale: 1, color: Ink.dim)
            }
        }
    }

    func claudeSection(_ w: CGFloat) -> some View {
        let c = s.claude, l = s.limits
        let left = max(c.blockEnd - F.now, 0)
        let letters = Array("MTWTFSS")
        let daysTip: String = (0..<7).map { "\(letters[$0]) \(F.tok(c.days[$0]))" }.joined(separator: " · ")
        let toggleTip: String = size == .claude ? "" : prefs.claudeOpen ? "Click to hide the breakdown" : "Click for tokens by model, project and account"
        let liveTip: String = "\(c.live) session\(c.live == 1 ? "" : "s") active in the last 5 minutes"
        let weekTip: String = "\(F.exact(c.week)) this week (all accounts on this Mac)"
        let ioTip: String = "Input \(F.num(c.input + c.cacheWrite, 0)) · output \(F.num(c.output, 0)) · cache reads \(F.num(c.cacheRead, 0)) · \(F.num(Double(c.calls), 0)) API calls"
        let blockTip: String = left > 0 ? "Local 5-hour block ends \(F.clock(c.blockEnd))" : ""
        let stats: [(String, String, String)] = [
            ("TODAY", F.tok(c.today), "\(F.exact(c.today)) today"),
            ("5H BLOCK", F.tok(left > 0 ? c.block : 0), left > 0 ? "\(F.exact(c.block)) in the current 5-hour block" : "No 5-hour block open"),
            ("EST. COST", F.usd(c.cost), "$\(F.num(c.cost, 2)) at API list prices (plans are billed differently)"),
            ("SESSIONS", "\(c.sessions)", "\(c.sessions) sessions this week"),
        ]
        let canToggle = size == .full || size == .landscape
        let showLimits = l.ready && (l.five != nil || l.week != nil)
        return VStack(alignment: .leading, spacing: 12 * z) {
            HStack(spacing: 6 * z) {
                PixelText(text: "CLAUDE CODE", scale: 2).help(toggleTip)
                Spacer()
                if c.live > 0 {
                    HStack(spacing: 6 * z) {
                        LivePip()
                        PixelText(text: "\(c.live) LIVE", scale: 1, color: Ink.mid)
                    }
                    .help(liveTip)
                } else {
                    PixelText(text: c.ready ? "IDLE" : "SCANNING", scale: 1, color: Ink.dim)
                }
            }
            if let email = c.email {
                let plan: String = c.plan.map { F.pixel($0, 12).trimmingCharacters(in: .whitespaces) } ?? ""
                let planW: CGFloat = plan.isEmpty ? 0 : PixelText.width(plan, 1) + 12
                let planNote: String = c.plan.map { " · \($0) plan" } ?? ""
                let signTip: String = "Signed in as \(email)" + planNote + " · follows /login"
                HStack(spacing: 0) {
                    PixelText(text: F.pixel(email, Int((w - planW) / 6)), scale: 1, color: Ink.mid)
                    Spacer(minLength: 0)
                    if plan == "ULTRA" {
                        RainbowText(text: plan)
                    } else if !plan.isEmpty {
                        PixelText(text: plan, scale: 1, color: Ink.dim)
                    }
                }
                .help(signTip)
            }
            HStack(alignment: .bottom, spacing: 16 * z) {
                VStack(alignment: .leading, spacing: 6 * z) {
                    PixelNumber(value: c.week, format: F.tok, scale: 3).animation(.easeOut(duration: 1.2), value: c.week)
                    PixelText(text: "TOKENS THIS WEEK", scale: 1, color: Ink.dim)
                }
                .help(weekTip)
                Spacer(minLength: 0)
                WeekChart(days: c.days, today: c.todayIndex).frame(width: 112 * z).help(daysTip)
            }
            HStack(alignment: .top, spacing: 8 * z) {
                ForEach(stats, id: \.0) { st in Stat(label: st.0, value: st.1).help(st.2) }
            }
            if showLimits {
                VStack(alignment: .leading, spacing: 9 * z) {
                    if let five = l.five { limitRow("5H LIMIT", five, l.fiveReset, "5-hour limit", w) }
                    if let wk = l.week { limitRow("WEEK LIMIT", wk, l.weekReset, "Weekly limit", w) }
                }
            }
            HStack {
                PixelText(text: "IN \(F.tok(c.input + c.cacheWrite)) · OUT \(F.tok(c.output)) · CACHED \(F.tok(c.cacheRead))", scale: 1, color: Ink.dim)
                Spacer()
                PixelText(text: "\(c.calls) CALLS", scale: 1, color: Ink.dim)
            }
            .help(ioTip)
            HStack(spacing: 10 * z) {
                PixelText(text: left > 0 ? "RESETS IN \(F.countdown(left))" : "NO 5H BLOCK OPEN", scale: 1, color: left > 0 ? Ink.mid : Ink.dim)
                Spacer(minLength: 0)
                PixelBar(value: left > 0 ? 1 - left / (5 * 3600) : 0, segments: 20, height: 3).frame(width: 118 * z)
            }
            .help(blockTip)
            if breakdownShown { breakdown(w) }
        }
        .contentShape(Rectangle())
        .onTapGesture { if canToggle { prefs.change { prefs.claudeOpen.toggle() } } }
    }

    func limitRow(_ label: String, _ used: Double, _ reset: Double, _ name: String, _ w: CGFloat) -> some View {
        let when: String = reset > 0 ? " · resets \(F.clock(reset))" : " · no window open"
        let tip: String = "\(name) \(F.trim1(used * 100))% used" + when
        return HStack(spacing: 0) {
            PixelText(text: label, scale: 1, color: Ink.dim).frame(width: 66 * z, alignment: .leading)
            PixelBar(value: used, segments: 24, height: 5).animation(tween, value: seg(used, 24))
                .frame(width: max(w - 66 - 30 - 8, 10) * z)
            Spacer(minLength: 0)
            PixelText(text: F.pct(used), scale: 1, color: used >= 0.9 ? Ink.on : Ink.mid)
        }
        .help(tip)
    }

    /// Where this week's tokens went: top three models, projects and accounts.
    func breakdown(_ w: CGFloat) -> some View {
        let c = s.claude
        let total = max(c.week, 1)
        let groups: [(String, [UsageSlice])] = [("BY MODEL", c.byModel), ("BY PROJECT", c.byProject), ("BY ACCOUNT", c.byAccount)]
        return VStack(alignment: .leading, spacing: 10 * z) {
            ForEach(groups, id: \.0) { g in
                VStack(alignment: .leading, spacing: 8 * z) {
                    DottedRule()
                    PixelText(text: g.0, scale: 1, color: Ink.dim).padding(.top, 2 * z)
                    if g.1.isEmpty {
                        PixelText(text: "-", scale: 1, color: Ink.off)
                    } else {
                        ForEach(0..<min(3, g.1.count), id: \.self) { i in sliceRow(g.1[i], total, w) }
                        if g.1.count > 3 {
                            PixelText(text: "+\(g.1.count - 3) MORE", scale: 1, color: Ink.dim)
                        }
                    }
                }
            }
        }
        .padding(.top, 2 * z)
    }

    func sliceRow(_ it: UsageSlice, _ total: Double, _ w: CGFloat) -> some View {
        let amount: String = "\(F.tok(it.tokens)) · \(Int((it.tokens / total * 100).rounded()))%"
        let chars = Int((w - PixelText.width(amount, 1) - 12) / 6)
        let tip: String = "\(it.name): \(F.exact(it.tokens)) · $\(F.num(it.cost, 2)) est."
        return VStack(alignment: .leading, spacing: 4 * z) {
            HStack(spacing: 0) {
                PixelText(text: F.pixel(it.name, chars), scale: 1, color: Ink.mid)
                Spacer(minLength: 0)
                PixelText(text: amount, scale: 1)
            }
            PixelBar(value: it.tokens / total, segments: 28, height: 2)
        }
        .help(tip)
    }

    // ---------- Mini: one quiet line, no scanner, no sweep; only a running-hot temperature blinks ----------

    func miniView(hot: Bool) -> some View {
        let t = s.cpuTemp ?? 0
        let items: [(String, String, Bool, String)] = [
            ("CPU", F.pct(s.cpu), false, cpuTip),
            ("MEM", F.pct(s.memUsed / s.memTotal), false, memTip),
            ("TMP", s.cpuTemp == nil ? "N/A" : "\(Int(t.rounded()))°", hot, tempTip),
        ]
        return HStack(spacing: 12 * z) {
            Rectangle().fill(Ink.on.opacity(0.85)).frame(width: 4 * z, height: 4 * z)
            ForEach(items, id: \.0) { it in
                HStack(spacing: 5 * z) {
                    PixelText(text: it.0, scale: 1, color: Ink.dim)
                    PixelText(text: it.1, scale: 1.5, color: it.2 && s.tick ? Ink.off : Ink.on)
                        .frame(width: PixelText.width("100%", 1.5) * z, alignment: .trailing)   // fixed: digits never shift the window
                }
                .help(it.3)
            }
        }
        .padding(.horizontal, 12 * z)
        .padding(.vertical, 9 * z)
        .contentShape(Rectangle())
        .onTapGesture { prefs.pickSize(size.next) }
    }

    // ---------- Compact: the four big numbers ----------

    @ViewBuilder func compact(hot: Bool) -> some View {
        let t = s.cpuTemp ?? 0
        let items: [(String, Double, Double, String, String)] = [
            ("CPU", s.cpu, s.cpu * 100, "%", cpuTip),
            ("MEM", s.memUsed / s.memTotal, s.memUsed / s.memTotal * 100, "%", memTip),
            ("TMP", (t - 30) / 70, t, "°", tempTip),
            ("DSK", s.diskUsed / s.diskTotal, s.diskUsed / s.diskTotal * 100, "%", diskTip),
        ]
        let c = s.claude, l = s.limits
        let left = c.blockEnd - F.now
        let parts: [String] = [l.five.map { "5H \(F.pct($0))" }, l.week.map { "WK \(F.pct($0))" }].compactMap { $0 }
        let limitText: String = parts.joined(separator: " · ")
        let rightText: String = !limitText.isEmpty ? limitText : left > 0 ? "RESETS \(F.countdown(left))" : "TODAY \(F.tok(c.today))"
        let claudeTip: String = "\(F.exact(c.week)) this week · $\(F.num(c.cost, 2)) at API list prices"
        let limitTip: String = limitText.isEmpty ? "" : "Plan limits used: " + limitText.replacingOccurrences(of: "WK", with: "week")
        VStack(alignment: .leading, spacing: 12 * z) {
            header
            DottedRule()
            HStack(alignment: .top, spacing: 12 * z) {
                ForEach(items, id: \.0) { it in
                    VStack(alignment: .leading, spacing: 6 * z) {
                        PixelText(text: it.0, scale: 1, color: Ink.dim)
                        PixelNumber(value: it.2, format: { "\(Int($0.rounded()))\(it.3)" }, scale: 2)
                        PixelBar(value: it.1, segments: 8, height: 4, blink: it.0 == "TMP" && hot && s.tick)
                            .animation(tween, value: seg(it.1, 8))
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .help(it.4)
                }
            }
            DottedRule()
            HStack(spacing: 6 * z) {
                if c.live > 0 { LivePip() }
                PixelText(text: "CLAUDE \(F.tok(c.week)) · ~\(F.usd(c.cost))", scale: 1, color: Ink.mid).help(claudeTip)
                Spacer()
                PixelText(text: rightText, scale: 1, color: Ink.dim).help(limitTip)
            }
        }
    }
}

// MARK: - View gallery ("Choose View…")

/// Every view, live and at half size, the way you'd pick a phone widget. Click one to switch; Esc or a click elsewhere closes.
struct GalleryView: View {
    @ObservedObject var s: Sampler
    @ObservedObject var prefs: Prefs
    let current: WidgetSize
    let pick: (WidgetSize) -> Void
    @State var shown = false

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .center, spacing: 0) {
                PixelText(text: "CHOOSE A VIEW", scale: 2)
                Spacer(minLength: 16)
                PixelText(text: "ESC TO CLOSE", scale: 1, color: Ink.dim)
            }
            .padding(.horizontal, 8)
            // Full and Claude stand tall on the left; the wide and short views stack on the right.
            HStack(alignment: .top, spacing: 0) {
                tile(.full)
                tile(.claude)
                VStack(alignment: .leading, spacing: 0) {
                    tile(.landscape)
                    tile(.compact)
                    tile(.mini)
                }
            }
        }
        .padding(EdgeInsets(top: 18, leading: 16, bottom: 12, trailing: 16))
        .background(Ink.bg)
        .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).strokeBorder(Ink.on.opacity(0.16), lineWidth: 1))
        .scaleEffect(shown || reduceMotion ? 1 : 0.97)
        .onAppear { withAnimation(.easeOut(duration: 0.22)) { shown = true } }
    }

    func tile(_ size: WidgetSize) -> GalleryTile {
        GalleryTile(s: s, prefs: prefs, size: size, current: size == current, pick: pick)
    }
}

struct GalleryTile: View {
    @ObservedObject var s: Sampler
    @ObservedObject var prefs: Prefs
    let size: WidgetSize
    let current: Bool
    let pick: (WidgetSize) -> Void
    @State var hover = false

    var body: some View {
        let border: Color = current ? Ink.mid : hover ? Ink.line : Color.clear
        VStack(alignment: .leading, spacing: 8) {
            WidgetView(s: s, prefs: prefs, preview: size)
                .allowsHitTesting(false)
                .padding(4)
                .overlay(RoundedRectangle(cornerRadius: 11, style: .continuous).strokeBorder(border, lineWidth: 1.5))
                .scaleEffect(hover && !reduceMotion ? 1.025 : 1)
                .animation(.easeOut(duration: 0.14), value: hover)
            PixelText(text: size.title, scale: 1, color: current ? Ink.on : Ink.dim).padding(.leading, 6)
        }
        .padding(8)
        .contentShape(Rectangle())
        .onHover { hover = $0 }
        .onTapGesture { pick(size) }
    }
}

final class GalleryPanel: NSPanel {
    override var canBecomeKey: Bool { true }
}

@MainActor
final class Gallery: NSObject, NSWindowDelegate {
    let panel: GalleryPanel
    var onClose: (() -> Void)?
    let pick: (WidgetSize) -> Void
    var keyMonitor: Any?
    var closing = false

    init(sampler: Sampler, prefs: Prefs, current: WidgetSize, screen: NSScreen?, pick: @escaping (WidgetSize) -> Void) {
        self.pick = pick
        panel = GalleryPanel(contentRect: NSRect(x: 0, y: 0, width: 100, height: 100), styleMask: [.borderless], backing: .buffered, defer: false)
        super.init()
        let content = GalleryView(s: sampler, prefs: prefs, current: current, pick: { [weak self] size in self?.choose(size) })
        let view = NSHostingView(rootView: content)
        let size = view.fittingSize
        view.frame = NSRect(origin: .zero, size: size)
        panel.contentView = view
        panel.setContentSize(size)
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.hasShadow = true
        panel.isReleasedWhenClosed = false
        panel.hidesOnDeactivate = false
        panel.level = NSWindow.Level(rawValue: NSWindow.Level.floating.rawValue + 1)
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        panel.delegate = self
        if let wa = (screen ?? NSScreen.main)?.visibleFrame {
            panel.setFrameOrigin(NSPoint(x: (wa.midX - size.width / 2).rounded(), y: (wa.midY - size.height / 2).rounded()))
        }
    }

    func show() {
        panel.alphaValue = 0
        NSApp.activate(ignoringOtherApps: true)
        panel.makeKeyAndOrderFront(nil)
        keyMonitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] e in
            if e.keyCode == 53 { self?.dismiss(); return nil }            // Esc
            return e
        }
        if reduceMotion { panel.alphaValue = 1; return }
        NSAnimationContext.runAnimationGroup { ctx in
            ctx.duration = 0.18
            ctx.timingFunction = AppDelegate.ease
            self.panel.animator().alphaValue = 1
        }
    }

    func windowDidResignKey(_ notification: Notification) { dismiss() }   // a click anywhere else closes it

    func choose(_ size: WidgetSize) {
        dismiss()
        pick(size)
    }

    func dismiss() {
        guard !closing else { return }
        closing = true
        if let m = keyMonitor { NSEvent.removeMonitor(m); keyMonitor = nil }
        let finish: () -> Void = { [weak self] in
            guard let self else { return }
            self.panel.orderOut(nil)
            self.onClose?()
        }
        if reduceMotion { finish(); return }
        NSAnimationContext.runAnimationGroup({ ctx in
            ctx.duration = 0.12
            self.panel.animator().alphaValue = 0
        }, completionHandler: {
            MainActor.assumeIsolated { finish() }
        })
    }
}

// MARK: - Alerts

/// Decides when something is worth a notification: a sustained hot CPU or full memory, the 5-hour block
/// resetting, and plan limits crossing 80% and 95%. Each fires once, then waits out a cooldown.
@MainActor
final class Alerts {
    let sustain = 30.0, cooldown = 15.0 * 60
    let notify: (String, String) -> Void
    var lastFired: [String: Double] = [:]
    var limitsFired = Set<String>()
    var hotSince = -1.0, memSince = -1.0, openBlockEnd = 0.0

    init(notify: @escaping (String, String) -> Void) { self.notify = notify }

    func fire(_ key: String, _ title: String, _ text: String, _ now: Double) {
        if let t = lastFired[key], now - t < cooldown { return }
        lastFired[key] = now
        notify(title, text)
    }

    static func held(_ on: Bool, _ since: inout Double, _ now: Double, _ sustain: Double) -> Bool {
        if !on { since = -1; return false }
        if since < 0 { since = now }
        return now - since >= sustain
    }

    func check(_ s: Sampler, enabled: Bool) {
        guard enabled else { return }
        let now = F.now

        let temp = s.cpuTemp ?? 0
        if Alerts.held(temp >= 85, &hotSince, now, sustain) {
            fire("hot", "Running hot", "\(Int(temp.rounded()))°C for over \(Int(sustain)) seconds.", now)
        }

        let mem = s.memUsed / s.memTotal
        if Alerts.held(mem >= 0.92, &memSince, now, sustain) {
            fire("mem", "Memory almost full", "\(Int((mem * 100).rounded()))% of \(F.gib(s.memTotal)) GB in use.", now)
        }

        let c = s.claude
        if c.ready {
            if c.blockEnd > now { openBlockEnd = c.blockEnd }
            else if openBlockEnd > 0 && now >= openBlockEnd {
                openBlockEnd = 0
                fire("block", "5-hour block reset", "Your Claude Code 5-hour block has ended — a fresh one starts with your next message.", now)
            }
        }

        let l = s.limits
        guard l.ready else { return }
        let windows: [(String, Double?, Double)] = [("5-hour limit", l.five, l.fiveReset), ("Weekly limit", l.week, l.weekReset)]
        for (name, used, reset) in windows {
            guard let u = used else { continue }
            for mark in [0.95, 0.8] where u >= mark {
                if limitsFired.insert("\(name)|\(mark)|\(Int(reset))").inserted {
                    let when: String = reset > 0 ? " Resets \(F.clock(reset))." : ""
                    let who: String = c.email ?? "Your account"
                    notify("\(name) \(Int((u * 100).rounded()))% used", "\(who) is past \(Int((mark * 100).rounded()))% of its \(name.lowercased()).\(when)")
                }
                break                                           // one notice per crossing, not both marks at once
            }
        }
    }
}

/// Posts notifications through the Notification Center when the app is allowed to; an ad-hoc signed build
/// often isn't, so it falls back to `osascript -e 'display notification …'`.
final class Notifier {
    private var useCenter = false

    init() {
        guard !snapshotMode, Bundle.main.bundleURL.pathExtension == "app", Bundle.main.bundleIdentifier != nil else { return }
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) { [weak self] ok, _ in
            DispatchQueue.main.async { self?.useCenter = ok }
        }
    }

    func post(_ title: String, _ body: String) {
        guard useCenter else { Notifier.script(title, body); return }
        let content = UNMutableNotificationContent()
        content.title = title
        content.body = body
        let req = UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: nil)
        UNUserNotificationCenter.current().add(req) { err in
            if err != nil { Notifier.script(title, body) }
        }
    }

    static func script(_ title: String, _ body: String) {
        func quoted(_ s: String) -> String {
            "\"" + s.replacingOccurrences(of: "\\", with: "\\\\").replacingOccurrences(of: "\"", with: "\\\"") + "\""
        }
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/bin/osascript")
        p.arguments = ["-e", "display notification \(quoted(body)) with title \(quoted(title))"]
        p.standardOutput = FileHandle.nullDevice
        p.standardError = FileHandle.nullDevice
        try? p.run()
    }
}

// MARK: - Global hotkey (⌃⌥P toggles click-through — the way back when the widget ignores the mouse)

final class HotKey {
    private var ref: EventHotKeyRef?
    private var handler: EventHandlerRef?
    let action: () -> Void

    init(action: @escaping () -> Void) {
        self.action = action
        var spec = EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed))
        InstallEventHandler(GetApplicationEventTarget(), { _, _, user in
            guard let user else { return OSStatus(noErr) }
            let hk = Unmanaged<HotKey>.fromOpaque(user).takeUnretainedValue()
            DispatchQueue.main.async { hk.action() }
            return OSStatus(noErr)
        }, 1, &spec, Unmanaged.passUnretained(self).toOpaque(), &handler)
        let id = EventHotKeyID(signature: OSType(0x50554C53), id: 1)          // 'PULS'
        RegisterEventHotKey(UInt32(kVK_ANSI_P), UInt32(controlKey | optionKey), id, GetApplicationEventTarget(), 0, &ref)
    }

    deinit {
        if let ref { UnregisterEventHotKey(ref) }
        if let handler { RemoveEventHandler(handler) }
    }
}

// MARK: - Prefs

/// Five views, cycled by clicking the header: everything → side by side → Claude only → the four big numbers → one quiet line.
enum WidgetSize: String, CaseIterable {
    case full, landscape, claude, compact, mini
    var next: WidgetSize {
        let all = WidgetSize.allCases
        let i = all.firstIndex(of: self) ?? 0
        return all[(i + 1) % all.count]
    }
    var title: String {
        switch self {
        case .full: return "Full"
        case .landscape: return "Landscape"
        case .claude: return "Claude"
        case .compact: return "Compact"
        case .mini: return "Mini"
        }
    }
}

/// Snap points for scaling.
let widgetScales: [Double] = [1, 1.25, 1.5, 1.75, 2]
let widgetOpacities: [Double] = [1, 0.85, 0.7, 0.5]

func nearestScale(_ v: Double) -> Double {
    var best = widgetScales[0]
    for s in widgetScales where abs(s - v) < abs(best - v) { best = s }
    return best
}

/// What the views ask the window to do (morphing, hopping between saved spots, the gallery…).
@MainActor
protocol WidgetActions: AnyObject {
    func setSize(_ size: WidgetSize)
    func morph(_ change: @escaping () -> Void)
    func scaleTo(_ scale: Double)
    func setOpacity(_ opacity: Double)
    func setClickThrough(_ on: Bool)
    func openGallery()
    func toggleShown()
}

@MainActor
final class Prefs: ObservableObject {
    private let persist: Bool
    @Published var onTop: Bool { didSet { store(onTop, "onTop"); apply?() } }
    @Published var size: WidgetSize { didSet { store(size.rawValue, "size") } }
    /// The scale on screen; saved by `saveScale()` so a live resize doesn't write every step.
    @Published var zoom: Double
    @Published var opacity: Double { didSet { store(opacity, "opacity") } }
    @Published var alerts: Bool { didSet { store(alerts, "alerts"); apply?() } }
    @Published var limits: Bool { didSet { store(limits, "limits"); apply?() } }
    @Published var claudeOpen: Bool { didSet { store(claudeOpen, "claudeOpen") } }
    @Published var clickThrough = false
    @Published var launchAtLogin: Bool {
        didSet {
            do { launchAtLogin ? try SMAppService.mainApp.register() : try SMAppService.mainApp.unregister() }
            catch { NSLog("Pulse login item: \(error)") }
        }
    }
    private(set) var savedScale: Double
    var apply: (() -> Void)?
    weak var actions: (any WidgetActions)?

    init(persist: Bool = true) {
        self.persist = persist
        let d = UserDefaults.standard
        onTop = d.object(forKey: "onTop") as? Bool ?? true
        size = d.string(forKey: "size").flatMap(WidgetSize.init) ?? (d.bool(forKey: "compact") ? .compact : .full)
        let sc = nearestScale(d.object(forKey: "scale") as? Double ?? 1)
        zoom = sc
        savedScale = sc
        let op = d.object(forKey: "opacity") as? Double ?? 1
        opacity = widgetOpacities.contains(op) ? op : 1
        alerts = d.object(forKey: "alerts") as? Bool ?? true
        limits = d.object(forKey: "limits") as? Bool ?? true
        claudeOpen = d.bool(forKey: "claudeOpen")
        launchAtLogin = SMAppService.mainApp.status == .enabled
    }

    private func store(_ value: Any, _ key: String) {
        if persist { UserDefaults.standard.set(value, forKey: key) }
    }

    func saveScale() {
        savedScale = zoom
        store(zoom, "scale")
    }

    /// Where each view lives, keyed by screen arrangement and view: [left, top] in screen coordinates.
    var positions: [String: [Double]] {
        get { UserDefaults.standard.dictionary(forKey: "positions") as? [String: [Double]] ?? [:] }
        set { store(newValue, "positions") }
    }

    func pickSize(_ s: WidgetSize) {
        if let a = actions { a.setSize(s) } else { size = s }
    }

    /// A change that alters the widget's size: the window morphs to the new shape.
    func change(_ body: @escaping () -> Void) {
        if let a = actions { a.morph(body) } else { body() }
    }
}

// MARK: - App

final class Panel: NSPanel {
    override var canBecomeKey: Bool { true }
}

final class FlippedView: NSView {
    override var isFlipped: Bool { true }
}

/// The bottom corner away from the anchored screen edge: drag it to scale the widget.
final class GripView: NSView {
    var began: (() -> Void)?
    var moved: (() -> Void)?
    var ended: (() -> Void)?
    override var mouseDownCanMoveWindow: Bool { false }
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
    override func updateTrackingAreas() {
        super.updateTrackingAreas()
        for t in trackingAreas { removeTrackingArea(t) }
        addTrackingArea(NSTrackingArea(rect: bounds, options: [.mouseEnteredAndExited, .activeAlways, .inVisibleRect], owner: self, userInfo: nil))
    }
    override func mouseEntered(with event: NSEvent) { NSCursor.crosshair.set() }
    override func mouseExited(with event: NSEvent) { NSCursor.arrow.set() }
    override func mouseDown(with event: NSEvent) { began?() }
    override func mouseDragged(with event: NSEvent) { moved?() }
    override func mouseUp(with event: NSEvent) { ended?() }
}

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate, NSMenuDelegate, WidgetActions {
    static let ease = CAMediaTimingFunction(controlPoints: 0.25, 1, 0.5, 1)   // quartic-ish ease-out
    static let morphTime = 0.28
    static let snapMargin: CGFloat = 12, snapReach: CGFloat = 28, gripSize: CGFloat = 14

    var panel: Panel!
    var host: NSHostingView<WidgetView>!
    let root = FlippedView()          // window content: clip + grip
    let clip = FlippedView()          // holds the widget; its rounded frame is what morphs
    let grip = GripView()
    let sampler = Sampler()
    let prefs = Prefs()
    var notifier: Notifier!
    var alerts: Alerts!
    var hotKey: HotKey?
    var statusItem: NSStatusItem?
    var shownItem: NSMenuItem?, throughItem: NSMenuItem?, alertsItem: NSMenuItem?
    var gallery: Gallery?
    var ghost: NSImageView?
    var eventMonitor: Any?
    var dragTimer: Timer?
    var morphing = false, gliding = false, hopping = false, resizing = false, ignoreMoves = false
    var morphGen = 0
    var morphRight = false
    var resizeX: CGFloat = 0, resizeWidth: CGFloat = 1, resizeScale = 1.0, resizeFromLeft = false
    var scrollAcc: CGFloat = 0, pinchAcc: CGFloat = 0
    var refitQueued = false
    var dragArmed = false             // a mouse-down on the widget; only a real drag ends in a snap

    func applicationDidFinishLaunching(_ n: Notification) {
        notifier = Notifier()
        alerts = Alerts { [weak self] title, text in self?.notifier.post(title, text) }
        prefs.actions = self
        prefs.apply = { [weak self] in self?.applyPrefs() }

        host = NSHostingView(rootView: WidgetView(s: sampler, prefs: prefs))
        host.sizingOptions = [.intrinsicContentSize]   // report size; window is resized manually (top-pinned)
        let size = host.fittingSize
        panel = Panel(contentRect: NSRect(origin: .zero, size: size), styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
        root.frame = NSRect(origin: .zero, size: size)
        clip.frame = root.bounds
        clip.autoresizingMask = [.width, .height]
        clip.wantsLayer = true
        clip.layer?.masksToBounds = true
        host.frame = clip.bounds
        host.autoresizingMask = [.width, .height]
        clip.addSubview(host)
        root.addSubview(clip)
        root.addSubview(grip)
        grip.toolTip = "Drag to scale"
        grip.began = { [weak self] in self?.beginResize() }
        grip.moved = { [weak self] in self?.dragResize() }
        grip.ended = { [weak self] in self?.endResize() }
        panel.contentView = root
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.hasShadow = true
        panel.isMovableByWindowBackground = true
        panel.collectionBehavior = [.canJoinAllSpaces, .stationary, .fullScreenAuxiliary]
        panel.hidesOnDeactivate = false
        applyPrefs()
        place(initial: true)
        panel.delegate = self
        panel.alphaValue = 0
        panel.orderFrontRegardless()
        fade(to: prefs.opacity, 0.35)

        sampler.onSample = { [weak self] in self?.tick() }
        setUpStatusItem()
        hotKey = HotKey { [weak self] in
            guard let self else { return }
            self.setClickThrough(!self.prefs.clickThrough)
        }
        eventMonitor = NSEvent.addLocalMonitorForEvents(matching: [.scrollWheel, .magnify, .leftMouseDown]) { [weak self] e in
            guard let self else { return e }
            return self.monitorEvent(e)
        }
        syncTray()
    }

    func applicationWillTerminate(_ n: Notification) { savePosition() }

    func applicationDidChangeScreenParameters(_ n: Notification) { place(initial: false) }

    // ---------- every second ----------

    func tick() {
        alerts?.check(sampler, enabled: prefs.alerts)
        queueRefit()
    }

    /// Data can change the widget's height (a limit row appears, the account line, a longer list): follow it.
    func queueRefit() {
        guard !refitQueued else { return }
        refitQueued = true
        DispatchQueue.main.async { [weak self] in
            guard let self else { return }
            self.refitQueued = false
            guard let panel = self.panel, !self.morphing, !self.hopping, !self.resizing, !self.gliding else { return }
            let s = self.host.fittingSize
            if abs(s.width - panel.frame.width) > 0.5 || abs(s.height - panel.frame.height) > 0.5 { self.fit() }
        }
    }

    func applyPrefs() {
        panel?.level = prefs.onTop ? .floating : .normal
        sampler.limitsEnabled = prefs.limits
        syncTray()
    }

    // ---------- frames ----------

    var rightAnchored: Bool {
        guard let panel, let scr = (panel.screen ?? NSScreen.main)?.visibleFrame else { return false }
        return panel.frame.midX > scr.midX
    }

    func cornerRadius() -> CGFloat { (prefs.size == .mini ? 10 : 14) * CGFloat(prefs.zoom) }

    /// `display: false` lets the caller rearrange the subviews before anything is drawn at the new size.
    func setPanelFrame(_ f: NSRect, display: Bool = true) {
        ignoreMoves = true
        panel.setFrame(f, display: display)
        ignoreMoves = false
        placeGrip()
    }

    func placeGrip() {
        let g = AppDelegate.gripSize, b = root.bounds
        grip.frame = NSRect(x: rightAnchored ? 0 : b.width - g, y: b.height - g, width: g, height: g)   // root is flipped: bottom = maxY
        grip.isHidden = morphing
    }

    /// Resize to content, keeping the top edge pinned; right-hand widgets grow and shrink leftward.
    func fit(right: Bool? = nil, display: Bool = true) {
        guard let panel else { return }
        let size = host.fittingSize
        guard size.width > 1, size.height > 1 else { return }
        var f = panel.frame
        let r = right ?? rightAnchored
        f.origin.y = f.maxY - size.height
        if r { f.origin.x = f.maxX - size.width }
        f.size = size
        setPanelFrame(f, display: display)
    }

    // ---------- positions: per view, per screen arrangement ----------

    func layoutKey(_ size: WidgetSize) -> String {
        let frames = NSScreen.screens.map { $0.frame }.sorted { $0.minX != $1.minX ? $0.minX < $1.minX : $0.minY < $1.minY }
        let screens = frames.map { "\(Int($0.minX)),\(Int($0.minY)),\(Int($0.width))x\(Int($0.height))" }.joined(separator: ";")
        return screens + "|" + size.rawValue
    }

    func onScreen(_ topLeft: NSPoint) -> Bool {
        NSScreen.screens.contains { $0.frame.contains(NSPoint(x: topLeft.x + 40, y: topLeft.y - 20)) }
    }

    func saved(_ size: WidgetSize) -> NSPoint? {
        guard let v = prefs.positions[layoutKey(size)], v.count >= 2 else { return nil }
        let p = NSPoint(x: v[0], y: v[1])
        return onScreen(p) ? p : nil
    }

    func savePosition() {
        guard let panel, panel.isVisible else { return }
        var all = prefs.positions
        all[layoutKey(prefs.size)] = [Double(panel.frame.minX), Double(panel.frame.maxY)]
        prefs.positions = all
    }

    func place(initial: Bool) {
        guard let panel else { return }
        let size = host.fittingSize
        var topLeft: NSPoint? = saved(prefs.size)
        if topLeft == nil && initial && panel.setFrameUsingName("Pulse") {           // where 1.x left it
            let p = NSPoint(x: panel.frame.minX, y: panel.frame.maxY)
            if onScreen(p) { topLeft = p }
        }
        if topLeft == nil && !initial {
            let p = NSPoint(x: panel.frame.minX, y: panel.frame.maxY)
            if onScreen(p) { topLeft = p }
        }
        if topLeft == nil, let scr = (NSScreen.main ?? NSScreen.screens.first)?.visibleFrame {
            topLeft = NSPoint(x: scr.maxX - size.width - 24, y: scr.maxY - 24)
        }
        guard let p = topLeft else { return }
        setPanelFrame(NSRect(x: p.x, y: p.y - size.height, width: size.width, height: size.height))
    }

    // ---------- drag: snap to edges, corners and centre ----------

    func windowDidMove(_ notification: Notification) {
        guard dragArmed, !ignoreMoves, !morphing, !gliding, !hopping, !resizing else { return }
        scheduleDragCheck()
    }

    func scheduleDragCheck() {
        dragTimer?.invalidate()
        dragTimer = Timer.scheduledTimer(withTimeInterval: 0.15, repeats: false) { [weak self] _ in
            MainActor.assumeIsolated { self?.dragCheck() }
        }
    }

    func dragCheck() {
        if NSEvent.pressedMouseButtons & 1 != 0 { scheduleDragCheck(); return }   // still dragging
        dragArmed = false
        snap()
    }

    /// After a drag, a widget dropped near an edge or corner of its screen glides onto it.
    func snap() {
        guard let panel, let wa = (panel.screen ?? NSScreen.main)?.visibleFrame else { return }
        let f = panel.frame, m = AppDelegate.snapMargin, reach = AppDelegate.snapReach
        var x = f.minX, top = f.maxY
        if abs(x - (wa.minX + m)) < reach { x = wa.minX + m }
        else if abs(wa.maxX - m - f.maxX) < reach { x = wa.maxX - m - f.width }
        else if abs(f.midX - wa.midX) < reach / 2 { x = wa.midX - f.width / 2 }
        if abs(top - (wa.maxY - m)) < reach { top = wa.maxY - m }
        else if abs(f.minY - (wa.minY + m)) < reach { top = wa.minY + m + f.height }
        if x == f.minX && top == f.maxY { savePosition(); placeGrip(); return }
        glide(to: NSRect(x: x, y: top - f.height, width: f.width, height: f.height))
    }

    func glide(to f: NSRect) {
        if reduceMotion { setPanelFrame(f); savePosition(); return }
        gliding = true
        NSAnimationContext.runAnimationGroup({ ctx in
            ctx.duration = 0.22
            ctx.timingFunction = AppDelegate.ease
            self.panel.animator().setFrame(f, display: true)
        }, completionHandler: { [weak self] in
            MainActor.assumeIsolated {
                guard let self else { return }
                self.gliding = false
                self.placeGrip()
                self.savePosition()
            }
        })
    }

    // ---------- fading, morphing, hopping ----------

    func fade(to alpha: Double, _ duration: Double, then done: (() -> Void)? = nil) {
        guard let panel else { return }
        if reduceMotion { panel.alphaValue = CGFloat(alpha); done?(); return }
        NSAnimationContext.runAnimationGroup({ ctx in
            ctx.duration = duration
            ctx.timingFunction = CAMediaTimingFunction(name: .easeOut)
            panel.animator().alphaValue = CGFloat(alpha)
        }, completionHandler: {
            MainActor.assumeIsolated { done?() }
        })
    }

    func snapshotImage() -> NSImage? {
        let b = host.bounds
        guard b.width > 0, b.height > 0, let rep = host.bitmapImageRepForCachingDisplay(in: b) else { return nil }
        host.cacheDisplay(in: b, to: rep)
        let img = NSImage(size: b.size)
        img.addRepresentation(rep)
        return img
    }

    func morph(_ change: @escaping () -> Void) { morphChange(change, crossfade: true) }

    /// Applies a change that alters the widget's size and morphs the outline from the old shape to the new one:
    /// the window briefly holds the larger of the two, a rounded clip eases between them and the old frame fades out.
    func morphChange(_ change: @escaping () -> Void, crossfade: Bool) {
        endMorph()
        guard let panel, panel.isVisible, !reduceMotion, !hopping else {
            change()
            DispatchQueue.main.async { [weak self] in
                self?.fit()
                self?.savePosition()
            }
            return
        }
        morphGen += 1
        let gen = morphGen
        let oldSize = host.frame.size
        let oldR = cornerRadius()
        morphRight = rightAnchored
        if crossfade, let img = snapshotImage() {
            let iv = NSImageView(frame: host.frame)
            iv.image = img
            iv.imageScaling = .scaleAxesIndependently
            iv.autoresizingMask = morphRight ? [.minXMargin] : []
            clip.addSubview(iv)
            ghost = iv
        }
        morphing = true
        grip.isHidden = true
        change()
        DispatchQueue.main.async { [weak self] in                  // let SwiftUI lay out the new content first
            guard let self, self.morphGen == gen, self.morphing else { return }
            self.animateMorph(from: oldSize, radius: oldR, gen: gen)
        }
    }

    func animateMorph(from old: CGSize, radius oldR: CGFloat, gen: Int) {
        let new = host.fittingSize
        guard new.width > 1, new.height > 1, old.width > 1, old.height > 1 else { endMorph(); return }
        let right = morphRight
        let w = max(old.width, new.width), h = max(old.height, new.height)
        let f = panel.frame
        clip.autoresizingMask = []
        host.autoresizingMask = right ? [.minXMargin] : []
        setPanelFrame(NSRect(x: right ? f.maxX - w : f.minX, y: f.maxY - h, width: w, height: h), display: false)
        grip.isHidden = true
        clip.frame = NSRect(x: right ? w - old.width : 0, y: 0, width: old.width, height: old.height)
        host.frame = NSRect(x: right ? old.width - new.width : 0, y: 0, width: new.width, height: new.height)
        ghost?.frame = NSRect(origin: .zero, size: old)
        let newR = cornerRadius()
        if let layer = clip.layer {
            let a = CABasicAnimation(keyPath: "cornerRadius")
            a.fromValue = oldR
            a.toValue = newR
            a.duration = AppDelegate.morphTime
            a.timingFunction = AppDelegate.ease
            layer.cornerRadius = newR
            layer.add(a, forKey: "morphRadius")
        }
        let target = NSRect(x: right ? w - new.width : 0, y: 0, width: new.width, height: new.height)
        NSAnimationContext.runAnimationGroup({ ctx in
            ctx.duration = AppDelegate.morphTime
            ctx.timingFunction = AppDelegate.ease
            ctx.allowsImplicitAnimation = true
            self.clip.animator().frame = target
            self.ghost?.animator().alphaValue = 0
        }, completionHandler: { [weak self] in
            MainActor.assumeIsolated {
                guard let self, self.morphGen == gen else { return }
                self.endMorph()
            }
        })
    }

    func endMorph() {
        guard morphing else { return }
        morphing = false
        morphGen += 1
        ghost?.removeFromSuperview()
        ghost = nil
        clip.layer?.removeAnimation(forKey: "morphRadius")
        clip.layer?.cornerRadius = 0
        fit(right: morphRight, display: false)
        clip.autoresizingMask = [.width, .height]
        clip.frame = root.bounds
        host.autoresizingMask = [.width, .height]
        host.frame = clip.bounds
        placeGrip()
        panel.invalidateShadow()
        savePosition()
    }

    /// Switching to a view that lives somewhere else: fade out here, reappear there.
    func hop(_ change: @escaping () -> Void, to p: NSPoint) {
        endMorph()
        hopping = true
        fade(to: 0, 0.13) { [weak self] in
            guard let self else { return }
            change()
            DispatchQueue.main.async { [weak self] in
                guard let self else { return }
                let s = self.host.fittingSize
                self.setPanelFrame(NSRect(x: p.x, y: p.y - s.height, width: s.width, height: s.height))
                self.hopping = false
                self.fade(to: self.prefs.opacity, 0.22)
            }
        }
    }

    // ---------- views ----------

    func setSize(_ size: WidgetSize) {
        guard size != prefs.size else { return }
        savePosition()                                         // the view we're leaving keeps its spot
        let apply: () -> Void = { [weak self] in
            guard let self else { return }
            if size != .full { self.sampler.topMode = nil }
            self.prefs.size = size
        }
        if let p = saved(size), let panel, panel.isVisible,
           abs(p.x - panel.frame.minX) > 4 || abs(p.y - panel.frame.maxY) > 4 {
            hop(apply, to: p)
        } else {
            morph(apply)
        }
    }

    func openGallery() {
        if !panel.isVisible { toggleShown() }
        if let g = gallery { g.panel.makeKeyAndOrderFront(nil); return }
        let g = Gallery(sampler: sampler, prefs: prefs, current: prefs.size, screen: panel.screen) { [weak self] size in
            self?.setSize(size)
        }
        g.onClose = { [weak self] in self?.gallery = nil }
        gallery = g
        g.show()
    }

    // ---------- scale ----------

    func setScale(_ s: Double) {
        prefs.zoom = s
        prefs.saveScale()
    }

    func scaleTo(_ s: Double) {
        guard s != prefs.zoom || s != prefs.savedScale else { return }
        morphChange({ [weak self] in self?.setScale(s) }, crossfade: false)
    }

    func stepScale(_ dir: Int) {
        guard !morphing else { return }
        let i = widgetScales.firstIndex(of: nearestScale(prefs.zoom)) ?? 0
        scaleTo(widgetScales[min(max(i + dir, 0), widgetScales.count - 1)])
    }

    /// ⌘ + scroll or a pinch over the widget steps through the scales; a mouse-down arms drag snapping.
    func monitorEvent(_ e: NSEvent) -> NSEvent? {
        guard let panel, e.window === panel, !resizing, !prefs.clickThrough else { return e }
        if e.type == .leftMouseDown { dragArmed = true; return e }
        if e.type == .magnify {
            pinchAcc += e.magnification
            if abs(pinchAcc) >= 0.15 { stepScale(pinchAcc > 0 ? 1 : -1); pinchAcc = 0 }
            if e.phase == .ended || e.phase == .cancelled { pinchAcc = 0 }
            return nil
        }
        guard e.modifierFlags.contains(.command) else { return e }
        scrollAcc += e.hasPreciseScrollingDeltas ? e.scrollingDeltaY / 30 : e.scrollingDeltaY
        if abs(scrollAcc) >= 1 { stepScale(scrollAcc > 0 ? 1 : -1); scrollAcc = 0 }
        return nil
    }

    func beginResize() {
        guard !morphing, !hopping else { return }
        resizing = true
        resizeX = NSEvent.mouseLocation.x
        resizeScale = prefs.zoom
        resizeWidth = max(panel.frame.width, 1)
        resizeFromLeft = rightAnchored
    }

    func dragResize() {
        guard resizing else { return }
        var dx = NSEvent.mouseLocation.x - resizeX
        if resizeFromLeft { dx = -dx }
        let lo = widgetScales[0] * 0.9, hi = widgetScales[widgetScales.count - 1] * 1.05
        prefs.zoom = min(max(resizeScale * Double((resizeWidth + dx) / resizeWidth), lo), hi)
        let right = resizeFromLeft
        DispatchQueue.main.async { [weak self] in self?.fit(right: right) }
    }

    func endResize() {
        guard resizing else { return }
        resizing = false
        dragArmed = false
        scaleTo(nearestScale(prefs.zoom))                     // ease onto the closest snap point
    }

    // ---------- opacity, click-through, showing ----------

    func setOpacity(_ o: Double) {
        prefs.opacity = o
        if panel.isVisible { fade(to: o, 0.2) }
    }

    func setClickThrough(_ on: Bool) {
        prefs.clickThrough = on
        panel.ignoresMouseEvents = on
        if on {
            notifier.post("Click-through on", "Clicks now pass through Pulse. Press ⌃⌥P or use the menu-bar icon to turn it off.")
        }
        syncTray()
    }

    func toggleShown() {
        if panel.isVisible {
            savePosition()
            fade(to: 0, 0.15) { [weak self] in
                self?.panel.orderOut(nil)
                self?.syncTray()
            }
        } else {
            panel.alphaValue = 0
            panel.orderFrontRegardless()
            fade(to: prefs.opacity, 0.25)
        }
        syncTray()
    }

    // ---------- menu-bar icon ----------

    func setUpStatusItem() {
        let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        if let img = NSImage(systemSymbolName: "waveform.path.ecg", accessibilityDescription: "Pulse") {
            img.isTemplate = true
            item.button?.image = img
        } else {
            item.button?.title = "P"
        }
        let menu = NSMenu()
        menu.delegate = self
        shownItem = menu.addItem(withTitle: "Hide Pulse", action: #selector(menuToggleShown), keyEquivalent: "")
        menu.addItem(withTitle: "Choose View…", action: #selector(menuGallery), keyEquivalent: "")
        let through = menu.addItem(withTitle: "Click-through", action: #selector(menuClickThrough), keyEquivalent: "p")
        through.keyEquivalentModifierMask = [.control, .option]
        throughItem = through
        alertsItem = menu.addItem(withTitle: "Alerts", action: #selector(menuAlerts), keyEquivalent: "")
        menu.addItem(NSMenuItem.separator())
        menu.addItem(withTitle: "Quit Pulse", action: #selector(menuQuit), keyEquivalent: "q")
        for i in menu.items { i.target = self }
        item.menu = menu
        statusItem = item
    }

    func menuNeedsUpdate(_ menu: NSMenu) { syncTray() }

    func syncTray() {
        let shown = panel?.isVisible ?? false
        shownItem?.title = shown ? "Hide Pulse" : "Show Pulse"
        throughItem?.state = prefs.clickThrough ? .on : .off
        alertsItem?.state = prefs.alerts ? .on : .off
        statusItem?.button?.toolTip = prefs.clickThrough ? "Pulse · click-through (⌃⌥P)" : "Pulse"
    }

    @objc func menuToggleShown() { toggleShown() }
    @objc func menuGallery() { openGallery() }
    @objc func menuClickThrough() { setClickThrough(!prefs.clickThrough) }
    @objc func menuAlerts() { prefs.alerts.toggle(); syncTray() }
    @objc func menuQuit() { NSApp.terminate(nil) }
}

@main
enum PulseApp {
    static func main() {
        let app = NSApplication.shared
        let args = CommandLine.arguments
        if let i = args.firstIndex(of: "--snapshot"), i + 1 < args.count {
            snapshotMode = true
            MainActor.assumeIsolated {   // render widget to PNG (debug aid)
                let s = Sampler(start: false)
                for _ in 0..<20 { Thread.sleep(forTimeInterval: 0.1); s.sample() }
                if args.contains("--demo") { s.loadDemo() } else {
                    s.claude = s.claudeUsage.scanSync()
                    if let th = Thermals().read() { s.cpuTemp = th.cpu; s.maxTemp = th.max }; s.gpu = Probe.gpu()
                }
                if let t = args.firstIndex(of: "--top"), t + 1 < args.count { s.topMode = args[t + 1] == "mem" ? .mem : .cpu }
                if args.contains("--demo"), let m = s.topMode {
                    s.top = m == .cpu ? [TopProc(name: "Xcode", value: 61), TopProc(name: "Safari", value: 23), TopProc(name: "WindowServer", value: 14)]
                                      : [TopProc(name: "Xcode", value: 3.1e9), TopProc(name: "Safari", value: 1.8e9), TopProc(name: "claude", value: 0.9e9)]
                }
                let p = Prefs(persist: false)
                p.size = args.contains("--mini") ? .mini : args.contains("--compact") ? .compact
                    : args.contains("--landscape") ? .landscape : args.contains("--claude") ? .claude : .full
                p.claudeOpen = args.contains("--open")
                p.zoom = 1
                let r = ImageRenderer(content: WidgetView(s: s, prefs: p)); r.scale = 2
                if let img = r.nsImage, let t = img.tiffRepresentation,
                   let b = NSBitmapImageRep(data: t)?.representation(using: .png, properties: [:]) {
                    try? b.write(to: URL(fileURLWithPath: args[i + 1]))
                }
            }
            return
        }
        let delegate = MainActor.assumeIsolated { AppDelegate() }
        app.delegate = delegate
        app.setActivationPolicy(.accessory)
        withExtendedLifetime(delegate) { app.run() }
    }
}
