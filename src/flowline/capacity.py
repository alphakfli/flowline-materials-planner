"""Weekly capacity plan: load production orders onto machines and labour, week by week, with finite capacity.

Each order follows its routing (one step after another). In each week a step can process as many units as the
machine hours and the labour hours left that week allow (whichever runs out first); what is left moves to the next
week. Orders are loaded in the chosen sequence (due date, or priority then due date), never before their earliest
start (material ready and, if chosen, the planned start). The result is each order's start and finish week, its
lateness against the customer date, the load on every resource, and the resource that held each late order back.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from flowline.ctb import CTBResult
from flowline.models import Dataset, Settings


@dataclass
class CapacityPlan:
    weeks: list                         # Monday of each week
    resources: pd.DataFrame             # resource table with capacity per week
    capacity: pd.DataFrame              # resource x week hours available
    load: pd.DataFrame                  # resource x week hours planned
    utilization: pd.DataFrame           # load / capacity, %
    orders: pd.DataFrame                # order schedule and lateness
    steps: pd.DataFrame                 # order x step x week: units and hours (for the Gantt and stacked load)
    binding: pd.DataFrame               # resource x week shortfall hours that held late orders back
    kpis: dict = field(default_factory=dict)
    advice: pd.DataFrame | None = None  # overtime that would bring the late orders back


def _monday(d) -> pd.Timestamp:
    d = pd.Timestamp(d).normalize()
    return d - pd.Timedelta(days=d.weekday())


def weekly_capacity(res: pd.DataFrame, weeks: list, calendar: pd.DataFrame | None) -> pd.DataFrame:
    """Hours available per resource and week: units x shifts x hours x days x efficiency x calendar + overtime."""
    base = (res["units"] * res["shifts_per_day"] * res["hours_per_shift"] * res["days_per_week"]
            * res["efficiency_pct"].where(res["efficiency_pct"] > 0, 100) / 100)
    cap = pd.DataFrame({w: base.values for w in weeks}, index=res["resource_id"])
    if calendar is not None and len(calendar):
        for c in calendar.itertuples():
            w = _monday(c.week_start)
            if w not in cap.columns:
                continue
            rows = cap.index if str(c.resource_id).upper() in ("ALL", "", "NAN") else [str(c.resource_id)]
            for r in rows:
                if r in cap.index:
                    cap.loc[r, w] *= float(c.available_pct) / 100
    ot = res.set_index("resource_id")["overtime_hours"].fillna(0)
    return cap.add(ot, axis=0).clip(lower=0)


def plan_capacity(data: Dataset, ctb: CTBResult, s: Settings, resources: pd.DataFrame | None = None,
                  orders: pd.DataFrame | None = None, rule: str = "Due date", respect_planned: bool = True,
                  weeks: int | None = None, advise: bool = True) -> CapacityPlan | None:
    res = (resources if resources is not None else data.resources).copy()
    rt = data.routings
    po = (orders if orders is not None else data.production_orders).copy()
    if res is None or res.empty or rt is None or rt.empty or po is None or po.empty:
        return None
    for c, d in (("units", 1), ("shifts_per_day", 1), ("hours_per_shift", 8), ("days_per_week", 5), ("efficiency_pct", 100),
                 ("overtime_hours", 0)):
        res[c] = pd.to_numeric(res[c], errors="coerce").fillna(d) if c in res else d
    res["resource_id"] = res["resource_id"].astype(str)
    H = int(weeks or s.capacity_weeks)
    w0 = _monday(s.as_of_date)
    wk = [w0 + pd.Timedelta(weeks=i) for i in range(H)]
    cap = weekly_capacity(res, wk, data.capacity_calendar)
    left = cap.copy()
    load = cap * 0.0
    short = cap * 0.0

    # earliest start and due date per order, from clear to build
    pj = ctb.projects.set_index("project_id") if ctb is not None and len(ctb.projects) else pd.DataFrame()
    po = po[po.get("include", pd.Series(True, index=po.index)).fillna(True).astype(bool)] if "include" in po else po
    po["qty"] = pd.to_numeric(po["qty"], errors="coerce").fillna(0)
    po = po[po["qty"] > 0].copy()

    def first(pid, col):
        return pj[col].get(pid) if len(pj) and col in pj and pid in pj.index else None

    earliest, due, mready = [], [], []
    for o in po.itertuples():
        mr = first(o.project_id, "material_ready")
        st = first(o.project_id, "ctb_status")
        planned = first(o.project_id, "planned_build_start")
        e = pd.Timestamp(s.as_of_date)
        if st not in ("In build", "Built") and mr is not None and pd.notna(mr):
            e = max(e, pd.Timestamp(mr))
        if respect_planned and st not in ("In build", "Built") and planned is not None and pd.notna(planned):
            e = max(e, pd.Timestamp(planned))
        earliest.append(e)
        mready.append(mr)
        d_ = o.due_date if pd.notna(o.due_date) else first(o.project_id, "required_ship_date")
        due.append(pd.Timestamp(d_) if d_ is not None and pd.notna(d_) else pd.NaT)
    po["earliest_start"] = earliest
    po["material_ready"] = mready
    po["due"] = due
    po["priority"] = pd.to_numeric(po.get("priority", 9), errors="coerce").fillna(9)
    if rule.startswith("Priority"):
        po = po.sort_values(["priority", "due", "earliest_start"])
    elif rule.startswith("Material"):
        po = po.sort_values(["earliest_start", "due"])
    else:
        po = po.sort_values(["due", "priority", "earliest_start"])

    rres = res.set_index("resource_id")
    steps_out, rows = [], []
    for o in po.itertuples():
        r_ = rt[rt["product_family"] == o.product_family].sort_values("seq")
        if o.from_step and str(o.from_step) not in ("", "nan", "<NA>"):
            k = r_.index[r_["step"] == o.from_step]
            if len(k):
                r_ = r_.loc[k[0]:]
        ws = max(0, int((_monday(o.earliest_start) - w0).days // 7)) if pd.notna(o.earliest_start) else 0
        start_w = finish_w = None
        unplanned = 0.0
        held = {}
        prev_done = None          # units the previous step has finished by the end of each week (unit by unit flow)
        for st_ in r_.itertuples():
            mid, lid = str(st_.machine_id or ""), str(st_.labour_id or "")
            mh, lh = float(st_.machine_hours or 0), float(st_.labour_hours or 0)
            mid = mid if mid in cap.index and mh > 0 else ""
            lid = lid if lid in cap.index and lh > 0 else ""
            rem = float(o.qty)
            w = ws
            done_cum = np.zeros(H)
            while rem > 1e-9 and w < H:
                wcol = wk[w]
                lag = int(getattr(st_, "lag_weeks", 0) or 0)
                avail = ((prev_done[w - lag] if w - lag >= 0 else 0.0) if prev_done is not None else float(o.qty)) \
                    - (float(o.qty) - rem)
                can = min(rem, max(avail, 0.0))
                lim = None
                waiting = can < rem - 1e-9      # held by the previous step, not by this resource
                if mid:
                    c_ = left.at[mid, wcol] / mh
                    if c_ < can:
                        can, lim = c_, mid
                if lid:
                    c_ = left.at[lid, wcol] / lh
                    if c_ < can:
                        can, lim = c_, lid
                can = max(can, 0.0)
                if can > 1e-9:
                    if mid:
                        left.at[mid, wcol] -= can * mh
                        load.at[mid, wcol] += can * mh
                    if lid:
                        left.at[lid, wcol] -= can * lh
                        load.at[lid, wcol] += can * lh
                    steps_out.append(dict(order_id=o.order_id, project_id=o.project_id, step=st_.step, seq=st_.seq, week=wcol,
                                          units=can, machine_id=mid, machine_hours=can * mh, labour_id=lid, labour_hours=can * lh))
                    start_w = w if start_w is None else min(start_w, w)
                    rem -= can
                done_cum[w:] = float(o.qty) - rem
                if rem > 1e-9:
                    if lim and not (waiting and lim is None):
                        need = rem * (mh if lim == mid else lh)
                        short.at[lim, wcol] += need
                        held[lim] = max(held.get(lim, 0.0), w + need / 1e6)   # the latest week it held the order back
                    w += 1
            if rem > 1e-9:
                unplanned = max(unplanned, rem)
                finish_w = None
                break
            finish_w = w
            done_cum[w:] = float(o.qty)
            prev_done = done_cum
            ws = max(ws, int(np.argmax(done_cum > 1e-9)))   # the next step can start once the first unit is through
            if pd.isna(o.due):
                pass
        fin = (wk[finish_w] + pd.Timedelta(days=4)) if finish_w is not None else pd.NaT
        horizon_end = wk[-1] + pd.Timedelta(days=4)
        if finish_w is None:
            late = None
            status = "Late" if pd.notna(o.due) and o.due <= horizon_end else "After horizon"
        else:
            late = int((fin - o.due).days) if pd.notna(o.due) else None
            status = "Late" if late is not None and late > 0 else "On time"
        # material, not capacity, when the order could not start in time to meet its date
        if status == "Late" and pd.notna(o.due) and pd.notna(o.earliest_start) and \
                _monday(o.earliest_start) + pd.Timedelta(days=4) > o.due - pd.Timedelta(days=0) and not held:
            held = {"MATERIAL": 1.0}
        elif status == "Late" and not held:
            held = {"MATERIAL": 1.0}
        rows.append(dict(order_id=o.order_id, project_id=o.project_id, product_family=o.product_family, item=getattr(o, "item", ""), qty=o.qty,
                         priority=o.priority, material_ready=o.material_ready, earliest_start=o.earliest_start,
                         start_week=wk[start_w] if start_w is not None else pd.NaT, finish=fin, due=o.due,
                         days_late=max(late, 0) if late is not None else None, status=status, units_unplanned=unplanned,
                         held_by=max(held, key=held.get) if held and status == "Late" else "",
                         held_by_name=("Material (clear to build)" if max(held, key=held.get) == "MATERIAL" else
                                       rres["name"].get(max(held, key=held.get), "")) if held and status == "Late" else ""))
    orders_df = pd.DataFrame(rows)
    steps_df = pd.DataFrame(steps_out, columns=["order_id", "project_id", "step", "seq", "week", "units", "machine_id", "machine_hours",
                                                "labour_id", "labour_hours"])
    util = (load / cap.replace(0, np.nan) * 100).fillna(0)
    late_orders = orders_df[orders_df["status"] != "On time"] if len(orders_df) else orders_df
    late_ids = set(late_orders["order_id"]) if len(late_orders) else set()
    _ = late_ids
    bott = util.mean(axis=1).sort_values(ascending=False)
    k = dict(orders=len(orders_df), on_time=int((orders_df["status"] == "On time").sum()) if len(orders_df) else 0,
             late=int((orders_df["status"] == "Late").sum()) if len(orders_df) else 0,
             beyond=int((orders_df["status"] == "After horizon").sum()) if len(orders_df) else 0,
             late_capacity=int(((orders_df["status"] == "Late") & (orders_df["held_by"] != "MATERIAL")).sum()) if len(orders_df) else 0,
             late_material=int(((orders_df["status"] == "Late") & (orders_df["held_by"] == "MATERIAL")).sum()) if len(orders_df) else 0,
             avg_util_labour=float(util.loc[res.loc[res["kind"] == "Labour", "resource_id"]].values.mean()) if (res["kind"] == "Labour").any() else 0.0,
             avg_util_machine=float(util.loc[res.loc[res["kind"] == "Machine", "resource_id"]].values.mean()) if (res["kind"] == "Machine").any() else 0.0,
             bottleneck=bott.index[0] if len(bott) else "", bottleneck_name=rres["name"].get(bott.index[0], "") if len(bott) else "",
             bottleneck_util=float(bott.iloc[0]) if len(bott) else 0.0,
             overtime_hours=float(res["overtime_hours"].sum()) * H,
             first_week=wk[0], last_week=wk[-1])
    res_out = res.assign(capacity_week=cap.mean(axis=1).reindex(res["resource_id"]).values)
    plan = CapacityPlan(wk, res_out, cap, load, util, orders_df, steps_df, short, k)
    if advise and k["late_capacity"] > 0:
        plan.advice = _advise(data, ctb, s, res, po, rule, respect_planned, H, k)
    return plan


def _advise(data, ctb, s, res, po, rule, respect_planned, H, k0) -> pd.DataFrame:
    """Overtime that brings capacity-late orders back: try a Saturday shift (8 h per machine and per person) on each
    work centre that held an order back, keep the one that cuts lateness most, and repeat."""
    r = res.copy()
    o_ = po.drop(columns=["earliest_start", "material_ready", "due"], errors="ignore")

    def score(p):
        """(capacity-late orders, units of their last step finished after the due week): the second is continuous,
        so a Saturday that moves part of an order earlier counts even when the finish week does not change yet."""
        cap_late = p.orders[(p.orders["status"] == "Late") & (p.orders["held_by"] != "MATERIAL")]
        units = 0.0
        for o in cap_late.itertuples():
            st = p.steps[p.steps["order_id"] == o.order_id]
            if not len(st):
                units += float(o.qty)
                continue
            last = st[st["seq"] == st["seq"].max()]
            done = float(last.loc[last["week"] <= _monday(o.due), "units"].sum())
            units += float(o.qty) - done
        return (len(cap_late), round(units, 3))

    base = plan_capacity(data, ctb, s, r, o_, rule, respect_planned, H, advise=False)
    best = score(base)
    out = []
    for _ in range(6):
        if best[0] == 0:
            break
        short = base.binding.sum(axis=1)
        held = set(short[short > 0].index)
        wcs = sorted(set(r.loc[r["resource_id"].isin(held), "wc_id"]))
        from itertools import combinations

        def trial(group, r=r):
            t = r.copy()
            m = t["wc_id"].isin(group)
            if (t.loc[m, "overtime_hours"] >= 16 * t.loc[m, "units"]).all():
                return None
            t.loc[m, "overtime_hours"] = t.loc[m, "overtime_hours"] + 8 * t.loc[m, "units"]
            return (score(plan_capacity(data, ctb, s, t, o_, rule, respect_planned, H, advise=False)), group, t)

        trials = [x for x in (trial([wc]) for wc in wcs) if x]
        if not trials or min(x[0] for x in trials) >= best:          # one work centre alone is not enough: try two
            trials += [x for x in (trial(list(g)) for g in combinations(wcs, 2)) if x]
        if not trials:
            break
        trials.sort(key=lambda x: (x[0], len(x[1])))
        sc, group, t = trials[0]
        if sc >= best:
            break
        p = plan_capacity(data, ctb, s, t, o_, rule, respect_planned, H, advise=False)
        wc = " + ".join(group)
        m = t["wc_id"].isin(group)
        out.append(dict(work_center=wc, resources=", ".join(t.loc[m, "name"]),
                        add_hours_per_week=float((8 * t.loc[m, "units"]).sum()),
                        detail="; ".join(f"{x.name} +{8 * x.units:.0f} h" for x in t[m].itertuples()),
                        late_before=best[0], late_after=sc[0], units_late_before=best[1], units_late_after=sc[1]))
        r, base, best = t, p, sc
    df = pd.DataFrame(out, columns=["work_center", "resources", "add_hours_per_week", "detail", "late_before", "late_after",
                                    "units_late_before", "units_late_after"])
    if len(df):    # one line per work centre: the total overtime it needs
        df = df.groupby("work_center", sort=False).agg(resources=("resources", "first"), add_hours_per_week=("add_hours_per_week", "sum"),
                                                       late_before=("late_before", "first"), late_after=("late_after", "last"),
                                                       units_late_before=("units_late_before", "first"),
                                                       units_late_after=("units_late_after", "last")).reset_index()
        tot = r.set_index("resource_id")["overtime_hours"] - res.set_index("resource_id")["overtime_hours"]
        names = r.set_index("resource_id")
        df["detail"] = [", ".join(f"{names.at[i, 'name']} +{tot[i]:.0f} h" for i in tot.index if tot[i] > 0 and
                                  names.at[i, "wc_id"] in str(w).split(" + ")) for w in df["work_center"]]
    df.attrs["fixed"] = best[0] == 0
    df.attrs["overtime"] = (r.set_index("resource_id")["overtime_hours"]).to_dict()
    return df
