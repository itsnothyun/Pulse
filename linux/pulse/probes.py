"""Linux readers for /proc, /sys and nvidia-smi.

Every parser takes text so it can be tested anywhere; the `read_*` wrappers add the file access
and swallow errors, returning None when a source is missing (the UI then shows N/A).
"""
import glob
import os
import shutil
import subprocess

CLK_TCK = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100
PAGE = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else 4096
NCPU = os.cpu_count() or 1


def _read(path):
    try:
        with open(path, "r", errors="replace") as f:
            return f.read()
    except OSError:
        return None


# ---------- CPU ----------

def parse_cpu_times(text):
    """Per-core (idle, total) jiffies from /proc/stat."""
    out = []
    for line in text.splitlines():
        if not line.startswith("cpu") or line.startswith("cpu "):
            continue
        f = line.split()
        v = [int(x) for x in f[1:9]] + [0] * (8 - len(f[1:9]))
        idle = v[3] + v[4]                   # idle + iowait
        out.append((idle, sum(v)))           # guest time is already inside user
    return out


def read_cpu_times():
    t = _read("/proc/stat")
    return parse_cpu_times(t) if t else []


# ---------- memory ----------

def parse_meminfo(text):
    kb = {}
    for line in text.splitlines():
        k, _, rest = line.partition(":")
        parts = rest.split()
        if parts:
            kb[k] = int(parts[0]) * 1024
    return kb


def read_memory():
    """(used, total, swap_used, swap_total) in bytes; used = total - available."""
    t = _read("/proc/meminfo")
    if not t:
        return None
    m = parse_meminfo(t)
    total = m.get("MemTotal", 0)
    if total <= 0:
        return None
    avail = m.get("MemAvailable", m.get("MemFree", 0))
    return (total - avail, total, m.get("SwapTotal", 0) - m.get("SwapFree", 0), m.get("SwapTotal", 0))


# ---------- disk ----------

def read_disk(path="/"):
    try:
        st = os.statvfs(path)
    except (OSError, AttributeError):
        return None
    total = st.f_blocks * st.f_frsize
    if total <= 0:
        return None
    return (total - st.f_bavail * st.f_frsize, total, path)


# ---------- network ----------

_SKIP_IF = ("lo", "docker", "veth", "br-", "virbr", "tailscale", "cni", "flannel")


def parse_netdev(text):
    rx = tx = 0
    for line in text.splitlines()[2:]:
        name, _, rest = line.partition(":")
        name = name.strip()
        if not rest or name == "lo" or name.startswith(_SKIP_IF[1:]):
            continue
        f = rest.split()
        rx += int(f[0])
        tx += int(f[8])
    return rx, tx


def read_net():
    t = _read("/proc/net/dev")
    return parse_netdev(t) if t else (0, 0)


# ---------- temperature ----------

def read_temps(root="/sys"):
    """Every plausible °C reading from thermal zones and hwmon, skipping drives and batteries."""
    temps = []
    for p in glob.glob(f"{root}/class/thermal/thermal_zone*/temp"):
        t = _read(p)
        if t and t.strip().lstrip("-").isdigit():
            temps.append(int(t) / 1000)
    for hw in glob.glob(f"{root}/class/hwmon/hwmon*"):
        name = (_read(f"{hw}/name") or "").strip()
        if name in ("nvme", "drivetemp", "BAT0", "BAT1"):
            continue
        for p in glob.glob(f"{hw}/temp*_input"):
            t = _read(p)
            if t and t.strip().lstrip("-").isdigit():
                temps.append(int(t) / 1000)
    return [t for t in temps if 1 < t < 150]


def read_gpu_temp():
    r = _nvidia("temperature.gpu")
    return r if r is not None else None


# ---------- GPU ----------

def _nvidia(field):
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    try:
        out = subprocess.run([exe, f"--query-gpu={field}", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=3).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    vals = []
    for line in out.splitlines():
        try:
            vals.append(float(line.strip()))
        except ValueError:
            pass                              # "[N/A]" on parts of the GB10
    return max(vals) if vals else None


def read_gpu():
    """GPU utilisation 0..1: NVIDIA via nvidia-smi, AMD via sysfs, else None."""
    u = _nvidia("utilization.gpu")
    if u is not None:
        return max(0.0, min(1.0, u / 100))
    for p in glob.glob("/sys/class/drm/card*/device/gpu_busy_percent"):
        t = _read(p)
        if t and t.strip().isdigit():
            return int(t) / 100
    return None


# ---------- power ----------

def read_battery(root="/sys/class/power_supply"):
    """(percent, charging, on_ac) or None when the machine has no battery (a Spark)."""
    for bat in sorted(glob.glob(f"{root}/BAT*")):
        cap = _read(f"{bat}/capacity")
        if not cap or not cap.strip().isdigit():
            continue
        status = (_read(f"{bat}/status") or "").strip()
        ac = any((_read(p) or "").strip() == "1" for p in glob.glob(f"{root}/A*/online"))
        return int(cap), status == "Charging", ac or status in ("Charging", "Full")
    return None


# ---------- processes ----------

def read_perf():
    """(process count, thread count) -- threads are the kernel entities in /proc/loadavg."""
    procs = sum(1 for n in os.listdir("/proc") if n.isdigit()) if os.path.isdir("/proc") else 0
    la = _read("/proc/loadavg")
    threads = 0
    if la:
        try:
            threads = int(la.split()[3].split("/")[1])
        except (IndexError, ValueError):
            pass
    return procs, threads


def read_uptime():
    t = _read("/proc/uptime")
    try:
        return float(t.split()[0])
    except (AttributeError, IndexError, ValueError):
        return 0.0


def parse_proc_stat(text):
    """(command, cpu_ticks, rss_bytes) from one /proc/<pid>/stat; the command may contain spaces and ')'."""
    lp, rp = text.find("("), text.rfind(")")
    if lp < 0 or rp < lp:
        return None
    f = text[rp + 2:].split()
    # after the command: state is f[0]; utime f[11], stime f[12], rss (pages) f[21]
    return text[lp + 1:rp], int(f[11]) + int(f[12]), int(f[21]) * PAGE


class TopProbe:
    """Top three commands by CPU (% of all cores) or resident memory, grouped by command name."""

    def __init__(self):
        self.prev = {}
        self.stamp = 0.0

    def read(self, mode):
        import time
        now = time.monotonic()
        elapsed = now - self.stamp if self.stamp else 0.0
        ticks, by = {}, {}
        try:
            pids = [n for n in os.listdir("/proc") if n.isdigit()]
        except OSError:
            return []
        for pid in pids:
            t = _read(f"/proc/{pid}/stat")
            if not t:
                continue
            try:
                parsed = parse_proc_stat(t)
            except (IndexError, ValueError):
                continue
            if parsed is None:
                continue
            name, cpu_ticks, rss = parsed
            ticks[pid] = cpu_ticks
            cpu = 0.0
            if elapsed > 0 and pid in self.prev:
                cpu = max(cpu_ticks - self.prev[pid], 0) / CLK_TCK / (elapsed * NCPU) * 100
            c, m = by.get(name, (0.0, 0.0))
            by[name] = (c + cpu, m + rss)
        self.prev, self.stamp = ticks, now
        idx = 0 if mode == "cpu" else 1
        top = sorted(by.items(), key=lambda kv: kv[1][idx], reverse=True)[:3]
        return [(n, v[idx]) for n, v in top]
