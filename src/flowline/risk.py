"""Supply continuity: safety-stock optimization for repeat parts, a risk register (entered risks plus risks the
model detects), logistics-provider performance, and the dual-sourcing plan."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import NormalDist

import numpy as np
import pandas as pd

from flowline.ctb import CTBResult
from flowline.models import Dataset, Settings
from flowline.suppliers import CMResult, SupplierResult

PERIOD_DAYS = 30.4


@dataclass
class RiskResult:
    safety_stock: pd.DataFrame     # one row per repeat part: demand, variability, recommended vs current
    register: pd.DataFrame         # entered + detected risks, scored likelihood x impact
    logistics: pd.DataFrame        # one row per logistics provider
    shipments: pd.DataFrame        # shipments with on-time flag
    dual_plan: pd.DataFrame        # single-source parts and their second-source plan
    kpis: dict


def safety_stock(data: Dataset, sup: SupplierResult, s: Settings) -> pd.DataFrame:
    """Recommended safety stock = z x sqrt(L/P x sd_d^2 + (mean_d / P)^2 x sd_L^2) (demand and lead-time variability).

    mean_d, sd_d: monthly consumption over the history; L: lead time in days; P: days per month;
    sd_L: standard deviation of delivery delay in days from receipts of that part (or its supplier)."""
    ch = data.consumption_history
    cols = ["item_id", "description", "supplier", "months", "avg_monthly_use", "demand_cv", "lead_time_days",
            "lead_time_sd_days", "current_ss", "recommended_ss", "reorder_point", "change_qty", "change_value",
            "recommendation", "days_of_cover_ss"]
    if ch.empty:
        return pd.DataFrame(columns=cols)
    items = data.items.set_index("item_id")
    names = data.supplier_names()
    z = NormalDist().inv_cdf(min(max(s.service_level_pct, 50.0), 99.9) / 100)
    rec = sup.receipts
    rows = []
    for item, g in ch.groupby("item_id"):
        if item not in items.index:
            continue
        it = items.loc[item]
        q = g.sort_values("month")["qty"].tail(12).astype(float)
        mu, sd = float(q.mean()), float(q.std(ddof=1)) if len(q) > 1 else 0.0
        L = float(it["lead_time_days"])
        dl = rec.loc[rec["item_id"] == item, "days_late"] if len(rec) else pd.Series(dtype=float)
        if len(dl) < 4 and len(rec):
            dl = rec.loc[rec["supplier_id"] == it["supplier_id"], "days_late"]
        sdl = float(dl.std(ddof=1)) if len(dl) > 2 else 0.0
        ss = z * np.sqrt(L / PERIOD_DAYS * sd ** 2 + (mu / PERIOD_DAYS) ** 2 * sdl ** 2)
        ss = float(np.ceil(ss))
        cur = float(it["safety_stock"])
        diff = ss - cur
        tol = s.safety_stock_tolerance_pct / 100
        if cur == 0 and ss > 0:
            reco = "Set safety stock"
        elif abs(diff) <= tol * max(cur, 1):
            reco = "OK"
        else:
            reco = "Raise" if diff > 0 else "Lower"
        rows.append(dict(item_id=item, description=it["description"], supplier=names.get(it["supplier_id"], it["supplier_id"]),
                         months=len(q), avg_monthly_use=mu, demand_cv=sd / mu if mu else np.nan, lead_time_days=L,
                         lead_time_sd_days=sdl, current_ss=cur, recommended_ss=ss,
                         reorder_point=float(np.ceil(mu / PERIOD_DAYS * L + ss)), change_qty=diff,
                         change_value=diff * float(it["std_cost"]), recommendation=reco,
                         days_of_cover_ss=ss / (mu / PERIOD_DAYS) if mu else np.nan))
    out = pd.DataFrame(rows, columns=cols)
    return out.sort_values("change_value", key=lambda x: x.abs(), ascending=False)


def _logistics(data: Dataset, s: Settings):
    sh = data.shipments.copy()
    cols = ["lsp", "mode", "shipments", "otd_pct", "avg_days_late", "cost_12m", "cost_per_kg", "premium_shipments",
            "premium_cost"]
    if sh.empty:
        return pd.DataFrame(columns=cols), sh
    asof = pd.Timestamp(s.as_of_date)
    sh = sh[(sh["delivered_date"] <= asof) & (sh["delivered_date"] > asof - pd.DateOffset(months=s.history_months))].copy()
    sh["days_late"] = (sh["delivered_date"] - sh["promised_date"]).dt.days
    sh["on_time"] = sh["days_late"] <= 0
    sh["is_premium"] = sh["premium"].str.upper().isin(["Y", "YES", "TRUE", "1"])
    rows = []
    for lsp, g in sh.groupby("lsp"):
        rows.append(dict(lsp=lsp, mode=", ".join(sorted(set(g["mode"]) - {""})), shipments=len(g),
                         otd_pct=100 * g["on_time"].mean(), avg_days_late=g.loc[g["days_late"] > 0, "days_late"].mean(),
                         cost_12m=g["cost"].sum(), cost_per_kg=g["cost"].sum() / g["weight_kg"].sum() if g["weight_kg"].sum() else np.nan,
                         premium_shipments=int(g["is_premium"].sum()), premium_cost=g.loc[g["is_premium"], "cost"].sum()))
    return pd.DataFrame(rows, columns=cols).sort_values("cost_12m", ascending=False), sh


def _level(score: float) -> str:
    return "High" if score >= 15 else "Medium" if score >= 8 else "Low"


def risk_register(data: Dataset, ctb: CTBResult, sup: SupplierResult, cm: CMResult, lsp: pd.DataFrame,
                  ss: pd.DataFrame, s: Settings) -> pd.DataFrame:
    rows = []
    for r in data.risk_register.itertuples():
        rows.append(dict(risk_id=r.risk_id, source="Register", risk=r.risk, category=r.category,
                         likelihood=r.likelihood, impact=r.impact, mitigation=r.mitigation, owner=r.owner,
                         status=r.status or "Open", due=r.due))
    n = 0

    def det(risk, cat, lk, im, mit):
        nonlocal n
        n += 1
        rows.append(dict(risk_id=f"D{n:02d}", source="Detected", risk=risk, category=cat, likelihood=lk, impact=im,
                         mitigation=mit, owner="", status="Open", due=pd.NaT))

    so = sup.sourcing
    hot = so[(so["risk_level"] == "High") & ((so["dual_status"] == "None identified") | (so["current_shortages"] > 0))] if len(so) else so
    for x in hot.itertuples() if len(hot) else []:
        det(f"Single source: {x.item_id} {x.description} from {x.supplier}", "Supply",
            4 if x.current_shortages else 3, 5 if x.projects_exposed >= 3 else 4,
            f"Dual sourcing {x.dual_status.lower()}" + (f" ({x.alternate})" if x.alternate else "")
            + "; hold a strategic buffer meanwhile")
    sc = sup.scorecard
    for x in sc[(sc["receipt_lines"] > 0) & (sc["otd_pct"] < s.otd_target_pct - 15)].itertuples() if len(sc) else []:
        det(f"Unreliable delivery: {x.name}, on time {x.otd_pct:.0f}%", "Supply", 4, 3 + (x.open_po_lines >= 3),
            "Recovery plan with dates; buffer lead time on open projects")
    for x in cm.plan[(cm.plan["load_pct"] > 100)].itertuples():
        det(f"CM capacity: {x.name or x.cm_id} at {x.load_pct:.0f}% in {x.month:%b %Y}", "Contract manufacturer",
            4 if x.in_commit_window else 3, 4, "Level the load, overtime, or split with a second source")
    ll = ctb.long_lead
    for x in ll[ll["status"] == "Order overdue"].itertuples() if len(ll) else []:
        det(f"Long-lead part not ordered: {x.item_id} for {x.project_id}", "Planning", 5, 4,
            "Order now; release long-lead parts at order intake")
    for x in lsp[lsp["otd_pct"] < s.lsp_otd_target_pct - 5].itertuples() if len(lsp) else []:
        det(f"Logistics provider late: {x.lsp}, on time {x.otd_pct:.0f}%", "Logistics", 3, 2,
            "Review lanes; add a backup carrier")
    low = ss[(ss["recommendation"].isin(["Raise", "Set safety stock"])) & (ss["current_ss"] < 0.5 * ss["recommended_ss"])] if len(ss) else ss
    if len(low):
        det(f"Safety stock too low on {len(low)} repeat parts ({', '.join(low['item_id'].head(4))}"
            + (", ..." if len(low) > 4 else "") + ")", "Inventory", 3, 3, "Raise safety stock to the recommended levels")
    cols = ["risk_id", "source", "risk", "category", "likelihood", "impact", "score", "level", "mitigation", "owner",
            "status", "due"]
    out = pd.DataFrame(rows, columns=[c for c in cols if c not in ("score", "level")])
    out["likelihood"] = pd.to_numeric(out["likelihood"], errors="coerce").fillna(1).clip(1, 5)
    out["impact"] = pd.to_numeric(out["impact"], errors="coerce").fillna(1).clip(1, 5)
    out["score"] = out["likelihood"] * out["impact"]
    out["level"] = out["score"].map(_level)
    out["due"] = pd.to_datetime(out["due"], errors="coerce")
    return out[cols].sort_values(["score", "source"], ascending=[False, False]).reset_index(drop=True)


def dual_plan(sup: SupplierResult, s: Settings) -> pd.DataFrame:
    so = sup.sourcing
    cols = ["item_id", "description", "supplier", "risk_level", "risk_score", "spend_12m", "dual_status", "alternate",
            "target_date", "days_to_target", "plan_status", "next_step"]
    if not len(so):
        return pd.DataFrame(columns=cols)
    x = so[so["single_source"] & so["risk_level"].isin(["High", "Medium"])].copy()
    asof = pd.Timestamp(s.as_of_date)
    x["target_date"] = pd.to_datetime(x["target_date"], errors="coerce")
    x["days_to_target"] = (x["target_date"] - asof).dt.days

    def st(r):
        if r.dual_status == "None identified":
            return "Not started", "Find and quote a second source"
        if pd.notna(r.target_date) and r.days_to_target < 0:
            return "Overdue", "Escalate the qualification"
        if r.dual_status == "Candidate":
            return "Candidate found", "Quote, samples and first-article inspection"
        return "In qualification", "Complete qualification and approve the source"

    res = [st(r) for r in x.itertuples()]
    x["plan_status"] = [a for a, _ in res]
    x["next_step"] = [b for _, b in res]
    return x[cols].sort_values(["risk_score"], ascending=False).reset_index(drop=True)


def run_risk(data: Dataset, ctb: CTBResult, sup: SupplierResult, cm: CMResult, s: Settings) -> RiskResult:
    ss = safety_stock(data, sup, s)
    lsp, shp = _logistics(data, s)
    reg = risk_register(data, ctb, sup, cm, lsp, ss, s)
    dp = dual_plan(sup, s)
    kpis = dict(
        risks_high=int((reg["level"] == "High").sum()), risks_total=len(reg),
        ss_raise=int(ss["recommendation"].isin(["Raise", "Set safety stock"]).sum()) if len(ss) else 0,
        ss_lower=int((ss["recommendation"] == "Lower").sum()) if len(ss) else 0,
        ss_value_change=float(ss["change_value"].sum()) if len(ss) else 0.0,
        lsp_otd_pct=100 * shp["on_time"].mean() if len(shp) else np.nan,
        premium_freight=float(shp.loc[shp["is_premium"], "cost"].sum()) if len(shp) else 0.0,
        dual_not_started=int((dp["plan_status"] == "Not started").sum()) if len(dp) else 0,
        dual_overdue=int((dp["plan_status"] == "Overdue").sum()) if len(dp) else 0)
    return RiskResult(ss, reg, lsp, shp, dp, kpis)
