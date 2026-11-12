import json
import os
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from types import SimpleNamespace  # noqa: E402

from pulse import alerts, claude, fmt, geometry, limits, loops, probes, settings, view  # noqa: E402
from pulse import pixelfont as px  # noqa: E402
from pulse.sampler import Sampler  # noqa: E402

STAT = """cpu  100 0 100 800 0 0 0 0 0 0
cpu0 50 0 50 400 0 0 0 0 0 0
cpu1 50 0 50 400 0 0 0 0 0 0
intr 1
"""

MEMINFO = """MemTotal:       16000000 kB
MemFree:         1000000 kB
MemAvailable:    6000000 kB
SwapTotal:       2000000 kB
SwapFree:        1500000 kB
"""

NETDEV = """Inter-|   Receive                                                |  Transmit
 face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed
    lo: 999 1 0 0 0 0 0 0 999 1 0 0 0 0 0 0
  eth0: 1000 1 0 0 0 0 0 0 200 1 0 0 0 0 0 0
docker0: 5000 1 0 0 0 0 0 0 5000 1 0 0 0 0 0 0
veth12: 7 1 0 0 0 0 0 0 7 1 0 0 0 0 0 0
enP7s7: 500 1 0 0 0 0 0 0 100 1 0 0 0 0 0 0
"""


class Format(unittest.TestCase):
    def test_numbers(self):
        self.assertEqual(fmt.pct(0.344), "34%")
        self.assertEqual(fmt.size(494e9), "494G")
        self.assertEqual(fmt.size(2.1e12), "2.1T")
        self.assertEqual(fmt.rate(1.84e6), "1.8M")
        self.assertEqual(fmt.rate(212e3), "212K")
        self.assertEqual(fmt.tok(412.6e6), "412.6M")
        self.assertEqual(fmt.tok(2.5e9), "2.50B")
        self.assertEqual(fmt.usd(184.2), "$184")
        self.assertEqual(fmt.usd(9.5), "$9.50")
        self.assertEqual(fmt.usd(12500), "$12.5K")
        self.assertEqual(fmt.countdown(2 * 3600 + 14 * 60 + 30), "2H 15M")
        self.assertEqual(fmt.countdown(59), "1M")
        self.assertEqual(fmt.uptime(3 * 86400 + 5 * 3600), "UP 3D 5H")
        self.assertEqual(fmt.uptime(3 * 3600 + 120), "UP 3H 2M")

    def test_proc_name_only_uses_known_glyphs(self):
        self.assertEqual(fmt.proc_name("gnome-shell"), "GNOME-SHELL")
        self.assertEqual(fmt.proc_name("a{b}"), "A B ")
        self.assertEqual(len(fmt.proc_name("x" * 40)), 20)


class Probes(unittest.TestCase):
    def test_cpu_times(self):
        self.assertEqual(probes.parse_cpu_times(STAT), [(400, 500), (400, 500)])

    def test_meminfo(self):
        m = probes.parse_meminfo(MEMINFO)
        self.assertEqual(m["MemTotal"], 16000000 * 1024)
        self.assertEqual(m["MemAvailable"], 6000000 * 1024)

    def test_netdev_skips_virtual_interfaces(self):
        self.assertEqual(probes.parse_netdev(NETDEV), (1500, 300))

    def test_proc_stat_handles_odd_command_names(self):
        fields = ["S"] + ["0"] * 10 + ["30", "12"] + ["0"] * 8 + ["250"] + ["0"] * 5
        line = "42 (my (weird) cmd) " + " ".join(fields)
        name, ticks, rss = probes.parse_proc_stat(line)
        self.assertEqual(name, "my (weird) cmd")
        self.assertEqual(ticks, 42)
        self.assertEqual(rss, 250 * probes.PAGE)

    def test_temps_from_fake_sysfs(self):
        with tempfile.TemporaryDirectory() as root:
            for rel, val, name in (("class/thermal/thermal_zone0", "51000", None),
                                   ("class/hwmon/hwmon0", "67000", "k10temp"),
                                   ("class/hwmon/hwmon1", "99000", "nvme")):
                d = os.path.join(root, rel)
                os.makedirs(d)
                with open(os.path.join(d, "temp" if "thermal" in rel else "temp1_input"), "w") as f:
                    f.write(val)
                if name:
                    with open(os.path.join(d, "name"), "w") as f:
                        f.write(name)
            self.assertEqual(sorted(probes.read_temps(root)), [51.0, 67.0])   # nvme ignored

    def test_no_battery_on_a_spark(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertIsNone(probes.read_battery(root))

    def test_battery(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "BAT0"))
            os.makedirs(os.path.join(root, "AC"))
            for p, v in (("BAT0/capacity", "86"), ("BAT0/status", "Charging"), ("AC/online", "1")):
                with open(os.path.join(root, p), "w") as f:
                    f.write(v)
            self.assertEqual(probes.read_battery(root), (86, True, True))


