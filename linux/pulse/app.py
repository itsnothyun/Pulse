"""The desktop widget: a borderless, draggable GTK 3 window around PulseView. Port of windows/Pulse/WidgetWindow.cs.

GTK 3 on purpose (GTK 4 dropped window positioning and keep-above). Under GNOME Wayland we run
through XWayland so remembered position, Always on Top and all-workspaces behave as on the other
platforms. Set PULSE_NATIVE_WAYLAND=1 to opt out.

There is no global hotkey (X11 key grabs clash with desktop shortcuts and don't exist under Wayland):
the way back from click-through is the tray icon, or `pulse --click-through`, which you can bind to
Ctrl+Alt+P in your desktop's keyboard settings.
"""
import os

if os.environ.get("DISPLAY") and not os.environ.get("PULSE_NATIVE_WAYLAND"):
    os.environ.setdefault("GDK_BACKEND", "x11")

import fcntl
import math
import shutil
import signal
import subprocess
import time

import cairo
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from . import geometry as G  # noqa: E402
from . import loops, settings, tray  # noqa: E402
from . import pixelfont as px  # noqa: E402
from .alerts import Alerts  # noqa: E402
from .gallery import Gallery  # noqa: E402
from .sampler import Sampler  # noqa: E402
from .settings import OPACITIES, SCALES  # noqa: E402
from .view import FULL, VIEWS, PulseView, next_size, title  # noqa: E402

DRAG_PX = 3
MONITORS = (["gnome-system-monitor"], ["mate-system-monitor"], ["plasma-systemmonitor"], ["ksysguard"],
            ["x-terminal-emulator", "-e", "htop"], ["x-terminal-emulator", "-e", "top"])
TOOLTIP_CSS = b"""
window { background: transparent; }
tooltip, tooltip.background { background-color: #090909; border: 1px solid rgba(242, 242, 237, 0.22); border-radius: 0; }
tooltip label { color: #f2f2ed; font-family: "DejaVu Sans Mono", monospace; font-size: 11.5px; }
"""


class WidgetWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="Pulse")
        self.settings = settings.Settings.load()
        self.sampler = Sampler(post=GLib.idle_add)
        self.sampler.limits_enabled = self.settings.limits
        self.view = PulseView(self.sampler, self.settings.size)
        self.view.claude_open = self.settings.claude_open
        self.motion = Gtk.Settings.get_default().get_property("gtk-enable-animations")
        self.view.live_rainbow = self.motion        # the ULTRA spectrum drifts in the overlay; still otherwise
        self.zoom = self.settings.scale
        self._t0 = time.monotonic()
        self._base = None
        self._view_h = 0
        self._dirty = True
        self._anim_id = 0
        self._tweens = {}
        self._press = None                          # (x_root, y_root, win_x, win_y, x, y) of a left press
        self._dragging = False
        self._resize = None                         # (x_root, zoom, width, from_left) while drag-resizing
        self._morph = None
        self._pop = 1.0
        self._scroll = 0.0
        self._changing = False
        self._syncing = False
        self._win_w = self._win_h = 0
        self._panel = (0, 0)                        # the panel's size in window pixels (zoom applied)
        self._loaded = False
        self._save_id = 0
        self.click_through = False
        self.gallery = None

        self.set_decorated(False)
        self.set_resizable(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        self.set_keep_above(self.settings.on_top)
        self.set_icon_name("pulse")
        self.set_app_paintable(True)
        visual = self.get_screen().get_rgba_visual()
        if visual is not None:
            self.set_visual(visual)
        css = Gtk.CssProvider()
        css.load_from_data(TOOLTIP_CSS)
        Gtk.StyleContext.add_provider_for_screen(self.get_screen(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        self.area = Gtk.DrawingArea()
        self.area.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK
                             | Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.BUTTON1_MOTION_MASK
                             | Gdk.EventMask.SCROLL_MASK | Gdk.EventMask.SMOOTH_SCROLL_MASK
                             | Gdk.EventMask.LEAVE_NOTIFY_MASK)
        self.area.connect("draw", self._on_draw)
        self.area.connect("button-press-event", self._on_press)
        self.area.connect("motion-notify-event", self._on_motion)
        self.area.connect("button-release-event", self._on_release)
        self.area.connect("scroll-event", self._on_scroll)
        self.area.set_has_tooltip(True)
        self.area.connect("query-tooltip", self._on_query_tooltip)
        self.add(self.area)

        self.tray = tray.Tray(self.toggle_shown, self.open_gallery, lambda: self.set_click_through(not self.click_through),
                              lambda: self.set_alerts(not self.settings.alerts), self.destroy)
        self.alerts = Alerts(tray.notify, self.settings.alerts)

        self.menu = self._build_menu()
        self._relayout()
        self._place()
        self.connect("configure-event", self._on_configure)
        self.connect("destroy", self._on_destroy)
        self.get_screen().connect("monitors-changed", lambda *_: GLib.idle_add(self._place))
        self.sampler.updated.append(self._on_updated)
        GLib.timeout_add_seconds(1, self._on_second)

        self.set_opacity(0)
        self.show_all()
        self.stick()
        self._loaded = True
        self._fade_to(self.settings.opacity, 0.35)
        self._sync_tray()
        self._ensure_anim()

    # ---------- tweens ----------

    def _tween(self, name, dur, step, done=None, ease=G.ease_out_quart):
        """Runs step(eased 0..1) every frame for `dur` seconds, then done(). A new tween of the same name replaces it."""
        self._cancel(name)
        start = time.monotonic()

        def tick():
            p = min((time.monotonic() - start) / dur, 1.0)
            step(ease(p))
            if p < 1.0:
                return True
            self._tweens.pop(name, None)
            if done is not None:
                done()
            return False
        self._tweens[name] = GLib.timeout_add(16, tick)

    def _cancel(self, name):
        tid = self._tweens.pop(name, None)
        if tid:
            GLib.source_remove(tid)

    def _fade_to(self, to, dur, done=None):
        if not self.motion:
            self._cancel("fade")
            self.set_opacity(to)
            if done is not None:
                done()
            return
        start = self.get_opacity()
        self._tween("fade", dur, lambda p: self.set_opacity(G.lerp(start, to, p)), done, G.ease_out_quad)

    # ---------- monitors and positions ----------

    def _monitors(self):
        d = Gdk.Display.get_default()
        return [d.get_monitor(i) for i in range(d.get_n_monitors())]

    def _monitor_rects(self):
        return [(g.x, g.y, g.width, g.height) for g in (m.get_geometry() for m in self._monitors())]

    def work_area(self):
        """The work area of the monitor the widget is on."""
        x, y = self.get_position()
        d = Gdk.Display.get_default()
        mon = d.get_monitor_at_point(int(x + self._win_w / 2), int(y + self._win_h / 2)) or d.get_primary_monitor()
        wa = (mon or self._monitors()[0]).get_workarea()
        return wa.x, wa.y, wa.width, wa.height

    def _right_anchored(self):
        return G.right_anchored(self.get_position()[0], self._win_w, self.work_area())

    def _key(self, size):
        return G.layout_key(self._monitor_rects(), size)

    def _saved(self, size):
        p = self.settings.positions.get(self._key(size))
        if p and G.on_screen(self._monitor_rects(), p[0], p[1]):
            return int(p[0]), int(p[1])
        return None

    def _place(self):
        s = self.settings
        p = self._saved(self.view.size)
        if p is None and s.left is not None and s.top is not None and G.on_screen(self._monitor_rects(), s.left, s.top):
            p = int(s.left), int(s.top)
        if p is None:
            mon = Gdk.Display.get_default().get_primary_monitor() or self._monitors()[0]
            wa = mon.get_workarea()
            p = wa.x + wa.width - self._win_w - 24, wa.y + 24
        self.move(*p)
        return False

    def _busy(self):
        """Mid-animation positions are temporary: don't remember them."""
        return self._morph is not None or any(n in self._tweens for n in ("glide", "hop", "pop"))

    def _save_position(self):
        self._save_id = 0
        if not self._loaded or self._busy() or not self.get_visible():
            return False
        x, y = self.get_position()
        self.settings.left, self.settings.top = x, y
        self.settings.positions[self._key(self.view.size)] = [x, y]
        self.settings.save()
        return False

    def _on_configure(self, *_):
        if self._loaded and not self._dragging:
            if self._save_id:
                GLib.source_remove(self._save_id)
            self._save_id = GLib.timeout_add(400, self._save_position)
        return False

    def _snap(self):
        """After a drag, a widget dropped near an edge or corner of its monitor glides onto it."""
        x, y = self.get_position()
        l, t = G.snap(x, y, self._win_w, self._win_h, self.work_area())
        if (l, t) == (x, y):
            self._save_position()
        else:
            self._glide(l, t, self._save_position)

    def _glide(self, l, t, done=None):
        if not self.motion:
            self.move(l, t)
            if done is not None:
                done()
            return
        x0, y0 = self.get_position()
        self._tween("glide", G.GLIDE_TIME, lambda p: self.move(round(G.lerp(x0, l, p)), round(G.lerp(y0, t, p))), done)

    def _on_destroy(self, *_):
        self._end_morph()
        for name in list(self._tweens):
            self._cancel(name)
        self._save_position()
        self.tray.dispose()
        Gtk.main_quit()

    # ---------- sizing and morphing ----------

    def _content_size(self):
        w, h = self.view.measure()
        return math.ceil(w * self.zoom), math.ceil(h * self.zoom)

    def _resize_to(self, w, h, right):
        """Sizes the window; a right-anchored widget keeps its right edge where it was."""
        old_w = self._win_w
        self._win_w, self._win_h = w, h
        self.area.set_size_request(w, h)
        self.resize(w, h)
        if self._loaded and old_w and old_w != w and right:
            x, y = self.get_position()
            self.move(x + old_w - w, y)

    def _relayout(self, right=None):
        if self._morph is not None:
            return                                  # the morph sizes the window when it lands
        self._panel = self._content_size()
        if self._panel != (self._win_w, self._win_h):
            self._resize_to(*self._panel, self._right_anchored() if right is None and self._loaded else bool(right))

    def _morph_to(self, change, crossfade=True):
        """Applies a change that alters the widget's size and morphs the outline from the old shape to the new one:
        the window briefly holds the larger of the two, a rounded clip eases between them and the old frame fades out.
        (WPF animates a clip geometry; here the same clip is recomputed in the draw handler each frame.)"""
        self._end_morph()
        if not self._loaded or not self.motion or not self.get_visible():
            self._apply(change)
            self._relayout()
            GLib.idle_add(self._save_position)
            return

        if self._dirty or self._base is None:
            self._render_base()
        old_w, old_h = self._panel
        old_zoom, old_r = self.zoom, self.view.radius * self.zoom
        ghost = self._base if crossfade else None
        right = self._right_anchored()
        self._apply(change)
        self._render_base()
        new_w, new_h = self._content_size()
        new_r = self.view.radius * self.zoom
        total_w, total_h = max(old_w, new_w), max(old_h, new_h)
        self._morph = {"old": (old_w, old_h, old_r), "new": (new_w, new_h, new_r), "right": right, "ghost": ghost,
                       "k0": old_zoom / self.zoom, "p": 0.0, "fade": 1.0 if ghost else 0.0, "t0": time.monotonic()}
        self._panel = (new_w, new_h)
        self._resize_to(total_w, total_h, right)
        self.area.trigger_tooltip_query()           # hides an open tooltip: none while morphing

        def step(p):
            m = self._morph
            if m is None:
                return
            m["p"] = p
            m["fade"] = 0.0 if ghost is None else 1 - G.ease_out_quad((time.monotonic() - m["t0"]) / 0.2)
            self.area.queue_draw()
        self._tween("morph", G.MORPH_TIME, step, self._end_morph)

    def _end_morph(self):
        m = self._morph
        if m is None:
            return
        self._cancel("morph")
        self._morph = None
        self._resize_to(*self._panel, m["right"])
        self._relayout()                            # the data may have moved on while it ran
        self.area.queue_draw()
        GLib.idle_add(self._save_position)

    def _apply(self, change):
        """Runs a view change without the sampler callbacks it triggers resizing the window halfway through."""
        self._changing = True
        try:
            change()
        finally:
            self._changing = False
        self._dirty = True

    def _hop(self, change, to):
        """Switching to a view that lives somewhere else: fade out here, reappear there."""
        self._end_morph()

        def arrive():
            self._apply(change)
            self._relayout(right=False)
            self.move(*to)
            if self.motion:
                self._tween("pop", 0.24, lambda p: self._set_pop(G.lerp(0.97, 1.0, p)), lambda: self._set_pop(1.0))
            self._fade_to(self.settings.opacity, 0.22, lambda: GLib.idle_add(self._save_position))
        if not self.motion:
            arrive()
            return
        self._cancel("fade")
        start = self.get_opacity()
        self._tween("hop", 0.13, lambda p: self.set_opacity(G.lerp(start, 0, p)), arrive, G.ease_out_quad)

    def _set_pop(self, k):
        self._pop = k
        self.area.queue_draw()

    # ---------- views ----------

    def set_size(self, size):
        if size == self.view.size:
            return
        self._save_position()                       # the view we're leaving keeps its spot

        def apply():
            if size != FULL:
                self.sampler.set_top_mode(None)
            self.view.size = size

        p = self._saved(size)
        x, y = self.get_position()
        if p is not None and (abs(p[0] - x) > 4 or abs(p[1] - y) > 4):
            self._hop(apply, p)
        else:
            self._morph_to(apply)
        self.settings.size = size
        self.settings.save()
        self._syncing = True
        self.size_items[size].set_active(True)
        self._syncing = False

    def open_gallery(self):
        if not self.get_visible():
            self.toggle_shown()
        if self.gallery is not None:
            self.gallery.present()
            return
        self.gallery = Gallery(self.sampler, self.view.size, self.set_size, self.work_area(), self.motion)
        self.gallery.connect("destroy", lambda *_: setattr(self, "gallery", None))

    # ---------- scale ----------

    def set_scale(self, scale, save=True):
        self.zoom = scale
        self._dirty = True
        if not save:
            return
        self.settings.scale = scale
        self.settings.save()
        self._syncing = True
        if scale in self.scale_items:
            self.scale_items[scale].set_active(True)
        self._syncing = False

    def scale_to(self, scale):
        if scale != self.zoom or scale != self.settings.scale:
            self._morph_to(lambda: self.set_scale(scale), crossfade=False)

    def _on_scroll(self, _w, e):
        """Ctrl + wheel steps through the scales."""
        if not e.state & Gdk.ModifierType.CONTROL_MASK or self._resize is not None:
            return False
        if e.direction == Gdk.ScrollDirection.UP:
            d = 1
        elif e.direction == Gdk.ScrollDirection.DOWN:
            d = -1
        elif e.direction == Gdk.ScrollDirection.SMOOTH:
            self._scroll -= e.delta_y                # touchpads send many small deltas: one step per notch's worth
            if abs(self._scroll) < 1:
                return True
            d, self._scroll = (1 if self._scroll > 0 else -1), 0.0
        else:
            return False
        self.scale_to(G.step_scale(self.zoom, d))
        return True

    # ---------- data and drawing ----------

    def _on_second(self):
        self.sampler.sample()
        return True

    def _on_updated(self):
        if self._changing:
            return
        self._relayout()
        self._invalidate()
        self.alerts.check(self.sampler)

    def _invalidate(self):
        self._dirty = True
        self.area.queue_draw()
        self._ensure_anim()

    def _render_base(self):
        f = self.get_scale_factor()
        w, h = self.view.measure()
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, math.ceil(w * self.zoom * f), math.ceil(h * self.zoom * f))
        surf.set_device_scale(f, f)
        dc = cairo.Context(surf)
        dc.scale(self.zoom, self.zoom)
        self._view_h = self.view.paint(dc)
        self._base = surf
        self._dirty = False

    def _paint_panel(self, cr, h):
        cr.set_source_surface(self._base, 0, 0)
        cr.paint()
        cr.save()
        cr.scale(self.zoom, self.zoom)
        loops.draw(cr, self.view, time.monotonic() - self._t0, h, self.motion)
        cr.restore()

    def _on_draw(self, _widget, cr):
        if self._dirty or self._base is None:
            self._render_base()
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        h = self._view_h
        m = self._morph
        if m is None:
            if self._pop != 1.0:                    # a hop lands at 97% and settles
                w = self._panel[0]
                cr.translate(w / 2, 0)
                cr.scale(self._pop, self._pop)
                cr.translate(-w / 2, 0)
            self._paint_panel(cr, h)
            return False

        total_w = self._win_w
        x, w, hh, r = G.morph_frame(m["old"], m["new"], total_w, m["right"], m["p"])
        cr.save()
        px.round_rect(cr, x, 0, w, hh, r)
        cr.clip()
        cr.save()
        new_w = m["new"][0]
        k = G.lerp(m["k0"], 1.0, m["p"])           # content starts at its old scale and grows into the new one
        if m["right"]:
            cr.translate(total_w, 0)
            cr.scale(k, k)
            cr.translate(-new_w, 0)
        else:
            cr.scale(k, k)
        self._paint_panel(cr, h)
        cr.restore()
        if m["ghost"] is not None and m["fade"] > 0:
            old_w = m["old"][0]
            cr.set_source_surface(m["ghost"], total_w - old_w if m["right"] else 0, 0)
            cr.paint_with_alpha(m["fade"])
        cr.restore()
        return False

    def _animating(self):
        if self.view.tw.active:
            return 33
        if self.motion and not self.view.is_mini:
            return 50                                  # scanner, sweep and the ULTRA drift: base frame stays cached
        if self.motion and self.view.pip_pos is not None:
            return 50
        return 0

    def _ensure_anim(self):
        if not self._anim_id and self._animating():
            self._anim_id = GLib.timeout_add(self._animating(), self._anim)

    def _anim(self):
        if self.view.tw.active:
            self._dirty = True                         # bars are tweening: repaint the base too
        if self._animating() and self.get_visible():
            self.area.queue_draw()
            return True
        self._anim_id = 0
        return False

    # ---------- mouse ----------

    def _to_view(self, x, y):
        """Window pixels -> view units."""
        return x / self.zoom, y / self.zoom

    def _grip(self, x, y):
        return self._morph is None and G.in_grip(x, y, self._win_w, self._win_h, self._right_anchored())

    def _set_cursor(self, name):
        win = self.area.get_window()
        if win is not None:
            win.set_cursor(Gdk.Cursor.new_from_name(self.get_display(), name) if name else None)

    def _on_press(self, _w, e):
        if e.type != Gdk.EventType.BUTTON_PRESS:
            return True                                # ignore the double-click synthesis
        if e.button == 1:
            if self._grip(e.x, e.y):
                self._resize = (e.x_root, self.zoom, self._win_w, self._right_anchored())
                return True
            x, y = self.get_position()
            self._press = (e.x_root, e.y_root, x, y, e.x, e.y)
            self._dragging = False
            return True
        if e.button == 3:
            # without a reachable tray icon, hiding would strand the widget (relaunching `pulse` still brings it back)
            self.hide_item.set_sensitive(self.tray.available)
            self.menu.popup_at_pointer(e)
            return True
        return False

    def _on_motion(self, _w, e):
        if self._resize is not None:
            x0, z0, w0, from_left = self._resize
            dx = e.x_root - x0
            if from_left:
                dx = -dx
            self.set_scale(max(SCALES[0] * 0.9, min(SCALES[-1] * 1.05, z0 * (w0 + dx) / w0)), save=False)
            self._relayout(right=from_left)            # live: the window follows the pointer
            self.area.queue_draw()
            return True
        if self._press is not None:
            px0, py0, wx, wy, _x, _y = self._press
            if not self._dragging and (abs(e.x_root - px0) > DRAG_PX or abs(e.y_root - py0) > DRAG_PX):
                self._dragging = True
                self._cancel("glide")
            if self._dragging:
                self.move(round(wx + e.x_root - px0), round(wy + e.y_root - py0))
            return True
        self._set_cursor(("nesw-resize" if self._right_anchored() else "nwse-resize") if self._grip(e.x, e.y) else None)
        return False

    def _on_release(self, _w, e):
        if e.button != 1:
            return False
        if self._resize is not None:
            self._resize = None
            self._set_cursor(None)
            self.scale_to(G.nearest_scale(self.zoom))  # ease onto the closest snap point
            return True
        if self._press is None:
            return True
        press, dragging = self._press, self._dragging
        self._press, self._dragging = None, False
        if dragging:
            self._snap()
            return True
        vx, vy = self._to_view(press[4], press[5])
        if vy < self.view.header_bottom:
            self.set_size(next_size(self.view.size))   # a click (not a drag) on the header changes view
        elif (row := self.view.row_at(vy)) is not None:
            self._morph_to(lambda: self.sampler.set_top_mode(None if self.sampler.top_mode == row else row))
        elif self.view.claude_at(vx, vy):
            def toggle():
                self.view.claude_open = self.settings.claude_open = not self.view.claude_open
                self.settings.save()
            self._morph_to(toggle)
        return True

    # ---------- tooltip ----------

    def _on_query_tooltip(self, _w, x, y, keyboard, tooltip):
        """The exact value under the pointer (GTK's own hover delay applies)."""
        if keyboard or self._morph is not None or self._resize is not None or self._press is not None or self._grip(x, y):
            return False
        hit = self.view.tip_at(*self._to_view(x, y))
        if hit is None:
            return False
        text, (rx, ry, rw, rh) = hit
        tooltip.set_text(text)
        area = Gdk.Rectangle()
        area.x, area.y = int(rx * self.zoom), int(ry * self.zoom)
        area.width, area.height = max(1, int(rw * self.zoom)), max(1, int(rh * self.zoom))
        tooltip.set_tip_area(area)
        return True

    # ---------- click-through, opacity, alerts, tray ----------

    def set_click_through(self, on):
        self.click_through = on
        try:
            self.input_shape_combine_region(cairo.Region() if on else None)   # empty region: clicks fall through
        except (TypeError, AttributeError):
            self.click_through = False
        if self.click_through:
            way_back = "the tray icon or " if self.tray.available else ""
            tray.notify("Click-through on", f"Clicks now pass through Pulse. Use {way_back}`pulse --click-through` to turn it off.")
        self._syncing = True
        self.through_item.set_active(self.click_through)
        self._syncing = False
        self._sync_tray()

    def set_opacity_setting(self, o):
        self.settings.opacity = o
        self.settings.save()
        self._fade_to(o, 0.2)
        self._syncing = True
        self.opacity_items[o].set_active(True)
        self._syncing = False

    def set_alerts(self, on):
        self.settings.alerts = self.alerts.enabled = on
        self.settings.save()
        self._syncing = True
        self.alerts_item.set_active(on)
        self._syncing = False
        self._sync_tray()

    def _set_limits(self, on):
        self.settings.limits = self.sampler.limits_enabled = on
        self.settings.save()
        self.sampler.sample()

    def toggle_shown(self):
        if self.get_visible():
            pos = self.get_position()

            def hide():
                self.hide()
                self.move(*pos)
                self._sync_tray()
            self._fade_to(0, 0.15, hide)
        else:
            self.show_widget()
        self._sync_tray()

    def show_widget(self):
        if self.get_visible():
            self.present()
            return
        x, y = self.get_position()
        self.show()
        self.move(x, y)
        self.stick()
        self.set_keep_above(self.settings.on_top)
        self._fade_to(self.settings.opacity, 0.25)
        self._ensure_anim()
        self._sync_tray()

    def _sync_tray(self):
        self.tray.sync(self.get_visible(), self.click_through, self.settings.alerts)
        return False

    # ---------- menu ----------

    def _radio_menu(self, label, choices, current, on_pick):
        """A submenu of radio items; returns (menu item, {value: radio item})."""
        top = Gtk.MenuItem(label=label)
        sub = Gtk.Menu()
        items, group = {}, None
        for value, text in choices:
            item = Gtk.RadioMenuItem.new_with_label_from_widget(group, text)
            group = item if group is None else group
            item.set_active(value == current)
            item.connect("toggled", lambda it, v=value: (not self._syncing and it.get_active()) and on_pick(v))
            items[value] = item
            sub.append(item)
        top.set_submenu(sub)
        return top, items

    def _check(self, label, active, on_toggle):
        item = Gtk.CheckMenuItem(label=label)
        item.set_active(active)
        item.connect("toggled", lambda it: self._syncing or on_toggle(it.get_active()))
        return item

    def _build_menu(self):
        menu = Gtk.Menu()
        view_item, self.size_items = self._radio_menu("View", [(v, title(v)) for v in VIEWS], self.view.size, self.set_size)
        choose = Gtk.MenuItem(label="Choose View…")
        choose.connect("activate", lambda _i: self.open_gallery())
        view_sub = view_item.get_submenu()
        view_sub.append(Gtk.SeparatorMenuItem())
        view_sub.append(choose)
        scale_item, self.scale_items = self._radio_menu("Scale", [(s, f"{s * 100:.0f}%") for s in SCALES],
                                                         G.nearest_scale(self.zoom), self.scale_to)
        current_o = min(OPACITIES, key=lambda o: abs(o - self.settings.opacity))
        opacity_item, self.opacity_items = self._radio_menu("Opacity", [(o, f"{o * 100:.0f}%") for o in OPACITIES],
                                                             current_o, self.set_opacity_setting)

        on_top = self._check("Always on Top", self.settings.on_top, self._toggle_on_top)
        self.through_item = self._check("Click-through", False, self.set_click_through)
        self.alerts_item = self._check("Alerts", self.settings.alerts, self.set_alerts)
        limits = self._check("Plan Limits (online)", self.settings.limits, self._set_limits)
        login = Gtk.CheckMenuItem(label="Launch at Login")
        login.set_active(settings.launch_at_login())
        login.connect("toggled", self._toggle_login)

        monitor = Gtk.MenuItem(label="Open System Monitor")
        monitor.connect("activate", lambda _i: self._open_monitor())
        self.hide_item = Gtk.MenuItem(label="Hide to Tray")
        self.hide_item.connect("activate", lambda _i: self.toggle_shown())
        quit_item = Gtk.MenuItem(label="Quit Pulse")
        quit_item.connect("activate", lambda _i: self.destroy())

        for item in (view_item, scale_item, opacity_item, Gtk.SeparatorMenuItem(), on_top, self.through_item,
                     self.alerts_item, limits, login, Gtk.SeparatorMenuItem(), monitor, self.hide_item, quit_item):
            menu.append(item)
        menu.show_all()
        return menu

    def _toggle_on_top(self, on):
        self.settings.on_top = on
        self.set_keep_above(on)
        self.settings.save()

    def _toggle_login(self, item):
        try:
            settings.set_launch_at_login(item.get_active())
        except OSError:
            item.set_active(settings.launch_at_login())

    @staticmethod
    def _open_monitor():
        for cmd in MONITORS:
            if shutil.which(cmd[0]):
                try:
                    subprocess.Popen(cmd, start_new_session=True)
                    return
                except OSError:
                    pass


def _lock_path():
    return os.path.join(os.environ.get("XDG_RUNTIME_DIR") or "/tmp", "pulse-widget.lock")


def _signal_running(sig):
    """Hands a request to the running widget (its pid is in the lock file)."""
    try:
        with open(_lock_path()) as f:
            os.kill(int(f.read().strip()), sig)
        return True
    except (OSError, ValueError):
        return False


def run(argv=()):
    if "--click-through" in argv:
        return 0 if _signal_running(signal.SIGUSR1) else 1
    fd = os.open(_lock_path(), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        _signal_running(signal.SIGUSR2)            # already running: bring it back (hidden or not)
        return 0
    os.ftruncate(fd, 0)
    os.write(fd, str(os.getpid()).encode())
    win = WidgetWindow()
    for sig in (signal.SIGINT, signal.SIGTERM):
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, sig, win.destroy)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGUSR1, lambda: win.set_click_through(not win.click_through) or True)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGUSR2, lambda: win.show_widget() or True)
    Gtk.main()
    return 0
