"""The whole widget, drawn as pixel rectangles. The same pass measures layout (dc is None)."""
import math
import time

import cairo

from . import fmt
from . import pixelfont as px
from .pixelfont import Ink, rect

FULL_W, PAD = 320, 18
W = FULL_W
INNER = W - PAD * 2
MINI_H = 29
MINI_VALUE_W = 4 * 6 * 1.5 - 1.5          # value slots sized for "100%"

FULL, COMPACT, MINI = "full", "compact", "mini"


def next_size(s):
    return {FULL: COMPACT, COMPACT: MINI, MINI: FULL}[s]


def mini_width():
    return 12 + 4 + 3 * 12 + 3 * (px.width("CPU", 1) + 5 + MINI_VALUE_W) + 12


class Tweens:
    """Bars tween only when they gain or lose a segment, so idle frames cost nothing."""
    DUR = 0.45

    def __init__(self):
        self.map = {}
        self.active = False

    def begin_frame(self):
        self.active = False

    @staticmethod
    def _seg(v, n):
        return int(max(0.0, min(1.0, v)) * n * 2)

    def _eval(self, t, now):
        p = max(0.0, min(1.0, (now - t[2]) / self.DUR))
        p = 1 - (1 - p) ** 3
        return t[0] + (t[1] - t[0]) * p

    def get(self, key, target, segments):
        now = time.monotonic()
        t = self.map.get(key)
        if t is None:
            self.map[key] = (target, target, now - self.DUR)
            return target
        if target != t[1]:
            cur = self._eval(t, now)
            if self._seg(cur, segments) != self._seg(target, segments):
                t = (cur, target, now)
            else:
                t = (target, target, now - self.DUR)
            self.map[key] = t
        if now - t[2] < self.DUR:
            self.active = True
        return self._eval(t, now)