def usage_line(ts, msg, req, inp=10, out=20, cw=30, cr=40, model="claude-sonnet-5-5", session="s1", cwd=None):
    return json.dumps({"type": "assistant", "sessionId": session, "requestId": req, "timestamp": ts,
                       **({"cwd": cwd} if cwd is not None else {}),
                       "message": {"id": msg, "model": model,
                                   "usage": {"input_tokens": inp, "output_tokens": out,
                                             "cache_creation_input_tokens": cw, "cache_read_input_tokens": cr}}},
                      separators=(",", ":")) + "\n"          # compact, like Claude Code's own transcripts


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


class ClaudeScan(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.proj = os.path.join(self.dir.name, "proj")
        os.makedirs(self.proj)
        self.file = os.path.join(self.proj, "a.jsonl")

    def tearDown(self):
        self.dir.cleanup()

    def usage(self, root=None, config=None):
        """A scanner that never touches the real ~/.claude.json or ~/.config/pulse/accounts.json."""
        return claude.ClaudeUsage(root or self.proj, config=config or os.path.join(self.dir.name, "none.json"),
                                  accounts=os.path.join(self.dir.name, "accounts.json"))

    def login(self, cfg, email, stamp):
        with open(cfg, "w", encoding="utf-8") as f:
            json.dump({"oauthAccount": {"emailAddress": email}}, f)
        os.utime(cfg, (stamp, stamp))

    def write(self, text, mode="a"):
        with open(self.file, mode) as f:
            f.write(text)

    def test_counts_dedupes_and_prices(self):
        now = datetime.now()
        ts = iso(now - timedelta(seconds=30))
        self.write(usage_line(ts, "msg_1", "req_1") + usage_line(ts, "msg_1", "req_1") + usage_line(ts, "msg_2", "req_2"))
        st = self.usage().scan(now.timestamp())
        self.assertEqual(st.calls, 2)                       # duplicate dropped
        self.assertEqual(st.week, 2 * 100)
        self.assertEqual(st.today, 200)
        self.assertEqual(st.sessions, 1)
        self.assertEqual(st.live, 1)
        p = claude.price("claude-sonnet-5-5")
        self.assertAlmostEqual(st.cost, 2 * (10 * p[0] + 20 * p[1] + 30 * p[2] + 40 * p[3]) / 1e6)
        self.assertEqual(st.days[st.today_index], 200)

    def test_incremental_and_partial_line(self):
        now = datetime.now()
        ts = iso(now - timedelta(seconds=30))
        u = self.usage()
        second = usage_line(ts, "msg_2", "req_2")
        self.write(usage_line(ts, "msg_1", "req_1") + second[:40])        # second line half-written
        self.assertEqual(u.scan(now.timestamp()).calls, 1)
        self.write(second[40:])
        self.assertEqual(u.scan(now.timestamp()).calls, 2)                # picked up from the saved offset

    def test_five_hour_block(self):
        now = datetime.now()
        self.write(usage_line(iso(now - timedelta(minutes=10)), "msg_1", "req_1"))
        st = self.usage().scan(now.timestamp())
        self.assertEqual(st.block, 100)
        self.assertGreater(st.block_end, now.timestamp())
        self.assertLessEqual(st.block_end - now.timestamp(), 5 * 3600)

    def test_unknown_model_is_free_and_old_events_ignored(self):
        now = datetime.now()
        self.write(usage_line(iso(now - timedelta(seconds=5)), "msg_1", "req_1", model="mystery-1"))
        self.write(usage_line(iso(now - timedelta(days=30)), "msg_9", "req_9"))
        st = self.usage().scan(now.timestamp())
        self.assertEqual((st.calls, st.cost), (1, 0))

    def test_missing_directory(self):
        st = self.usage(os.path.join(self.dir.name, "nope")).scan()
        self.assertTrue(st.ready)
        self.assertEqual(st.week, 0)

    def test_account_follows_login(self):
        cfg = os.path.join(self.dir.name, ".claude.json")
        u = self.usage(config=cfg)
        self.assertIsNone(u.scan().email)                   # no config file yet

        def login(account, stamp):
            with open(cfg, "w", encoding="utf-8") as f:
                json.dump({"numStartups": 3, **({"oauthAccount": account} if account else {})}, f)
            os.utime(cfg, (stamp, stamp))

        login({"emailAddress": "a@example.com", "planDisplayName": "Max"}, 1_000_000)
        st = u.scan()
        self.assertEqual((st.email, st.plan), ("a@example.com", "Max"))
        login({"emailAddress": "b@example.com"}, 1_000_100)  # /login with another account
        st = u.scan()
        self.assertEqual((st.email, st.plan), ("b@example.com", None))
        login(None, 1_000_200)                               # API key, no claude.ai account
        self.assertIsNone(u.scan().email)

    def test_breakdown_by_model_and_project(self):
        now = datetime.now()
        ts = iso(now - timedelta(seconds=30))
        root = os.path.join(self.dir.name, "projects")
        os.makedirs(os.path.join(root, "-home-u-site"))
        with open(os.path.join(root, "-home-u-site", "t.jsonl"), "w") as f:
            f.write(usage_line(ts, "msg_1", "req_1", model="claude-opus-5", cwd="/home/u/pulse/")
                    + usage_line(ts, "msg_2", "req_2", inp=1000, model="claude-opus-4-5", cwd="C:\\Users\\u\\pulse")
                    + usage_line(ts, "msg_3", "req_3", model="claude-haiku-5")       # no cwd: the transcript folder
                    + usage_line(ts, "msg_4", "req_4", model="mystery"))
        st = self.usage(root).scan(now.timestamp())
        self.assertEqual([(m.name, m.tokens) for m in st.by_model], [("OPUS", 1190), ("HAIKU", 100), ("OTHER", 100)])
        self.assertEqual([p.name for p in st.by_project], ["pulse", "-home-u-site"])
        self.assertEqual(st.by_project[0].tokens, 1190)
        self.assertAlmostEqual(sum(m.cost for m in st.by_model), st.cost)

    def test_model_family_and_project_name(self):
        self.assertEqual([claude.family(m) for m in ("claude-fable-1", "claude-opus-4-5", "claude-sonnet-5", "claude-haiku-4", "x")],
                         ["FABLE", "OPUS", "SONNET", "HAIKU", "OTHER"])
        self.assertEqual(claude.project_name("/home/u/web/", "f"), "web")
        self.assertEqual(claude.project_name("C:\\\\work\\\\api", "f"), "api")      # as it sits in the raw JSON
        self.assertEqual(claude.project_name("", "f"), "f")
        self.assertEqual(claude.project_name(None, "f"), "f")

    def test_first_account_owns_history_then_switches_are_logged(self):
        now = datetime.now()
        cfg = os.path.join(self.dir.name, ".claude.json")
        log = os.path.join(self.dir.name, "accounts.json")
        self.write(usage_line(iso(now - timedelta(minutes=30)), "msg_1", "req_1"))
        self.login(cfg, "a@example.com", 1_000_000)
        u = self.usage(config=cfg)
        st = u.scan(now.timestamp() - 600)
        with open(log) as f:
            self.assertEqual(json.load(f), [{"from": 0.0, "email": "a@example.com"}])
        self.assertEqual([(a.name, a.tokens) for a in st.by_account], [("a@example.com", 100)])

        self.login(cfg, "b@example.com", 1_000_100)                     # /login, seen 5 minutes ago
        self.write(usage_line(iso(now - timedelta(seconds=5)), "msg_2", "req_2", inp=1000))
        st = u.scan(now.timestamp() - 300)
        with open(log) as f:
            self.assertEqual([e["email"] for e in json.load(f)], ["a@example.com", "b@example.com"])
        self.assertEqual([(a.name, a.tokens) for a in st.by_account], [("b@example.com", 1090), ("a@example.com", 100)])
        u.scan(now.timestamp())                                          # same account: nothing appended
        self.assertEqual(len(self.usage(config=cfg).account_log), 2)    # and it reloads from disk

    def test_no_account_means_unknown(self):
        now = datetime.now()
        self.write(usage_line(iso(now - timedelta(seconds=5)), "msg_1", "req_1"))
        st = self.usage().scan(now.timestamp())
        self.assertEqual([a.name for a in st.by_account], ["UNKNOWN"])
        self.assertFalse(os.path.exists(os.path.join(self.dir.name, "accounts.json")))


class PlanLimitsProbe(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.cred = os.path.join(self.dir.name, ".credentials.json")

    def tearDown(self):
        self.dir.cleanup()

    def creds(self, token="tok-1", expires=None):
        with open(self.cred, "w") as f:
            json.dump({"claudeAiOauth": {"accessToken": token, "expiresAt": expires}}, f)

    def test_parse(self):
        body = json.dumps({"five_hour": {"utilization": 34.0, "resets_at": "2026-11-12T15:00:00Z"},
                           "seven_day": {"utilization": 42, "resets_at": None}, "seven_day_opus": None}).encode()
        lim = limits.parse(body)
        self.assertTrue(lim.ready)
        self.assertAlmostEqual(lim.five, 0.34)
        self.assertAlmostEqual(lim.week, 0.42)
        self.assertEqual(lim.five_reset, datetime(2026, 11, 12, 15, tzinfo=timezone.utc).timestamp())
        self.assertEqual(lim.week_reset, 0)

    def test_null_windows_stay_none(self):
        lim = limits.parse(b'{"five_hour": null, "seven_day": {"utilization": null}}')
        self.assertIsNone(lim.five)
        self.assertIsNone(lim.week)
        self.assertIsNone(limits.parse(b"[1, 2]"))
        self.assertIsNone(limits.parse(b"<html>"))

    def test_read_sends_the_token_and_headers(self):
        self.creds(expires=(time.time() + 3600) * 1000)
        calls = []

        def fetch(url, headers, timeout):
            calls.append((url, headers, timeout))
            return 200, b'{"five_hour": {"utilization": 95.5}}'
        lim = limits.read(fetch, self.cred)
        self.assertAlmostEqual(lim.five, 0.955)
        url, headers, timeout = calls[0]
        self.assertEqual(url, "https://api.anthropic.com/api/oauth/usage")
        self.assertEqual(headers["Authorization"], "Bearer tok-1")
        self.assertEqual(headers["anthropic-beta"], "oauth-2025-04-20")
        self.assertEqual(headers["User-Agent"], "Pulse")
        self.assertEqual(timeout, 10)

    def test_expired_or_missing_token_never_calls_out(self):
        def fetch(*_):
            raise AssertionError("no request without a valid token")
        self.assertIsNone(limits.read(fetch, self.cred))                 # no file
        self.creds(expires=(time.time() - 60) * 1000)
        self.assertIsNone(limits.read(fetch, self.cred))                 # expired: never refreshed
        self.creds(token="")
        self.assertIsNone(limits.read(fetch, self.cred))

    def test_errors_return_none(self):
        self.creds()
        self.assertIsNone(limits.read(lambda *_: (401, b"{}"), self.cred))

        def offline(*_):
            raise OSError("network unreachable")
        self.assertIsNone(limits.read(offline, self.cred))


def alert_sampler(temp=40.0, mem=0.5, block_end=0.0, five=None, week=None, five_reset=0.0, week_reset=0.0):
    return SimpleNamespace(temp=temp, mem_used=mem * 16e9, mem_total=16e9,
                           claude=claude.ClaudeStats(ready=True, block_end=block_end, email="a@example.com"),
                           limits=limits.PlanLimits(ready=True, five=five, week=week, five_reset=five_reset, week_reset=week_reset))


class AlertRules(unittest.TestCase):
    def setUp(self):
        self.sent = []
        self.a = alerts.Alerts(lambda t, x: self.sent.append(t))

    def test_hot_must_be_sustained_then_cools_down(self):
        s = alert_sampler(temp=90)
        self.a.check(s, now=1000)
        self.a.check(s, now=1029)
        self.assertEqual(self.sent, [])
        self.a.check(s, now=1030)
        self.assertEqual(self.sent, ["Running hot"])
        s.temp = 50                                                       # cools, heats again: still in cooldown
        self.a.check(s, now=1040)
        s.temp = 90
        self.a.check(s, now=1100)
        self.a.check(s, now=1140)
        self.assertEqual(self.sent, ["Running hot"])
        self.a.check(s, now=1030 + 15 * 60)
        self.assertEqual(self.sent, ["Running hot"] * 2)

    def test_memory_and_dip_resets_the_timer(self):
        s = alert_sampler(mem=0.95)
        self.a.check(s, now=0)
        s.mem_used = 0.5 * 16e9
        self.a.check(s, now=20)
        s.mem_used = 0.93 * 16e9
        self.a.check(s, now=25)
        self.a.check(s, now=50)
        self.assertEqual(self.sent, [])
        self.a.check(s, now=55)
        self.assertEqual(self.sent, ["Memory almost full"])

    def test_block_reset(self):
        s = alert_sampler(block_end=500)
        self.a.check(s, now=100)
        self.assertEqual(self.sent, [])
        s.claude.block_end = 0
        self.a.check(s, now=501)
        self.assertEqual(self.sent, ["5-hour block reset"])
        self.a.check(s, now=600)
        self.assertEqual(len(self.sent), 1)

    def test_limits_cross_80_then_95_once_per_window(self):
        s = alert_sampler(five=0.5, five_reset=9000)
        self.a.check(s, now=0)
        s.limits.five = 0.85
        self.a.check(s, now=1)
        self.a.check(s, now=2)
        self.assertEqual(self.sent, ["5-hour limit 85% used"])
        s.limits.five = 0.97                                              # one notice, not both marks
        self.a.check(s, now=3)
        self.assertEqual(self.sent[1:], ["5-hour limit 97% used"])
        s.limits.five, s.limits.five_reset = 0.81, 27000                 # a new window crosses 80% again
        s.limits.week, s.limits.week_reset = 0.99, 50000
        self.a.check(s, now=4)
        self.assertEqual(self.sent[2:], ["5-hour limit 81% used", "Weekly limit 99% used"])

    def test_disabled(self):
        self.a.enabled = False
        s = alert_sampler(temp=99, mem=0.99, five=0.99)
        for t in range(0, 100, 10):
            self.a.check(s, now=t)
        self.assertEqual(self.sent, [])


class SettingsFile(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "pulse", "settings.json")
            s = settings.Settings()
            s.left, s.top, s.size, s.on_top = 10, 20, "landscape", False
            s.scale, s.opacity, s.alerts, s.limits, s.claude_open = 1.5, 0.7, False, False, True
            s.positions = {"0,0,1920x1080|Landscape": [12, 12]}
            s.save(path)
            r = settings.Settings.load(path)
            self.assertEqual((r.left, r.top, r.size, r.on_top, r.scale, r.opacity, r.alerts, r.limits, r.claude_open),
                             (10, 20, "landscape", False, 1.5, 0.7, False, False, True))
            self.assertEqual(r.positions, {"0,0,1920x1080|Landscape": [12.0, 12.0]})

    def test_defaults_and_bad_values(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "settings.json")
            r = settings.Settings.load(path)                              # missing file
            self.assertEqual((r.size, r.scale, r.opacity, r.alerts, r.limits, r.claude_open),
                             ("full", 1.0, 1.0, True, True, False))
            with open(path, "w") as f:
                json.dump({"size": "huge", "scale": 9, "opacity": "x", "positions": {"k": [1], "ok": [3, 4], "bad": "x"}}, f)
            r = settings.Settings.load(path)
            self.assertEqual((r.size, r.scale, r.opacity), ("full", 2, 1.0))
            self.assertEqual(r.positions, {"ok": [3.0, 4.0]})


class Geometry(unittest.TestCase):
    WA = (0, 0, 1920, 1040)

    def test_snap_to_edges_corners_and_centre(self):
        self.assertEqual(geometry.snap(20, 30, 320, 700, self.WA), (12, 12))                    # top-left corner
        self.assertEqual(geometry.snap(1580, 300, 320, 700, self.WA), (1588, 300))              # right edge
        self.assertEqual(geometry.snap(805, 320, 320, 700, self.WA), (800, 328))                # centre line, bottom
        self.assertEqual(geometry.snap(500, 200, 320, 700, self.WA), (500, 200))                # nowhere near

    def test_scales(self):
        self.assertEqual(geometry.nearest_scale(1.3), 1.25)
        self.assertEqual(geometry.nearest_scale(0.5), 1)
        self.assertEqual(geometry.step_scale(1, 1), 1.25)
        self.assertEqual(geometry.step_scale(2, 1), 2)
        self.assertEqual(geometry.step_scale(1.1, -1), 1)

    def test_layout_key_is_order_independent(self):
        a = geometry.layout_key([(1920, 0, 2560, 1440), (0, 0, 1920, 1080)], "full")
        b = geometry.layout_key([(0, 0, 1920, 1080), (1920, 0, 2560, 1440)], "full")
        self.assertEqual(a, b)
        self.assertEqual(a, "0,0,1920x1080;1920,0,2560x1440|Full")
        self.assertTrue(geometry.on_screen([(0, 0, 1920, 1080)], 100, 100))
        self.assertFalse(geometry.on_screen([(0, 0, 1920, 1080)], 1900, 100))

    def test_grip_and_morph(self):
        self.assertTrue(geometry.in_grip(310, 700, 320, 710, right=False))
        self.assertFalse(geometry.in_grip(5, 700, 320, 710, right=False))
        self.assertTrue(geometry.in_grip(5, 700, 320, 710, right=True))
        self.assertEqual(geometry.morph_frame((320, 700, 14), (660, 500, 14), 660, True, 0), (340, 320, 700, 14))
        self.assertEqual(geometry.morph_frame((320, 700, 14), (660, 500, 14), 660, True, 1), (0, 660, 500, 14))
        self.assertEqual(geometry.ease_out_quart(1), 1)
        self.assertGreater(geometry.ease_out_quart(0.25), 0.6)                           # quick start, soft landing

    def test_gallery_layout(self):
        s = Sampler(background=False)
        s.load_demo()
        sizes = {z: view.PulseView(s, z).measure() for z in view.VIEWS}
        w, h, cards = geometry.gallery_layout(sizes)
        self.assertEqual(set(cards), set(view.VIEWS))
        self.assertAlmostEqual(cards["full"][2], 320 * 0.5 + 11)
        self.assertLess(cards["full"][0], cards["claude"][0])                            # tall ones side by side
        self.assertLess(cards["claude"][0], cards["landscape"][0])
        self.assertEqual(cards["landscape"][0], cards["compact"][0])                     # wide and short stacked
        self.assertLess(cards["landscape"][1], cards["compact"][1])
        self.assertLess(cards["compact"][1], cards["mini"][1])
        for x, y, cw, ch in cards.values():
            self.assertLessEqual(x + cw, w)
            self.assertLessEqual(y + ch, h)


class Render(unittest.TestCase):
    def sampler(self):
        s = Sampler(background=False)
        s.load_demo()
        return s

    def test_sizes_and_layout_are_stable(self):
        s = self.sampler()
        full, compact, mini = (view.PulseView(s, z).measure() for z in (view.FULL, view.COMPACT, view.MINI))
        self.assertEqual(full[0], 320)
        self.assertEqual(compact, (320, 144))
        self.assertEqual(mini[1], 29)
        self.assertLess(mini[0], 320)
        self.assertGreater(full[1], compact[1])

    def test_row_hit_testing(self):
        v = view.PulseView(self.sampler())
        v.measure()
        self.assertEqual(v.row_at((v.cpu_row[0] + v.cpu_row[1]) / 2), "cpu")
        self.assertEqual(v.row_at((v.mem_row[0] + v.mem_row[1]) / 2), "mem")
        self.assertIsNone(v.row_at(v.header_bottom - 1))
        v.size = view.COMPACT
        self.assertIsNone(v.row_at((v.cpu_row[0] + v.cpu_row[1]) / 2))

    def test_top_list_makes_full_taller(self):
        s = self.sampler()
        v = view.PulseView(s)
        base = v.measure()[1]
        s.top_mode = "cpu"
        self.assertGreater(v.measure()[1], base)

    def test_size_cycle(self):
        seen = [view.FULL]
        for _ in range(5):
            seen.append(view.next_size(seen[-1]))
        self.assertEqual(seen, ["full", "landscape", "claude", "compact", "mini", "full"])

    def test_landscape_and_claude_views(self):
        s = self.sampler()
        land = view.PulseView(s, view.LANDSCAPE)
        w, h = land.measure()
        self.assertEqual(w, 660)
        self.assertLess(h, view.PulseView(s, view.FULL).measure()[1])
        self.assertGreater(land.claude_area[0], 320)                     # Claude on the right column
        self.assertTrue(land.claude_at(land.claude_area[0] + 5, land.claude_area[1] + 20))
        cl = view.PulseView(s, view.CLAUDE)
        self.assertEqual(cl.measure()[0], 320)
        self.assertFalse(cl.claude_at(cl.claude_area[0] + 5, cl.claude_area[1] + 20))   # always open: no toggle

    def test_breakdown_toggle(self):
        s = self.sampler()
        v = view.PulseView(s)
        closed = v.measure()[1]
        v.claude_open = True
        opened = v.measure()[1]
        self.assertGreater(opened, closed)
        s.claude.by_model = [claude.Slice(f"M{i}", 10 - i, 0) for i in range(5)]         # "+2 MORE" adds a line
        self.assertGreater(v.measure()[1], opened)

    def test_limit_rows_only_for_present_windows(self):
        s = self.sampler()
        v = view.PulseView(s, view.CLAUDE)
        both = v.measure()[1]
        s.limits.week = None
        one = v.measure()[1]
        s.limits.five = None
        none = v.measure()[1]
        self.assertEqual(both - one, 16)
        self.assertEqual(one - none, 16 + 4)

    @staticmethod
    def tips(v):
        import cairo
        w, h = v.measure()
        v.paint(cairo.Context(cairo.ImageSurface(cairo.FORMAT_ARGB32, int(w) + 1, int(h) + 1)))
        return [t for _r, t in v.tips]

    def test_tooltips(self):
        s = self.sampler()
        v = view.PulseView(s)
        tips = self.tips(v)
        self.assertIn("CPU 34.0% across 8 cores · 241 processes", tips)
        self.assertIn("5-hour limit 34% used · resets " + alerts.clock(s.limits.five_reset), tips)
        self.assertIn("412,600,000 tokens this week (all accounts on this PC)", tips)
        self.assertIn("Click for tokens by model, project and account", tips)
        cpu = next(r for r, t in v.tips if t.startswith("CPU"))
        self.assertTrue(v.tip_at(cpu[0] + 5, cpu[1] + 5)[0].startswith("CPU"))
        self.assertIsNone(v.tip_at(-50, -50))
        v.claude_open = True
        self.assertIn("OPUS: 301,200,000 tokens · $151.00 est.", self.tips(v))
        self.assertIn("Plan limits used: 5H 34% · week 42%", self.tips(view.PulseView(s, view.COMPACT)))
        self.assertTrue(self.tips(view.PulseView(s, view.MINI)))

    def test_compact_falls_back_without_limits(self):
        from pulse.limits import PlanLimits
        s = self.sampler()
        s.limits = PlanLimits()
        self.assertFalse(any(t.startswith("Plan limits") for t in self.tips(view.PulseView(s, view.COMPACT))))

    def test_ultra_label_is_rainbow(self):
        import cairo
        s = self.sampler()
        v = view.PulseView(s, view.CLAUDE)
        self.tips(v)
        self.assertIsNone(v.rainbow)
        s.claude.plan = "Ultra"
        self.tips(v)
        text, right, y = v.rainbow
        self.assertEqual((text, right), ("ULTRA", 302))
        self.assertEqual(loops.rainbow_phase(3.5), 32)                   # half a period after half of 7 s
        self.assertEqual(loops.rainbow_phase(3.5, motion=False), 0)
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 330, 400)
        v.paint(cairo.Context(surf))
        surf.flush()
        stride, data = surf.get_stride(), bytes(surf.get_data())
        colors = set()
        for xx in range(int(right - px.width("ULTRA", 1)), int(right)):
            for yy in range(int(y), int(y) + 7):
                b, g, r, a = data[yy * stride + xx * 4: yy * stride + xx * 4 + 4]
                if a and not r == g == b:
                    colors.add((r, g, b))
        self.assertGreater(len(colors), 3)                                # tinted, and not one flat colour
        v.live_rainbow = True                                             # the window: loops.draw paints it instead
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 330, 400)
        v.paint(cairo.Context(surf))
        surf.flush()
        data = bytes(surf.get_data())
        self.assertFalse(any(not data[yy * stride + xx * 4] == data[yy * stride + xx * 4 + 1] == data[yy * stride + xx * 4 + 2]
                             for xx in range(int(right) - 29, int(right)) for yy in range(int(y), int(y) + 7)))

    def test_renders_every_size_without_a_sensor(self):
        import cairo
        s = self.sampler()
        s.temp = s.temp_max = s.gpu = None                  # a machine with no readable sensors
        s.swap_total = 0
        s.limits.five = s.limits.week = None
        for z in view.VIEWS:
            v = view.PulseView(s, z)
            v.claude_open = True
            w, h = v.measure()
            surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, int(w) + 1, int(h) + 1)
            dc = cairo.Context(surf)
            v.paint(dc)
            loops.draw(dc, v, 0.7, h)
            data = bytes(surf.get_data())
            self.assertTrue(any(data[i] for i in range(0, len(data), 4)), z)   # something was drawn

    def test_hot_temperature(self):
        s = self.sampler()
        v = view.PulseView(s)
        s.temp = 90
        self.assertTrue(v.hot)
        s.temp = 50
        self.assertFalse(v.hot)

    def test_every_glyph_used_by_the_ui_exists(self):
        for ch in ("PULSE CPU MEM TMP DSK GPU NETWORK SWAP POWER CLAUDE CODE BY MODEL PROJECT ACCOUNT LIMIT WEEK MORE "
                   "CHOOSE A VIEW ESC TO CLOSE FULL LANDSCAPE COMPACT MINI 0123456789%·°↓↑⚡$~+-/.:@"):
            self.assertTrue(px.has(ch), ch)

    def test_tween_only_when_segment_changes(self):
        tw = view.Tweens()
        tw.get("k", 0.5, 28)
        tw.begin_frame()
        tw.get("k", 0.5001, 28)                              # same segment: no animation
        self.assertFalse(tw.active)
        tw.begin_frame()
        tw.get("k", 0.9, 28)
        self.assertTrue(tw.active)


