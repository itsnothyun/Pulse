"""Decides when something is worth a notification: a sustained hot CPU or full memory, the 5-hour block
resetting, and plan limits crossing 80% and 95%. Each fires once, then waits out a cooldown.

Pure logic -- `notify(title, text)` delivers (tray.notify in the app). Port of windows/Pulse/Alerts.cs.
"""
from datetime import datetime

from . import fmt

SUSTAIN = 30
COOLDOWN = 15 * 60
DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def clock(unix):
    """'Wed 14:30' in local time, without the locale (matches the C# InvariantCulture "ddd HH:mm")."""
    d = datetime.fromtimestamp(unix)
    return f"{DAYS[d.weekday()]} {d:%H:%M}"


class Alerts:
    def __init__(self, notify, enabled=True):
        self.notify = notify
        self.enabled = enabled
        self.last_fired = {}
        self.limits_fired = set()
        self.hot_since = self.mem_since = -1.0
        self.open_block_end = 0.0

    def _fire(self, key, title, text, now):
        t = self.last_fired.get(key)
        if t is not None and now - t < COOLDOWN:
            return
        self.last_fired[key] = now
        self.notify(title, text)

    def _held(self, on, attr, now):
        if not on:
            setattr(self, attr, -1.0)
            return False
        if getattr(self, attr) < 0:
            setattr(self, attr, now)
        return now - getattr(self, attr) >= SUSTAIN

    def check(self, s, now=None):
        if not self.enabled:
            return
        now = fmt.now() if now is None else now

        if self._held((s.temp or 0) >= 85, "hot_since", now):
            self._fire("hot", "Running hot", f"{s.temp:.0f}°C for over {SUSTAIN} seconds.", now)

        mem = s.mem_used / s.mem_total
        if self._held(mem >= 0.92, "mem_since", now):
            self._fire("mem", "Memory almost full", f"{mem * 100:.0f}% of {fmt.gib(s.mem_total)} GB in use.", now)

        c = s.claude
        if c.ready:
            if c.block_end > now:
                self.open_block_end = c.block_end
            elif self.open_block_end > 0 and now >= self.open_block_end:
                self.open_block_end = 0.0
                self._fire("block", "5-hour block reset",
                           "Your Claude Code 5-hour block has ended — a fresh one starts with your next message.", now)

        lim = s.limits
        if not lim.ready:
            return
        for name, used, reset in (("5-hour limit", lim.five, lim.five_reset), ("Weekly limit", lim.week, lim.week_reset)):
            if used is None:
                continue
            for mark in (0.95, 0.8):
                if used < mark:
                    continue
                key = f"{name}|{mark}|{reset:.0f}"
                if key not in self.limits_fired:
                    self.limits_fired.add(key)
                    when = f" Resets {clock(reset)}." if reset > 0 else ""
                    self.notify(f"{name} {used * 100:.0f}% used",
                                f"{c.email or 'Your account'} is past {mark * 100:.0f}% of its {name.lower()}.{when}")
                break                                   # one notice per crossing, not both marks at once
