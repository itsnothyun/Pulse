"""~/.config/pulse/settings.json and the autostart entry."""
import json
import os
import sys

CONFIG_DIR = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config"), "pulse")
PATH = os.path.join(CONFIG_DIR, "settings.json")
AUTOSTART = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config"),
                         "autostart", "pulse.desktop")


class Settings:
    def __init__(self):
        self.left = None
        self.top = None
        self.size = "full"
        self.on_top = True

    @classmethod
    def load(cls, path=PATH):
        s = cls()
        try:
            with open(path) as f:
                d = json.load(f)
            s.left = d.get("left") if isinstance(d.get("left"), (int, float)) else None
            s.top = d.get("top") if isinstance(d.get("top"), (int, float)) else None
            s.size = d.get("size") if d.get("size") in ("full", "compact", "mini") else "full"
            s.on_top = bool(d.get("on_top", True))
        except (OSError, ValueError, AttributeError):
            pass
        return s

    def save(self, path=PATH):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                json.dump({"left": self.left, "top": self.top, "size": self.size, "on_top": self.on_top}, f)
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
