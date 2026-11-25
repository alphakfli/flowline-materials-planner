"""Supplier and contract-manufacturer performance: on-time delivery, quality, purchase price variance,
single-source risk and dual-sourcing progress; plus the CM forecast-versus-commitment view."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from flowline.ctb import CTBResult
from flowline.models import Dataset, Settings


@dataclass
class SupplierResult:
    scorecard: pd.DataFrame        # one row per supplier
    receipts: pd.DataFrame         # receipt lines with on-time flags and PPV
    monthly_otd: pd.DataFrame      # supplier x month OTD %
    sourcing: pd.DataFrame         # one row per bought item: sources, single-source risk, dual-sourcing status
    kpis: dict


@dataclass
class CMResult:
    plan: pd.DataFrame             # cm x month: demand now, forecast sent, committed, capacity, load
    by_item: pd.DataFrame          # cm x item x month
    performance: pd.DataFrame      # cm: OTD, quantity fill, open orders, late orders
    kpis: dict


def _receipts(data: Dataset, s: Settings) -> pd.DataFrame:
    r = data.receipts.copy()
    if r.empty:
        return r.assign(days_late=[], on_time=[], early=[], ppv=[], std_value=[], spend=[], month=[])
    asof = pd.Timestamp(s.as_of_date)
    r = r[(r["receipt_date"] <= asof) & (r["receipt_date"] > asof - pd.DateOffset(months=s.history_months))].copy()
    r["days_late"] = (r["receipt_date"] - r["promised_date"]).dt.days
    r["on_time"] = r["days_late"].between(-s.otd_early_days, s.otd_late_days)
    r["early"] = r["days_late"] < -s.otd_early_days
    r["spend"] = r["qty"] * r["unit_price"]
    r["std_value"] = r["qty"] * r["std_cost"]
    r["ppv"] = r["spend"] - r["std_value"]
    r["month"] = r["receipt_date"].dt.to_period("M").dt.to_timestamp()
    return r


def score_suppliers(data: Dataset, ctb: CTBResult, s: Settings) -> SupplierResult:
    r = _receipts(data, s)
    sup = data.suppliers.copy()
    if sup.empty and not r.empty:
        sup = pd.DataFrame({"supplier_id": sorted(r["supplier_id"].unique())}).assign(name="", supplier_type="Supplier",
                                                                                     region="", commodity="")
    names = data.supplier_names()

    g = r.groupby("supplier_id") if not r.empty else None
    rows = []
    open_po = ctb.po_actions
    single = _sourcing(data, ctb, s, r)
    for sp in sup.itertuples():
        x = r[r["supplier_id"] == sp.supplier_id] if g is not None else r
        lines = len(x)
        otd = 100 * x["on_time"].mean() if lines else np.nan
        qty = x["qty"].sum() if lines else 0
        ppm = 1e6 * x["qty_rejected"].sum() / qty if qty else np.nan
        spend = x["spend"].sum() if lines else 0.0
        ppv = x["ppv"].sum() if lines else 0.0
        ppv_pct = 100 * ppv / x["std_value"].sum() if lines and x["std_value"].sum() else np.nan
        op = open_po[open_po["supplier_id"] == sp.supplier_id] if not open_po.empty else open_po
        ss_items = single[(single["primary_supplier"] == sp.supplier_id) & single["single_source"]]
        # score: delivery 50, quality 30, price 20
        s_otd = 0 if np.isnan(otd) else min(otd, 100)
        s_q = 100 if np.isnan(ppm) else max(0.0, 100 - ppm / 100)       # 10,000 ppm -> 0
        s_p = 100 if np.isnan(ppv_pct) else max(0.0, 100 - max(ppv_pct, 0) * 10)   # +10% PPV -> 0
        score = 0.5 * s_otd + 0.3 * s_q + 0.2 * s_p if lines else np.nan
        grade = "" if np.isnan(score) else ("A" if score >= 85 else "B" if score >= 70 else "C")
        rows.append(dict(supplier_id=sp.supplier_id, name=sp.name or names.get(sp.supplier_id, ""),
                         supplier_type=sp.supplier_type or "Supplier", region=sp.region, commodity=sp.commodity,
                         receipt_lines=lines, otd_pct=otd, avg_days_late=x.loc[x["days_late"] > s.otd_late_days, "days_late"].mean() if lines else np.nan,
                         early_pct=100 * x["early"].mean() if lines else np.nan, quality_ppm=ppm, spend_12m=spend,
                         ppv=ppv, ppv_pct=ppv_pct,
                         open_po_lines=len(op), open_po_value=float(op["value"].sum()) if len(op) else 0.0,
                         late_open_lines=int((op["past_due"] | op["action"].str.startswith("Expedite")).sum()) if len(op) else 0,
                         single_source_items=len(ss_items), single_source_spend=float(ss_items["spend_12m"].sum()),
                         score=score, grade=grade))
    sc = pd.DataFrame(rows).sort_values(["spend_12m"], ascending=False) if rows else pd.DataFrame()
    mo = (r.groupby(["supplier_id", "month"])["on_time"].mean().mul(100).rename("otd_pct").reset_index()
          if not r.empty else pd.DataFrame(columns=["supplier_id", "month", "otd_pct"]))
    sups = sc[sc["supplier_type"].str.lower() != "cm"] if len(sc) else sc
    tot_lines = r[r["supplier_id"].isin(sups["supplier_id"])] if len(sups) else r
    kpis = dict(otd_pct=100 * tot_lines["on_time"].mean() if len(tot_lines) else np.nan,
                spend_12m=float(r["spend"].sum()) if len(r) else 0.0,
                ppv=float(r["ppv"].sum()) if len(r) else 0.0,
                ppv_pct=100 * r["ppv"].sum() / r["std_value"].sum() if len(r) and r["std_value"].sum() else np.nan,
                single_source_items=int(single["single_source"].sum()) if len(single) else 0,
                single_source_spend_pct=100 * single.loc[single["single_source"], "spend_12m"].sum() / single["spend_12m"].sum()
                if len(single) and single["spend_12m"].sum() else np.nan,
                dual_in_progress=int(single["dual_status"].isin(["In qualification", "Candidate"]).sum()) if len(single) else 0)
    return SupplierResult(sc, r, mo, single, kpis)


def _sourcing(data: Dataset, ctb: CTBResult, s: Settings, r: pd.DataFrame) -> pd.DataFrame:
    it = data.items[data.items["make_buy"].isin(["buy", "cm"])].copy()
    src = data.item_sources
    names = data.supplier_names()
    spend = r.groupby("item_id")["spend"].sum() if len(r) else pd.Series(dtype=float)
    open_val = ctb.po_actions.groupby("item_id")["value"].sum() if len(ctb.po_actions) else pd.Series(dtype=float)
    rq = ctb.requirements
    used = rq[rq["level"] > 0].groupby("item_id")["project_id"].nunique() if len(rq) else pd.Series(dtype=float)
    short = ctb.shortages.groupby("item_id").size() if len(ctb.shortages) else pd.Series(dtype=float)
    rows = []
    for i in it.itertuples():
        x = src[src["item_id"] == i.item_id] if not src.empty else src
        approved = x[x["status"].str.lower() == "approved"] if len(x) else x
        n_appr = max(len(approved), 1 if i.supplier_id else 0)
        pending = x[x["status"].str.lower().isin(["in qualification", "candidate"])] if len(x) else x
        if n_appr >= 2:
            dual = "Dual sourced"
        elif len(pending):
            dual = "In qualification" if (pending["status"].str.lower() == "in qualification").any() else "Candidate"
        else:
            dual = "None identified"
        alt = ", ".join(names.get(v, v) for v in pending["supplier_id"]) if len(pending) else ""
        tgt = pending["target_date"].min() if len(pending) else pd.NaT
        sp = float(spend.get(i.item_id, 0.0)) + 0.0
        projects = int(used.get(i.item_id, 0))
        single_flag = n_appr < 2
        # risk 0-100: lead time 40, spend 30, projects exposed 20, current shortages 10
        risk = (40 * min(i.lead_time_days / 180, 1) + 30 * min(sp / 500_000, 1) + 20 * min(projects / 6, 1)
                + 10 * (1 if short.get(i.item_id, 0) else 0)) if single_flag else 0.0
        rows.append(dict(item_id=i.item_id, description=i.description, commodity=i.commodity, make_buy=i.make_buy,
                         primary_supplier=i.supplier_id, supplier=names.get(i.supplier_id, i.supplier_id),
                         approved_sources=n_appr, single_source=single_flag, lead_time_days=i.lead_time_days,
                         long_lead=i.lead_time_days >= s.long_lead_days, spend_12m=sp,
                         open_po_value=float(open_val.get(i.item_id, 0.0)), projects_exposed=projects,
                         current_shortages=int(short.get(i.item_id, 0)), dual_status=dual, alternate=alt,
                         target_date=tgt, risk_score=risk,
                         risk_level="High" if risk >= 65 else "Medium" if risk >= 35 else "Low" if single_flag else ""))
    out = pd.DataFrame(rows)
    return out.sort_values(["risk_score", "spend_12m"], ascending=False) if len(out) else out


def cm_view(data: Dataset, ctb: CTBResult, s: Settings, sup: SupplierResult) -> CMResult:
    items = data.items.set_index("item_id")
    cm_items = data.items[data.items["make_buy"] == "cm"]
    hrs = items["cm_hours_per_unit"].to_dict()
    cm_of = dict(zip(cm_items["item_id"], cm_items["supplier_id"], strict=False))
    start = pd.Timestamp(s.as_of_date).to_period("M").to_timestamp()
    horizon = pd.period_range(start, periods=6, freq="M").to_timestamp()

    rq = ctb.requirements
    d = rq[rq["item_id"].isin(cm_of)].copy() if len(rq) else pd.DataFrame(columns=["item_id", "need_date", "qty_required"])
    # demand the CM must deliver = requirement not covered from our own stock
    d["qty"] = pd.to_numeric(d["qty_required"], errors="coerce").fillna(0.0) - pd.to_numeric(
        d.get("from_stock", 0), errors="coerce")
    d["month"] = pd.to_datetime(d["need_date"]).dt.to_period("M").dt.to_timestamp().clip(lower=start)
    d["cm_id"] = d["item_id"].map(cm_of)
    dem = d.groupby(["cm_id", "item_id", "month"])["qty"].sum().rename("demand_now")

    f = data.cm_forecast.copy()
    f["cm_id"] = f["cm_id"].where(f["cm_id"] != "", f["item_id"].map(cm_of))
    fc = f.groupby(["cm_id", "item_id", "month"])[["forecast_qty", "committed_qty"]].sum()
    bi = pd.concat([dem, fc], axis=1).fillna(0.0).reset_index()
    bi = bi[bi["month"].isin(horizon)].copy()
    for c in ("demand_now", "forecast_qty", "committed_qty"):    # empty tables come back as text columns
        bi[c] = pd.to_numeric(bi[c], errors="coerce").fillna(0.0).astype(float)
    bi["hours_per_unit"] = pd.to_numeric(bi["item_id"].map(hrs), errors="coerce").fillna(0.0).astype(float)
    for c in ("demand_now", "forecast_qty", "committed_qty"):
        bi[c.replace("_qty", "") + "_hours"] = bi[c] * bi["hours_per_unit"]
    bi["commit_gap"] = bi["committed_qty"] - bi["forecast_qty"]

    plan = bi.groupby(["cm_id", "month"])[["demand_now_hours", "forecast_hours", "committed_hours"]].sum().reset_index()
    cap = data.cm_capacity.groupby(["cm_id", "month"])["capacity_hours"].sum()
    grid = pd.MultiIndex.from_product([sorted(set(plan["cm_id"]) | set(cm_of.values()) - {""}), horizon],
                                      names=["cm_id", "month"])
    plan = plan.set_index(["cm_id", "month"]).reindex(grid, fill_value=0.0)
    plan["capacity_hours"] = cap.reindex(grid).fillna(np.nan)
    plan = plan.reset_index()
    plan["load_pct"] = 100 * plan["demand_now_hours"] / plan["capacity_hours"]
    plan["forecast_load_pct"] = 100 * plan["forecast_hours"] / plan["capacity_hours"]
    plan["commit_pct"] = np.where(plan["forecast_hours"] > 0, 100 * plan["committed_hours"] / plan["forecast_hours"], np.nan)
    plan["forecast_change_pct"] = np.where(plan["forecast_hours"] > 0,
                                           100 * (plan["demand_now_hours"] - plan["forecast_hours"]) / plan["forecast_hours"],
                                           np.where(plan["demand_now_hours"] > 0, 100.0, 0.0))
    plan["month_index"] = plan["month"].map({m: i for i, m in enumerate(horizon)})
    plan["in_commit_window"] = plan["month_index"] < s.cm_commit_horizon_months
    names = data.supplier_names()
    plan["name"] = plan["cm_id"].map(names).astype(object).fillna("")

    sc = sup.scorecard
    rec = sup.receipts
    perf = []
    for cm in sorted(plan["cm_id"].unique()):
        x = rec[rec["supplier_id"] == cm] if len(rec) else rec
        row = sc[sc["supplier_id"] == cm]
        op = ctb.po_actions[ctb.po_actions["supplier_id"] == cm] if len(ctb.po_actions) else ctb.po_actions
        pl = plan[plan["cm_id"] == cm]
        perf.append(dict(cm_id=cm, name=names.get(cm, ""), receipt_lines=len(x),
                         otd_pct=100 * x["on_time"].mean() if len(x) else np.nan,
                         avg_days_late=x.loc[x["days_late"] > s.otd_late_days, "days_late"].mean() if len(x) else np.nan,
                         quality_ppm=float(row["quality_ppm"].iloc[0]) if len(row) else np.nan,
                         open_orders=len(op), late_open_orders=int((op["past_due"] | op["action"].str.startswith("Expedite")).sum()) if len(op) else 0,
                         peak_load_pct=float(pl["load_pct"].max()) if pl["load_pct"].notna().any() else np.nan,
                         commit_pct_window=100 * pl.loc[pl["in_commit_window"], "committed_hours"].sum()
                         / pl.loc[pl["in_commit_window"], "forecast_hours"].sum()
                         if pl.loc[pl["in_commit_window"], "forecast_hours"].sum() else np.nan,
                         forecast_change_pct=100 * (pl["demand_now_hours"].sum() - pl["forecast_hours"].sum()) / pl["forecast_hours"].sum()
                         if pl["forecast_hours"].sum() else np.nan,
                         last_forecast_sent=data.cm_forecast.loc[data.cm_forecast["cm_id"] == cm, "sent_date"].max()
                         if len(data.cm_forecast) else pd.NaT))
    performance = pd.DataFrame(perf)
    w = plan[plan["in_commit_window"]]
    kpis = dict(commit_pct=100 * w["committed_hours"].sum() / w["forecast_hours"].sum() if w["forecast_hours"].sum() else np.nan,
                otd_pct=100 * rec.loc[rec["supplier_id"].isin(plan["cm_id"]), "on_time"].mean()
                if len(rec) and rec["supplier_id"].isin(plan["cm_id"]).any() else np.nan,
                overloaded_months=int((plan["load_pct"] > 100).sum()), cms=plan["cm_id"].nunique())
    return CMResult(plan, bi, performance, kpis)
