"""Isometric "plant" version of the value stream map: every step stands on its own tile as a small illustrated
building (original drawings, plain SVG), with the same numbers as the 2D map, and the same animation on top.

Supplier and customer sit on the top row with production control between them; the flow runs along a conveyor in
the middle row; data cards and the timeline ladder are underneath, like the classic VSM layout.
"""

from __future__ import annotations

import math
from html import escape

import numpy as np

from flowline.reports.vsm_anim import _page
from flowline.reports.vsm_draw import INFO, INK, MUTED, WARN_FILL, WARN_LINE, supplier_note

W, H = 1200, 680
C30, S30 = math.cos(math.pi / 6), 0.5

# palette (original, muted)
PLATE_TOP, PLATE_SIDE = "#7a6d64", "#574c45"
CREAM = ("#f3e7c9", "#dccb9f", "#c3b07f")      # top, left, right
GREY = ("#e9ecef", "#c9cfd6", "#a9b1ba")
BLUE = ("#8fb5e8", "#5b8fd6", "#3f6fb5")
TEAL = ("#5fc9d3", "#2ba6b3", "#1d7f8a")
STEEL = ("#dfe6ee", "#b8c4d1", "#94a3b3")
ROOF_RED = ("#e98a6b", "#cf6a4c", "#a9513a")
NAVY = ("#3a5a85", "#1f3a5f", "#16304f")
CRATE = ("#e3c08a", "#c8a46e", "#a8854f")
CRATE_HOT = ("#ffd27a", "#eda100", "#b97f00")
GLASS = "#c9def5"


class Pen:
    def __init__(self, prefix: str = "p"):
        self.out: list[str] = []
        self.prefix, self.n = prefix, 0

    def uid(self) -> str:
        self.n += 1
        return f"{self.prefix}{self.n}"

    def poly(self, pts, fill, stroke="#3a3530", sw=0.8, extra=""):
        p = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        self.out.append(f'<polygon points="{p}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" stroke-linejoin="round"{extra}/>')

    def raw(self, s):
        self.out.append(s)

    def text(self, x, y, s, size=11, bold=False, anchor="middle", fill=INK):
        self.out.append(f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" text-anchor="{anchor}" fill="{fill}"'
                        + (' font-weight="600"' if bold else "") + f">{escape(str(s))}</text>")

    def line(self, x1, y1, x2, y2, stroke=INK, sw=1.4, dash=False, cls=""):
        self.out.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{stroke}" stroke-width="{sw}"'
                        + (' stroke-dasharray="6 4"' if dash else "") + (f' class="{cls}"' if cls else "") + "/>")


def P(cx, cy, u, v, z=0.0):
    """Isometric point: u along the right-going axis, v along the left-going axis, z up (screen units)."""
    return (cx + (u - v) * C30, cy + (u + v) * S30 - z)


def box(pen, cx, cy, w, d, h, col, z0=0.0, sw=0.8):
    """Box with its ground centre at (cx, cy): w along u, d along v, height h."""
    a, b = w / 2, d / 2
    top = [P(cx, cy, -a, -b, z0 + h), P(cx, cy, a, -b, z0 + h), P(cx, cy, a, b, z0 + h), P(cx, cy, -a, b, z0 + h)]
    left = [P(cx, cy, -a, b, z0), P(cx, cy, a, b, z0), P(cx, cy, a, b, z0 + h), P(cx, cy, -a, b, z0 + h)]
    right = [P(cx, cy, a, b, z0), P(cx, cy, a, -b, z0), P(cx, cy, a, -b, z0 + h), P(cx, cy, a, b, z0 + h)]
    pen.poly(left, col[1], sw=sw)
    pen.poly(right, col[2], sw=sw)
    pen.poly(top, col[0], sw=sw)


