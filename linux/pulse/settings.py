"""~/.config/pulse/settings.json and the autostart entry. Mirrors windows/Pulse/Settings.cs."""
import json
import os
import sys

CONFIG_DIR = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config"), "pulse")
PATH = os.path.join(CONFIG_DIR, "settings.json")
AUTOSTART = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config"),
                         "autostart", "pulse.desktop")

VIEWS = ("full", "landscape", "claude", "compact", "mini")
SCALES = (1, 1.25, 1.5, 1.75, 2)          # snap points; whole steps keep the pixel font crisp
OPACITIES = (1, 0.85, 0.7, 0.5)


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


class Settings:
    def __init__(self):
        self.left = None
        self.top = None
        self.size = "full"
        self.on_top = True
        self.scale = 1.0
        self.opacity = 1.0
        self.alerts = True
        self.limits = True                 # plan limits come from Anthropic's servers; everything else stays local
        self.claude_open = False
        self.positions = {}                # where each view lives, keyed by monitor arrangement and view

    @classmethod
    def load(cls, path=PATH):
        s = cls()
        try:
            with open(path) as f:
                d = json.load(f)
            s.left = _num(d.get("left"))
            s.top = _num(d.get("top"))
            s.size = d.get("size") if d.get("size") in VIEWS else "full"
            s.on_top = bool(d.get("on_top", True))
            s.scale = min(max(_num(d.get("scale")) or 1.0, SCALES[0]), SCALES[-1])
            s.opacity = min(max(_num(d.get("opacity")) or 1.0, 0.2), 1.0)
            s.alerts = bool(d.get("alerts", True))
            s.limits = bool(d.get("limits", True))
            s.claude_open = bool(d.get("claude_open", False))
            pos = d.get("positions")
            if isinstance(pos, dict):
                s.positions = {k: [float(v[0]), float(v[1])] for k, v in pos.items()
                               if isinstance(k, str) and isinstance(v, list) and len(v) >= 2
                               and _num(v[0]) is not None and _num(v[1]) is not None}
        except (OSError, ValueError, AttributeError):
            pass
        return s

    def save(self, path=PATH):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                json.dump({"left": self.left, "top": self.top, "size": self.size, "on_top": self.on_top,
                           "scale": self.scale, "opacity": self.opacity, "alerts": self.alerts, "limits": self.limits,
                           "claude_open": self.claude_open, "positions": self.positions}, f)
        except OSError:
            pass


def launcher_command():
    """How the autostart entry should start us: the installed `pulse` launcher if present."""
    exe = os.path.join(os.path.expanduser("~"), ".local", "bin", "pulse")
    if os.path.exists(exe):
        return exe
    return f"{sys.executable} -m pulse"


def launch_at_login():
    return os.path.exists(AUTOSTART)


def set_launch_at_login(on):
    if on:
        os.makedirs(os.path.dirname(AUTOSTART), exist_ok=True)
        with open(AUTOSTART, "w") as f:
            f.write("[Desktop Entry]\nType=Application\nName=Pulse\nComment=Pixel system monitor\n"
                    f"Exec={launcher_command()}\nIcon=pulse\nX-GNOME-Autostart-enabled=true\n")
    else:
        try:
            os.remove(AUTOSTART)
        except FileNotFoundError:
            pass
