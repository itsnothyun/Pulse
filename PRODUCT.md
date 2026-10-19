# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Delegated: static HTML/CSS/JS with no build step, in `site/`. Chosen because the user will self-host on a VPS (any web server can serve the folder as-is), and a single marketing page does not need a framework.

## Users

Mac and Windows users who keep an eye on their machine and want a monitor that looks good on the desktop, not another Activity Monitor or Task Manager window. A large subset are developers who use Claude Code daily and want to see what they spend. Vitals hook first; the Claude Code tally is the differentiator.

## Product Purpose

Pulse is a small, always-visible desktop widget that shows a machine's vital signs at a glance, plus a weekly tally of Claude Code tokens. Success: people install it and keep it on their desktop. Success for the marketing page: visitors star the GitHub repo (primary) and download it (secondary).

## Positioning

The only desktop system monitor that also counts your Claude Code tokens for the week, read locally from Claude Code's own transcripts, with no account and no network. Rendered entirely in a hand-made 5×7 pixel font, monochrome, on both macOS and Windows from one design.

## Operating Context

Sits on the desktop beside an editor, terminal or browser all day. Drag to place; click the header for a compact strip; right-click for options (compact, always on top, launch at login, Activity Monitor / Task Manager, quit). Installed from GitHub Releases: a zipped `.app` on macOS (ad-hoc signed, needs `xattr -dr com.apple.quarantine`), a single self-contained `Pulse.exe` on Windows (SmartScreen warns; not code-signed).

## Capabilities and Constraints

- Metrics: CPU total + per-core meters, memory, temperature (Apple Silicon SoC sensors; ACPI thermal zone on Windows, may be N/A), disk, GPU, network up/down, swap (macOS) / commit (Windows), battery/power, uptime.
- Claude Code: tokens this week (Mon–Sun), today, current 5-hour block with reset countdown, estimated API-rate cost, output, sessions, live sessions, calls, cached vs new input.
- Click CPU or MEM (Full size) for the three heaviest processes. Claude Code only; cannot see the Claude desktop/web apps or plan limits.
- Idles at a few percent CPU; loop animations run on the compositor; respects reduced motion.
- macOS 13+ (universal), Windows 10/11 x64. Free, MIT licensed, open source.
- Not decided: custom domain, code signing/notarization, a paid tier (none planned).

## Brand Commitments

- Name: Pulse. Icon: a pixel heartbeat trace on a black rounded tile (`assets/icon.png`).
- Visual identity is the widget itself: monochrome (near-black ground, warm off-white pixels, greys), the 5×7 pixel font, segmented bars, sparklines, faint scanlines. The user asked for the marketing page to carry this design style.
- Voice: plain, short, technical but warm; uppercase pixel labels in the UI.

## Evidence on Hand

- Real renders: `docs/pulse-macos.png`, `docs/pulse-macos-compact.png`, `docs/pulse-windows.png` (demo data, labeled as such).
- Live repo and v1.0.0 release with both platform builds.
- No testimonials, user counts, press, star counts or benchmarks exist; do not invent them.

## Product Principles

1. Glanceable over exhaustive: one look tells you how the machine is doing.
2. Local and private: reads only what's on the machine, sends nothing.
3. Quiet by default: subtle motion, tiny footprint, never nags.
4. One design, every desktop: macOS and Windows look and behave the same.

## Accessibility & Inclusion

Honor reduced-motion preferences (the app already does). Pixel type must stay legible: real text for content, pixel rendering for display and data.
