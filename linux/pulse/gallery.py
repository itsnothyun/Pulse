"""Pick a view the way you'd pick a phone widget: every view, live and at its true relative size.
Click one to switch; Esc or a click elsewhere closes. Port of windows/Pulse/Gallery.cs.

Previews are painted at full size into an offscreen surface and drawn at half size with smooth filtering --
the pixel font drawn directly at 0.5x would drop half its dots.
"""
import math
import time

import cairo
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from . import geometry as G  # noqa: E402
from . import pixelfont as px  # noqa: E402
from .pixelfont import Ink  # noqa: E402
from .view import PulseView, title  # noqa: E402

LIFT, LIFT_TIME = 1.025, 0.14


class Gallery(Gtk.Window):
    def __init__(self, sampler, current, pick, work_area, motion=True):
        super().__init__(title="Pulse views")
        self.sampler = sampler
        self.current = current
        self.pick = pick
        self.motion = motion
        self.closing = False
        self.hover = None
        self.lift = {v: 1.0 for v in G.GALLERY_ORDER}
        self._lift_id = 0
        self._open_t = time.monotonic()
        self._open_id = 0
        self.previews = {}
        for v in G.GALLERY_ORDER:
            p = PulseView(sampler, v)
            p.claude_open = False
            self.previews[v] = p

        self.set_decorated(False)
        self.set_resizable(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_keep_above(True)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.set_app_paintable(True)
        visual = self.get_screen().get_rgba_visual()
        if visual is not None:
            self.set_visual(visual)

        self.area = Gtk.DrawingArea()
        self.area.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK
                             | Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK)
        self.area.connect("draw", self._on_draw)
        self.area.connect("motion-notify-event", self._on_motion)
        self.area.connect("leave-notify-event", lambda *_: self._set_hover(None))
        self.area.connect("button-release-event", self._on_release)
        self.add(self.area)
        self.connect("key-press-event", self._on_key)
        self.connect("focus-out-event", lambda *_: self.dismiss())
        self.connect("destroy", lambda *_: self._detach())

        self._layout()
        wa = work_area
        self.move(int(wa[0] + (wa[2] - self.w) / 2), int(wa[1] + (wa[3] - self.h) / 2))
        self._refresh = self._on_updated
        sampler.updated.append(self._refresh)

        self.set_opacity(0 if motion else 1)
        self.show_all()
        self.present()
        if motion:
            self._open_id = GLib.timeout_add(16, self._opening)

    # ---------- layout ----------

    def _layout(self):
        sizes = {v: p.measure() for v, p in self.previews.items()}
        w, h, self.cards = G.gallery_layout(sizes)
        self.w, self.h = math.ceil(w), math.ceil(h)
        self.area.set_size_request(self.w, self.h)

    def _on_updated(self):
        old = (self.w, self.h)
        self._layout()
        if (self.w, self.h) != old:
            self.resize(self.w, self.h)
        self.area.queue_draw()

    def _detach(self):
        if self._refresh in self.sampler.updated:
            self.sampler.updated.remove(self._refresh)

    def _card_at(self, x, y):
        for v, (cx, cy, cw, ch) in self.cards.items():
            if cx - G.TILE_MARGIN <= x <= cx + cw + G.TILE_MARGIN and cy - G.TILE_MARGIN <= y <= cy + ch + G.LABEL_GAP + 7 + G.TILE_MARGIN:
                return v
        return None

    # ---------- motion ----------

    def _opening(self):
        p = (time.monotonic() - self._open_t)
        self.set_opacity(G.ease_out_quart(p / 0.18))
        self.area.queue_draw()
        if p >= 0.22:
            self._open_id = 0
            self.set_opacity(1)
            return False
        return True

    def _set_hover(self, v):
        if v == self.hover:
            return False
        self.hover = v
        win = self.get_window()
        if win is not None:
            win.set_cursor(Gdk.Cursor.new_from_name(self.get_display(), "pointer") if v else None)
        if not self.motion:
            for k in self.lift:
                self.lift[k] = LIFT if k == v else 1.0
            self.area.queue_draw()
        elif not self._lift_id:
            self._lift_last = time.monotonic()
            self._lift_id = GLib.timeout_add(16, self._lifting)
        return False

    def _lifting(self):
        now = time.monotonic()
        step = (now - self._lift_last) / LIFT_TIME * (LIFT - 1)
        self._lift_last = now
        moving = False
        for k, cur in self.lift.items():
            target = LIFT if k == self.hover else 1.0
            if cur != target:
                cur = min(target, cur + step) if target > cur else max(target, cur - step)
                self.lift[k] = cur
                moving = moving or cur != target
        self.area.queue_draw()
        if not moving:
            self._lift_id = 0
        return moving

    def _on_motion(self, _w, e):
        self._set_hover(self._card_at(e.x, e.y))
        return True

    def _on_release(self, _w, e):
        if e.button == 1 and (v := self._card_at(e.x, e.y)) is not None:
            self.dismiss()
            self.pick(v)
        return True

    def _on_key(self, _w, e):
        if e.keyval == Gdk.KEY_Escape:
            self.dismiss()
            return True
        return False

    def dismiss(self):
        if self.closing:
            return
        self.closing = True
        self._detach()
        if not self.motion:
            self.destroy()
            return
        start, from_o = time.monotonic(), self.get_opacity()

        def fade():
            p = (time.monotonic() - start) / 0.12
            self.set_opacity(max(0.0, from_o * (1 - p)))
            if p >= 1:
                self.destroy()
                return False
            return True
        GLib.timeout_add(16, fade)

    # ---------- drawing ----------

    def _on_draw(self, _w, cr):
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)

        if self._open_id:                                   # grows from 97% while it fades in
            k = G.lerp(0.97, 1.0, G.ease_out_quart((time.monotonic() - self._open_t) / 0.22))
            cr.translate(self.w / 2, self.h / 2)
            cr.scale(k, k)
            cr.translate(-self.w / 2, -self.h / 2)

        px.round_rect(cr, 0, 0, self.w, self.h, 18)
        cr.set_source_rgba(*Ink.BG)
        cr.fill()
        px.round_rect(cr, 0.5, 0.5, self.w - 1, self.h - 1, 18)
        cr.set_source_rgba(*Ink.alpha(Ink.ON, 0.16))
        cr.set_line_width(1)
        cr.stroke()

        cr.set_antialias(cairo.ANTIALIAS_NONE)
        hx, hy = 1 + G.G_PAD[0] + G.HEAD_INSET, 1 + G.G_PAD[1]
        px.draw(cr, "CHOOSE A VIEW", hx, hy, 2, Ink.ON)
        px.draw_right(cr, "ESC TO CLOSE", self.w - 1 - G.G_PAD[2] - G.HEAD_INSET, hy + 3.5, 1, Ink.DIM)

        f = self.get_scale_factor()
        inset = G.CARD_PAD + G.CARD_BORDER
        for v, (cx, cy, cw, ch) in self.cards.items():
            k = self.lift[v]
            cr.save()
            cr.translate(cx + cw / 2, cy + ch / 2)
            cr.scale(k, k)
            cr.translate(-(cx + cw / 2), -(cy + ch / 2))
            border = Ink.MID if v == self.current else Ink.LINE if v == self.hover else None
            if border is not None:
                cr.set_antialias(cairo.ANTIALIAS_DEFAULT)
                px.round_rect(cr, cx + 0.75, cy + 0.75, cw - 1.5, ch - 1.5, 14 * G.PREVIEW + 4)
                cr.set_source_rgba(*border)
                cr.set_line_width(1.5)
                cr.stroke()
            self._preview(cr, self.previews[v], cx + inset, cy + inset, f)
            cr.restore()
            cr.set_antialias(cairo.ANTIALIAS_NONE)
            px.draw(cr, title(v), cx + G.LABEL_INDENT, cy + ch + G.LABEL_GAP, 1, Ink.ON if v == self.current else Ink.DIM)
        return False

    @staticmethod
    def _preview(cr, view, x, y, f):
        w, h = view.measure()
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, math.ceil(w * f), math.ceil(h * f))
        ctx = cairo.Context(surf)
        ctx.scale(f, f)
        view.paint(ctx)
        cr.save()
        cr.translate(x, y)
        cr.scale(G.PREVIEW / f, G.PREVIEW / f)              # full-size device pixels shown at half size
        cr.set_source_surface(surf, 0, 0)
        cr.get_source().set_filter(cairo.FILTER_GOOD)
        cr.paint()
        cr.restore()
