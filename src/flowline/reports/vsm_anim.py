"""Animation for the value stream map, in plain SVG and JavaScript: lineups moving through a drawing of the stream
(used by the isometric plant view in vsm_iso.py). No WebGL and no libraries, so it works in any browser, on remote
desktops and offline.

The clock runs in days. A new lineup starts every 365 / units-a-year days; it waits at each stock point for that
point's days (stacked by the pile) and moves through each process step in its process days, so one
trip takes the map's lead time. A marker on the timeline ladder follows one lineup.
"""

from __future__ import annotations

import json

import numpy as np


def _n(x, nd=2):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if np.isnan(x) else round(x, nd)


def _durations(v, state: str) -> dict:
    st = v.steps if state == "current" else v.future
    k = v.kpis if state == "current" else v.future_kpis
    days_col = "days" if state == "current" else "target_days"
    d = [_n(getattr(r, days_col)) if r.kind == "Stock" else _n(r.process_days) for r in st.itertuples()]
    return dict(durations=d, lead=_n(k["lead_time_days"], 1), wait=_n(k["wait_days"], 1), process=_n(k["process_days"], 1),
                va=_n(k["va_pct"], 0), freed=_n(k.get("freed_value", 0), 0))


def _page(v, cur, start, geo, svgs, w, h) -> str:
    data = dict(family=v.family, cur=cur, demand=_n(v.demand_units, 0), start=start, geo=geo,
                states={s: _durations(v, s) for s in ("current", "future")})
    return (PAGE.replace("__W__", str(w)).replace("__H__", str(h))
            .replace("__SVG_CURRENT__", svgs["current"]).replace("__SVG_FUTURE__", svgs["future"])
            .replace("__DATA__", json.dumps(data)))