def windows(pen, cx, cy, w, d, h, rows=2, cols=4, face="left", z0=0.0, col=GLASS):
    a, b = w / 2, d / 2
    for r in range(rows):
        for c in range(cols):
            z1 = z0 + h * (0.2 + 0.7 * r / rows)
            z2 = z1 + h * 0.7 / rows * 0.6
            if face == "left":
                u1 = -a + w * (0.1 + 0.85 * c / cols)
                u2 = u1 + w * 0.85 / cols * 0.6
                pts = [P(cx, cy, u1, b, z1), P(cx, cy, u2, b, z1), P(cx, cy, u2, b, z2), P(cx, cy, u1, b, z2)]
            else:
                v1 = b - d * (0.1 + 0.85 * c / cols)
                v2 = v1 - d * 0.85 / cols * 0.6
                pts = [P(cx, cy, a, v1, z1), P(cx, cy, a, v2, z1), P(cx, cy, a, v2, z2), P(cx, cy, a, v1, z2)]
            pen.poly(pts, col, stroke="#5b6b7d", sw=0.5)


def gable(pen, cx, cy, w, d, z, rh, col):
    """Gable roof along u on top of a box at height z."""
    a, b = w / 2, d / 2
    pen.poly([P(cx, cy, -a, -b, z), P(cx, cy, a, -b, z), P(cx, cy, a, 0, z + rh), P(cx, cy, -a, 0, z + rh)], col[2])
    pen.poly([P(cx, cy, -a, b, z), P(cx, cy, a, b, z), P(cx, cy, a, 0, z + rh), P(cx, cy, -a, 0, z + rh)], col[0])
    pen.poly([P(cx, cy, a, b, z), P(cx, cy, a, -b, z), P(cx, cy, a, 0, z + rh)], col[1])


def sawtooth(pen, cx, cy, w, d, z, n, rh, col):
    a, b = w / 2, d / 2
    for i in range(n):
        v0 = -b + d * i / n
        v1 = v0 + d / n
        pen.poly([P(cx, cy, -a, v0, z), P(cx, cy, a, v0, z), P(cx, cy, a, v0, z + rh), P(cx, cy, -a, v0, z + rh)], GLASS,
                 stroke="#5b6b7d")
        pen.poly([P(cx, cy, -a, v0, z + rh), P(cx, cy, a, v0, z + rh), P(cx, cy, a, v1, z), P(cx, cy, -a, v1, z)], col[0])
        pen.poly([P(cx, cy, a, v0, z), P(cx, cy, a, v1, z), P(cx, cy, a, v0, z + rh)], col[2])


def cylinder(pen, x, y, r, h, col, stripes=0, z0=0.0, stripe_col="#d9534f"):
    """Vertical cylinder with its ground centre at screen (x, y)."""
    y0 = y - z0
    ry = r * 0.5
    gid = pen.uid()
    pen.raw(f'<defs><linearGradient id="{gid}" x1="0" x2="1"><stop offset="0" stop-color="{col[1]}"/>'
            f'<stop offset=".55" stop-color="{col[0]}"/><stop offset="1" stop-color="{col[2]}"/></linearGradient></defs>')
    pen.raw(f'<path d="M{x - r:.1f},{y0 - h:.1f} L{x - r:.1f},{y0:.1f} A{r:.1f},{ry:.1f} 0 0 0 {x + r:.1f},{y0:.1f} '
            f'L{x + r:.1f},{y0 - h:.1f} Z" fill="url(#{gid})" stroke="#3a3530" stroke-width=".8"/>')
    for i in range(stripes):
        yy = y0 - h + h * (0.12 + i * 0.28)
        pen.raw(f'<path d="M{x - r:.1f},{yy:.1f} A{r:.1f},{ry:.1f} 0 0 0 {x + r:.1f},{yy:.1f} L{x + r:.1f},{yy + h * .12:.1f} '
                f'A{r:.1f},{ry:.1f} 0 0 1 {x - r:.1f},{yy + h * .12:.1f} Z" fill="{stripe_col}" stroke="none"/>')
    pen.raw(f'<ellipse cx="{x:.1f}" cy="{y0 - h:.1f}" rx="{r:.1f}" ry="{ry:.1f}" fill="{col[0]}" stroke="#3a3530" stroke-width=".8"/>')


