// Pulse — monochrome pixel system monitor widget
import AppKit
import SwiftUI
import ServiceManagement
import IOKit
import IOKit.ps
import Darwin

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
]

struct PixelText: View {
    let text: String
    var scale: CGFloat = 2
    var color: Color = Ink.on

    static func width(_ s: String, _ scale: CGFloat) -> CGFloat { CGFloat(max(s.count * 6 - 1, 0)) * scale }

    var body: some View {
        let chars = Array(text.uppercased())
        Canvas { ctx, _ in
            let dot = scale >= 3 ? scale - 0.75 : scale
            for (i, ch) in chars.enumerated() {
                guard let rows = glyphs[ch] else { continue }
                let ox = CGFloat(i * 6) * scale
                for (y, row) in rows.enumerated() {
                    for x in 0..<5 where row & (0x10 >> UInt8(x)) != 0 {
                        ctx.fill(Path(CGRect(x: ox + CGFloat(x) * scale, y: CGFloat(y) * scale,
                                             width: dot, height: dot)), with: .color(color))
                    }
                }
            }
        }
        .frame(width: PixelText.width(text, scale), height: 7 * scale)
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

// MARK: - Pixel widgets

struct PixelBar: View, Animatable {
    var value: Double          // 0...1
    var segments = 28
    var height: CGFloat = 8
    var blink = false
    var animatableData: Double { get { value } set { value = newValue } }

    var body: some View {
        Canvas { ctx, size in
            let gap: CGFloat = 2
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
        .frame(height: height)
    }
}

struct Sparkline: View {
    let data: [Double]         // 0...1
    var columns = 18
    var height: CGFloat = 18

    var body: some View {
        Canvas { ctx, size in
            let cw: CGFloat = 2, gap: CGFloat = 1, px: CGFloat = 2
            let pts = Array(data.suffix(columns))
            let start = CGFloat(columns - pts.count) * (cw + gap)
            let levels = Int(size.height / px)
            for i in 0..<columns {                                     // baseline dots
                ctx.fill(Path(CGRect(x: CGFloat(i) * (cw + gap), y: size.height - 1, width: cw, height: 1)), with: .color(Ink.off))
            }
            for (i, v) in pts.enumerated() {
                let h = max(1, Int((min(max(v, 0), 1) * Double(levels)).rounded()))
                let x = start + CGFloat(i) * (cw + gap)
                let age = Double(i + 1) / Double(pts.count)
                for l in 0..<h {
                    let top = l == h - 1
                    ctx.fill(Path(CGRect(x: x, y: size.height - CGFloat(l + 1) * px, width: cw, height: px - 0.5)),
                             with: .color(top ? Ink.on.opacity(0.35 + 0.65 * age) : Ink.dim.opacity(0.12 + 0.3 * age)))
                }
            }
        }
        .frame(width: CGFloat(columns) * 3 - 1, height: height)
    }
}

/// One mini vertical meter per core.
struct CoreGrid: View {
    let cores: [Double]
    let perfCount: Int

    var body: some View {
        Canvas { ctx, size in
            guard !cores.isEmpty else { return }
            let gap: CGFloat = 4, levels = 5, px: CGFloat = 2, lg: CGFloat = 1
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
        .frame(height: 15)
    }
}

struct DottedRule: View {
    var body: some View {
        Canvas { ctx, size in
            var x: CGFloat = 0
            while x < size.width { ctx.fill(Path(CGRect(x: x, y: 0, width: 2, height: 1)), with: .color(Ink.line)); x += 4 }
        }.frame(height: 1)
    }
}

/// Mon–Sun token bars; today bright, past days mid, future days empty.
struct WeekChart: View {
    let days: [Double]
    let today: Int
    var body: some View {
        VStack(spacing: 4) {
            Canvas { ctx, size in
                let gap: CGFloat = 4, levels = 8, px: CGFloat = 2, lg: CGFloat = 1
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
            .frame(height: 24)
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
    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
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
    var body: some View {
        if snapshotMode { Rectangle().fill(Ink.on).frame(width: 4, height: 4) } else { Pulse() }
    }
}

/// Header scanner (static in snapshots).
struct HeaderScanner: View {
    var hot = false
    var body: some View {
        if snapshotMode {
            HStack(spacing: 2) { ForEach(0..<8, id: \.self) { i in Rectangle().fill(Ink.on.opacity(i == 2 ? 0.9 : 0.12)).frame(width: 3, height: 3) } }
        } else { Scanner(hot: hot) }
    }
}

/// Softly breathing pixel, used as a "live" indicator.
struct Pulse: NSViewRepresentable {
    func makeNSView(context: Context) -> NSView {
        let v = NSView(); v.wantsLayer = true
        let l = CALayer(); l.frame = CGRect(x: 0, y: 0, width: 4, height: 4); l.backgroundColor = caColor(0.95, 1)
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
    func sizeThatFits(_ p: ProposedViewSize, nsView: NSView, context: Context) -> CGSize? { CGSize(width: 4, height: 4) }
}

/// KITT-style scanner: a pixel stepping back and forth across a dim track, with a fading trail.
struct Scanner: NSViewRepresentable {
    var hot = false
    let n = 8, step: CGFloat = 5, dot: CGFloat = 3

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
        let positions = (0..<n).map { CGFloat($0) * step } + (1..<(n - 1)).reversed().map { CGFloat($0) * step }
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
    var body: some View {
        ZStack {
            Canvas { ctx, size in
                var y: CGFloat = 0
                while y < size.height { ctx.fill(Path(CGRect(x: 0, y: y, width: size.width, height: 1)), with: .color(.white.opacity(0.022))); y += 3 }
            }
            if !reduceMotion && !snapshotMode { Sweep() }
        }
        .allowsHitTesting(false)
    }

    struct Sweep: NSViewRepresentable {
        func makeNSView(context: Context) -> NSView { SweepView() }
        func updateNSView(_ v: NSView, context: Context) { (v as? SweepView)?.restart() }
    }

    final class SweepView: NSView {
        let band = CAGradientLayer()
        var lastHeight: CGFloat = -1
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
            let h = bounds.height, bh: CGFloat = 80
            guard h > 0, h != lastHeight else { return }
            lastHeight = h
            CATransaction.begin(); CATransaction.setDisableActions(true)
            band.frame = CGRect(x: 0, y: -bh, width: bounds.width, height: bh)
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

    static func load() -> Double { var l = [Double](repeating: 0, count: 3); getloadavg(&l, 3); return l[0] }
}

// MARK: - Claude Code usage (local transcripts in ~/.claude/projects)

struct ClaudeStats {
    var week = 0.0, input = 0.0, output = 0.0, cacheWrite = 0.0, cacheRead = 0.0
    var today = 0.0, window5h = 0.0
    var sessions = 0, live = 0, calls = 0
    var days = [Double](repeating: 0, count: 7)
    var todayIndex = 0
    var ready = false
}

/// Incremental tally of this week's tokens across every Claude Code session on this Mac.
/// Each pass reads only bytes appended since the last pass; API calls are de-duplicated by message+request id.
final class ClaudeUsage {
    private struct Event { let ts: Double; let input, output, cw, cr: Double; let session: String }
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

    private func ingest(_ line: UnsafeRawBufferPointer, weekStart ws: Double) {
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
        events.append(Event(ts: ts, input: n("input_tokens"), output: n("output_tokens"),
                            cw: n("cache_creation_input_tokens"), cr: n("cache_read_input_tokens"),
                            session: Self.field(line, "\"sessionId\":\"") ?? ""))
    }

    private func scan() -> ClaudeStats {
        var cal = Calendar(identifier: .iso8601); cal.timeZone = .current          // weeks start Monday
        let now = Date()
        let ws = cal.dateInterval(of: .weekOfYear, for: now)?.start.timeIntervalSince1970 ?? 0
        if ws != weekStart { weekStart = ws; offsets = [:]; seen = []; events = [] }

        let base = ProcessInfo.processInfo.environment["CLAUDE_CONFIG_DIR"].map { URL(fileURLWithPath: $0) }
            ?? FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".claude")
        let root = base.appendingPathComponent("projects")
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
                            ingest(UnsafeRawBufferPointer(start: p, count: UnsafeRawPointer(nl) - p), weekStart: ws)
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

        var st = ClaudeStats(); st.ready = true; st.live = live; st.calls = events.count
        let dayStart = cal.startOfDay(for: now).timeIntervalSince1970
        let win = now.timeIntervalSince1970 - 5 * 3600
        var sessions = Set<String>()
        for e in events {
            let t = e.input + e.output + e.cw + e.cr
            st.week += t; st.input += e.input; st.output += e.output; st.cacheWrite += e.cw; st.cacheRead += e.cr
            if e.ts >= dayStart { st.today += t }
            if e.ts >= win { st.window5h += t }
            st.days[min(max(Int((e.ts - ws) / 86400), 0), 6)] += t
            sessions.insert(e.session)
        }
        st.sessions = sessions.count
        st.todayIndex = min(max(Int((dayStart - ws) / 86400 + 0.5), 0), 6)
        return st
    }
}

// MARK: - Sampler

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
    let claudeUsage = ClaudeUsage()

    let perfCores = { var v: Int32 = 0; var s = 4; sysctlbyname("hw.perflevel0.logicalcpu", &v, &s, nil, 0); return Int(v) }()
    private let thermals = Thermals()
    private let probeQ = DispatchQueue(label: "pulse.probe", qos: .utility)
    private var timer: Timer?
    private var n = 0
    private var prevTicks: [[UInt32]] = []
    private var prevNet: [String: (UInt32, UInt32)] = [:]
    private var prevNetTime = Date()
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
        var c = ClaudeStats()
        c.ready = true; c.week = 412.6e6; c.today = 58.3e6; c.window5h = 31.9e6; c.output = 2.41e6
        c.input = 9.8e6; c.cacheRead = 400.4e6; c.sessions = 9; c.live = 1; c.calls = 3184; c.todayIndex = 3
        c.days = [88e6, 102e6, 164e6, 58.3e6, 0, 0, 0]
        claude = c
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
        n += 1
    }
}

// MARK: - Formatting

enum F {
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

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .center, spacing: 10) {
                VStack(alignment: .leading, spacing: 5) {
                    PixelText(text: label, scale: 2)
                    PixelText(text: detail, scale: 1, color: Ink.dim)
                }
                Spacer(minLength: 0)
                Sparkline(data: history)
                PixelNumber(value: value, format: format, scale: 3)
                    .frame(width: 70, alignment: .trailing)
            }
            meter
        }
    }
}

struct Tile<Content: View>: View {
    let label: String
    @ViewBuilder var content: Content
    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            PixelText(text: label, scale: 1, color: Ink.dim)
            content
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .overlay(Rectangle().strokeBorder(Ink.line, lineWidth: 1))
    }
}

// MARK: - Main view

struct WidgetView: View {
    @ObservedObject var s: Sampler
    @ObservedObject var prefs: Prefs

    var body: some View {
        let t = s.cpuTemp ?? 0
        let hot = t >= 85 || s.thermalState == .serious || s.thermalState == .critical
        Group {
            if prefs.compact { compact(hot: hot) } else { full(hot: hot) }
        }
        .padding(18)
        .frame(width: 320)
        .background(Ink.bg)
        .overlay(CRTOverlay())
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).strokeBorder(Ink.on.opacity(0.16), lineWidth: 1))
        .contextMenu {
            Toggle("Compact", isOn: $prefs.compact)
            Toggle("Always on Top", isOn: $prefs.onTop)
            Toggle("Launch at Login", isOn: $prefs.launchAtLogin)
            Divider()
            Button("Open Activity Monitor") {
                NSWorkspace.shared.openApplication(at: URL(fileURLWithPath: "/System/Applications/Utilities/Activity Monitor.app"), configuration: .init())
            }
            Button("Quit Pulse") { NSApp.terminate(nil) }
        }
    }

