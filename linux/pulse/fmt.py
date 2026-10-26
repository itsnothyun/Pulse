"""Number formatting for the pixel font (mirror of `F` in the C# and Swift ports)."""
import math
import time

from . import pixelfont


def pct(v):
    return f"{round(v * 100)}%"


def gib(b):
    return f"{b / 1073741824:.1f}"


def size(b):
    if b >= 1e12:
        return f"{b / 1e12:.1f}T"
    if b >= 1e9:
        return f"{b / 1e9:.0f}G"
    return f"{b / 1e6:.0f}M"


def rate(b):
    if b >= 1e9:
        return f"{b / 1e9:.1f}G"
    if b >= 1e6:
        return f"{b / 1e6:.1f}M"
    if b >= 1e3:
        return f"{b / 1e3:.0f}K"
    return f"{b:.0f}B"


def tok(v):
    if v >= 1e9:
        return f"{v / 1e9:.2f}B"
    if v >= 1e6:
        return f"{v / 1e6:.1f}M"
    if v >= 1e3:
        return f"{v / 1e3:.0f}K"
    return f"{v:.0f}"


def usd(v):
    if v < 100:
        return f"${v:.2f}"
    if v < 10000:
        return f"${v:.0f}"
    return f"${v / 1e3:.1f}K"


def mem(b):
    return f"{b / 1e9:.1f}G" if b >= 1e9 else f"{b / 1e6:.0f}M"


def countdown(seconds):
    m = math.ceil(seconds / 60)
    h = m // 60
    return f"{h}H {m % 60}M" if h > 0 else f"{m}M"


def proc_name(name):
    """Process names in the pixel font: unknown characters become spaces."""
    return "".join(c if pixelfont.has(c) else " " for c in name.upper())[:20]


def now():
    return time.time()


def uptime(seconds):
    s = int(seconds)
    d, h, m = s // 86400, s % 86400 // 3600, s % 3600 // 60
    return f"UP {d}D {h}H" if d > 0 else f"UP {h}H {m}M"