class PulseView:
    def __init__(self, sampler, size=FULL):
        self.s = sampler
        self.tw = Tweens()
        self.size = size
        self.scanner_pos = (-100, -100)
        self.pip_pos = None
        self.cpu_row = self.mem_row = (0, 0)

    # ---------- geometry the window and loops need ----------

    @property
    def is_mini(self):
        return self.size == MINI

    @property
    def radius(self):
        return 10 if self.is_mini else 14

    @property
    def panel_width(self):
        return mini_width() if self.is_mini else FULL_W

    @property
    def header_bottom(self):
        return MINI_H if self.is_mini else PAD + 14 + 6

    @property
    def hot(self):
        return (self.s.temp or 0) >= 85

    def measure(self):
        return self.panel_width, self._body(None)

    def row_at(self, y):
        """Which top-process list a click at y opens (Full size only)."""
        if self.size != FULL:
            return None
        if self.cpu_row[0] <= y <= self.cpu_row[1]:
            return "cpu"
        if self.mem_row[0] <= y <= self.mem_row[1]:
            return "mem"
        return None

    # ---------- primitives ----------

    @staticmethod
    def _dotted_rule(dc, x, y, w):
        if dc is None:
            return
        i = 0
        while i < w:
            dc.rectangle(x + i, y, 2, 1)
            i += 4
        dc.set_source_rgba(*Ink.LINE)
        dc.fill()

    def _bar(self, dc, key, x, y, w, h, value, segments=28, blink=False):
        if dc is None:
            return
        v = self.tw.get(key, max(0.0, min(1.0, value)), segments)
        gap = 2
        sw = math.floor((w - gap * (segments - 1)) / segments)
        exact = v * segments
        lit = int(exact)
        partial = exact - lit
        for i in range(segments):
            c = Ink.ON if i < lit else Ink.OFF
            if i == lit and partial > 0.15:
                c = Ink.DIM                                     # leading half-lit pixel
            if blink and i == max(lit - 1, 0):
                c = Ink.OFF
            rect(dc, c, x + i * (sw + gap), y, sw, h)

    @staticmethod
    def _sparkline(dc, x, y, data, columns=18, height=18):
        if dc is None:
            return
        cw, gap, p = 2, 1, 2
        count = min(columns, len(data))
        start = x + (columns - count) * (cw + gap)
        levels = int(height / p)
        for i in range(columns):
            rect(dc, Ink.OFF, x + i * (cw + gap), y + height - 1, cw, 1)
        for i in range(count):
            v = data[len(data) - count + i]
            hgt = max(1, round(max(0.0, min(1.0, v)) * levels))
            age = (i + 1) / count
            cx = start + i * (cw + gap)
            for l in range(hgt):
                if l == hgt - 1:
                    b = Ink.alpha(Ink.ON, 0.35 + 0.65 * age)
                else:
                    b = Ink.alpha(Ink.DIM, 0.12 + 0.3 * age)
                rect(dc, b, cx, y + height - (l + 1) * p, cw, p - 0.5)

    @staticmethod
    def _core_grid(dc, x, y, w, cores):
        if dc is None or not cores:
            return
        gap, p, lg, height, levels = 4, 2, 1, 15, 5
        cw = math.floor((w - gap * (len(cores) - 1)) / len(cores))
        for i, c in enumerate(cores):
            lit = math.ceil(max(0.0, min(1.0, c)) * levels)
            for l in range(levels):
                rect(dc, Ink.ON if l < lit else Ink.OFF, x + i * (cw + gap), y + height - (l + 1) * (p + lg), cw, p)

    @staticmethod
    def _week_chart(dc, x, y, w, days, today):
        if dc is None:
            return
        gap, p, lg, chart_h, levels = 4, 2, 1, 24, 8
        cw = math.floor((w - gap * 6) / 7)
        peak = max([1.0] + list(days))
        for i in range(7):
            lit = max(1, math.ceil(days[i] / peak * levels)) if days[i] > 0 else 0
            for l in range(levels):
                if l < lit:
                    c = Ink.ON if i == today else Ink.alpha(Ink.MID, 0.75)
                else:
                    c = Ink.alpha(Ink.OFF, 0.5) if i > today else Ink.OFF
                rect(dc, c, x + i * (cw + gap), y + chart_h - (l + 1) * (p + lg), cw, p)
            px.draw(dc, "MTWTFSS"[i], x + i * (cw + gap) + (cw - 5) / 2, y + chart_h + 4, 1, Ink.ON if i == today else Ink.DIM)

    # ---------- layout ----------

    def _temp_state(self, t):
        if self.s.temp is None:
            return "NO SENSOR"
        return "COOL" if t < 50 else "WARM" if t < 70 else "HOT" if t < 85 else "CRITICAL"

    def paint(self, dc):
        """Draws the panel; returns its height."""
        h = self._body(None)
        if dc is None:
            return h
        w, r = self.panel_width, self.radius
        dc.save()
        px.round_rect(dc, 0, 0, w, h, r)
        dc.clip()                                       # smooth rounded edge ...
        dc.set_antialias(cairo.ANTIALIAS_NONE)          # ... crisp pixels inside it
        rect(dc, Ink.BG, 0, 0, w, h)
        y = 0
        while y < h:                                    # faint static scanlines
            dc.rectangle(0, y, w, 1)
            y += 3
        dc.set_source_rgba(*Ink.alpha(Ink.ON, 0.02))
        dc.fill()
        self.tw.begin_frame()
        self._body(dc)
        dc.restore()
        px.round_rect(dc, 0.5, 0.5, w - 1, h - 1, r)
        dc.set_source_rgba(*Ink.alpha(Ink.ON, 0.16))
        dc.set_line_width(1)
        dc.stroke()
        return h

    def _body(self, dc):
        return {COMPACT: self._paint_compact, MINI: self._paint_mini}.get(self.size, self._paint_full)(dc)

    def _paint_mini(self, dc):
        """One quiet line: no scanner, no sweep. Only a running-hot temperature blinks."""
        s = self.s
        self.pip_pos = None
        self.scanner_pos = (-100, -100)
        t, x, y = s.temp or 0, 12, (MINI_H - 10.5) / 2
        rect(dc, Ink.alpha(Ink.ON, 0.85), x, (MINI_H - 4) / 2, 4, 4)
        x += 4 + 12
        items = [
            ("CPU", fmt.pct(s.cpu), False),
            ("MEM", fmt.pct(s.mem_used / s.mem_total), False),
            ("TMP", "N/A" if s.temp is None else f"{round(t)}°", self.hot),
        ]
        for label, value, blink in items:
            px.draw(dc, label, x, y + 1.75, 1, Ink.DIM)
            x += px.width(label, 1) + 5
            px.draw_right(dc, value, x + MINI_VALUE_W, y, 1.5, Ink.OFF if blink and s.tick else Ink.ON)   # fixed slot
            x += MINI_VALUE_W + 12
        return MINI_H

    def _header(self, dc, y):
        s = self.s
        px.draw(dc, "PULSE", PAD, y, 2, Ink.ON)
        self.scanner_pos = (PAD + px.width("PULSE", 2) + 8, y + 5.5)
        toggle = "+" if self.size == COMPACT else "-"
        px.draw_right(dc, toggle, W - PAD, y + 1.75, 1.5, Ink.DIM)
        px.draw_right(dc, s.clock, W - PAD - px.width(toggle, 1.5) - 8, y + 1.75, 1.5, Ink.MID)
        return y + 14

    def _rule(self, dc, y, gap=14):
        y += gap
        self._dotted_rule(dc, PAD, y, INNER)
        return y + 1 + gap

    def _hero(self, dc, y, label, detail, value, hist):
        px.draw(dc, label, PAD, y, 2, Ink.ON)
        px.draw(dc, detail, PAD, y + 19, 1, Ink.DIM)
        px.draw_right(dc, value, W - PAD, y + 2.5, 3, Ink.ON)
        self._sparkline(dc, W - PAD - 70 - 10 - 53, y + 4, hist)
        return y + 26 + 8

    def _tile(self, dc, x, y, w, label, value, sub, bar, key):
        h = 62
        if dc is not None:
            dc.set_source_rgba(*Ink.LINE)
            dc.set_line_width(1)
            dc.rectangle(x + 0.5, y + 0.5, w - 1, h - 1)
            dc.stroke()
        px.draw(dc, label, x + 10, y + 10, 1, Ink.DIM)
        px.draw(dc, value, x + 10, y + 24, 2, Ink.ON)
        if bar is not None:
            self._bar(dc, key, x + 10, y + 45, min(w - 20, 16 * 7), 5, bar, 16)
        elif sub is not None:
            px.draw(dc, sub, x + 10, y + 45, 1, Ink.MID)
        return h

    def _top_list(self, dc, y, mode):
        s = self.s
        y += 14
        for i in range(3):
            ry = y + i * 13
            px.draw(dc, str(i + 1), PAD, ry, 1, Ink.DIM)
            if i < len(s.top):
                name, value = s.top[i]
                px.draw(dc, fmt.proc_name(name), PAD + 14, ry, 1, Ink.MID)
                px.draw_right(dc, f"{round(value)}%" if mode == "cpu" else fmt.mem(value), W - PAD, ry, 1, Ink.ON)
            else:
                px.draw(dc, "READING" if i == 0 else "-", PAD + 14, ry, 1, Ink.OFF)
        return y + 2 * 13 + 7

    def _paint_full(self, dc):
        s = self.s
        y = self._header(dc, PAD)
        y = self._rule(dc, y)

        mem_f, disk_f = s.mem_used / s.mem_total, s.disk_used / s.disk_total
        t = s.temp or 0
        temp_f = (t - 30) / 70

        y0 = y
        y = self._hero(dc, y, "CPU", f"{len(s.cores)} CORES · {s.procs} PROCS", fmt.pct(s.cpu), s.history("cpu"))
        self._core_grid(dc, PAD, y, INNER, s.cores)
        y += 15
        self.cpu_row = (y0 - 7, y + 7)
        if s.top_mode == "cpu":
            y = self._top_list(dc, y, "cpu")
        y = self._rule(dc, y)

        y0 = y
        y = self._hero(dc, y, "MEM", f"{fmt.gib(s.mem_used)} / {fmt.gib(s.mem_total)} GB", fmt.pct(mem_f), s.history("mem"))
        self._bar(dc, "mem", PAD, y, INNER, 8, mem_f)
        y += 8
        self.mem_row = (y0 - 7, y + 7)
        if s.top_mode == "mem":
            y = self._top_list(dc, y, "mem")
        y = self._rule(dc, y)

        detail = f"{self._temp_state(t)} · PEAK {round(s.temp_max)}°" if s.temp_max is not None else self._temp_state(t)
        y = self._hero(dc, y, "TMP", detail, "N/A" if s.temp is None else f"{round(t)}°", s.history("tmp"))
        self._bar(dc, "tmp", PAD, y, INNER, 8, temp_f, blink=self.hot and s.tick)
        y = self._rule(dc, y + 8)

        y = self._hero(dc, y, "DSK", f"{s.disk_name} {fmt.size(s.disk_total - s.disk_used)} FREE OF {fmt.size(s.disk_total)}",
                       fmt.pct(disk_f), s.history("dsk"))
        self._bar(dc, "dsk", PAD, y, INNER, 8, disk_f)
        y += 8 + 14

        tw = (INNER - 8) / 2
        self._tile(dc, PAD, y, tw, "GPU", "N/A" if s.gpu is None else fmt.pct(s.gpu), None, s.gpu or 0, "gpu")
        self._tile(dc, PAD + tw + 8, y, tw, "NETWORK", f"↓{fmt.rate(s.net_in)}/S", f"↑{fmt.rate(s.net_out)}/S", None, "net")
        y += 62 + 8
        self._tile(dc, PAD, y, tw, "SWAP", fmt.size(s.swap_used), f"OF {fmt.size(s.swap_total)}" if s.swap_total > 0 else "NONE", None, "swap")
        if s.battery is not None:
            pct, charging, ac = s.battery
            self._tile(dc, PAD + tw + 8, y, tw, "POWER", f"{pct}%", "⚡ CHARGING" if charging else "AC POWER" if ac else "ON BATTERY", None, "pwr")
        else:
            self._tile(dc, PAD + tw + 8, y, tw, "POWER", "AC", "NO BATTERY", None, "pwr")
        y += 62

        y = self._rule(dc, y)
        y = self._claude_section(dc, y)
        y = self._rule(dc, y)

        px.draw(dc, f"{s.threads} THREADS", PAD, y, 1, Ink.DIM)
        px.draw_right(dc, fmt.uptime(s.uptime), W - PAD, y, 1, Ink.DIM)
        return y + 7 + PAD

    def _claude_section(self, dc, y):
        c = self.s.claude
        px.draw(dc, "CLAUDE CODE", PAD, y, 2, Ink.ON)
        self.pip_pos = None
        if c.live > 0:
            live = f"{c.live} LIVE"
            px.draw_right(dc, live, W - PAD, y + 3.5, 1, Ink.MID)
            self.pip_pos = (W - PAD - px.width(live, 1) - 6 - 4, y + 5)
        else:
            px.draw_right(dc, "IDLE" if c.ready else "SCANNING", W - PAD, y + 3.5, 1, Ink.DIM)
        y += 14 + 12

        px.draw(dc, fmt.tok(c.week), PAD, y, 3, Ink.ON)
        px.draw(dc, "TOKENS THIS WEEK", PAD, y + 28, 1, Ink.DIM)
        self._week_chart(dc, W - PAD - 112, y, 112, c.days, c.today_index)
        y += 35 + 12

        left = max(c.block_end - fmt.now(), 0)
        cw = (INNER - 3 * 8) / 4
        stats = [("TODAY", fmt.tok(c.today)), ("5H BLOCK", fmt.tok(c.block if left > 0 else 0)),
                 ("EST. COST", fmt.usd(c.cost)), ("SESSIONS", str(c.sessions))]
        for i, (label, value) in enumerate(stats):
            px.draw(dc, label, PAD + i * (cw + 8), y, 1, Ink.DIM)
            px.draw(dc, value, PAD + i * (cw + 8), y + 12, 1.5, Ink.ON)
        y += 23 + 12

        px.draw(dc, f"IN {fmt.tok(c.input + c.cache_write)} · OUT {fmt.tok(c.output)} · CACHED {fmt.tok(c.cache_read)}", PAD, y, 1, Ink.DIM)
        px.draw_right(dc, f"{c.calls} CALLS", W - PAD, y, 1, Ink.DIM)
        y += 7 + 12

        px.draw(dc, f"RESETS IN {fmt.countdown(left)}" if left > 0 else "NO 5H BLOCK OPEN", PAD, y, 1, Ink.MID if left > 0 else Ink.DIM)
        self._bar(dc, "block", W - PAD - 118, y + 2, 118, 3, 1 - left / (5 * 3600) if left > 0 else 0, 20)
        return y + 7

    def _paint_compact(self, dc):
        s = self.s
        y = self._header(dc, PAD)
        y = self._rule(dc, y, 12)

        t = s.temp or 0
        items = [
            ("CPU", s.cpu, fmt.pct(s.cpu), "c-cpu"),
            ("MEM", s.mem_used / s.mem_total, fmt.pct(s.mem_used / s.mem_total), "c-mem"),
            ("TMP", (t - 30) / 70, "N/A" if s.temp is None else f"{round(t)}°", "c-tmp"),
            ("DSK", s.disk_used / s.disk_total, fmt.pct(s.disk_used / s.disk_total), "c-dsk"),
        ]
        cw = (INNER - 3 * 12) / 4
        for i, (label, frac, value, key) in enumerate(items):
            x = PAD + i * (cw + 12)
            px.draw(dc, label, x, y, 1, Ink.DIM)
            px.draw(dc, value, x, y + 13, 2, Ink.ON)
            self._bar(dc, key, x, y + 33, cw, 4, frac, 8, label == "TMP" and self.hot and s.tick)
        y += 37
        y = self._rule(dc, y, 12)

        tx = PAD
        self.pip_pos = None
        if s.claude.live > 0:
            self.pip_pos = (PAD, y + 1.5)
            tx += 10
        left = s.claude.block_end - fmt.now()
        px.draw(dc, f"CLAUDE {fmt.tok(s.claude.week)} · ~{fmt.usd(s.claude.cost)}", tx, y, 1, Ink.MID)
        px.draw_right(dc, f"RESETS {fmt.countdown(left)}" if left > 0 else f"TODAY {fmt.tok(s.claude.today)}", W - PAD, y, 1, Ink.DIM)
        return y + 7 + PAD
