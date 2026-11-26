"""Shop floor: today's build plan against demand and capacity, the SQDCC tier board, misses and countermeasures,
hourly output, downtime, first-pass yield, the skills matrix, ERP items to clear, and kits short for the next builds.

Hours are standard hours. Planned = the work scheduled; earned = standard hours of work completed; clocked = hours
people booked. Schedule attainment = earned / planned (to the current hour, today); labour productivity = earned /
clocked; first-pass yield = units passing first time / units inspected.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from flowline.ctb import CTBResult
from flowline.models import Dataset, Settings

TIERS = ["Safety", "Quality", "Delivery", "Cost", "Cash"]
LEVELS = {0: "Not trained", 1: "In training", 2: "With help", 3: "Independent", 4: "Can train"}


@dataclass
class ShopFloorResult:
    today: pd.Timestamp
    now_hour: float
    elapsed: float                    # share of the day shift gone
    plan: pd.DataFrame                # today's plan by work centre
    hourly: pd.DataFrame              # today's cumulative planned vs earned by hour and work centre
    tier: pd.DataFrame                # the SQDCC board: one row per letter
    history: pd.DataFrame             # daily metrics for trends
    downtime: pd.DataFrame            # downtime minutes by reason, last 7 working days
    downtime_today: pd.DataFrame
    fpy: pd.DataFrame                 # first-pass yield by work centre, today and 4 weeks
    misses: pd.DataFrame              # today's red items and whether a countermeasure exists
    countermeasures: pd.DataFrame
    skills: pd.DataFrame              # operators x work centres matrix
    coverage: pd.DataFrame            # qualified people per work centre and shift vs the minimum
    training: pd.DataFrame            # who to train where
    erp: pd.DataFrame                 # ERP items to clear, with age
    kits: pd.DataFrame                # parts not in stock for builds starting soon
    safety: pd.DataFrame
    kpis: dict = field(default_factory=dict)


def _status(value, target, higher=True, amber=5.0):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "No data"
    gap = (value - target) if higher else (target - value)
    return "Green" if gap >= 0 else ("Amber" if gap >= -amber else "Red")


def run_shopfloor(data: Dataset, ctb: CTBResult, s: Settings) -> ShopFloorResult | None:
    sch = data.shop_schedule
    if sch is None or sch.empty:
        return None
    wc = data.work_centers.set_index("wc_id") if len(data.work_centers) else pd.DataFrame()
    name = lambda w: wc["name"].get(w, w) if len(wc) else w  # noqa: E731
    sch = sch.copy()
    today = pd.Timestamp(s.as_of_date)
    if not (sch["date"] == today).any():
        today = sch["date"].max()
    hr = data.hourly_output
    hr_today = hr[hr["date"] == today] if len(hr) else hr
    now = s.shop_now_hour or (float(hr_today["hour"].max()) + 1 if len(hr_today) else s.shop_day_start_hour + 8)
    shift_len = float(wc["shift_hours"].max()) if len(wc) and wc["shift_hours"].max() > 0 else 8.0
    elapsed = float(np.clip((now - s.shop_day_start_hour) / shift_len, 0.0, 1.0))

    # ---- today's plan by work centre
    t = sch[sch["date"] == today]
    g = t.groupby("wc_id").agg(planned_hours=("planned_hours", "sum"), earned_hours=("earned_hours", "sum"),
                               actual_hours=("actual_hours", "sum"), people_needed=("people_needed", "sum"),
                               people_assigned=("people_assigned", "sum"),
                               project_id=("project_id", lambda x: ", ".join(sorted({str(v) for v in x if str(v) not in ("", "nan", "<NA>")}))),
                               operation=("operation", "first")).reset_index()
    g.insert(1, "work_center", g["wc_id"].map(name))
    if len(wc):     # flow order, as listed in work_centers
        g = g.assign(_o=g["wc_id"].map({w: i for i, w in enumerate(wc.index)}).fillna(99)).sort_values("_o").drop(columns="_o")
        g = g.reset_index(drop=True)
    g["planned_to_now"] = g["planned_hours"] * elapsed
    g["attainment_pct"] = np.where(g["planned_to_now"] > 0, g["earned_hours"] / g["planned_to_now"] * 100, np.nan)
    g["productivity_pct"] = np.where(g["actual_hours"] > 0, g["earned_hours"] / g["actual_hours"] * 100, np.nan)
    g["people_short"] = (g["people_needed"] - g["people_assigned"]).clip(lower=0)
    g["status"] = [_status(a, s.attainment_target_pct) for a in g["attainment_pct"]]
    dt = data.downtime
    dtt = dt[dt["date"] == today] if len(dt) else dt
    g["downtime_min"] = g["wc_id"].map(dtt.groupby("wc_id")["minutes"].sum() if len(dtt) else {}).fillna(0.0)
    reason = dtt.sort_values("minutes").groupby("wc_id")["reason"].last().to_dict() if len(dtt) else {}
    g["downtime_reason"] = [str(reason.get(w, "")) for w in g["wc_id"]]
    plan = g

    # ---- hourly, cumulative
    if len(hr_today):
        h = hr_today.copy()
        h = h.sort_values(["wc_id", "hour"])
        h["cum_planned"] = h.groupby("wc_id")["planned_hours"].cumsum()
        h["cum_earned"] = h.groupby("wc_id")["earned_hours"].cumsum()
        hourly = h
    else:
        hourly = pd.DataFrame(columns=["hour", "wc_id", "planned_hours", "earned_hours", "cum_planned", "cum_earned"])

    # ---- daily history (whole plant)
    q = data.quality_checks
    se = data.safety_events
    daily = sch.groupby("date").agg(planned=("planned_hours", "sum"), earned=("earned_hours", "sum"),
                                    actual=("actual_hours", "sum"), overtime=("overtime_hours", "sum"))
    daily.loc[today, "planned"] = plan["planned_to_now"].sum() if len(plan) else 0.0
    daily["attainment_pct"] = daily["earned"] / daily["planned"].replace(0, np.nan) * 100
    daily["productivity_pct"] = daily["earned"] / daily["actual"].replace(0, np.nan) * 100
    daily["overtime_pct"] = daily["overtime"] / daily["actual"].replace(0, np.nan) * 100
    if len(q):
        qq = q.groupby("date")[["inspected", "passed"]].sum()
        daily["fpy_pct"] = (qq["passed"] / qq["inspected"].replace(0, np.nan) * 100).reindex(daily.index)
    else:
        daily["fpy_pct"] = np.nan
    inc = se[se["type"].isin(["Recordable", "Lost time", "First aid"])] if len(se) else se
    daily["incidents"] = (inc.groupby("date").size().reindex(daily.index).fillna(0) if len(inc) else 0.0)
    daily = daily.sort_index()
    history = daily.reset_index().rename(columns={"index": "date"})

    # ---- ERP items to clear
    erp = data.erp_open_items.copy()
    if len(erp):
        erp["age_days"] = (today - erp["created"]).dt.days.fillna(0).astype(int)
        erp["overdue"] = erp["age_days"] > s.erp_max_age_days
        erp["work_center"] = erp["wc_id"].map(name)
        erp = erp.sort_values(["overdue", "value", "age_days"], ascending=False)
    unposted = float(erp.loc[erp["kind"].str.contains("Completion", case=False, na=False), "value"].sum()) if len(erp) else 0.0

    # ---- the SQDCC board
    last = history.tail(10)
    rec = se[se["type"].isin(["Recordable", "Lost time"])] if len(se) else se
    days_since = int((today - rec["date"].max()).days) if len(rec) else None
    today_inc = se[(se["date"] == today) & se["type"].isin(["Recordable", "Lost time", "First aid"])] if len(se) else se
    nm_week = int(((se["date"] > today - pd.Timedelta(days=7)) & (se["type"] == "Near miss")).sum()) if len(se) else 0
    qt = q[q["date"] == today] if len(q) else q
    fpy_today = float(qt["passed"].sum() / qt["inspected"].sum() * 100) if len(qt) and qt["inspected"].sum() else np.nan
    att_today = float(plan["earned_hours"].sum() / plan["planned_to_now"].sum() * 100) if plan["planned_to_now"].sum() else np.nan
    prod_today = float(plan["earned_hours"].sum() / plan["actual_hours"].sum() * 100) if plan["actual_hours"].sum() else np.nan
    worst = plan.sort_values("attainment_pct").iloc[0] if len(plan) else None
    fails = qt[qt["passed"] < qt["inspected"]] if len(qt) else qt
    rows = [
        dict(tier="Safety", metric="Recordables and first aids", value=float(len(today_inc)), target=0.0,
             status="Green" if len(today_inc) == 0 else "Red",
             detail=(f"{days_since} days since the last recordable · " if days_since is not None else "")
             + f"{nm_week} near misses reported this week",
             trend=list(last["incidents"].astype(float))),
        dict(tier="Quality", metric="First-pass yield", value=fpy_today, target=s.fpy_target_pct,
             status=_status(fpy_today, s.fpy_target_pct),
             detail="; ".join(f"{x.wc_id} {x.project_id}: {x.defect}" for x in fails.itertuples()) or "No failures today",
             trend=list(last["fpy_pct"].round(1))),
        dict(tier="Delivery", metric="Schedule attainment", value=att_today,
             target=s.attainment_target_pct, status=_status(att_today, s.attainment_target_pct),
             detail="" if worst is None else f"Lowest: {worst['work_center']} {worst['attainment_pct']:.0f}%"
             + (f", {worst['downtime_reason'].lower()}" if worst["downtime_reason"] else ""),
             trend=list(last["attainment_pct"].round(1))),
        dict(tier="Cost", metric="Labour productivity", value=prod_today,
             target=s.productivity_target_pct, status=_status(prod_today, s.productivity_target_pct),
             detail=f"Overtime {history['overtime_pct'].iloc[-11:-1].mean():.1f}% of hours over 10 days "
                    f"(target {s.overtime_target_pct:g}%)" if len(history) > 1 else "",
             trend=list(last["productivity_pct"].round(1))),
        dict(tier="Cash", metric="Completions not posted in SAP", value=unposted, target=0.0,
             status="Green" if unposted <= 0 else "Red",
             detail="; ".join(f"{x.project_id or x.ref}: {x.note}" for x in erp[erp["kind"].str.contains("Completion", case=False,
                                                                                                    na=False)].itertuples())
             if len(erp) else "", trend=[]),
    ]
    tier = pd.DataFrame(rows)

    # ---- downtime and FPY
    recent = sorted(sch["date"].unique())[-7:]
    d7 = dt[dt["date"].isin(recent)] if len(dt) else dt
    downtime = (d7.groupby("reason")["minutes"].sum().sort_values(ascending=False).reset_index() if len(d7)
                else pd.DataFrame(columns=["reason", "minutes"]))
    if len(downtime):
        downtime["cum_pct"] = downtime["minutes"].cumsum() / downtime["minutes"].sum() * 100
    downtime_today = dtt.assign(work_center=dtt["wc_id"].map(name)) if len(dtt) else dtt
    if len(q):
        f4 = q[q["date"] > today - pd.Timedelta(days=28)].groupby("wc_id")[["inspected", "passed"]].sum()
        ft = qt.groupby("wc_id")[["inspected", "passed"]].sum() if len(qt) else pd.DataFrame(columns=["inspected", "passed"])
        fpy = pd.DataFrame({"fpy_4w_pct": f4["passed"] / f4["inspected"] * 100,
                            "fpy_today_pct": (ft["passed"] / ft["inspected"] * 100) if len(ft) else np.nan,
                            "inspected_4w": f4["inspected"]}).reset_index()
        fpy.insert(1, "work_center", fpy["wc_id"].map(name))
    else:
        fpy = pd.DataFrame(columns=["wc_id", "work_center", "fpy_4w_pct", "fpy_today_pct", "inspected_4w"])

    # ---- misses and countermeasures
    cm = data.countermeasures.copy()
    open_cm = cm[cm["status"].fillna("").str.lower() != "done"] if len(cm) else cm
    misses = []

    def add_miss(metric, wc_id, miss, detail):
        ex = open_cm[(open_cm["metric"] == metric) & ((open_cm["wc_id"].fillna("") == wc_id) | (wc_id == ""))] \
            if len(open_cm) else open_cm
        misses.append(dict(tier="Tier 1", metric=metric, wc_id=wc_id, miss=miss, detail=detail,
                           countermeasure=ex["countermeasure"].iloc[0] if len(ex) else "",
                           cm_id=ex["cm_id"].iloc[0] if len(ex) else "",
                           needs="Escalate to Tier 2: it repeats with a countermeasure open" if len(ex)
                           else "Needs a countermeasure today"))

    # plant-level letters (Delivery and Quality are taken per work centre below)
    for r in tier.itertuples():
        if r.status in ("Red", "Amber") and r.tier in ("Safety", "Cost", "Cash"):
            add_miss(r.tier, "", f"{r.metric}: {_fmt(r.tier, r.value, s.currency)} vs {_fmt(r.tier, r.target, s.currency)}", r.detail)
    for r in plan[plan["status"] == "Red"].itertuples():
        add_miss("Delivery", r.wc_id, f"{r.work_center}: {r.attainment_pct:.0f}% of plan to {int(now)}:00",
                 ", ".join(x for x in [f"{r.people_short:.0f} short" if r.people_short else "",
                                       r.downtime_reason.lower() if r.downtime_reason else ""] if x))
    if len(qt):
        for w, x in qt.groupby("wc_id"):
            f_ = x["passed"].sum() / x["inspected"].sum() * 100 if x["inspected"].sum() else 100
            if f_ < s.fpy_target_pct:
                add_miss("Quality", w, f"{name(w)}: first-pass yield {f_:.0f}% vs {s.fpy_target_pct:.0f}%",
                         "; ".join(d_ for d_ in x["defect"].fillna("") if d_))
    misses = pd.DataFrame(misses, columns=["tier", "metric", "wc_id", "miss", "detail", "countermeasure", "cm_id", "needs"])
    if len(cm):
        cm["overdue"] = (cm["due"] < today) & (cm["status"].fillna("").str.lower() != "done")

    # ---- skills, coverage and training
    ops, sk = data.operators, data.skills
    if len(ops) and len(sk):
        m = sk.merge(ops, on="operator_id", how="left")
        matrix = m.pivot_table(index=["operator_id", "name", "shift", "home_wc"], columns="wc_id", values="level",
                               aggfunc="max").fillna(0).reset_index()
        cov = []
        for w in (wc.index if len(wc) else sorted(sk["wc_id"].unique())):
            shifts = ["Day", "Evening"][: int(wc["shifts"].get(w, 1)) if len(wc) else 1]
            for sh in shifts:
                mm = m[(m["wc_id"] == w) & (m["shift"] == sh)]
                need = int(wc["people_needed"].get(w, 0)) if len(wc) else 0
                cov.append(dict(wc_id=w, work_center=name(w), shift=sh, qualified=int((mm["level"] >= 3).sum()),
                                trainers=int((mm["level"] >= 4).sum()), in_training=int(mm["level"].between(1, 2).sum()),
                                people_needed=need, minimum=max(s.skills_min_qualified, need)))
        coverage = pd.DataFrame(cov)
        coverage["gap"] = (coverage["minimum"] - coverage["qualified"]).clip(lower=0)
        coverage["no_trainer"] = coverage["trainers"] == 0
        train = []
        for c in coverage[(coverage["gap"] > 0) | coverage["no_trainer"]].itertuples():
            cand = m[(m["wc_id"] == c.wc_id) & (m["shift"] == c.shift) & m["level"].between(1, 2)].sort_values("level", ascending=False)
            if not len(cand):   # anyone on the shift from a neighbouring station
                cand = m[(m["shift"] == c.shift) & (m["wc_id"] != c.wc_id)].drop_duplicates("operator_id").head(1)
                cand = cand.assign(level=0)
            trainer = m[(m["wc_id"] == c.wc_id) & (m["level"] >= 4)]["name"].head(1)
            for x in cand.head(max(int(c.gap), 1)).itertuples():
                train.append(dict(work_center=c.work_center, shift=c.shift, operator=x.name, from_level=int(x.level),
                                  to_level=3, trainer=trainer.iloc[0] if len(trainer) else "External / another site",
                                  target=(today + pd.Timedelta(days=30 if x.level >= 2 else 60)).date(),
                                  reason=(f"{c.qualified} qualified, need {c.minimum}" if c.gap else "No one can train others")))
        training = pd.DataFrame(train, columns=["work_center", "shift", "operator", "from_level", "to_level", "trainer",
                                                "target", "reason"])
    else:
        matrix = coverage = training = pd.DataFrame()

    # ---- kits short for builds starting soon (from clear to build)
    kits = pd.DataFrame(columns=["project_id", "build_start", "item_id", "description", "qty", "kind", "po_number",
                                 "supplier_id", "supply_date"])
    if ctb is not None and len(ctb.allocations):
        pj = ctb.projects
        start = pd.concat([pd.to_datetime(pj["planned_build_start"]), pd.to_datetime(pj["forecast_build_start"])], axis=1).min(axis=1)
        soon = pj[(pj["ctb_status"] == "In build") | ((start <= today + pd.Timedelta(days=s.kit_horizon_days))
                                                      & ~pj["ctb_status"].isin(["Built", "Shipped"]))]
        soon = soon.assign(forecast_build_start=pd.to_datetime(soon["planned_build_start"]))   # the date the floor plans to
        a = ctb.allocations[ctb.allocations["project_id"].isin(soon["project_id"]) & ctb.allocations["kind"].isin(["PO", "Shortage"])]
        if len(a):
            it = data.items.set_index("item_id")
            kits = a.assign(description=a["item_id"].map(it["description"]),
                            build_start=a["project_id"].map(soon.set_index("project_id")["forecast_build_start"]))
            kits = kits[["project_id", "build_start", "item_id", "description", "qty", "kind", "po_number", "supplier_id", "supply_date",
                         "need_date"]].sort_values(["build_start", "supply_date"])

    k = dict(attainment_pct=att_today, fpy_pct=fpy_today, productivity_pct=prod_today,
             people_short=float(plan["people_short"].sum()), downtime_min_today=float(dtt["minutes"].sum()) if len(dtt) else 0.0,
             erp_overdue=int(erp["overdue"].sum()) if len(erp) else 0, unposted_value=unposted,
             tier_red=int((tier["status"] == "Red").sum()), misses_without_cm=int((misses["countermeasure"] == "").sum()),
             coverage_gaps=int((coverage["gap"] > 0).sum()) if len(coverage) else 0,
             kits_short_lines=int(len(kits)), days_since_recordable=days_since,
             cm_overdue=int(cm["overdue"].sum()) if len(cm) else 0)
    return ShopFloorResult(today, now, elapsed, plan, hourly, tier, history, downtime, downtime_today, fpy, misses, cm, matrix,
                           coverage, training, erp, kits, se, k)


def _fmt(tier: str, v, cur: str = "$") -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "–"
    if tier == "Cash":
        return f"{cur}{v:,.0f}"
    if tier == "Safety":
        return f"{v:.0f}"
    return f"{v:.0f}%"
