import json
import os
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pulse import claude, fmt, loops, probes, view  # noqa: E402
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


def usage_line(ts, msg, req, inp=10, out=20, cw=30, cr=40, model="claude-sonnet-5-5", session="s1"):
    return json.dumps({"type": "assistant", "sessionId": session, "requestId": req, "timestamp": ts,
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

    def write(self, text, mode="a"):
        with open(self.file, mode) as f:
            f.write(text)

    def test_counts_dedupes_and_prices(self):
        now = datetime.now()
        ts = iso(now - timedelta(seconds=30))
        self.write(usage_line(ts, "msg_1", "req_1") + usage_line(ts, "msg_1", "req_1") + usage_line(ts, "msg_2", "req_2"))
        st = claude.ClaudeUsage(self.proj).scan(now.timestamp())
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
        u = claude.ClaudeUsage(self.proj)
        second = usage_line(ts, "msg_2", "req_2")
        self.write(usage_line(ts, "msg_1", "req_1") + second[:40])        # second line half-written
        self.assertEqual(u.scan(now.timestamp()).calls, 1)
        self.write(second[40:])
        self.assertEqual(u.scan(now.timestamp()).calls, 2)                # picked up from the saved offset

    def test_five_hour_block(self):
        now = datetime.now()
        self.write(usage_line(iso(now - timedelta(minutes=10)), "msg_1", "req_1"))
        st = claude.ClaudeUsage(self.proj).scan(now.timestamp())
        self.assertEqual(st.block, 100)
        self.assertGreater(st.block_end, now.timestamp())
        self.assertLessEqual(st.block_end - now.timestamp(), 5 * 3600)

    def test_unknown_model_is_free_and_old_events_ignored(self):
        now = datetime.now()
        self.write(usage_line(iso(now - timedelta(seconds=5)), "msg_1", "req_1", model="mystery-1"))
        self.write(usage_line(iso(now - timedelta(days=30)), "msg_9", "req_9"))
        st = claude.ClaudeUsage(self.proj).scan(now.timestamp())
        self.assertEqual((st.calls, st.cost), (1, 0))

    def test_missing_directory(self):
        st = claude.ClaudeUsage(os.path.join(self.dir.name, "nope")).scan()
        self.assertTrue(st.ready)
        self.assertEqual(st.week, 0)


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
        self.assertEqual(view.next_size(view.FULL), view.COMPACT)
        self.assertEqual(view.next_size(view.COMPACT), view.MINI)
        self.assertEqual(view.next_size(view.MINI), view.FULL)

    def test_renders_every_size_without_a_sensor(self):
        import cairo
        s = self.sampler()
        s.temp = s.temp_max = s.gpu = None                  # a machine with no readable sensors
        s.swap_total = 0
        for z in (view.FULL, view.COMPACT, view.MINI):
            v = view.PulseView(s, z)
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
        for ch in "PULSE CPU MEM TMP DSK GPU NETWORK SWAP POWER CLAUDE CODE 0123456789%·°↓↑⚡$~+-/.:":
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
                                (["--demo", "--top", "mem"], 640)):
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
