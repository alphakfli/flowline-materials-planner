"""Draw the value stream map once, as simple shapes, then render it as SVG (app) or a ReportLab drawing (PDF)."""

from __future__ import annotations

import math
from html import escape

import numpy as np

W, H = 1200, 545
INK, MUTED, LINE, PAPER = "#0b0b0b", "#52514e", "#c9c7bf", "#ffffff"
INFO = "#2a78d6"          # information flow
WARN_FILL, WARN_LINE = "#fbebc8", "#b97f00"
BOX_FILL = "#f4f3ef"
TOP, TOP_ROOF, SIDE = "#1f3a5f", "#d6d3c9", "#cfccc2"   # 3D look: lid, roof, shaded side


def _money(v: float, cur: str) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "–"
    return f"{cur}{v / 1e6:,.2f}M" if abs(v) >= 1e6 else f"{cur}{v / 1e3:,.0f}k"


def shapes(v, state: str = "current", cur: str = "$", supplier_note: str = "", depth: bool = False,
           geo: dict | None = None) -> list[dict]:
    """The map as a list of shapes. state 'current' or 'future' (targets applied).

    depth=True draws the boxes, triangles and buildings as solid 3D-like objects (for the animated view); geo, if
    given, is filled with the positions the animation needs."""
    st = v.steps if state == "current" else v.future
    k = v.kpis if state == "current" else v.future_kpis
    days_col = "days" if state == "current" else "target_days"
    co_col = "changeover_hours" if state == "current" else "target_changeover_hours"
    big = v.kpis.get("biggest_wait") if state == "current" else None
    out: list[dict] = []

    DX, DY = 11, -9                     # extrusion for the 3D look

    def rect(x, y, w, h, fill=PAPER, stroke=INK, dash=False, width=1.2, solid=False, top=TOP, shadow=False):
        if depth and solid:
            out.append(dict(t="poly", pts=[(x + w, y), (x + w + DX, y + DY), (x + w + DX, y + h + DY), (x + w, y + h)],
                            fill=SIDE, stroke=stroke, width=width, shadow=True))
            out.append(dict(t="poly", pts=[(x, y), (x + DX, y + DY), (x + w + DX, y + DY), (x + w, y)],
                            fill=top, stroke=stroke, width=width))
        out.append(dict(t="rect", x=x, y=y, w=w, h=h, fill=fill, stroke=stroke, dash=dash, width=width,
                        shadow=depth and (shadow or solid)))

    def text(x, y, s, size=12, bold=False, anchor="middle", fill=INK):
        out.append(dict(t="text", x=x, y=y, s=str(s), size=size, bold=bold, anchor=anchor, fill=fill))

    def line(x1, y1, x2, y2, stroke=INK, width=1.4, dash=False, arrow=False):
        out.append(dict(t="line", x1=x1, y1=y1, x2=x2, y2=y2, stroke=stroke, width=width, dash=dash, arrow=arrow))

    def poly(pts, fill=PAPER, stroke=INK, width=1.2):
        out.append(dict(t="poly", pts=pts, fill=fill, stroke=stroke, width=width))

    def factory(x, y, w, h, label, sub):
        tooth = w / 3
        pts = [(x, y + h), (x, y + 18)]
        for i in range(3):
            pts += [(x + i * tooth, y + 18), (x + (i + 1) * tooth, y)] if i < 2 else [(x + i * tooth, y + 18), (x + w, y)]
        pts += [(x + w, y + h)]
        if depth:
            poly([(x + w, y + h), (x + w + DX, y + h + DY), (x + w + DX, y + DY), (x + w, y)], fill=SIDE)
            for i in range(3):          # roof faces
                a, b = (x + i * tooth, y + 18), (x + (i + 1) * tooth, y if i < 2 else y)
                poly([a, b, (b[0] + DX, b[1] + DY), (a[0] + DX, a[1] + DY)], fill=TOP_ROOF)
        poly(pts, fill=BOX_FILL)
        text(x + w / 2, y + h - 22, label, 13, True)
        text(x + w / 2, y + h - 7, sub, 11, fill=MUTED)

    # ---- Information flow (top)
    sx, sy, sw, sh = 20, 40, 150, 80
    cx, cy = W - 170, 40
    px, py, pw, ph = W / 2 - 130, 30, 260, 62
    factory(sx, sy, sw, sh, "Suppliers", supplier_note)
    factory(cx, cy, sw, sh, "Customer", f"{v.demand_units:.0f} {v.family.lower()} units a year")
    rect(px, py, pw, ph, fill=BOX_FILL, solid=True, top=TOP_ROOF)
    text(px + pw / 2, py + 24, "Production control", 13, True)
    text(px + pw / 2, py + 44, "SAP / MRP, weekly run", 11, fill=MUTED)
    line(cx, cy + 30, px + pw, py + 31, INFO, 1.4, dash=True, arrow=True)
    text((cx + px + pw) / 2, py + 22, "Customer orders", 11, fill=INFO)
    line(px, py + 31, sx + sw, sy + 30, INFO, 1.4, dash=True, arrow=True)
    text((px + sx + sw) / 2, py + 22, "Supplier POs", 11, fill=INFO)
    rect(cx + 30, cy + sh + 10, sw - 30, 40, fill=PAPER, stroke=INK)
    text(cx + 15 + sw / 2, cy + sh + 27, f"Takt {v.takt_hours:,.0f} h", 12, True)
    text(cx + 15 + sw / 2, cy + sh + 42, "per unit", 10, fill=MUTED)

    # ---- Material flow
    n = len(st)
    left, right = 200, W - 190
    step = (right - left) / max(n, 1)
    my = 255                      # middle of the flow row
    xs = [left + step * (i + 0.5) for i in range(n)]
    bw, bh = min(118, step - 18), 58
    first_proc = None
    for i, r in enumerate(st.itertuples()):
        x = xs[i]
        if r.kind == "Process":
            first_proc = first_proc if first_proc is not None else x
            rect(x - bw / 2, my - bh / 2, bw, bh, fill=BOX_FILL, solid=True, top=WARN_LINE if r.over_takt else TOP)
            text(x, my + 5, r.name, 12, True)
            over = bool(r.over_takt)
            rows = [("C/T", f"{r.cycle_time_hours:,.0f} h"), ("C/O", f"{getattr(r, co_col):,.1f} h".replace(".0 h", " h")),
                    ("Uptime", f"{r.uptime_pct:,.0f}%"), ("Operators", f"{r.operators:,.0f}"),
                    ("vs takt", f"{r.load_pct:,.0f}%" if not np.isnan(r.load_pct) else "–")]
            dy = my + bh / 2 + 8
            rect(x - bw / 2, dy, bw, 16 * len(rows) + 8, fill=WARN_FILL if over else PAPER, stroke=WARN_LINE if over else INK,
                 shadow=True)
            for j, (a, b) in enumerate(rows):
                text(x - bw / 2 + 6, dy + 17 + j * 16, a, 10, anchor="start", fill=MUTED)
                text(x + bw / 2 - 6, dy + 17 + j * 16, b, 10, anchor="end")
        else:
            d = getattr(r, days_col)
            hot = big is not None and r.name == big
            tw, th = 52, 46
            if depth:
                poly([(x + tw / 2, my + th / 2), (x + tw / 2 + DX, my + th / 2 + DY), (x + DX, my - th / 2 + DY),
                      (x, my - th / 2)], fill=WARN_LINE if hot else SIDE)
            poly([(x - tw / 2, my + th / 2), (x + tw / 2, my + th / 2), (x, my - th / 2)],
                 fill=WARN_FILL if hot else PAPER, stroke=WARN_LINE if hot else INK, width=2 if hot else 1.2)
            if hot and depth:
                out[-1]["cls"] = "hot"          # the triangle pulses in the animated view
            text(x, my + th / 2 - 8, "I", 13, True)
            text(x, my + th / 2 + 16, r.name, 11, True)
            val = d * v.daily_cogs if not np.isnan(d) else np.nan
            text(x, my + th / 2 + 31, f"{d:,.1f} days", 11)
            text(x, my + th / 2 + 45, _money(val, cur), 10, fill=MUTED)
            if hot and depth:
                text(x, my + th / 2 + 60, "Start here", 11, True, fill=WARN_LINE)
            elif hot:
                text(x, my - th / 2 - 10, "Start here", 11, True, fill=WARN_LINE)
    # arrows between elements (push)
    edge = lambda i, side: xs[i] + side * ((bw / 2 + (DX if depth and side > 0 else 0)) if st.iloc[i]["kind"] == "Process"  # noqa: E731
                                           else 28 + (DX * .6 if depth and side > 0 else 0))
    line(sx + sw / 2, sy + sh, xs[0] - 28 if st.iloc[0]["kind"] != "Process" else xs[0] - bw / 2, my, INK, 2, arrow=True)
    for i in range(n - 1):
        line(edge(i, 1) + 2, my, edge(i + 1, -1) - 2, my, INK, 2, arrow=True)
    line(edge(n - 1, 1) + 2, my, cx + 8, cy + sh + 2, INK, 2, arrow=True)
    if first_proc is not None:
        line(px + pw / 2, py + ph, first_proc, my - bh / 2 - 2, INFO, 1.4, dash=True, arrow=True)
        text(px + pw / 2 + 8, (py + ph + my - bh / 2) / 2 + 20, "Build schedule and kit list", 11, anchor="start", fill=INFO)

    # ---- Timeline ladder
    hi, lo = 448, 488
    prev = None
    for i, r in enumerate(st.itertuples()):
        x0, x1 = xs[i] - step / 2, xs[i] + step / 2
        if r.kind == "Process":
            y, label = lo, f"{r.process_days:,.1f} d"
            text((x0 + x1) / 2, lo + 16, label, 11)
        else:
            y = hi
            d = getattr(r, days_col)
            hot = big is not None and r.name == big
            text((x0 + x1) / 2, hi - 7, f"{d:,.1f} d", 11, hot, fill=WARN_LINE if hot else INK)
        line(x0, y, x1, y, INK, 2)
        if prev is not None and prev != y:
            line(x0, prev, x0, y, INK, 2)
        prev = y
    text(left - 10, hi + 4, "Waiting", 11, anchor="end", fill=MUTED)
    text(left - 10, lo + 4, "Process", 11, anchor="end", fill=MUTED)
    bx = W - 175
    rect(bx, hi - 30, 160, 92, fill=BOX_FILL)
    text(bx + 10, hi - 10, "Lead time", 11, anchor="start", fill=MUTED)
    text(bx + 150, hi - 10, f"{k['lead_time_days']:,.0f} d", 12, True, anchor="end")
    text(bx + 10, hi + 10, "Waiting", 11, anchor="start", fill=MUTED)
    text(bx + 150, hi + 10, f"{k['wait_days']:,.1f} d", 11, anchor="end")
    text(bx + 10, hi + 30, "Process", 11, anchor="start", fill=MUTED)
    text(bx + 150, hi + 30, f"{k['process_days']:,.1f} d", 11, anchor="end")
    text(bx + 10, hi + 50, "Value-added", 11, anchor="start", fill=MUTED)
    text(bx + 150, hi + 50, f"{k['va_pct']:,.0f}%", 12, True, anchor="end")
    if geo is not None:
        geo.update(xs=xs, my=my, bh=bh, bw=bw, step=step, hi=hi, lo=lo, kinds=list(st["kind"]),
                   sup=(sx + sw / 2, sy + sh), cus=(cx + 8, cy + sh + 2), dx=DX, dy=DY)
    return out


