"""Tray icon and notifications. Port of windows/Pulse/Tray.cs.

The tray brings the widget back when it's hidden or click-through. It uses AyatanaAppIndicator3 / AppIndicator3
when installed (Ubuntu, KDE, most panels), else the legacy Gtk.StatusIcon (XFCE, MATE, Cinnamon), else nothing.
Stock GNOME shows neither without the AppIndicator extension; `pulse` (show) and `pulse --click-through` work
everywhere as the way back.
"""
import importlib
import shutil
import subprocess
import warnings

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gio, Gtk  # noqa: E402

APP_ID = "app.crestcloud.Pulse"


def _indicator_module():
    for name in ("AyatanaAppIndicator3", "AppIndicator3"):
        try:
            gi.require_version(name, "0.1")
            return importlib.import_module(f"gi.repository.{name}")
        except (ValueError, ImportError):
            continue
    return None


def _icon_name():
    theme = Gtk.IconTheme.get_default()
    return "pulse" if theme is not None and theme.has_icon("pulse") else "utilities-system-monitor"


class Tray:
    def __init__(self, toggle_shown, views, toggle_through, toggle_alerts, quit_app):
        self._syncing = False
        self.kind = None
        self.indicator = self.status = None

        self.menu = Gtk.Menu()
        self.shown = Gtk.CheckMenuItem(label="Show Pulse")
        self.shown.connect("toggled", lambda _i: self._syncing or toggle_shown())
        choose = Gtk.MenuItem(label="Choose View…")
        choose.connect("activate", lambda _i: views())
        self.through = Gtk.CheckMenuItem(label="Click-through")
        self.through.connect("toggled", lambda _i: self._syncing or toggle_through())
        self.alerts = Gtk.CheckMenuItem(label="Alerts")
        self.alerts.connect("toggled", lambda _i: self._syncing or toggle_alerts())
        quit_item = Gtk.MenuItem(label="Quit Pulse")
        quit_item.connect("activate", lambda _i: quit_app())
        for item in (self.shown, choose, self.through, self.alerts, Gtk.SeparatorMenuItem(), quit_item):
            self.menu.append(item)
        self.menu.show_all()

        icon = _icon_name()
        mod = _indicator_module()
        if mod is not None:
            try:
                ind = mod.Indicator.new("pulse", icon, mod.IndicatorCategory.APPLICATION_STATUS)
                ind.set_status(mod.IndicatorStatus.ACTIVE)
                ind.set_title("Pulse")
                ind.set_menu(self.menu)
                ind.set_secondary_activate_target(self.shown)      # middle click shows / hides
                self.indicator, self.kind = ind, "indicator"
                return
            except Exception:
                self.indicator = None
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                st = Gtk.StatusIcon.new_from_icon_name(icon)
                st.set_title("Pulse")
                st.set_tooltip_text("Pulse")
                st.connect("activate", lambda _s: toggle_shown())
                st.connect("popup-menu", lambda s, button, t: self.menu.popup(None, None, Gtk.StatusIcon.position_menu, s, button, t))
                st.set_visible(True)
            self.status, self.kind = st, "status"
        except Exception:
            self.status = None

    @property
    def available(self):
        """Whether there's an icon the user can actually reach (a status icon needs a tray to sit in)."""
        if self.kind == "indicator":
            return True
        if self.kind == "status":
            try:
                return bool(self.status.is_embedded())
            except Exception:
                return False
        return False

    def sync(self, shown, click_through, alerts_on):
        self._syncing = True
        self.shown.set_active(shown)
        self.through.set_active(click_through)
        self.alerts.set_active(alerts_on)
        self._syncing = False
        tip = "Pulse · click-through (pulse --click-through)" if click_through else "Pulse"
        if self.status is not None:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                self.status.set_tooltip_text(tip)
        if self.indicator is not None:
            try:
                self.indicator.set_title(tip)
            except Exception:
                pass

    def dispose(self):
        if self.status is not None:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                self.status.set_visible(False)
        if self.indicator is not None:
            try:
                mod = _indicator_module()
                self.indicator.set_status(mod.IndicatorStatus.PASSIVE)
            except Exception:
                pass


_gio_app = None


def notify(title, text):
    """A desktop notification. notify-send first: Gio.Notification on GNOME is dropped silently unless a
    .desktop file named after the app id is installed, and ours is plain pulse.desktop."""
    exe = shutil.which("notify-send")
    if exe:
        try:
            subprocess.Popen([exe, "-a", "Pulse", "-i", _icon_name(), title, text],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            return
        except OSError:
            pass
    global _gio_app
    try:
        if _gio_app is None:
            _gio_app = Gio.Application(application_id=APP_ID, flags=Gio.ApplicationFlags.NON_UNIQUE)
            _gio_app.register(None)
        n = Gio.Notification.new(title)
        n.set_body(text)
        _gio_app.send_notification(None, n)
    except Exception:
        pass                                   # no session bus: alerts stay quiet
