# Pulse for Linux (DGX Spark) — design

Goal: the same widget as macOS and Windows — Full / Compact / Mini sizes, hand-drawn 5×7 pixel
font, header scanner, live pip, CRT sweep, click-header-to-resize, click CPU/MEM for top processes,
right-click menu, drag to move with remembered position, Claude Code usage block — running natively
on a DGX Spark (aarch64, DGX OS = Ubuntu 24.04 + GNOME).

## Approach

Python 3 + GTK 3 (PyGObject) + Cairo, shipped as source (`linux/pulse/`). Nothing to compile, so it
runs on aarch64 and x86-64 alike, and DGX OS already has `python3-gi`.

GTK 3 rather than 4 on purpose: GTK 4 removed window positioning and always-on-top. Under GNOME
Wayland the app opts into XWayland (`GDK_BACKEND=x11`) so *remember position*, *Always on Top* and
*all workspaces* behave exactly as on the other platforms.

## Modules

| file | role | depends on |
|---|---|---|
| `pixelfont.py` | glyph table (copied from `Glyphs.cs`), ink palette, text drawing | cairo |
| `fmt.py` | number formatting (`F` in the C# port) | – |
| `probes.py` | `/proc`, `/sys`, `nvidia-smi` readers; parsers take text so they are testable anywhere | stdlib |
| `claude.py` | incremental `~/.claude/projects` scanner, pricing table, 5-hour blocks | stdlib |
| `sampler.py` | owns all metrics, history, 1 s tick, background probes, demo data | probes, claude |
| `view.py` | `PulseView.paint(ctx)` — pure Cairo, also used for measuring | pixelfont, sampler |
| `loops.py` | scanner / pip / sweep overlay drawn over a cached base frame | pixelfont |
| `settings.py` | `~/.config/pulse/settings.json`, autostart `.desktop` | stdlib |
| `app.py` | GTK window, drag, click, menu, timers | gi |
| `__main__.py` | CLI: widget, or `--snapshot out.png [--compact\|--mini] [--demo] [--top cpu\|mem]` | – |

`--snapshot` never imports GTK, so CI and tests render the real UI headlessly.

## Linux metric mapping

| row | source |
|---|---|
| CPU, cores | `/proc/stat` per-core deltas (GB10 has 20 cores) |
| MEM | `MemTotal − MemAvailable` (unified memory: this is also the GPU's memory) |
| TMP | max of `/sys/class/thermal/*/temp` and hwmon `temp*_input`; falls back to GPU temp; `N/A` if none |
| DSK | `statvfs("/")` |
| GPU | `nvidia-smi --query-gpu=utilization.gpu` (low rate, background); AMD `gpu_busy_percent` fallback; else `N/A` |
| NETWORK | `/proc/net/dev`, skipping `lo`, `docker*`, `veth*`, `br-*`, `virbr*` |
| SWAP (tile) | `SwapTotal − SwapFree` (macOS shows swap too; Windows shows commit) |
| POWER (tile) | `/sys/class/power_supply`; `AC / NO BATTERY` on a Spark |
| procs / threads | `/proc` entry count / 4th field of `/proc/loadavg` |
| top 3 | `/proc/*/stat` tick deltas (CPU % of all cores) and RSS, grouped by command name |

## Window behaviour

Borderless RGBA window, `UTILITY` hint, skip taskbar/pager, sticky, keep-above (setting). Drag starts
after 3 px of motion via `begin_move_drag`; a press-release without motion is a click (header → next
size, CPU/MEM row → top list). Right-hand widgets grow leftwards. 350 ms fade-in. Loops honour
`gtk-enable-animations`. Single instance via `flock`.

## Out of scope

Native Wayland positioning, a system-tray icon, packaging as `.deb` (install is `linux/install.sh`).

## Testing

`unittest` under `linux/tests`: formatting, text parsers for every probe, Claude scanner on a fixture
transcript (dedupe, incremental read, cost, 5 h block), and snapshot smoke tests (all sizes + demo
produce a PNG with the expected dimensions). CI runs them plus a snapshot on `ubuntu-24.04-arm`.