PAGE = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Value stream, animated</title>
<style>
  html, body { margin: 0; background: transparent; font-family: "Source Sans Pro", "Segoe UI", Helvetica, Arial, sans-serif; color: #0b0b0b; }
  .bar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; padding: 6px 2px 8px; font-size: 13px; }
  button { font: inherit; font-size: 12px; border: 1px solid #c9c7bf; background: #fff; border-radius: 6px; padding: 4px 10px; cursor: pointer; }
  button.on { background: #1f3a5f; color: #fff; border-color: #1f3a5f; }
  .muted { color: #52514e; font-size: 12px; }
  #status { margin-left: auto; text-align: right; }
  .stage { position: relative; border: 1px solid #e1e0d9; border-radius: 8px; background: #fff; overflow: hidden; margin: 0 auto; }
  .stage > svg { display: block; }
  .layer { position: absolute; inset: 0; }
  .hidden { display: none; }
  @keyframes flow { to { stroke-dashoffset: -20; } }
  line.info { animation: flow 1.2s linear infinite; }
  @keyframes pulse { 0%, 100% { stroke-width: 2; } 50% { stroke-width: 5; } }
  polygon.hot { animation: pulse 1.4s ease-in-out infinite; }
  .legend { font-size: 12px; color: #52514e; padding-top: 6px; }
  .sw { display: inline-block; width: 11px; height: 11px; border-radius: 2px; vertical-align: -1px; margin: 0 4px 0 12px; }
  .sw:first-child { margin-left: 0; }
</style></head>
<body>
<div class="bar" id="bar">
  <button id="bCur">Current state</button><button id="bFut">Future state</button>
  <button id="bPlay">Pause</button><span class="muted">Speed</span>
  <input id="speed" type="range" min="2" max="60" value="15"><span class="muted" id="speedTxt"></span>
  <span id="status"></span>
</div>
<div class="stage" id="stage">
  <svg viewBox="0 0 __W__ __H__" width="100%" aria-hidden="true"></svg>
  <div class="layer" id="lCur">__SVG_CURRENT__</div>
  <div class="layer hidden" id="lFut">__SVG_FUTURE__</div>
  <svg class="layer" id="anim" viewBox="0 0 __W__ __H__" width="100%"></svg>
</div>
<div class="legend" id="legend"><span class="sw" style="background:#2a78d6"></span>lineup moving<span class="sw" style="background:#eda100"></span>waiting in stock
  <span class="sw" style="background:#1baf7a"></span>in process<span class="sw" style="background:#d9480f;border-radius:50%"></span>one lineup followed on the timeline</div>
<script>
const D = __DATA__;
// Fit the whole map in the window (or the app's frame): never wider than the height allows
function fit() {
  const st = document.getElementById("stage");
  const chrome = document.getElementById("bar").offsetHeight + document.getElementById("legend").offsetHeight + 14;
  const avail = Math.max(window.innerHeight - chrome, 200);
  st.style.maxWidth = Math.floor(avail * __W__ / __H__) + "px";
}
window.addEventListener("resize", fit); window.addEventListener("load", fit); fit();
const G = D.geo, NS = "http://www.w3.org/2000/svg";
const A = document.getElementById("anim");
const COL = { move: ["#2a78d6", "#5b97e0", "#1d5aa3"], wait: ["#eda100", "#f5c04d", "#b97f00"], proc: ["#1baf7a", "#4dc99b", "#12805a"] };
let stateName = D.start in D.states ? D.start : "current";
let S = D.states[stateName];
const el = (tag, attrs, parent) => { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); (parent || A).appendChild(e); return e; };

function applyState(name) {
  stateName = name; S = D.states[name];
  document.getElementById("lCur").classList.toggle("hidden", name !== "current");
  document.getElementById("lFut").classList.toggle("hidden", name !== "future");
  document.getElementById("bCur").classList.toggle("on", name === "current");
  document.getElementById("bFut").classList.toggle("on", name === "future");
}
document.getElementById("bCur").onclick = () => applyState("current");
document.getElementById("bFut").onclick = () => applyState("future");
applyState(stateName);

let playing = true, speed = 15, simDay = 0;
const sp = document.getElementById("speed"), spT = document.getElementById("speedTxt");
const setSpeed = () => { speed = +sp.value; spT.textContent = speed + " days/s"; }; sp.oninput = setSpeed; setSpeed();
document.getElementById("bPlay").onclick = e => { playing = !playing; e.target.textContent = playing ? "Pause" : "Play"; };

// a small isometric cube
function cube() {
  const g = el("g", {});
  const s = G.cube || 7, dx = 5, dy = -4;
  g.top = el("polygon", { points: `${-s},${-s} ${-s + dx},${-s + dy} ${s + dx},${-s + dy} ${s},${-s}`, stroke: "#0b0b0b", "stroke-width": .6 }, g);
  g.side = el("polygon", { points: `${s},${-s} ${s + dx},${-s + dy} ${s + dx},${s + dy} ${s},${s}`, stroke: "#0b0b0b", "stroke-width": .6 }, g);
  g.front = el("rect", { x: -s, y: -s, width: 2 * s, height: 2 * s, stroke: "#0b0b0b", "stroke-width": .6 }, g);
  g.paint = c => { g.front.setAttribute("fill", c[0]); g.top.setAttribute("fill", c[1]); g.side.setAttribute("fill", c[2]); };
  return g;
}
const n = G.xs.length, MOVE = 1.2;
const spawnEvery = D.demand ? 365 / D.demand : 30;
// G.pt[i]: flow point of step i; G.wait[i]: base of the waiting stack; G.proc[i]: [from, to] while processed;
// G.inPath / G.outPath: polylines from the supplier to step 0 and from the last step to the customer.
function plan() {
  const legs = [{ kind: "move", path: G.inPath, dur: MOVE * 2 }];
  for (let i = 0; i < n; i++) {
    legs.push({ kind: G.kinds[i] === "Stock" ? "wait" : "proc", node: i, dur: Math.max(S.durations[i] || 0, 0) });
    const path = i < n - 1 ? [G.pt[i], G.pt[i + 1]] : G.outPath;
    legs.push({ kind: "move", path, dur: i < n - 1 ? MOVE : MOVE * 2 });
  }
  return legs;
}
function along(path, u) {
  let tot = 0; const seg = [];
  for (let i = 0; i < path.length - 1; i++) { const l = Math.hypot(path[i + 1][0] - path[i][0], path[i + 1][1] - path[i][1]); seg.push(l); tot += l; }
  let d = u * tot;
  for (let i = 0; i < seg.length; i++) {
    if (d <= seg[i] || i === seg.length - 1) { const f = seg[i] ? Math.min(d / seg[i], 1) : 1;
      return [path[i][0] + (path[i + 1][0] - path[i][0]) * f, path[i][1] + (path[i + 1][1] - path[i][1]) * f]; }
    d -= seg[i];
  }
  return path[path.length - 1];
}
const tokens = []; let seq = 0, done = [], followed = null;
let nextSpawn = -Math.ceil(S.lead + 10);          // start with a full stream
const marker = el("circle", { r: 6, fill: "#d9480f", stroke: "#fff", "stroke-width": 2, opacity: 0 });
const markerTxt = el("text", { "font-size": 11, "text-anchor": "middle", fill: "#d9480f", "font-weight": 600 });
function spawn(t) {
  const g = cube();
  tokens.push({ g, legs: plan(), leg: 0, legStart: t, born: t, wait: 0, proc: 0, id: ++seq });
}
function update(t) {
  while (t >= nextSpawn) { spawn(nextSpawn); nextSpawn += spawnEvery; }
  if (!followed || !tokens.includes(followed)) followed = tokens.find(k => k.born >= t - 2) || null;
  const stacks = {};
  for (let j = tokens.length - 1; j >= 0; j--) {
    const k = tokens[j];
    let L = k.legs[k.leg];
    while (L && t - k.legStart >= L.dur) {
      if (L.kind === "wait") k.wait += L.dur; if (L.kind === "proc") k.proc += L.dur;
      k.legStart += L.dur; k.leg++; L = k.legs[k.leg];
    }
    if (!L) { done.push({ lead: k.wait + k.proc, wait: k.wait, proc: k.proc }); if (done.length > 5) done.shift(); k.g.remove(); tokens.splice(j, 1); continue; }
    const u = L.dur ? Math.min((t - k.legStart) / L.dur, 1) : 1;
    let x, y;
    if (L.kind === "move") {
      [x, y] = along(L.path, u); y -= Math.sin(Math.PI * u) * (G.hop || 6);
    } else if (L.kind === "wait") {           // stack at the stock point
      const h = stacks[L.node] = (stacks[L.node] || 0) + 1;
      x = G.wait[L.node][0] + (G.stackDx || 0) * (h - 1); y = G.wait[L.node][1] - (h - 1) * (G.stackDy || 15);
    } else {                                   // move through the step
      [x, y] = along(G.proc[L.node], u);
    }
    k.g.setAttribute("transform", `translate(${x.toFixed(1)},${y.toFixed(1)})`);
    k.g.paint(COL[L.kind]);
    k.pos = { leg: L, u };
  }
  // follow one lineup on the timeline ladder
  if (followed && followed.pos) {
    const { leg, u } = followed.pos;
    let x, y;
    if (leg.kind === "move") {               // between two steps: stand on the boundary
      const m = followed.legs.indexOf(leg), idx = m === 0 ? -1 : (m - 2) / 2;
      x = idx < 0 ? G.xs[0] - G.step / 2 : G.xs[idx] + G.step / 2;
      y = +marker.getAttribute("cy") || G.hi;
    } else {
      x = G.xs[leg.node] - G.step / 2 + G.step * u; y = leg.kind === "wait" ? G.hi : G.lo;
    }
    marker.setAttribute("cx", x); marker.setAttribute("cy", y); marker.setAttribute("opacity", 1);
    markerTxt.setAttribute("x", x); markerTxt.setAttribute("y", y + (y === G.hi ? 22 : -12));
    markerTxt.textContent = `day ${Math.round(t - followed.born)}`;
    A.appendChild(marker); A.appendChild(markerTxt);
  }
}
const statusEl = document.getElementById("status");
let last = performance.now();
function frame(now) {
  const dt = Math.min((now - last) / 1000, 0.1); last = now;
  if (playing) { simDay += dt * speed; update(simDay); }
  const d = done[done.length - 1];
  statusEl.innerHTML = `<b>Day ${Math.floor(simDay)}</b> · ${tokens.length} lineups in the stream · a new one every ${spawnEvery.toFixed(0)} days` +
    (d ? `<br><span class="muted">Last delivered: <b>${Math.round(d.lead)} days</b> (${Math.round(d.wait)} waiting, ${d.proc.toFixed(1)} in process) · ` +
         `${stateName === "current" ? "current" : "future"} state lead time ${Math.round(S.lead)} days, value-added ${Math.round(S.va)}%</span>` : "");
  requestAnimationFrame(frame);
}
update(0); requestAnimationFrame(frame);
window.__vsmAnim = { tokens: () => tokens.length };
</script>
</body></html>"""
