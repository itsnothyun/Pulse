"""The subtle loops -- header scanner, live pulse, CRT sweep -- drawn over a cached base frame,
so the pixel view itself only repaints when data changes. Pure Cairo; the window feeds it time."""
import math

import cairo

from . import pixelfont as px
from .pixelfont import Ink

SWEEP_H = 80
SWEEP_PERIOD = 9.0
PIP_PERIOD = 2.6                                   # 1.3 s up, 1.3 s down
# head positions along the 8-slot track: out and back, 5 px per slot
POSITIONS = [i * 5.0 for i in range(8)] + [i * 5.0 for i in range(6, 0, -1)]
TRAIL_ALPHA = (0.25, 0.5, 0.9)                     # trail first, head last (on top)


def draw(dc, view, t, h, motion=True):
    """Paints the overlay for time `t` (seconds). Cheap: a handful of rectangles and one gradient."""
    w = view.panel_width
    if not view.is_mini:
        _scanner(dc, view, t, motion)
        if motion:
            _sweep(dc, view, t, w, h)
    if view.pip_pos is not None:
        a = 0.3 + 0.7 * (1 - math.cos(2 * math.pi * t / PIP_PERIOD)) / 2 if motion else 1.0
        dc.set_antialias(cairo.ANTIALIAS_NONE)
        px.rect(dc, Ink.alpha(Ink.ON, a), view.pip_pos[0], view.pip_pos[1], 4, 4)


def _scanner(dc, view, t, motion):
    x0, y0 = view.scanner_pos
    dc.set_antialias(cairo.ANTIALIAS_NONE)
    for i in range(8):                             # dim track
        px.rect(dc, Ink.alpha(Ink.ON, 0.12), x0 + i * 5, y0, 3, 3)
    beat = 0.07 if view.hot else 0.16
    step = int(t / beat)
    n = len(POSITIONS)
    for k in range(3):
        if motion:
            x = POSITIONS[(step - (2 - k)) % n]    # trail runs `lag` steps behind the head
        else:
            if k != 2:
                continue
            x = 10
        px.rect(dc, Ink.alpha(Ink.ON, TRAIL_ALPHA[k]), x0 + x, y0, 3, 3)


def _sweep(dc, view, t, w, h):
    y = -SWEEP_H + (h + SWEEP_H) * ((t % SWEEP_PERIOD) / SWEEP_PERIOD)
    dc.save()
    dc.set_antialias(cairo.ANTIALIAS_DEFAULT)
    px.round_rect(dc, 0, 0, w, h, view.radius)
    dc.clip()
    g = cairo.LinearGradient(0, y, 0, y + SWEEP_H)
    g.add_color_stop_rgba(0, 1, 1, 1, 0)
    g.add_color_stop_rgba(0.5, 1, 1, 1, 10 / 255)
    g.add_color_stop_rgba(1, 1, 1, 1, 0)
    dc.set_source(g)
    dc.rectangle(0, y, w, SWEEP_H)
    dc.fill()
    dc.restore()