    var header: some View {
        HStack(spacing: 8) {
            PixelText(text: "PULSE", scale: 2)
            HeaderScanner(hot: (s.cpuTemp ?? 0) >= 85)
            Spacer()
            PixelText(text: s.clock, scale: 1.5, color: Ink.mid)
            PixelText(text: prefs.compact ? "+" : "-", scale: 1.5, color: Ink.dim)
        }
        .contentShape(Rectangle())
        .onTapGesture { prefs.compact.toggle() }
        .help("Click to toggle compact view · right-click for options")
    }

    func tempState(_ t: Double) -> String {
        s.cpuTemp == nil ? "NO SENSOR" : t < 50 ? "COOL" : t < 70 ? "WARM" : t < 85 ? "HOT" : "CRITICAL"
    }

    @ViewBuilder func full(hot: Bool) -> some View {
        let memF = s.memUsed / s.memTotal, diskF = s.diskUsed / s.diskTotal
        let t = s.cpuTemp ?? 0, tempF = (t - 30) / 70
        VStack(alignment: .leading, spacing: 14) {
            header
            DottedRule()
            HeroRow(label: "CPU", detail: "\(s.cores.count) CORES · LOAD \(String(format: "%.1f", s.load))",
                    value: s.cpu * 100, format: { "\(Int($0.rounded()))%" }, history: s.hist["cpu"] ?? []) {
                CoreGrid(cores: s.cores, perfCount: s.perfCores)
            }
            DottedRule()
            HeroRow(label: "MEM", detail: "\(F.gib(s.memUsed)) / \(F.gib(s.memTotal)) GB",
                    value: memF * 100, format: { "\(Int($0.rounded()))%" }, history: s.hist["mem"] ?? []) {
                PixelBar(value: memF).animation(tween, value: seg(memF))
            }
            DottedRule()
            HeroRow(label: "TMP", detail: s.maxTemp.map { "\(tempState(t)) · PEAK \(Int($0.rounded()))°" } ?? tempState(t),
                    value: t, format: { s.cpuTemp == nil ? "N/A" : "\(Int($0.rounded()))°" }, history: s.hist["tmp"] ?? []) {
                PixelBar(value: tempF, blink: hot && s.tick).animation(tween, value: seg(tempF))
            }
            DottedRule()
            HeroRow(label: "DSK", detail: "\(F.size(s.diskTotal - s.diskUsed)) FREE OF \(F.size(s.diskTotal))",
                    value: diskF * 100, format: { "\(Int($0.rounded()))%" }, history: s.hist["dsk"] ?? []) {
                PixelBar(value: diskF).animation(tween, value: seg(diskF))
            }
            Grid(horizontalSpacing: 8, verticalSpacing: 8) {
                GridRow {
                    Tile(label: "GPU") {
                        PixelNumber(value: (s.gpu ?? 0) * 100, format: { s.gpu == nil ? "N/A" : "\(Int($0.rounded()))%" }, scale: 2)
                        PixelBar(value: s.gpu ?? 0, segments: 16, height: 5).animation(tween, value: seg(s.gpu ?? 0, 16))
                    }
                    Tile(label: "NETWORK") {
                        PixelText(text: "↓\(F.rate(s.netIn))/S", scale: 2)
                        PixelText(text: "↑\(F.rate(s.netOut))/S", scale: 1, color: Ink.mid)
                    }
                }
                GridRow {
                    Tile(label: "SWAP") {
                        PixelText(text: F.size(s.swapUsed), scale: 2)
                        PixelText(text: s.swapTotal > 0 ? "OF \(F.size(s.swapTotal))" : "NONE", scale: 1, color: Ink.mid)
                    }
                    Tile(label: "POWER") {
                        if let b = s.battery {
                            PixelText(text: "\(b.pct)%", scale: 2)
                            PixelText(text: b.charging ? "⚡ CHARGING" : b.ac ? "AC POWER" : "ON BATTERY", scale: 1, color: Ink.mid)
                        } else {
                            PixelText(text: "AC", scale: 2)
                            PixelText(text: "NO BATTERY", scale: 1, color: Ink.mid)
                        }
                    }
                }
            }
            DottedRule()
            claudeSection
            DottedRule()
            HStack {
                PixelText(text: "THERMAL \(F.thermal(s.thermalState))", scale: 1, color: hot ? Ink.on : Ink.dim)
                Spacer()
                PixelText(text: F.uptime(), scale: 1, color: Ink.dim)
            }
        }
    }

