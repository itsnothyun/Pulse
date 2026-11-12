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
CWD_KEY = b'"cwd":"'


def price(model):
    for m, p in PRICES:
        if m in model:
            return p
    return FREE


def family(model):
    return ("FABLE" if "fable" in model else "OPUS" if "opus" in model else "SONNET" if "sonnet" in model
            else "HAIKU" if "haiku" in model else "OTHER")


def project_name(cwd, fallback):
    """Project name: the last folder of the session's working directory, else the transcript folder."""
    if cwd:
        parts = [p for p in cwd.replace("\\\\", "/").replace("\\", "/").split("/") if p]
        if parts:
            return parts[-1]
    return fallback


@dataclass
class Slice:
    """One line of a breakdown: who or what spent the tokens."""
    name: str
    tokens: float
    cost: float


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
    email: str = None                    # the account Claude Code is signed in with (None = API key or signed out)
    plan: str = None
    by_model: list = field(default_factory=list)     # [Slice], this week, largest first
    by_project: list = field(default_factory=list)
    by_account: list = field(default_factory=list)


def root():
    cfg = os.environ.get("CLAUDE_CONFIG_DIR")
    base = cfg if cfg else os.path.join(os.path.expanduser("~"), ".claude")
    return os.path.join(base, "projects")


def config_file():
    """~/.claude.json (or $CLAUDE_CONFIG_DIR/.claude.json) -- rewritten by /login, so it names the current account."""
    cfg = os.environ.get("CLAUDE_CONFIG_DIR")
    return os.path.join(cfg, ".claude.json") if cfg else os.path.join(os.path.expanduser("~"), ".claude.json")


def account_log_path():
    """When each account was first seen signed in -- next to settings.json."""
    from .settings import CONFIG_DIR
    return os.path.join(CONFIG_DIR, "accounts.json")


def _top(events, key):
    groups = {}
    for e in events:
        g = groups.setdefault(key(e), [0.0, 0.0])
        g[0] += e[1] + e[2] + e[3] + e[4]
        g[1] += e[5]
    return sorted((Slice(k, t, c) for k, (t, c) in groups.items()), key=lambda s: -s.tokens)


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
    def __init__(self, projects_root=None, config=None, accounts=None):
        self.root = projects_root
        self.config = config
        self.accounts = accounts
        self.account_stamp = None
        self.email = self.plan = None
        # When each account was first seen signed in (unix s). Transcripts don't name the account, so tokens are
        # credited to whoever was signed in at the time; the first account ever seen also owns the history before it.
        self.account_log = self._load_account_log()
        self.offsets = {}
        self.seen = set()
        self.events = []                 # (ts, input, output, cache_write, cache_read, cost, session, model, project)
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
                            live += self._read_file(os.path.join(dirpath, name), base, ws, now)
                        except OSError:
                            pass         # file vanished -- next pass

        self._read_account()
        self._note_account(self.email, now)
        st = ClaudeStats(ready=True, live=live, calls=len(self.events), today_index=since_monday,
                         email=self.email, plan=self.plan,
                         by_model=_top(self.events, lambda e: e[7]), by_project=_top(self.events, lambda e: e[8]),
                         by_account=_top(self.events, lambda e: self.account_at(e[0])))
        day_start = datetime.fromtimestamp(now).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        sessions = set()
        for ts, i, o, cw, cr, cost, sess, _model, _project in self.events:
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

    # ---------- account attribution ----------

    def _load_account_log(self):
        try:
            with open(self.accounts or account_log_path(), encoding="utf-8") as f:
                d = json.load(f)
            log = [(float(e["from"]), e["email"]) for e in d
                   if isinstance(e, dict) and isinstance(e.get("from"), (int, float)) and isinstance(e.get("email"), str)
                   and e["email"]]
            return sorted(log, key=lambda e: e[0])
        except (OSError, ValueError, TypeError, KeyError):
            return []

    def _note_account(self, current, now):
        if current is None or (self.account_log and self.account_log[-1][1] == current):
            return
        self.account_log.append((0.0 if not self.account_log else now, current))
        path = self.accounts or account_log_path()
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump([{"from": t, "email": e} for t, e in self.account_log], f)
        except OSError:
            pass

    def account_at(self, ts):
        who = self.account_log[0][1] if self.account_log else "UNKNOWN"
        for start, e in self.account_log:
            if start <= ts:
                who = e
            else:
                break
        return who

    def _read_account(self):
        """Re-reads the signed-in account only when the config file changes."""
        path = self.config or config_file()
        try:
            stamp = os.stat(path).st_mtime_ns
        except OSError:
            self.email = self.plan = self.account_stamp = None
            return
        if stamp == self.account_stamp:
            return
        try:
            with open(path, encoding="utf-8") as f:
                acct = json.load(f).get("oauthAccount")
        except (OSError, ValueError):
            return                       # mid-write -- next pass
        acct = acct if isinstance(acct, dict) else {}
        str_or_none = lambda v: v if isinstance(v, str) else None
        self.email, self.plan = str_or_none(acct.get("emailAddress")), str_or_none(acct.get("planDisplayName"))
        self.account_stamp = stamp

    def _read_file(self, path, base, ws, now):
        """Reads the new bytes of one transcript; returns 1 if it looks like a live session."""
        folder = os.path.relpath(path, base).split(os.sep)[0]
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
                    self._ingest(line, ws, folder)
                consumed += last_nl + 1
                pending = pending[last_nl + 1:]
        self.offsets[path] = off + consumed
        return live

    def _ingest(self, line, ws, folder=""):
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
        model = _field(line, MODEL_KEY) or ""
        p = price(model)
        self.events.append((ts, i, o, cw, cr, (i * p[0] + o * p[1] + cw * p[2] + cr * p[3]) / 1e6,
                            _field(line, SESSION_KEY) or "", family(model), project_name(_field(line, CWD_KEY), folder)))