def plate(pen, cx, cy, a, glow=False):
    """Tile: a rhombus of half-width a with a little thickness."""
    t = 7
    top = [(cx - a, cy), (cx, cy - a * .5), (cx + a, cy), (cx, cy + a * .5)]
    pen.poly([(cx - a, cy), (cx, cy + a * .5), (cx, cy + a * .5 + t), (cx - a, cy + t)], PLATE_SIDE, sw=.6)
    pen.poly([(cx + a, cy), (cx, cy + a * .5), (cx, cy + a * .5 + t), (cx + a, cy + t)], "#4a403a", sw=.6)
    pen.poly(top, PLATE_TOP, sw=.6)
    if glow:
        pen.raw(f'<ellipse class="hotring" cx="{cx:.1f}" cy="{cy:.1f}" rx="{a + 6:.1f}" ry="{a * .5 + 4:.1f}" fill="none" '
                f'stroke="#d9480f" stroke-width="3"/>')


def truck(pen, x, y, col=("#f6f6f4", "#dcdcd6", "#b9b9b1")):
    box(pen, x - 6, y - 3, 22, 11, 10, col)
    box(pen, x + 10, y + 6, 8, 11, 8, ("#9fc3ee", "#5b8fd6", "#3f6fb5"))


def crates(pen, cx, cy, n, hot=False):
    """Pile of n crates (3 x 3 per layer), drawn back to front."""
    c = 10
    col = CRATE_HOT if hot else CRATE
    order = sorted([(i, j) for i in range(3) for j in range(3)], key=lambda t: t[0] + t[1])
    k = 0
    layer = 0
    while k < n:
        for (i, j) in order:
            if k >= n:
                break
            box(pen, *P(cx, cy, (i - 1) * c, (j - 1) * c), c * .92, c * .92, c * .92, col, z0=layer * c, sw=.5)
            k += 1
        layer += 1
    return math.ceil(n / 9) * c


# ---- buildings (original, generic) -------------------------------------------------------------------------
def b_supplier(pen, cx, cy):
    box(pen, cx - 14, cy - 4, 46, 34, 34, CREAM)
    windows(pen, cx - 14, cy - 4, 46, 34, 34, 2, 4, "left")
    gable(pen, cx - 14, cy - 4, 46, 34, 34, 10, ROOF_RED)
    for i, (dx, dy) in enumerate([(30, -14), (42, -6), (54, 2)]):
        cylinder(pen, cx + dx, cy + dy, 7, 38 - i * 4, STEEL)
    truck(pen, cx - 34, cy + 22)


def b_customer(pen, cx, cy):
    # substation: transformers on a pad and a lattice tower
    box(pen, cx - 6, cy + 4, 60, 40, 3, GREY)
    for dx, dy in [(-24, 6), (-6, 15), (12, 24)]:
        box(pen, cx + dx, cy + dy - 6, 14, 12, 16, ("#cfe0c8", "#8fb07f", "#6f8f60"), z0=3)
        cylinder(pen, cx + dx + 2, cy + dy - 30, 2, 8, STEEL)
    tx, ty = cx + 34, cy - 10
    top = ty - 78
    for sx in (-10, 10):
        pen.line(tx + sx, ty, tx + sx * .25, top, "#596470", 1.6)
    for k in range(6):
        y1 = ty - k * 13
        w1 = 10 - k * 1.25
        pen.line(tx - w1, y1, tx + w1 - 1.25, y1 - 13, "#7c8794", .9)
        pen.line(tx + w1, y1, tx - w1 + 1.25, y1 - 13, "#7c8794", .9)
    pen.line(tx - 18, top + 10, tx + 18, top + 10, "#596470", 1.6)
    pen.line(tx - 12, top + 22, tx + 12, top + 22, "#596470", 1.6)


def b_office(pen, cx, cy):
    box(pen, cx, cy, 60, 40, 44, STEEL)
    windows(pen, cx, cy, 60, 40, 44, 3, 5, "left")
    windows(pen, cx, cy, 60, 40, 44, 3, 3, "right")
    box(pen, cx + 4, cy - 2, 18, 14, 8, GREY, z0=44)
    cylinder(pen, *P(cx, cy, 20, 12), 1.5, 22, STEEL, z0=44)


def b_kitting(pen, cx, cy, top=TEAL):
    box(pen, cx, cy, 54, 40, 24, GREY)
    windows(pen, cx, cy, 54, 40, 24, 1, 3, "left")
    box(pen, cx, cy, 56, 42, 4, top, z0=24)
    # racks in front
    for i in range(3):
        box(pen, *P(cx, cy, -18 + i * 14, 30), 9, 6, 14, ("#f2b632", "#d99a16", "#b07d10"), sw=.5)


