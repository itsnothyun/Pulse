"""The whole widget, drawn as pixel rectangles. The same pass measures layout (dc is None).

Port of windows/Pulse/PulseView.cs -- keep the layout numbers in step so every port looks identical.
"""
import math
import time

import cairo

from . import fmt
from . import pixelfont as px
from .alerts import clock
from .pixelfont import Ink, rect

FULL_W, LAND_W, PAD = 320, 660, 18
W = FULL_W
INNER = W - PAD * 2
COL = (LAND_W - PAD * 2 - 24) / 2                # landscape column width
MINI_H = 29
MINI_VALUE_W = 4 * 6 * 1.5 - 1.5                 # value slots sized for "100%"
GIB = 1073741824

# The views, like a phone widget's sizes: everything, everything side by side, Claude only, the four big
# numbers, one quiet line. Clicking the header steps through them in this order.
FULL, LANDSCAPE, CLAUDE, COMPACT, MINI = "full", "landscape", "claude", "compact", "mini"
VIEWS = (FULL, LANDSCAPE, CLAUDE, COMPACT, MINI)


def next_size(s):
    return VIEWS[(VIEWS.index(s) + 1) % len(VIEWS)]


def title(s):
    return s.capitalize()


def mini_width():
    return 12 + 4 + 3 * 12 + 3 * (px.width("CPU", 1) + 5 + MINI_VALUE_W) + 12


def exact(tokens):
    return f"{tokens:,.0f} tokens"


def one_decimal(v):
    """C# "0.#": one decimal place, dropped when it's zero."""
    return f"{v:.1f}".rstrip("0").rstrip(".")


class Tweens:
    """Bars tween only when they gain or lose a segment, so idle frames cost nothing."""
    DUR = 0.45
    SETTLED = float("-inf")             # start time of a tween that isn't moving (now - start can't round under DUR)

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
            self.map[key] = (target, target, self.SETTLED)
            return target
        if target != t[1]:
            cur = self._eval(t, now)
            if self._seg(cur, segments) != self._seg(target, segments):
                t = (cur, target, now)
            else:
                t = (target, target, self.SETTLED)
            self.map[key] = t
        if now - t[2] < self.DUR:
            self.active = True
        return self._eval(t, now)


