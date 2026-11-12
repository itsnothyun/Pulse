"""How much of the plan's rolling limits is used -- the same numbers as Claude Code's /usage.

Reads the token Claude Code keeps in .credentials.json. Read-only: Pulse never refreshes the token,
so an expired one just means "no data until Claude Code runs again".
Port of windows/Pulse/Limits.cs -- keep the two in step.
"""
import http.client
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from .claude import _parse_ts

URL = "https://api.anthropic.com/api/oauth/usage"
TIMEOUT = 10


@dataclass
class PlanLimits:
    """Used fraction (0-1) of each window, and when it resets (unix s, 0 = no window open)."""
    five: float = None
    week: float = None
    five_reset: float = 0
    week_reset: float = 0
    ready: bool = False


def credentials_file():
    cfg = os.environ.get("CLAUDE_CONFIG_DIR")
    base = cfg if cfg else os.path.join(os.path.expanduser("~"), ".claude")
    return os.path.join(base, ".credentials.json")


def token(path=None, now=None):
    """The OAuth access token, or None when signed out, unreadable or expired."""
    try:
        with open(path or credentials_file(), encoding="utf-8") as f:
            o = json.load(f).get("claudeAiOauth")
    except (OSError, ValueError, AttributeError):
        return None
    if not isinstance(o, dict):
        return None
    exp = o.get("expiresAt")
    now_ms = (now if now is not None else time.time()) * 1000
    if isinstance(exp, (int, float)) and not isinstance(exp, bool) and exp < now_ms:
        return None
    t = o.get("accessToken")
    return t if isinstance(t, str) and t else None


def _window(root, name):
    w = root.get(name)
    if not isinstance(w, dict):
        return None, 0
    u = w.get("utilization")
    used = u / 100 if isinstance(u, (int, float)) and not isinstance(u, bool) else None
    r = w.get("resets_at")
    reset = (_parse_ts(r) or 0) if isinstance(r, str) else 0
    return used, reset


def parse(body):
    """The usage endpoint's JSON -> PlanLimits; None if it isn't an object."""
    try:
        root = json.loads(body)
    except (ValueError, TypeError):
        return None
    if not isinstance(root, dict):
        return None
    five, five_reset = _window(root, "five_hour")
    week, week_reset = _window(root, "seven_day")
    return PlanLimits(five=five, week=week, five_reset=five_reset, week_reset=week_reset, ready=True)


def _fetch(url, headers, timeout):
    """GET with urllib; returns (status, body bytes)."""
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return res.status, res.read()


def read(fetch=None, credentials=None):
    """Blocking (run it off the UI thread). None when signed out, offline, or the endpoint changed;
    callers keep the last good reading."""
    t = token(credentials)
    if t is None:
        return None
    headers = {"Authorization": "Bearer " + t, "anthropic-beta": "oauth-2025-04-20", "User-Agent": "Pulse"}
    try:
        status, body = (fetch or _fetch)(URL, headers, TIMEOUT)
    except (OSError, urllib.error.URLError, http.client.HTTPException, ValueError):
        return None
    if not 200 <= status < 300:
        return None
    return parse(body)