def b_fab(pen, cx, cy, top=CREAM):
    box(pen, cx - 4, cy, 58, 44, 26, CREAM)
    windows(pen, cx - 4, cy, 58, 44, 26, 1, 4, "left")
    sawtooth(pen, cx - 4, cy, 58, 44, 26, 3, 9, ("#d8d4c8", "#bdb8aa", "#a29d8f"))
    cylinder(pen, *P(cx, cy, 24, -14), 4, 46, ("#f4f4f2", "#dddcd6", "#bdbbb3"), stripes=3)
    cylinder(pen, *P(cx, cy, 34, -2), 3, 36, ("#f4f4f2", "#dddcd6", "#bdbbb3"), stripes=2)


def b_assembly(pen, cx, cy):
    box(pen, cx, cy, 66, 46, 30, BLUE)
    windows(pen, cx, cy, 66, 46, 30, 2, 5, "left", col="#dbe8f8")
    box(pen, cx, cy, 68, 48, 4, ("#e9ecef", "#c9cfd6", "#a9b1ba"), z0=30)
    # roller door
    pen.poly([P(cx, cy, 34, 6, 0), P(cx, cy, 34, -10, 0), P(cx, cy, 34, -10, 18), P(cx, cy, 34, 6, 18)], "#d6dbe1", sw=.6)


def b_test(pen, cx, cy):
    box(pen, cx - 6, cy, 48, 40, 26, GREY)
    windows(pen, cx - 6, cy, 48, 40, 26, 2, 3, "left")
    box(pen, cx - 6, cy, 50, 42, 4, NAVY, z0=26)
    # HV test tower and loading dock with a truck
    tx, ty = P(cx, cy, 20, -12)
    for k in range(4):
        cylinder(pen, tx, ty - 26 - k * 7, 6 - k, 5, ("#f7f7f5", "#d9d7d0", "#b6b3aa"), z0=0)
    cylinder(pen, tx, ty, 2, 26, STEEL)
    truck(pen, *P(cx, cy, 34, 18))


STYLE = [("kit", b_kitting), ("pick", b_kitting), ("fab", b_fab), ("weld", b_fab), ("machin", b_fab), ("cut", b_fab),
         ("assem", b_assembly), ("wir", b_assembly), ("test", b_test), ("ship", b_test), ("pack", b_test)]
FALLBACK = [b_kitting, b_fab, b_assembly, b_test]


def _building(name: str, i: int):
    low = name.lower()
    for key, fn in STYLE:
        if key in low:
            return fn
    return FALLBACK[i % len(FALLBACK)]


def _money(v: float, cur: str) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "–"
    return f"{cur}{v / 1e6:,.2f}M" if abs(v) >= 1e6 else f"{cur}{v / 1e3:,.0f}k"


