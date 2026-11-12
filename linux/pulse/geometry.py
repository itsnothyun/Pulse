"""Window maths with no GTK in it, so it can be tested: easing, scale snap points, edge snapping,
per-monitor-layout position keys and the view gallery's layout. Numbers mirror windows/Pulse/WidgetWindow.cs
and Gallery.cs."""
from . import pixelfont as px
from .settings import SCALES

GRIP, SNAP_MARGIN, SNAP_REACH = 14, 12, 28
MORPH_TIME, GLIDE_TIME = 0.28, 0.22


def ease_out_quart(p):
    return 1 - (1 - max(0.0, min(1.0, p))) ** 4


def ease_out_quad(p):
    return 1 - (1 - max(0.0, min(1.0, p))) ** 2


def lerp(a, b, p):
    return a + (b - a) * p


def nearest_scale(scale):
    best = SCALES[0]
    for s in SCALES:
        if abs(s - scale) < abs(best - scale):
            best = s
    return best


def step_scale(scale, direction):
    """The next snap point up (+1) or down (-1) from the one nearest `scale`."""
    i = SCALES.index(nearest_scale(scale)) + (1 if direction > 0 else -1)
    return SCALES[max(0, min(len(SCALES) - 1, i))]


def layout_key(monitors, view):
    """Positions are remembered per view and per monitor arrangement, so docking or undocking a laptop puts each
    view back where it lived. `monitors` is a list of (x, y, w, h)."""
    rects = sorted(monitors, key=lambda r: (r[0], r[1]))
    return ";".join(f"{x},{y},{w}x{h}" for x, y, w, h in rects) + "|" + view.capitalize()


def on_screen(monitors, x, y):
    """True when a window whose top-left is (x, y) still has its grab area on one of the monitors."""
    return any(mx <= x + 40 < mx + mw and my <= y + 20 < my + mh for mx, my, mw, mh in monitors)


def snap(left, top, w, h, wa):
    """After a drag, a widget dropped near an edge, corner or the centre line of its monitor's work area
    (x, y, w, h) lands on it."""
    ax, ay, aw, ah = wa
    l, t = left, top
    if abs(l - (ax + SNAP_MARGIN)) < SNAP_REACH:
        l = ax + SNAP_MARGIN
    elif abs(ax + aw - SNAP_MARGIN - (l + w)) < SNAP_REACH:
        l = ax + aw - SNAP_MARGIN - w
    elif abs(l + w / 2 - (ax + aw / 2)) < SNAP_REACH / 2:
        l = ax + (aw - w) / 2
    if abs(t - (ay + SNAP_MARGIN)) < SNAP_REACH:
        t = ay + SNAP_MARGIN
    elif abs(ay + ah - SNAP_MARGIN - (t + h)) < SNAP_REACH:
        t = ay + ah - SNAP_MARGIN - h
    return round(l), round(t)


def right_anchored(x, w, wa):
    """Right-hand widgets grow and shrink leftward, so the edge you placed stays put."""
    return x + w / 2 > wa[0] + wa[2] / 2


def in_grip(x, y, w, h, right):
    """The bottom corner away from the anchored edge is the resize grip."""
    return y >= h - GRIP and (x <= GRIP if right else x >= w - GRIP)


def morph_frame(old, new, total_w, right, p):
    """The rounded outline between two panel shapes (w, h, radius) at eased progress p: (x, w, h, radius)."""
    w, h, r = lerp(old[0], new[0], p), lerp(old[1], new[1], p), lerp(old[2], new[2], p)
    return (total_w - w if right else 0), w, h, r


# ---------- view gallery ----------

PREVIEW = 0.5
G_PAD = (16, 18, 16, 12)                  # left, top, right, bottom inside the 1 px border
TILE_MARGIN, CARD_PAD, CARD_BORDER = 8, 4, 1.5
LABEL_GAP, LABEL_INDENT = 8, 6
HEAD_H, HEAD_GAP, HEAD_INSET = 14, 6, 8
GALLERY_ORDER = ("full", "claude", "landscape", "compact", "mini")


def gallery_layout(sizes):
    """Full and Claude stand tall on the left; the wide and short views stack on the right.
    `sizes` maps view -> panel (w, h) at 1x. Returns (width, height, {view: (card_x, card_y, card_w, card_h)})."""
    inset = CARD_PAD + CARD_BORDER
    cards = {v: (sizes[v][0] * PREVIEW + 2 * inset, sizes[v][1] * PREVIEW + 2 * inset) for v in GALLERY_ORDER}

    def tile(v):
        cw, ch = cards[v]
        return cw + 2 * TILE_MARGIN, ch + LABEL_GAP + 7 + 2 * TILE_MARGIN

    x0, y0 = 1 + G_PAD[0], 1 + G_PAD[1] + HEAD_H + HEAD_GAP
    out, x, row_h = {}, x0, 0.0
    for v in ("full", "claude"):
        tw, th = tile(v)
        out[v] = (x + TILE_MARGIN, y0 + TILE_MARGIN) + cards[v]
        x += tw
        row_h = max(row_h, th)
    y, col_w = y0, 0.0
    for v in ("landscape", "compact", "mini"):
        tw, th = tile(v)
        out[v] = (x + TILE_MARGIN, y + TILE_MARGIN) + cards[v]
        y += th
        col_w = max(col_w, tw)
    row_h = max(row_h, y - y0)
    row_w = x + col_w - x0
    head_w = HEAD_INSET * 2 + px.width("CHOOSE A VIEW", 2) + 16 + px.width("ESC TO CLOSE", 1)
    width = 1 + G_PAD[0] + max(row_w, head_w) + G_PAD[2] + 1
    height = y0 + row_h + G_PAD[3] + 1
    return width, height, out