    var claudeSection: some View {
        let c = s.claude
        return VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 6) {
                PixelText(text: "CLAUDE CODE", scale: 2)
                Spacer()
                if c.live > 0 { LivePip(); PixelText(text: "\(c.live) LIVE", scale: 1, color: Ink.mid) }
                else { PixelText(text: c.ready ? "IDLE" : "SCANNING", scale: 1, color: Ink.dim) }
            }
            HStack(alignment: .bottom, spacing: 16) {
                VStack(alignment: .leading, spacing: 6) {
                    PixelNumber(value: c.week, format: F.tok, scale: 3).animation(.easeOut(duration: 1.2), value: c.week)
                    PixelText(text: "TOKENS THIS WEEK", scale: 1, color: Ink.dim)
                }
                Spacer(minLength: 0)
                WeekChart(days: c.days, today: c.todayIndex).frame(width: 112)
            }
            HStack(alignment: .top, spacing: 8) {
                Stat(label: "TODAY", value: F.tok(c.today))
                Stat(label: "LAST 5H", value: F.tok(c.window5h))
                Stat(label: "OUTPUT", value: F.tok(c.output))
                Stat(label: "SESSIONS", value: "\(c.sessions)")
            }
            HStack {
                PixelText(text: "IN \(F.tok(c.input + c.cacheWrite)) · CACHED \(F.tok(c.cacheRead))", scale: 1, color: Ink.dim)
                Spacer()
                PixelText(text: "\(c.calls) CALLS", scale: 1, color: Ink.dim)
            }
        }
    }

    @ViewBuilder func compact(hot: Bool) -> some View {
        let t = s.cpuTemp ?? 0
        let items: [(String, Double, Double, String)] = [
            ("CPU", s.cpu, s.cpu * 100, "%"),
            ("MEM", s.memUsed / s.memTotal, s.memUsed / s.memTotal * 100, "%"),
            ("TMP", (t - 30) / 70, t, "°"),
            ("DSK", s.diskUsed / s.diskTotal, s.diskUsed / s.diskTotal * 100, "%"),
        ]
        VStack(alignment: .leading, spacing: 12) {
            header
            DottedRule()
            HStack(alignment: .top, spacing: 12) {
                ForEach(items, id: \.0) { it in
                    VStack(alignment: .leading, spacing: 6) {
                        PixelText(text: it.0, scale: 1, color: Ink.dim)
                        PixelNumber(value: it.2, format: { "\(Int($0.rounded()))\(it.3)" }, scale: 2)
                        PixelBar(value: it.1, segments: 8, height: 4, blink: it.0 == "TMP" && hot && s.tick)
                            .animation(tween, value: seg(it.1, 8))
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
            DottedRule()
            HStack(spacing: 6) {
                if s.claude.live > 0 { LivePip() }
                PixelText(text: "CLAUDE \(F.tok(s.claude.week)) WK", scale: 1, color: Ink.mid)
                Spacer()
                PixelText(text: "TODAY \(F.tok(s.claude.today))", scale: 1, color: Ink.dim)
            }
        }
    }
}

// MARK: - Prefs

@MainActor
final class Prefs: ObservableObject {
    @Published var onTop: Bool { didSet { UserDefaults.standard.set(onTop, forKey: "onTop"); apply?() } }
    @Published var compact: Bool { didSet { UserDefaults.standard.set(compact, forKey: "compact"); resize?() } }
    @Published var launchAtLogin: Bool {
        didSet {
            do { launchAtLogin ? try SMAppService.mainApp.register() : try SMAppService.mainApp.unregister() }
            catch { NSLog("Pulse login item: \(error)") }
        }
    }
    var apply: (() -> Void)?
    var resize: (() -> Void)?
    init() {
        onTop = UserDefaults.standard.object(forKey: "onTop") as? Bool ?? true
        compact = UserDefaults.standard.bool(forKey: "compact")
        launchAtLogin = SMAppService.mainApp.status == .enabled
    }
}

// MARK: - App

final class Panel: NSPanel {
    override var canBecomeKey: Bool { true }
}

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    var panel: Panel!
    var host: NSHostingView<WidgetView>!
    let sampler = Sampler()
    let prefs = Prefs()

    func applicationDidFinishLaunching(_ n: Notification) {
        host = NSHostingView(rootView: WidgetView(s: sampler, prefs: prefs))
        host.sizingOptions = [.intrinsicContentSize]   // report size; window is resized manually (top-pinned)
        host.frame.size = host.fittingSize
        panel = Panel(contentRect: host.frame, styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
        panel.contentView = host
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.hasShadow = true
        panel.isMovableByWindowBackground = true
        panel.collectionBehavior = [.canJoinAllSpaces, .stationary, .fullScreenAuxiliary]
        panel.hidesOnDeactivate = false
        prefs.apply = { [weak self] in self?.applyLevel() }
        prefs.resize = { [weak self] in DispatchQueue.main.async { self?.fit(animate: true) } }
        applyLevel()
        if panel.setFrameUsingName("Pulse") {
            fit(animate: false)
        } else if let scr = NSScreen.main?.visibleFrame {
            panel.setFrameOrigin(NSPoint(x: scr.maxX - host.frame.width - 24, y: scr.maxY - host.frame.height - 24))
        }
        panel.setFrameAutosaveName("Pulse")
        panel.alphaValue = 0
        panel.orderFrontRegardless()
        NSAnimationContext.runAnimationGroup { $0.duration = 0.35; panel.animator().alphaValue = 1 }
    }

    /// Resize to content, keeping the top edge pinned.
    func fit(animate: Bool) {
        let size = host.fittingSize
        var f = panel.frame
        f.origin.y += f.height - size.height
        f.size = size
        panel.setFrame(f, display: true, animate: animate)
    }

    func applyLevel() { panel?.level = prefs.onTop ? .floating : .normal }
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
                let p = Prefs(); p.compact = args.contains("--compact")
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