class Snapshot(unittest.TestCase):
    def test_cli_writes_pngs(self):
        from pulse import __main__ as cli
        with tempfile.TemporaryDirectory() as d:
            for args, width in ((["--demo"], 640), (["--demo", "--compact"], 640), (["--demo", "--mini"], None),
                                (["--demo", "--top", "mem"], 640), (["--demo", "--landscape"], 1320),
                                (["--demo", "--claude", "--open"], 640)):
                out = os.path.join(d, "s.png")
                self.assertEqual(cli.main(["--snapshot", out] + args), 0)
                with open(out, "rb") as f:
                    head = f.read(24)
                self.assertEqual(head[:8], b"\x89PNG\r\n\x1a\n")
                if width:
                    self.assertEqual(int.from_bytes(head[16:20], "big"), width)


class LiveSampler(unittest.TestCase):
    @unittest.skipUnless(os.path.exists("/proc/stat"), "needs Linux")
    def test_real_proc_reads(self):
        s = Sampler(background=False)
        time.sleep(0.2)
        s.sample()
        self.assertTrue(s.cores)
        self.assertGreater(s.mem_total, 1)
        self.assertGreaterEqual(s.cpu, 0)
        top = probes.TopProbe()
        top.read("mem")
        self.assertTrue(top.read("mem"))


if __name__ == "__main__":
    unittest.main()