def _head(x1, y1, x2, y2, size=8):
    a = math.atan2(y2 - y1, x2 - x1)
    return [(x2, y2), (x2 - size * math.cos(a - 0.4), y2 - size * math.sin(a - 0.4)),
            (x2 - size * math.cos(a + 0.4), y2 - size * math.sin(a + 0.4))]


def to_svg(items: list[dict], width: int = W, height: int = H) -> str:
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" '
           f'style="font-family: Source Sans Pro, Helvetica, Arial, sans-serif; background:#fff" role="img" '
           f'aria-label="Value stream map"><defs><filter id="sh" x="-20%" y="-20%" width="140%" height="160%">'
           '<feDropShadow dx="3" dy="5" stdDeviation="3.5" flood-color="#000" flood-opacity=".18"/></filter></defs>']
    for s in items:
        if s["t"] == "rect":
            out.append(f'<rect x="{s["x"]:.1f}" y="{s["y"]:.1f}" width="{s["w"]:.1f}" height="{s["h"]:.1f}" rx="3" '
                       f'fill="{s["fill"]}" stroke="{s["stroke"]}" stroke-width="{s["width"]}"'
                       + (' stroke-dasharray="5 4"' if s["dash"] else "") + (' filter="url(#sh)"' if s.get("shadow") else "") + "/>")
        elif s["t"] == "poly":
            pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in s["pts"])
            out.append(f'<polygon points="{pts}" fill="{s["fill"]}" stroke="{s["stroke"]}" stroke-width="{s["width"]}" '
                       'stroke-linejoin="round"' + (' filter="url(#sh)"' if s.get("shadow") else "")
                       + (f' class="{s["cls"]}"' if s.get("cls") else "") + "/>")
        elif s["t"] == "line":
            out.append(f'<line x1="{s["x1"]:.1f}" y1="{s["y1"]:.1f}" x2="{s["x2"]:.1f}" y2="{s["y2"]:.1f}" '
                       f'stroke="{s["stroke"]}" stroke-width="{s["width"]}"'
                       + (' stroke-dasharray="6 4" class="info"' if s["dash"] else "") + "/>")
            if s["arrow"]:
                pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in _head(s["x1"], s["y1"], s["x2"], s["y2"]))
                out.append(f'<polygon points="{pts}" fill="{s["stroke"]}"/>')
        elif s["t"] == "text":
            anchor = {"start": "start", "middle": "middle", "end": "end"}[s["anchor"]]
            out.append(f'<text x="{s["x"]:.1f}" y="{s["y"]:.1f}" font-size="{s["size"]}" text-anchor="{anchor}" '
                       f'fill="{s["fill"]}"' + (' font-weight="600"' if s["bold"] else "") + f">{escape(s['s'])}</text>")
    out.append("</svg>")
    return "".join(out)


