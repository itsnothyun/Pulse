"""Collects every metric. Cheap probes run each second on the caller's thread; slow ones in workers.

The sampler never imports GTK: `post` is how a worker hands its result back to the UI thread
(the app passes GLib.idle_add; tests and --snapshot leave the default, which runs it inline).
"""
import math
import random
import threading
import time
from datetime import datetime

from . import probes
from .claude import ClaudeStats, ClaudeUsage


class Sampler:
    def __init__(self, post=None, background=True):
        self.post = post or (lambda fn: fn())
        self.background = background             # False for --snapshot: probes run via probe_sync()
        self.cpu = 0.0
        self.cores = []
        self.mem_used, self.mem_total = 0.0, 1.0
        self.swap_used, self.swap_total = 0.0, 0.0
        self.disk_used, self.disk_total, self.disk_name = 0.0, 1.0, "/"
        self.temp = None
        self.temp_max = None
        self.gpu = None
        self.net_in = self.net_out = 0.0
        self.procs = self.threads = 0
        self.uptime = 0.0
        self.battery = None                       # (percent, charging, on_ac)
        self.claude = ClaudeStats()
        self.top = []                             # [(name, value)]
        self.clock = ""
        self.tick = False
        self.hist = {}
        self.updated = []                         # callbacks, run after every sample
        self.top_mode = None
        self._top_busy = self._probe_busy = self._claude_busy = False
        self._top_probe = probes.TopProbe()
        self._claude = ClaudeUsage()
        self._prev_cpu = probes.read_cpu_times()
        self._prev_net = probes.read_net()
        self._prev_net_time = time.monotonic()
        self._n = 0
        self.sample()

    # ---------- top-process list ----------

    def set_top_mode(self, mode):
        self.top_mode = mode
        self.top = []
        self._refresh_top()
        self._notify()

    def _refresh_top(self):
        mode = self.top_mode
        if mode is None or self._top_busy or not self.background:
            return
        self._top_busy = True

        def work():
            try:
                result = self._top_probe.read(mode)
            except Exception:
                result = None

            def done():
                self._top_busy = False
                if result is not None and self.top_mode == mode:
                    self.top = result
                    self._notify()
            self.post(done)
        threading.Thread(target=work, daemon=True).start()

    def top_sync(self, mode):
        """Synchronous read for --snapshot (two passes, so CPU has a delta)."""
        self.top_mode = mode
        self._top_probe.read(mode)
        time.sleep(0.5)
        self.top = self._top_probe.read(mode)

    # ---------- sampling ----------

    def history(self, key):
        return self.hist.get(key, [])

    def _push(self, key, v):
        h = self.hist.setdefault(key, [])
        h.append(max(0.0, min(1.0, v)))
        if len(h) > 40:
            h.pop(0)

    def _notify(self):
        for cb in self.updated:
            cb()

    def sample(self):
        self.tick = not self.tick
        self.clock = datetime.now().strftime("%H:%M")

        t = probes.read_cpu_times()
        if t and len(t) == len(self._prev_cpu):
            busy_all = tot_all = 0.0
            cores = []
            for (idle, total), (pidle, ptotal) in zip(t, self._prev_cpu):
                d_total = total - ptotal
                busy = d_total - (idle - pidle)
                busy_all += busy
                tot_all += d_total
                cores.append(max(0.0, min(1.0, busy / d_total)) if d_total > 0 else 0.0)
            self.cores = cores
            self.cpu = max(0.0, min(1.0, busy_all / tot_all)) if tot_all > 0 else 0.0
        self._prev_cpu = t or self._prev_cpu
        self._push("cpu", self.cpu)

        m = probes.read_memory()
        if m:
            self.mem_used, self.mem_total, self.swap_used, self.swap_total = m
        self._push("mem", self.mem_used / self.mem_total)

        if self._n % 5 == 0:
            d = probes.read_disk()
            if d:
                self.disk_used, self.disk_total, self.disk_name = d
        self._push("dsk", self.disk_used / self.disk_total)

        # sysfs is cheap but nvidia-smi is a process spawn -- keep both off the UI thread.
        if self.background and self._n % 3 == 0 and not self._probe_busy:
            self._probe_busy = True
            read_gpu = self._n % 2 == 0

            def work():
                temps = probes.read_temps()
                gpu = probes.read_gpu() if read_gpu else None
                if not temps:
                    g = probes.read_gpu_temp()
                    temps = [g] if g else []

                def done():
                    self._probe_busy = False
                    if temps:
                        self.temp = max(temps)
                        self.temp_max = max(self.temp_max or 0, self.temp)
                    if read_gpu:
                        self.gpu = gpu
                self.post(done)
            threading.Thread(target=work, daemon=True).start()
        if self.temp is not None:
            self._push("tmp", (self.temp - 30) / 70)
        self._push("gpu", self.gpu or 0)

        rx, tx = probes.read_net()
        now = time.monotonic()
        dt = max(now - self._prev_net_time, 0.1)
        self.net_in = max(rx - self._prev_net[0], 0) / dt
        self.net_out = max(tx - self._prev_net[1], 0) / dt
        self._prev_net, self._prev_net_time = (rx, tx), now
        self._push("net", math.log10(max(self.net_in, 1)) / 8)

        if self._n % 5 == 0:
            self.procs, self.threads = probes.read_perf()
            self.uptime = probes.read_uptime()
        if self._n % 10 == 0:
            self.battery = probes.read_battery()

        if self.background and self._n % 20 == 0 and not self._claude_busy:
            self._claude_busy = True

            def claude_work():
                try:
                    result = self._claude.scan()
                except Exception:
                    result = None

                def done():
                    self._claude_busy = False
                    if result is not None:
                        self.claude = result
                        self._notify()
                self.post(done)
            threading.Thread(target=claude_work, daemon=True).start()

        if self._n % 2 == 0:
            self._refresh_top()

        self._n += 1
        self._notify()

    def probe_sync(self):
        """Synchronous version of the background probes, for --snapshot."""
        temps = probes.read_temps()
        if not temps and (g := probes.read_gpu_temp()):
            temps = [g]
        if temps:
            self.temp = self.temp_max = max(temps)
        self.gpu = probes.read_gpu()
        self.claude = self._claude.scan()

    def load_demo(self):
        """Plausible fake numbers for screenshots (--demo), so no real usage is published."""
        rnd = random.Random(7)

        def wave(i, b, a):
            return max(0.0, min(1.0, b + a * math.sin(i / 4.0) + (rnd.random() - 0.5) * a))

        self.hist.clear()
        for i in range(40):
            self._push("cpu", wave(i, 0.32, 0.18)); self._push("mem", wave(i, 0.62, 0.03)); self._push("dsk", 0.58)
            self._push("tmp", wave(i, 0.27, 0.06)); self._push("gpu", wave(i, 0.2, 0.15)); self._push("net", wave(i, 0.6, 0.15))
        gib = 1073741824
        self.cpu = 0.34
        self.cores = [0.62, 0.48, 0.41, 0.35, 0.22, 0.18, 0.12, 0.08]
        self.mem_used, self.mem_total = 10.4 * gib, 16.0 * gib
        self.swap_used, self.swap_total = 1.2e9, 2.1e9
        self.disk_used, self.disk_total, self.disk_name = 287e9, 494e9, "/"
        self.temp, self.temp_max, self.gpu = 48, 55, 0.21
        self.net_in, self.net_out = 1.84e6, 212e3
        self.procs, self.threads, self.uptime = 241, 3120, 3 * 86400 + 5 * 3600
        self.battery = None
        self.clock = "09:41"
        if self.top_mode == "cpu":
            self.top = [("code", 61), ("chrome", 23), ("gnome-shell", 14)]
        if self.top_mode == "mem":
            self.top = [("code", 3.1e9), ("chrome", 1.8e9), ("claude", 0.9e9)]
        self.claude = ClaudeStats(
            ready=True, week=412.6e6, today=58.3e6, block=31.9e6, output=2.41e6, cost=184.2,
            block_end=time.time() + 2 * 3600 + 14 * 60 + 30, input=9.8e6, cache_read=400.4e6,
            sessions=9, live=1, calls=3184, today_index=3, days=[88e6, 102e6, 164e6, 58.3e6, 0, 0, 0])
