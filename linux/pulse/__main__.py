"""Pulse for Linux.

    python3 -m pulse                    start the widget (a second launch brings the running one back)
    python3 -m pulse --click-through    toggle click-through on the running widget (bind it to a shortcut)
    python3 -m pulse --snapshot out.png [--landscape|--claude|--compact|--mini] [--open] [--demo] [--top cpu|mem]
"""
import sys
import time

from . import view as V
from .sampler import Sampler


def snapshot(path, size, demo, top, open_breakdown=False):
    """Renders the widget to a PNG without opening a window (debug aid, used by CI). Needs only cairo."""
    import cairo
    from . import loops

    s = Sampler(background=False)
    if demo:
        if top:
            s.top_sync(top)
        s.load_demo()
    else:
        for _ in range(15):
            time.sleep(0.1)
            s.sample()
        s.probe_sync()
        if top:
            s.top_sync(top)
    v = V.PulseView(s, size)
    v.claude_open = open_breakdown
    w, h = v.measure()
    scale = 2
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, int(w * scale), int(h * scale))
    dc = cairo.Context(surf)
    dc.scale(scale, scale)
    v.paint(dc)
    loops.draw(dc, v, 1.0, h)
    surf.write_to_png(path)
    return 0


def main(argv):
    if "--snapshot" in argv:
        i = argv.index("--snapshot")
        if i + 1 >= len(argv):
            print("usage: --snapshot out.png", file=sys.stderr)
            return 2
        top = None
        if "--top" in argv and argv.index("--top") + 1 < len(argv):
            top = "mem" if argv[argv.index("--top") + 1] == "mem" else "cpu"
        size = (V.MINI if "--mini" in argv else V.COMPACT if "--compact" in argv else V.LANDSCAPE if "--landscape" in argv
                else V.CLAUDE if "--claude" in argv else V.FULL)
        return snapshot(argv[i + 1], size, "--demo" in argv, top, "--open" in argv)
    from .app import run
    return run(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