def iso_svg(v, state: str = "current", cur: str = "$", note: str = "", geo: dict | None = None) -> str:
    st = v.steps if state == "current" else v.future
    k = v.kpis if state == "current" else v.future_kpis
    days_col = "days" if state == "current" else "target_days"
    co_col = "changeover_hours" if state == "current" else "target_changeover_hours"
    big = k.get("biggest_wait")
    pen = Pen("c" if state == "current" else "f")
    pen.raw(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="Value stream, '
            f'isometric" style="font-family: Source Sans Pro, Helvetica, Arial, sans-serif; background:#efeee9">')
    pen.raw('<style>@keyframes hr{0%,100%{opacity:.25}50%{opacity:1}} .hotring{animation:hr 1.4s ease-in-out infinite}'
            '@keyframes flow{to{stroke-dashoffset:-20}} line.info{animation:flow 1.2s linear infinite}</style>')

    # ---- top row: supplier, production control, customer
    sx, sy, cx_, cy_, px, py = 110, 118, W - 110, 118, W / 2, 100
    n = len(st)
    left, right = 80, W - 80
    step = (right - left) / n
    xs = [left + step * (i + .5) for i in range(n)]
    yc = 330
    a = min(54, step / 2 - 6)

    # information flow (behind the tiles)
    pen.line(cx_ - 60, cy_ - 30, px + 70, py - 20, INFO, 1.4, True, "info")
    pen.text((cx_ - 60 + px + 70) / 2, py - 34, "Customer orders", 11, fill=INFO)
    pen.line(px - 70, py - 20, sx + 60, sy - 30, INFO, 1.4, True, "info")
    pen.text((px - 70 + sx + 60) / 2, py - 34, "Supplier POs", 11, fill=INFO)
    first_proc = next((i for i, r in enumerate(st.itertuples()) if r.kind == "Process"), 0)
    pen.line(px - 60, py + 8, xs[first_proc], yc - 70, INFO, 1.4, True, "info")
    pen.text((px - 60 + xs[first_proc]) / 2 + 12, (py + 8 + yc - 70) / 2 + 4, "Build schedule and kit list", 11, anchor="start",
             fill=INFO)

    plate(pen, sx, sy, 78)
    b_supplier(pen, sx, sy)
    pen.text(sx + 86, sy + 14, "Suppliers", 13, True, anchor="start")
    pen.text(sx + 86, sy + 29, note, 11, anchor="start", fill=MUTED)
    plate(pen, px, py, 70)
    b_office(pen, px, py)
    pen.text(px, py + 56, "Production control", 13, True)
    pen.text(px, py + 71, "SAP / MRP, weekly run", 11, fill=MUTED)
    plate(pen, cx_, cy_, 78)
    b_customer(pen, cx_, cy_)
    pen.text(cx_ - 86, cy_ + 14, "Customer", 13, True, anchor="end")
    pen.text(cx_ - 86, cy_ + 29, f"{v.demand_units:.0f} {v.family.lower()} units a year", 11, anchor="end", fill=MUTED)
    pen.text(cx_ - 86, cy_ + 44, f"takt {v.takt_hours:,.0f} h per unit", 11, True, anchor="end")

    # ---- conveyor and material paths
    x_in, x_out = xs[0] - step / 2, xs[-1] + step / 2
    in_path = [[sx - 39, sy + 20], [x_in - 22, yc - 34], [x_in - 10, yc], [xs[0], yc]]
    out_path = [[xs[-1], yc], [x_out + 10, yc], [x_out + 22, yc - 34], [cx_ + 39, cy_ + 20]]
    for pth in (in_path, out_path):
        d = " ".join(("M" if j == 0 else "L") + f"{x:.1f},{y:.1f}" for j, (x, y) in enumerate(pth))
        pen.raw(f'<path d="{d}" fill="none" stroke="#5b5a56" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/>'
                f'<path d="{d}" fill="none" stroke="#efeee9" stroke-width="1.2" stroke-dasharray="6 6"/>')
    pen.raw(f'<rect x="{x_in - 14:.1f}" y="{yc - 5:.1f}" width="{x_out - x_in + 28:.1f}" height="10" rx="5" fill="#5b5a56"/>')
    pen.raw(f'<line x1="{xs[0] - step / 2 + 4:.1f}" y1="{yc:.1f}" x2="{xs[-1] + step / 2 - 4:.1f}" y2="{yc:.1f}" stroke="#bdbab1" '
            f'stroke-width="1.5" stroke-dasharray="8 8" class="info"/>')
    # delivery trucks shuttling on the two roads
    for pth, dur in ((in_path, 7), (out_path, 9)):
        d = " ".join(("M" if j == 0 else "L") + f"{x:.1f},{y:.1f}" for j, (x, y) in enumerate(pth))
        t = Pen(pen.uid())
        truck(t, 0, 0)
        pen.raw(f'<g>{"".join(t.out)}<animateMotion dur="{dur}s" repeatCount="indefinite" path="{d}"/></g>')

    # ---- flow tiles
    waits, procs, pts = [], [], []
    for i, r in enumerate(st.itertuples()):
        x = xs[i]
        hot = big is not None and r.name == big and r.kind == "Stock"
        plate(pen, x, yc, a, glow=hot)
        pts.append([x, yc])
        if r.kind == "Process":
            over = bool(r.over_takt)
            _building(r.name, i)(pen, x, yc - 4)
            pen.text(x, yc + a * .5 + 24, r.name, 12, True, fill=WARN_LINE if over else INK)
            rows = [("C/T", f"{r.cycle_time_hours:,.0f} h"), ("C/O", f"{getattr(r, co_col):,.1f} h".replace(".0 h", " h")),
                    ("Uptime", f"{r.uptime_pct:,.0f}%"), ("Operators", f"{r.operators:,.0f}"),
                    ("vs takt", f"{r.load_pct:,.0f}%" if not np.isnan(r.load_pct) else "–")]
            cw, top = min(112, step - 12), yc + a * .5 + 32
            pen.raw(f'<rect x="{x - cw / 2:.1f}" y="{top:.1f}" width="{cw:.1f}" height="{16 * len(rows) + 8}" rx="4" '
                    f'fill="{WARN_FILL if over else "#ffffff"}" stroke="{WARN_LINE if over else "#c9c7bf"}"/>')
            for j, (lab, val) in enumerate(rows):
                pen.text(x - cw / 2 + 6, top + 17 + j * 16, lab, 10, anchor="start", fill=MUTED)
                pen.text(x + cw / 2 - 6, top + 17 + j * 16, val, 10, anchor="end")
            waits.append([x, yc])
            procs.append([[x - a * .6, yc + 4], [x + a * .6, yc + 4]])
        else:
            d = getattr(r, days_col)
            h = crates(pen, x - 4, yc - 6, int(round(d or 0)), hot)
            pen.text(x, yc + a * .5 + 24, r.name, 12, True, fill=WARN_LINE if hot else INK)
            pen.text(x, yc + a * .5 + 40, f"{d:,.1f} days", 11)
            pen.text(x, yc + a * .5 + 54, _money(d * v.daily_cogs, cur), 10, fill=MUTED)
            if hot:
                pen.text(x, yc + a * .5 + 70, "Start here" if state == "current" else "Still the biggest wait", 11, True,
                         fill=WARN_LINE)
            waits.append([x + 26, yc + 12])
            procs.append([[x, yc], [x, yc]])
            _ = h

    # ---- timeline ladder and totals
    hi, lo = 560, 600
    prev = None
    for i, r in enumerate(st.itertuples()):
        x0, x1 = xs[i] - step / 2, xs[i] + step / 2
        if r.kind == "Process":
            y = lo
            pen.text((x0 + x1) / 2, lo + 16, f"{r.process_days:,.1f} d", 11)
        else:
            y = hi
            d = getattr(r, days_col)
            hot = big is not None and r.name == big
            pen.text((x0 + x1) / 2, hi - 7, f"{d:,.1f} d", 11, hot, fill=WARN_LINE if hot else INK)
        pen.line(x0, y, x1, y, INK, 2)
        if prev is not None and prev != y:
            pen.line(x0, prev, x0, y, INK, 2)
        prev = y
    pen.text(xs[0] - step / 2 + 2, hi - 22, "Waiting", 11, anchor="start", fill=MUTED)
    pen.text(xs[0] - step / 2 + 2, lo - 8, "Process", 11, anchor="start", fill=MUTED)
    bx, by = W - 250, 658
    pen.raw(f'<rect x="{xs[0] - step / 2:.1f}" y="{by - 14}" width="{xs[-1] - xs[0] + step:.1f}" height="22" rx="4" fill="#ffffff" '
            f'stroke="#c9c7bf"/>')
    pen.text(xs[0] - step / 2 + 10, by + 2, f"Lead time {k['lead_time_days']:,.0f} days  ·  waiting {k['wait_days']:,.1f} d  ·  "
             f"process {k['process_days']:,.1f} d  ·  value-added {k['va_pct']:,.0f}%", 12, True, anchor="start")
    _ = bx
    pen.raw("</svg>")
    if geo is not None:
        geo.update(xs=xs, my=yc, step=step, hi=hi, lo=lo, kinds=list(st["kind"]), pt=pts, wait=waits, proc=procs,
                   inPath=in_path, outPath=out_path, stackDy=11, stackDx=0, hop=3, cube=6)
    return "".join(pen.out)


def vsm_iso_html(r, v=None, start: str = "current") -> str:
    """Animated isometric plant view as a full HTML page."""
    v = v or r.vsm
    cur, note = r.settings.currency, supplier_note(r.data)
    geo: dict = {}
    svgs = {"current": iso_svg(v, "current", cur, note, geo), "future": iso_svg(v, "future", cur, note)}
    return _page(v, cur, start, geo, svgs, W, H)
