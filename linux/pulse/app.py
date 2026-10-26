"""The desktop widget: a borderless, draggable GTK 3 window around PulseView.

GTK 3 on purpose (GTK 4 dropped window positioning and keep-above). Under GNOME Wayland we run
through XWayland so remembered position, Always on Top and all-workspaces behave as on the other
platforms. Set PULSE_NATIVE_WAYLAND=1 to opt out.
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

from . import loops, settings  # noqa: E402
from .sampler import Sampler  # noqa: E402
from .view import COMPACT, FULL, MINI, PulseView, next_size  # noqa: E402

DRAG_PX = 3
MONITORS = (["gnome-system-monitor"], ["mate-system-monitor"], ["plasma-systemmonitor"], ["ksysguard"],
            ["x-terminal-emulator", "-e", "htop"], ["x-terminal-emulator", "-e", "top"])


class WidgetWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="Pulse")
        self.settings = settings.Settings.load()
        self.sampler = Sampler(post=GLib.idle_add)
        self.view = PulseView(self.sampler, self.settings.size)
        self.motion = Gtk.Settings.get_default().get_property("gtk-enable-animations")
        self._t0 = time.monotonic()
        self._base = None
        self._dirty = True
        self._anim_id = 0
        self._press = None
        self._syncing = False
        self._size_w = self._size_h = 0
        self._loaded = False
        self._save_id = 0

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
        css.load_from_data(b"window { background: transparent; }")
        Gtk.StyleContext.add_provider_for_screen(self.get_screen(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        self.area = Gtk.DrawingArea()
        self.area.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK
                             | Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.BUTTON1_MOTION_MASK)
        self.area.connect("draw", self._on_draw)
        self.area.connect("button-press-event", self._on_press)
        self.area.connect("motion-notify-event", self._on_motion)
        self.area.connect("button-release-event", self._on_release)
        self.add(self.area)

        self.menu = self._build_menu()
        self._apply_size_request()
        self._place()
        self.connect("configure-event", self._on_configure)
        self.connect("destroy", self._on_destroy)
        self.sampler.updated.append(self._on_updated)
        GLib.timeout_add_seconds(1, self._on_second)

        self.set_opacity(0)
        self.show_all()
        self.stick()
        self._loaded = True
        self._fade_start = time.monotonic()
        GLib.timeout_add(16, self._fade)
        self._ensure_anim()

    # ---------- placement and sizing ----------

    def _apply_size_request(self):
        w, h = self.view.measure()
        self._size_w, self._size_h = math.ceil(w), math.ceil(h)
        self.area.set_size_request(self._size_w, self._size_h)

    def _monitors(self):
        d = Gdk.Display.get_default()
        return [d.get_monitor(i) for i in range(d.get_n_monitors())]

    def _place(self):
        mons = self._monitors()
        s = self.settings
        if s.left is not None and s.top is not None and any(
                m.get_geometry().x <= s.left + 40 < m.get_geometry().x + m.get_geometry().width
                and m.get_geometry().y <= s.top + 20 < m.get_geometry().y + m.get_geometry().height for m in mons):
            self.move(int(s.left), int(s.top))
            return
        mon = Gdk.Display.get_default().get_primary_monitor() or mons[0]
        wa = mon.get_workarea()
        self.move(wa.x + wa.width - self._size_w - 24, wa.y + 24)

    def _relayout(self):
        old_w = self._size_w
        self._apply_size_request()
        if self._loaded and old_w and old_w != self._size_w:
            # right-hand widgets grow and shrink leftward, so the edge you placed stays put
            x, y = self.get_position()
            mon = Gdk.Display.get_default().get_monitor_at_point(x, y)
            wa = mon.get_workarea()
            if x + old_w / 2 > wa.x + wa.width / 2:
                self.move(x + old_w - self._size_w, y)

    def set_size(self, size):
        if size != FULL:
            self.sampler.set_top_mode(None)
        self.view.size = size
        self.settings.size = size
        self.settings.save()
        self._syncing = True
        self.size_items[size].set_active(True)
        self._syncing = False
        self._relayout()
        self._invalidate()

    def _on_configure(self, *_):
        if self._loaded:
            if self._save_id:
                GLib.source_remove(self._save_id)
            self._save_id = GLib.timeout_add(400, self._save_position)
        return False

    def _save_position(self):
        self._save_id = 0
        self.settings.left, self.settings.top = self.get_position()
        self.settings.save()
        return False

    def _on_destroy(self, *_):
        self._save_position()
        Gtk.main_quit()

    def _fade(self):
        p = min((time.monotonic() - self._fade_start) / 0.35, 1.0)
        self.set_opacity(p)
        return p < 1.0

    # ---------- data and drawing ----------

    def _on_second(self):
        self.sampler.sample()
        return True

    def _on_updated(self):
        self._relayout()
        self._invalidate()

    def _invalidate(self):
        self._dirty = True
        self.area.queue_draw()
        self._ensure_anim()

    def _render_base(self):
        scale = self.get_scale_factor()
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, self._size_w * scale, self._size_h * scale)
        surf.set_device_scale(scale, scale)
        self.view.paint(cairo.Context(surf))
        self._base = surf
        self._dirty = False

    def _on_draw(self, widget, cr):
        if self._dirty or self._base is None:
            self._render_base()
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        cr.set_source_surface(self._base, 0, 0)
        cr.paint()
        loops.draw(cr, self.view, time.monotonic() - self._t0, self._size_h, self.motion)
        return False

    def _animating(self):
        if self.view.tw.active:
            return 33
        if self.motion and not self.view.is_mini:
            return 50                                  # scanner and sweep only: base frame stays cached
        if self.motion and self.view.pip_pos is not None:
            return 50
        return 0

    def _ensure_anim(self):
        if not self._anim_id and self._animating():
            self._anim_id = GLib.timeout_add(self._animating(), self._anim)

    def _anim(self):
        if self.view.tw.active:
            self._dirty = True                         # bars are tweening: repaint the base too
        self.area.queue_draw()
        if self._animating():
            return True
        self._anim_id = 0
        return False

    # ---------- mouse ----------

    def _on_press(self, _w, e):
        if e.button == 1:
            self._press = (e.x_root, e.y_root)
            return True
        if e.button == 3:
            self.menu.popup_at_pointer(e)
            return True
        return False

    def _on_motion(self, _w, e):
        if self._press and (abs(e.x_root - self._press[0]) > DRAG_PX or abs(e.y_root - self._press[1]) > DRAG_PX):
            x, y = self._press
            self._press = None                         # the window manager owns the pointer from here
            self.begin_move_drag(1, int(x), int(y), e.time)
        return True

    def _on_release(self, _w, e):
        if e.button == 1 and self._press:              # a click, not a drag
            self._press = None
            if e.y < self.view.header_bottom:
                self.set_size(next_size(self.view.size))
            elif (row := self.view.row_at(e.y)) is not None:
                self.sampler.set_top_mode(None if self.sampler.top_mode == row else row)
        return True

    # ---------- menu ----------

    def _build_menu(self):
        menu = Gtk.Menu()
        size_item = Gtk.MenuItem(label="Size")
        sub = Gtk.Menu()
        self.size_items = {}
        group = None
        for s, label in ((FULL, "Full"), (COMPACT, "Compact"), (MINI, "Mini")):
            item = Gtk.RadioMenuItem.new_with_label_from_widget(group, label)
            group = item if group is None else group
            item.set_active(s == self.view.size)
            item.connect("toggled", lambda it, s=s: (not self._syncing and it.get_active()) and self.set_size(s))
            self.size_items[s] = item
            sub.append(item)
        size_item.set_submenu(sub)

        on_top = Gtk.CheckMenuItem(label="Always on Top")
        on_top.set_active(self.settings.on_top)
        on_top.connect("toggled", self._toggle_on_top)

        login = Gtk.CheckMenuItem(label="Launch at Login")
        login.set_active(settings.launch_at_login())
        login.connect("toggled", self._toggle_login)

        monitor = Gtk.MenuItem(label="Open System Monitor")
        monitor.connect("activate", lambda _i: self._open_monitor())
        quit_item = Gtk.MenuItem(label="Quit Pulse")
        quit_item.connect("activate", lambda _i: self.destroy())

        for item in (size_item, on_top, login, Gtk.SeparatorMenuItem(), monitor, quit_item):
            menu.append(item)
        menu.show_all()
        return menu

    def _toggle_on_top(self, item):
        self.settings.on_top = item.get_active()
        self.set_keep_above(self.settings.on_top)
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


def run():
    lock = os.path.join(os.environ.get("XDG_RUNTIME_DIR") or "/tmp", "pulse-widget.lock")
    fd = open(lock, "w")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return 0                                       # already running
    win = WidgetWindow()
    for sig in (signal.SIGINT, signal.SIGTERM):
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, sig, win.destroy)
    Gtk.main()
    return 0
