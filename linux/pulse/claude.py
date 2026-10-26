"""Incremental tally of this week's Claude Code tokens (transcripts in ~/.claude/projects).

Each pass reads only the bytes appended since the last pass; API calls are de-duplicated by
message + request id. Port of windows/Pulse/ClaudeUsage.cs -- keep the two in step.
"""
import json
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

# Estimated API list price in USD per million tokens: input, output, cache write, cache read.
# First match wins; unknown models count as free. Edit when prices change.
PRICES = [
    ("fable", (10, 50, 12.5, 1)),
    ("opus-5", (4, 20, 5, 0.4)), ("opus-4-5", (5, 25, 6.25, 0.5)), ("opus", (15, 75, 18.75, 1.5)),
    ("sonnet-5", (2, 10, 2.5, 0.1)), ("sonnet", (3, 15, 3.75, 0.3)),
    ("haiku-5", (0.1, 0.5, 0.125, 0.01)), ("haiku-4", (1, 5, 1.25, 0.1)), ("haiku", (0.8, 4, 1, 0.08)),
]
FREE = (0, 0, 0, 0)
FIVE_HOURS = 5 * 3600

USAGE_KEY = b'"usage":{'
TS_KEY = b'"timestamp":"'
ID_KEY = b'"id":"msg_'
REQ_KEY = b'"requestId":"'
SESSION_KEY = b'"sessionId":"'
MODEL_KEY = b'"model":"'


def price(model):
    for m, p in PRICES:
        if m in model:
            return p
    return FREE


@dataclass
class ClaudeStats:
    week: float = 0
    input: float = 0
    output: float = 0
    cache_write: float = 0
    cache_read: float = 0
    today: float = 0
    cost: float = 0                      # estimated USD at API list prices
    block: float = 0                     # tokens in the current 5-hour block
    block_end: float = 0                 # when it resets (unix s, 0 = none)
    sessions: int = 0
    live: int = 0
    calls: int = 0
    today_index: int = 0
    days: list = field(default_factory=lambda: [0.0] * 7)
    ready: bool = False


def root():
    cfg = os.environ.get("CLAUDE_CONFIG_DIR")
    base = cfg if cfg else os.path.join(os.path.expanduser("~"), ".claude")
    return os.path.join(base, "projects")


def _field(line, key, last=False):
    i = line.rfind(key) if last else line.find(key)
    if i < 0:
        return None
    start = i + len(key)
    end = line.find(b'"', start)
    return None if end < 0 else line[start:end].decode("utf-8", "replace")


def _parse_ts(s):
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def week_start(now=None):
    """Monday 00:00 local time (unix s) and the weekday index of today (Mon = 0)."""
    n = datetime.fromtimestamp(now if now is not None else time.time())
    midnight = n.replace(hour=0, minute=0, second=0, microsecond=0)
    return (midnight - timedelta(days=n.weekday())).timestamp(), n.weekday()


class ClaudeUsage:
    def __init__(self, projects_root=None):
        self.root = projects_root
        self.offsets = {}
        self.seen = set()
        self.events = []                 # (ts, input, output, cache_write, cache_read, cost, session)
        self.gate = threading.Lock()
        self.ws = 0.0

    def scan(self, now=None):
        with self.gate:
            return self._scan(now if now is not None else time.time())

    def _scan(self, now):
        ws, since_monday = week_start(now)
        if ws != self.ws:
            self.ws = ws
            self.offsets.clear()
            self.seen.clear()
            self.events.clear()

        live = 0
        base = self.root or root()
        if os.path.isdir(base):
            for dirpath, _dirs, files in os.walk(base):
                for name in files:
                    if name.endswith(".jsonl"):
                        try:
                            live += self._read_file(os.path.join(dirpath, name), ws, now)
                        except OSError:
                            pass         # file vanished -- next pass

        st = ClaudeStats(ready=True, live=live, calls=len(self.events), today_index=since_monday)
        day_start = datetime.fromtimestamp(now).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        sessions = set()
        for ts, i, o, cw, cr, cost, sess in self.events:
            t = i + o + cw + cr
            st.week += t
            st.input += i
            st.output += o
            st.cache_write += cw
            st.cache_read += cr
            st.cost += cost
            if ts >= day_start:
                st.today += t
            st.days[min(max(int((ts - ws) // 86400), 0), 6)] += t
            sessions.add(sess)
        st.sessions = len(sessions)

        # 5-hour blocks: one opens at the hour of the first message after the last block ran out.
        b_start, b_tok = float("-inf"), 0.0
        for ts, t in sorted((e[0], e[1] + e[2] + e[3] + e[4]) for e in self.events):
            if ts >= b_start + FIVE_HOURS:
                b_start, b_tok = (ts // 3600) * 3600, 0.0
            b_tok += t
        if now < b_start + FIVE_HOURS:
            st.block, st.block_end = b_tok, b_start + FIVE_HOURS
        return st

    def _read_file(self, path, ws, now):
        """Reads the new bytes of one transcript; returns 1 if it looks like a live session."""
        stt = os.stat(path)
        if stt.st_mtime < ws:
            return 0
        live = 1 if (now - stt.st_mtime) < 300 and f"{os.sep}subagents{os.sep}" not in path else 0
        off = self.offsets.get(path, 0)
        if stt.st_size <= off:
            return live

        consumed = 0
        pending = b""
        with open(path, "rb") as f:
            f.seek(off)
            while True:
                chunk = f.read(4 << 20)        # stream in 4 MB chunks to keep memory flat
                if not chunk:
                    break
                pending += chunk
                last_nl = pending.rfind(b"\n")
                if last_nl < 0:
                    continue                   # a single line larger than the chunk
                for line in pending[:last_nl].split(b"\n"):
                    self._ingest(line, ws)
                consumed += last_nl + 1
                pending = pending[last_nl + 1:]
        self.offsets[path] = off + consumed
        return live

    def _ingest(self, line, ws):
        # Cheap field extraction -- lines can be megabytes, so avoid parsing the whole record.
        u = line.find(USAGE_KEY)
        if u < 0:
            return
        ts_s = _field(line, TS_KEY, last=True)
        ts = _parse_ts(ts_s) if ts_s else None
        if ts is None or ts < ws:
            return

        opn, depth, close = u + len(USAGE_KEY) - 1, 0, -1
        for i in range(opn, len(line)):
            c = line[i]
            if c == 0x7B:                      # {
                depth += 1
            elif c == 0x7D:                    # }
                depth -= 1
                if depth == 0:
                    close = i
                    break
        if close < 0:
            return

        req = _field(line, REQ_KEY)
        key = f"{_field(line, ID_KEY)}|{req if req is not None else ts}"
        if key in self.seen:
            return
        self.seen.add(key)

        try:
            r = json.loads(line[opn:close + 1])
        except ValueError:
            return

        def n(k):
            v = r.get(k)
            return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0

        i, o, cw, cr = n("input_tokens"), n("output_tokens"), n("cache_creation_input_tokens"), n("cache_read_input_tokens")
        p = price(_field(line, MODEL_KEY) or "")
        self.events.append((ts, i, o, cw, cr, (i * p[0] + o * p[1] + cw * p[2] + cr * p[3]) / 1e6,
                            _field(line, SESSION_KEY) or ""))