class PulseView:
    def __init__(self, sampler, size=FULL):
        self.s = sampler
        self.tw = Tweens()
        self.size = size
        self.claude_open = False             # the breakdown under the Claude section; always open in the Claude view
        self.live_rainbow = False            # True: the base frame leaves the ULTRA label to loops.draw (it drifts)
        self.rainbow = None                  # (text, right, y) of the ULTRA label, set during layout
        self._phase = 0.0
        self.scanner_pos = (-100, -100)
        self.pip_pos = None
        self.cpu_row = self.mem_row = (0, 0)
        self.claude_area = None              # (x, y, w, h)
        self.tips = []                       # [((x, y, w, h), text)], recorded while drawing

    # ---------- geometry the window and loops need ----------

    @property
    def is_mini(self):
        return self.size == MINI

    @property
    def radius(self):
        return 10 if self.is_mini else 14

    @property
    def panel_width(self):
        return mini_width() if self.is_mini else LAND_W if self.size == LANDSCAPE else FULL_W

    @property
    def header_bottom(self):
        return MINI_H if self.is_mini else PAD + 14 + 6

    @property
    def hot(self):
        return (self.s.temp or 0) >= 85

    @property
    def breakdown_shown(self):
        return self.size == CLAUDE or self.claude_open

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

    def claude_at(self, x, y):
        """A click on the Claude section (Full and Landscape) opens or closes its breakdown."""
        if self.size not in (FULL, LANDSCAPE) or self.claude_area is None:
            return False
        ax, ay, aw, ah = self.claude_area
        return ax <= x <= ax + aw and ay <= y <= ay + ah

    def tip_at(self, x, y):
        """The exact value under a point, for the hover tooltip."""
        for (rx, ry, rw, rh), text in reversed(self.tips):
            if rx <= x <= rx + rw and ry <= y <= ry + rh:
                return text, (rx, ry, rw, rh)
        return None

    def _tip(self, dc, x, y, w, h, text):
        if dc is not None:
            self.tips.append(((x - 3, y - 3, w + 6, h + 6), text))

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

    @staticmethod
    def _vertical_rule(dc, x, y, h):
        if dc is None:
            return
        i = 0
        while i < h:
            dc.rectangle(x, y + i, 1, 2)
            i += 4
        dc.set_source_rgba(*Ink.LINE)
        dc.fill()

    def _bar(self, dc, key, x, y, w, h, value, segments=28, blink=False):
        if dc is None:
            return
        v = self.tw.get(key, max(0.0, min(1.0, value)), segments)
        gap = 2
        sw = math.floor((w - gap * (segments - 1)) / segments)
        exact_v = v * segments
        lit = int(exact_v)
        partial = exact_v - lit
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

    def draw_rainbow(self, dc, phase):
        """The ULTRA label in the drifting spectrum (loops.draw calls this every frame when live_rainbow)."""
        if dc is None or self.rainbow is None:
            return
        text, right, y = self.rainbow
        px.draw_right(dc, text, right, y, 1, px.rainbow(phase))

    # ---------- exact values for the hover tooltip ----------

    def _temp_state(self, t):
        if self.s.temp is None:
            return "NO SENSOR"
        return "COOL" if t < 50 else "WARM" if t < 70 else "HOT" if t < 85 else "CRITICAL"

    @property
    def cpu_tip(self):
        s = self.s
        return f"CPU {s.cpu * 100:.1f}% across {len(s.cores)} cores · {s.procs:,} processes"

    @property
    def mem_tip(self):
        s = self.s
        return f"Memory {s.mem_used / GIB:.2f} GB used of {s.mem_total / GIB:.2f} GB ({s.mem_used / s.mem_total * 100:.1f}%)"

    @property
    def temp_tip(self):
        s = self.s
        if s.temp is None:
            return "No temperature sensor found"
        return f"Temperature {s.temp:.1f}°C" + (f" · hottest sensor {s.temp_max:.1f}°C" if s.temp_max is not None else "")

    @property
    def disk_tip(self):
        s = self.s
        return f"{s.disk_name} {(s.disk_total - s.disk_used) / 1e9:.1f} GB free of {s.disk_total / 1e9:.1f} GB"

    @property
    def gpu_tip(self):
        return f"GPU {self.s.gpu * 100:.1f}% busy" if self.s.gpu is not None else "No GPU counters"

    @property
    def net_tip(self):
        return f"Download {self.s.net_in / 1e3:,.1f} KB/s · upload {self.s.net_out / 1e3:,.1f} KB/s"

    @property
    def swap_tip(self):
        s = self.s
        if s.swap_total <= 0:
            return "No swap configured"
        return f"Swap {s.swap_used / 1e9:.2f} GB used of {s.swap_total / 1e9:.2f} GB"

    @property
    def power_tip(self):
        if self.s.battery is None:
            return "Mains power, no battery"
        pct, charging, ac = self.s.battery
        return f"Battery {pct}% · {'charging' if charging else 'plugged in' if ac else 'on battery'}"

    # ---------- layout ----------

    def paint(self, dc, phase=0.0):
        """Draws the panel; returns its height. `phase` places a still ULTRA spectrum (see live_rainbow)."""
        h = self._body(None)
        if dc is None:
            return h
        self.tips = []
        self._phase = phase
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
        return {LANDSCAPE: self._paint_landscape, CLAUDE: self._paint_claude, COMPACT: self._paint_compact,
                MINI: self._paint_mini}.get(self.size, self._paint_full)(dc)

    def _paint_mini(self, dc):
        """One quiet line: no scanner, no sweep. Only a running-hot temperature blinks."""
        s = self.s
        self.pip_pos = None
        self.rainbow = None
        self.scanner_pos = (-100, -100)
        t, x, y = s.temp or 0, 12, (MINI_H - 10.5) / 2
        rect(dc, Ink.alpha(Ink.ON, 0.85), x, (MINI_H - 4) / 2, 4, 4)
        x += 4 + 12
        items = [
            ("CPU", fmt.pct(s.cpu), False, self.cpu_tip),
            ("MEM", fmt.pct(s.mem_used / s.mem_total), False, self.mem_tip),
            ("TMP", "N/A" if s.temp is None else f"{round(t)}°", self.hot, self.temp_tip),
        ]
        for label, value, blink, tip in items:
            x0 = x
            px.draw(dc, label, x, y + 1.75, 1, Ink.DIM)
            x += px.width(label, 1) + 5
            px.draw_right(dc, value, x + MINI_VALUE_W, y, 1.5, Ink.OFF if blink and s.tick else Ink.ON)   # fixed slot
            x += MINI_VALUE_W + 12
            self._tip(dc, x0, y, x - 12 - x0, 10.5, tip)
        return MINI_H

    def _header(self, dc, y, width=W):
        s = self.s
        px.draw(dc, "PULSE", PAD, y, 2, Ink.ON)
        self.scanner_pos = (PAD + px.width("PULSE", 2) + 8, y + 5.5)
        toggle = "+" if self.size == COMPACT else "-"
        px.draw_right(dc, toggle, width - PAD, y + 1.75, 1.5, Ink.DIM)
        px.draw_right(dc, s.clock, width - PAD - px.width(toggle, 1.5) - 8, y + 1.75, 1.5, Ink.MID)
        self._tip(dc, width - PAD - 70, y, 70, 14, f"{title(self.size)} view · click the header for the next one")
        return y + 14

    def _rule(self, dc, y, gap=14, width=INNER):
        y += gap
        self._dotted_rule(dc, PAD, y, width)
        return y + 1 + gap

    def _hero(self, dc, y, label, detail, value, hist, tip):
        px.draw(dc, label, PAD, y, 2, Ink.ON)
        px.draw(dc, detail, PAD, y + 19, 1, Ink.DIM)
        px.draw_right(dc, value, W - PAD, y + 2.5, 3, Ink.ON)
        self._sparkline(dc, W - PAD - 70 - 10 - 53, y + 4, hist)
        self._tip(dc, PAD, y, INNER, 26, tip)
        return y + 26 + 8

    def _tile(self, dc, x, y, w, label, value, sub, bar, key, tip):
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
        self._tip(dc, x, y, w, h, tip)
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

    def _footer(self, dc, y, width):
        s = self.s
        px.draw(dc, f"{s.threads} THREADS", PAD, y, 1, Ink.DIM)
        px.draw_right(dc, fmt.uptime(s.uptime), width - PAD, y, 1, Ink.DIM)

    # ---------- views ----------

    def _paint_full(self, dc):
        s = self.s
        y = self._header(dc, PAD)
        y = self._rule(dc, y)

        mem_f, disk_f = s.mem_used / s.mem_total, s.disk_used / s.disk_total
        t = s.temp or 0
        temp_f = (t - 30) / 70

        y0 = y
        y = self._hero(dc, y, "CPU", f"{len(s.cores)} CORES · {s.procs} PROCS", fmt.pct(s.cpu), s.history("cpu"), self.cpu_tip)
        self._core_grid(dc, PAD, y, INNER, s.cores)
        y += 15
        self.cpu_row = (y0 - 7, y + 7)
        if s.top_mode == "cpu":
            y = self._top_list(dc, y, "cpu")
        y = self._rule(dc, y)

        y0 = y
        y = self._hero(dc, y, "MEM", f"{fmt.gib(s.mem_used)} / {fmt.gib(s.mem_total)} GB", fmt.pct(mem_f), s.history("mem"),
                       self.mem_tip)
        self._bar(dc, "mem", PAD, y, INNER, 8, mem_f)
        y += 8
        self.mem_row = (y0 - 7, y + 7)
        if s.top_mode == "mem":
            y = self._top_list(dc, y, "mem")
        y = self._rule(dc, y)

        detail = f"{self._temp_state(t)} · PEAK {round(s.temp_max)}°" if s.temp_max is not None else self._temp_state(t)
        y = self._hero(dc, y, "TMP", detail, "N/A" if s.temp is None else f"{round(t)}°", s.history("tmp"), self.temp_tip)
        self._bar(dc, "tmp", PAD, y, INNER, 8, temp_f, blink=self.hot and s.tick)
        y = self._rule(dc, y + 8)

        y = self._hero(dc, y, "DSK", f"{s.disk_name} {fmt.size(s.disk_total - s.disk_used)} FREE OF {fmt.size(s.disk_total)}",
                       fmt.pct(disk_f), s.history("dsk"), self.disk_tip)
        self._bar(dc, "dsk", PAD, y, INNER, 8, disk_f)
        y += 8 + 14

        tw = (INNER - 8) / 2
        self._tile(dc, PAD, y, tw, "GPU", "N/A" if s.gpu is None else fmt.pct(s.gpu), None, s.gpu or 0, "gpu", self.gpu_tip)
        self._tile(dc, PAD + tw + 8, y, tw, "NETWORK", f"↓{fmt.rate(s.net_in)}/S", f"↑{fmt.rate(s.net_out)}/S", None, "net",
                   self.net_tip)
        y += 62 + 8
        # Linux shows swap where Windows shows its commit charge
        self._tile(dc, PAD, y, tw, "SWAP", fmt.size(s.swap_used), f"OF {fmt.size(s.swap_total)}" if s.swap_total > 0 else "NONE",
                   None, "swap", self.swap_tip)
        if s.battery is not None:
            pct, charging, ac = s.battery
            self._tile(dc, PAD + tw + 8, y, tw, "POWER", f"{pct}%", "⚡ CHARGING" if charging else "AC POWER" if ac else "ON BATTERY",
                       None, "pwr", self.power_tip)
        else:
            self._tile(dc, PAD + tw + 8, y, tw, "POWER", "AC", "NO BATTERY", None, "pwr", self.power_tip)
        y += 62

        y = self._rule(dc, y)
        y = self._claude_section(dc, PAD, y, INNER)
        y = self._rule(dc, y)

        self._footer(dc, y, W)
        return y + 7 + PAD

    def _paint_landscape(self, dc):
        """System on the left, Claude on the right: for a wide spot like the top of a screen."""
        s = self.s
        y = self._header(dc, PAD, LAND_W)
        y = self._rule(dc, y, 14, LAND_W - PAD * 2)
        top, rx = y, PAD + COL + 24

        t = s.temp or 0
        mem_f, disk_f = s.mem_used / s.mem_total, s.disk_used / s.disk_total
        tmp_detail = f"{self._temp_state(t)} · PEAK {round(s.temp_max)}°" if s.temp_max is not None else self._temp_state(t)
        rows = [
            ("CPU", f"{len(s.cores)} CORES · {s.procs} PROCS", fmt.pct(s.cpu), s.cpu, "l-cpu", False, self.cpu_tip),
            ("MEM", f"{fmt.gib(s.mem_used)} / {fmt.gib(s.mem_total)} GB", fmt.pct(mem_f), mem_f, "l-mem", False, self.mem_tip),
            ("TMP", tmp_detail, "N/A" if s.temp is None else f"{round(t)}°", (t - 30) / 70, "l-tmp", self.hot and s.tick,
             self.temp_tip),
            ("DSK", f"{s.disk_name} {fmt.size(s.disk_total - s.disk_used)} FREE", fmt.pct(disk_f), disk_f, "l-dsk", False,
             self.disk_tip),
        ]
        ly = top
        for label, detail, value, frac, key, blink, tip in rows:
            px.draw(dc, label, PAD, ly, 2, Ink.ON)
            px.draw(dc, detail, PAD + 46, ly + 3.5, 1, Ink.DIM)
            px.draw_right(dc, value, PAD + COL, ly, 2, Ink.ON)
            self._bar(dc, key, PAD, ly + 21, COL, 5, frac, 28, blink)
            self._tip(dc, PAD, ly, COL, 26, tip)
            ly += 26 + 16

        cw = (COL - 2 * 8) / 3
        small = [
            ("GPU", "N/A" if s.gpu is None else fmt.pct(s.gpu), self.gpu_tip),
            ("NETWORK", f"↓{fmt.rate(s.net_in)}/S", self.net_tip),
            ("POWER", f"{s.battery[0]}%" if s.battery is not None else "AC", self.power_tip),
        ]
        for i, (label, value, tip) in enumerate(small):
            x = PAD + i * (cw + 8)
            px.draw(dc, label, x, ly, 1, Ink.DIM)
            px.draw(dc, value, x, ly + 12, 1.5, Ink.ON)
            self._tip(dc, x, ly, cw, 23, tip)
        ly += 23

        ry = self._claude_section(dc, rx, top, COL)
        bottom = max(ly, ry)
        self._vertical_rule(dc, PAD + COL + 12, top, bottom - top)

        y = self._rule(dc, bottom, 14, LAND_W - PAD * 2)
        self._footer(dc, y, LAND_W)
        return y + 7 + PAD

    def _paint_claude(self, dc):
        """Claude only: the account, limits, this week and where the tokens went."""
        s = self.s
        y = self._header(dc, PAD)
        y = self._rule(dc, y)
        y = self._claude_section(dc, PAD, y, INNER)
        y = self._rule(dc, y)
        px.draw(dc, f"{s.claude.calls} CALLS · {s.claude.sessions} SESSIONS", PAD, y, 1, Ink.DIM)
        px.draw_right(dc, fmt.uptime(s.uptime), W - PAD, y, 1, Ink.DIM)
        return y + 7 + PAD

    def _claude_section(self, dc, x, y, w):
        c = self.s.claude
        right, top = x + w, y
        px.draw(dc, "CLAUDE CODE", x, y, 2, Ink.ON)
        self.pip_pos = None
        self.rainbow = None
        if c.live > 0:
            live = f"{c.live} LIVE"
            px.draw_right(dc, live, right, y + 3.5, 1, Ink.MID)
            self.pip_pos = (right - px.width(live, 1) - 6 - 4, y + 5)
            self._tip(dc, right - 60, y, 60, 14, f"{c.live} session{'' if c.live == 1 else 's'} active in the last 5 minutes")
        else:
            px.draw_right(dc, "IDLE" if c.ready else "SCANNING", right, y + 3.5, 1, Ink.DIM)
        y += 14 + 12

        if c.email is not None:
            plan = fmt.glyphs(c.plan, 12).strip() if c.plan else ""
            plan_w = px.width(plan, 1) + 12 if plan else 0
            px.draw(dc, fmt.glyphs(c.email, int((w - plan_w) // 6)), x, y, 1, Ink.MID)
            if plan == "ULTRA":
                self.rainbow = (plan, right, y)
                if not self.live_rainbow:
                    self.draw_rainbow(dc, self._phase)
            elif plan:
                px.draw_right(dc, plan, right, y, 1, Ink.DIM)
            self._tip(dc, x, y, w, 7, f"Signed in as {c.email}" + (f" · {c.plan} plan" if c.plan else "") + " · follows /login")
            y += 7 + 12

        px.draw(dc, fmt.tok(c.week), x, y, 3, Ink.ON)
        px.draw(dc, "TOKENS THIS WEEK", x, y + 28, 1, Ink.DIM)
        self._tip(dc, x, y, w - 124, 35, f"{exact(c.week)} this week (all accounts on this PC)")
        self._week_chart(dc, right - 112, y, 112, c.days, c.today_index)
        self._tip(dc, right - 112, y, 112, 35, " · ".join(f"{'MTWTFSS'[i]} {fmt.tok(d)}" for i, d in enumerate(c.days)))
        y += 35 + 12

        left = max(c.block_end - fmt.now(), 0)
        cw = (w - 3 * 8) / 4
        stats = [
            ("TODAY", fmt.tok(c.today), f"{exact(c.today)} today"),
            ("5H BLOCK", fmt.tok(c.block if left > 0 else 0),
             f"{exact(c.block)} in the current 5-hour block" if left > 0 else "No 5-hour block open"),
            ("EST. COST", fmt.usd(c.cost), f"${c.cost:,.2f} at API list prices (plans are billed differently)"),
            ("SESSIONS", str(c.sessions), f"{c.sessions} sessions this week"),
        ]
        for i, (label, value, tip) in enumerate(stats):
            px.draw(dc, label, x + i * (cw + 8), y, 1, Ink.DIM)
            px.draw(dc, value, x + i * (cw + 8), y + 12, 1.5, Ink.ON)
            self._tip(dc, x + i * (cw + 8), y, cw, 23, tip)
        y += 23 + 12

        lim = getattr(self.s, "limits", None)
        if lim is not None and lim.ready and (lim.five is not None or lim.week is not None):
            if lim.five is not None:
                y = self._limit_row(dc, x, y, w, "5H LIMIT", lim.five, lim.five_reset, "l5", "5-hour limit")
            if lim.week is not None:
                y = self._limit_row(dc, x, y, w, "WEEK LIMIT", lim.week, lim.week_reset, "lw", "Weekly limit")
            y += 4

        px.draw(dc, f"IN {fmt.tok(c.input + c.cache_write)} · OUT {fmt.tok(c.output)} · CACHED {fmt.tok(c.cache_read)}",
                x, y, 1, Ink.DIM)
        px.draw_right(dc, f"{c.calls} CALLS", right, y, 1, Ink.DIM)
        self._tip(dc, x, y, w, 7, f"Input {c.input + c.cache_write:,.0f} · output {c.output:,.0f} · "
                                  f"cache reads {c.cache_read:,.0f} · {c.calls:,} API calls")
        y += 7 + 12

        px.draw(dc, f"RESETS IN {fmt.countdown(left)}" if left > 0 else "NO 5H BLOCK OPEN", x, y, 1, Ink.MID if left > 0 else Ink.DIM)
        self._bar(dc, "block", right - 118, y + 2, 118, 3, 1 - left / (5 * 3600) if left > 0 else 0, 20)
        if left > 0:
            self._tip(dc, x, y, w, 7, f"Local 5-hour block ends {clock(c.block_end)}")
        y += 7

        if self.breakdown_shown:
            y = self._breakdown(dc, x, y, w)
        self.claude_area = (x, top - 7, w, y - top + 14)
        if self.size != CLAUDE:
            self._tip(dc, x, top, 120, 14,
                      "Click to hide the breakdown" if self.claude_open else "Click for tokens by model, project and account")
        return y

    def _limit_row(self, dc, x, y, w, label, used, reset, key, name):
        label_w, pct_w = 66, 30
        px.draw(dc, label, x, y, 1, Ink.DIM)
        self._bar(dc, key, x + label_w, y + 1, w - label_w - pct_w - 8, 5, used, 24)
        px.draw_right(dc, fmt.pct(used), x + w, y, 1, Ink.ON if used >= 0.9 else Ink.MID)
        self._tip(dc, x, y, w, 7, f"{name} {one_decimal(used * 100)}% used"
                                  + (f" · resets {clock(reset)}" if reset > 0 else " · no window open"))
        return y + 7 + 9

    def _breakdown(self, dc, x, y, w):
        c = self.s.claude
        total, right = max(c.week, 1), x + w
        for heading, items in (("BY MODEL", c.by_model), ("BY PROJECT", c.by_project), ("BY ACCOUNT", c.by_account)):
            y += 14
            self._dotted_rule(dc, x, y, w)
            y += 1 + 10
            px.draw(dc, heading, x, y, 1, Ink.DIM)
            y += 7 + 7
            if not items:
                px.draw(dc, "-", x, y, 1, Ink.OFF)
                y += 7
                continue
            n = min(3, len(items))
            for i in range(n):
                it = items[i]
                amount = f"{fmt.tok(it.tokens)} · {round(it.tokens / total * 100)}%"
                amount_w = px.width(amount, 1)
                self._bar(dc, f"bd-{heading}-{i}", x, y + 11, w, 2, it.tokens / total, 28)
                px.draw(dc, fmt.glyphs(it.name, int((w - amount_w - 12) / 6)), x, y, 1, Ink.MID)
                px.draw_right(dc, amount, right, y, 1, Ink.ON)
                self._tip(dc, x, y, w, 10, f"{it.name}: {exact(it.tokens)} · ${it.cost:,.2f} est.")
                y += 7 + 12
            if len(items) > n:
                px.draw(dc, f"+{len(items) - n} MORE", x, y, 1, Ink.DIM)
                y += 7 + 4
            y -= 4
        return y

    def _paint_compact(self, dc):
        s = self.s
        self.rainbow = None
        y = self._header(dc, PAD)
        y = self._rule(dc, y, 12)

        t = s.temp or 0
        items = [
            ("CPU", s.cpu, fmt.pct(s.cpu), "c-cpu", self.cpu_tip),
            ("MEM", s.mem_used / s.mem_total, fmt.pct(s.mem_used / s.mem_total), "c-mem", self.mem_tip),
            ("TMP", (t - 30) / 70, "N/A" if s.temp is None else f"{round(t)}°", "c-tmp", self.temp_tip),
            ("DSK", s.disk_used / s.disk_total, fmt.pct(s.disk_used / s.disk_total), "c-dsk", self.disk_tip),
        ]
        cw = (INNER - 3 * 12) / 4
        for i, (label, frac, value, key, tip) in enumerate(items):
            x = PAD + i * (cw + 12)
            px.draw(dc, label, x, y, 1, Ink.DIM)
            px.draw(dc, value, x, y + 13, 2, Ink.ON)
            self._bar(dc, key, x, y + 33, cw, 4, frac, 8, label == "TMP" and self.hot and s.tick)
            self._tip(dc, x, y, cw, 37, tip)
        y += 37
        y = self._rule(dc, y, 12)

        tx = PAD
        self.pip_pos = None
        if s.claude.live > 0:
            self.pip_pos = (PAD, y + 1.5)
            tx += 10
        left = s.claude.block_end - fmt.now()
        px.draw(dc, f"CLAUDE {fmt.tok(s.claude.week)} · ~{fmt.usd(s.claude.cost)}", tx, y, 1, Ink.MID)
        self._tip(dc, PAD, y, INNER / 2, 7, f"{exact(s.claude.week)} this week · ${s.claude.cost:,.2f} at API list prices")
        lim = getattr(s, "limits", None)
        parts = []
        if lim is not None and lim.five is not None:
            parts.append(f"5H {fmt.pct(lim.five)}")
        if lim is not None and lim.week is not None:
            parts.append(f"WK {fmt.pct(lim.week)}")
        limit_text = " · ".join(parts)
        right_text = (limit_text if limit_text
                      else f"RESETS {fmt.countdown(left)}" if left > 0 else f"TODAY {fmt.tok(s.claude.today)}")
        px.draw_right(dc, right_text, W - PAD, y, 1, Ink.DIM)
        if limit_text:
            self._tip(dc, W - PAD - 100, y, 100, 7, f"Plan limits used: {limit_text.replace('WK', 'week')}")
        return y + 7 + PAD