def to_drawing(items: list[dict], width_pt: float):
    """ReportLab Drawing scaled to width_pt."""
    from reportlab.graphics.shapes import Drawing, Group, Line, Polygon, Rect, String
    from reportlab.lib import colors

    c = colors.HexColor
    g = Group()
    for s in items:
        if s["t"] == "rect":
            g.add(Rect(s["x"], H - s["y"] - s["h"], s["w"], s["h"], fillColor=c(s["fill"]), strokeColor=c(s["stroke"]),
                       strokeWidth=s["width"], strokeDashArray=[5, 4] if s["dash"] else None, rx=3, ry=3))
        elif s["t"] == "poly":
            pts = [v for x, y in s["pts"] for v in (x, H - y)]
            g.add(Polygon(pts, fillColor=c(s["fill"]), strokeColor=c(s["stroke"]), strokeWidth=s["width"]))
        elif s["t"] == "line":
            g.add(Line(s["x1"], H - s["y1"], s["x2"], H - s["y2"], strokeColor=c(s["stroke"]), strokeWidth=s["width"],
                       strokeDashArray=[6, 4] if s["dash"] else None))
            if s["arrow"]:
                pts = [v for x, y in _head(s["x1"], s["y1"], s["x2"], s["y2"]) for v in (x, H - y)]
                g.add(Polygon(pts, fillColor=c(s["stroke"]), strokeColor=c(s["stroke"]), strokeWidth=0.5))
        elif s["t"] == "text":
            g.add(String(s["x"], H - s["y"], s["s"], fontSize=s["size"], fillColor=c(s["fill"]),
                         fontName="Helvetica-Bold" if s["bold"] else "Helvetica", textAnchor=s["anchor"]))
    k = width_pt / W
    g.scale(k, k)
    d = Drawing(width_pt, H * k)
    d.add(g)
    return d


def supplier_note(data) -> str:
    sp = data.suppliers
    if sp is None or sp.empty:
        return ""
    t = sp["supplier_type"].astype(str).str.upper()
    n_cm = int((t == "CM").sum())
    n = len(sp) - n_cm
    return f"{n} suppliers" + (f", {n_cm} CMs" if n_cm else "")


def vsm_svg(r, state: str = "current") -> str:
    """SVG of the map for a Result (engine.run)."""
    return to_svg(shapes(r.vsm, state, r.settings.currency, supplier_note(r.data)))
