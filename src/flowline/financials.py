"""Project financials for engineer-to-order projects: cost, margin, revenue recognition, billing, receivables,
change orders and submittals.

Material cost to complete comes from the clear-to-build model, not from the budget: committed cost is the open PO
lines allocated to the project (at PO price), and the rest is stock allocated to it plus parts not yet bought (at
standard cost). Other cost elements use the budget remaining, or an estimate entered in ``cost_actuals``.

Billing milestones follow their triggers: a shipment milestone moves with the project's forecast ship date, a
drawings milestone with the approval of the submittal that holds it. So a late part shows up as revenue and cash
moving, not only as a late project.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

import numpy as np
import pandas as pd

from flowline.ctb import CTBResult, rolled_cost
from flowline.models import Dataset, Settings

ELEMENTS = ["Material", "Labour", "Engineering", "Freight", "Commissioning", "Contingency"]


@dataclass
class FinancialResult:
    projects: pd.DataFrame       # one row per project: contract, as sold, budget, actual, committed, ETC, EAC, margin, POC
    wbs: pd.DataFrame            # project x cost element
    milestones: pd.DataFrame     # billing milestones with forecast date, status, amount
    receivables: pd.DataFrame    # open invoices with aging
    billing_by_month: pd.DataFrame   # month: planned billing, forecast billing, forecast cash
    change_orders: pd.DataFrame
    submittals: pd.DataFrame
    kpis: dict


def _d(x):
    return None if x is None or pd.isna(x) else pd.Timestamp(x)


def _bucket(days: float) -> str:
    if days <= 0:
        return "Not due"
    return "1-30" if days <= 30 else "31-60" if days <= 60 else "61-90" if days <= 90 else "90+"


def run_financials(data: Dataset, ctb: CTBResult, s: Settings) -> FinancialResult | None:
    wb = data.wbs_budget
    if wb.empty:
        return None
    asof = pd.Timestamp(s.as_of_date)
    ye = pd.Timestamp(s.year_end)
    terms = timedelta(days=int(s.payment_terms_days))
    pj = ctb.projects.set_index("project_id")
    roll = rolled_cost(data)
    std = dict(zip(data.items["item_id"], data.items["std_cost"], strict=False))
    price = {lt.lot_id: lt.unit_price for lt in ctb.lots if lt.kind == "PO"}
    al = ctb.allocations.copy()
    al["unit_cost"] = [price.get(l_, 0.0) if k == "PO" else roll.get(i, std.get(i, 0.0))
                       for l_, k, i in zip(al["lot_id"], al["kind"], al["item_id"], strict=False)]
    al["value"] = al["qty"] * al["unit_cost"]
    mat = al.pivot_table(index="project_id", columns="kind", values="value", aggfunc="sum").fillna(0.0)
    act = data.cost_actuals.groupby(["project_id", "cost_element"])[["cost_to_date", "etc_override"]].sum()
    co = data.change_orders.copy()
    co["status"] = co["status"].str.strip().str.capitalize().replace("", "Pending")
    approved = co[co["status"] == "Approved"]
    co_price = approved.groupby("project_id")["price_change"].sum()

    # ---- WBS: project x cost element
    rows = []
    for (pid, el), g in wb.groupby(["project_id", "cost_element"]):
        if pid not in pj.index:
            continue
        status = pj.at[pid, "ctb_status"]
        a = float(act["cost_to_date"].get((pid, el), 0.0))
        ov = float(act["etc_override"].get((pid, el), 0.0))
        committed = etc = 0.0
        if el == "Material" and status not in ("In build", "Built"):
            m = mat.loc[pid] if pid in mat.index else pd.Series(dtype=float)
            committed = float(m.get("PO", 0.0))
            etc = float(m.get("Stock", 0.0)) + float(m.get("Shortage", 0.0))
        else:
            etc = ov if ov > 0 else max(float(g["budget"].sum()) - a, 0.0)
        rows.append(dict(project_id=pid, cost_element=el, as_sold=float(g["as_sold"].sum()), budget=float(g["budget"].sum()),
                         actual=a, committed=committed, etc=etc, eac=a + committed + etc))
    w = pd.DataFrame(rows)
    w["variance"] = w["budget"] - w["eac"]
    w["_o"] = w["cost_element"].map({e: i for i, e in enumerate(ELEMENTS)}).fillna(99)
    w = w.sort_values(["project_id", "_o"]).drop(columns="_o").reset_index(drop=True)

    # ---- billing milestones
    sub = data.submittals.copy()
    ms = data.billing_milestones.copy()
    mrows = []
    for m in ms.itertuples():
        if m.project_id not in pj.index:
            continue
        p = pj.loc[m.project_id]
        contract = float(p["sell_value"]) + float(co_price.get(m.project_id, 0.0))
        amount = contract * m.pct / 100
        planned = _d(m.planned_date)
        trig = (m.trigger or "").strip().lower()
        fc = planned
        if trig == "shipment":
            fc = pd.Timestamp(p["forecast_ship"])
        elif trig == "commissioning":
            fc = pd.Timestamp(p["forecast_ship"]) + timedelta(days=int(s.commissioning_days))
        elif trig == "build start":
            fc = pd.Timestamp(p["forecast_build_start"])
        elif trig == "material ready" and p["material_ready"] is not None and not pd.isna(p["material_ready"]):
            fc = pd.Timestamp(p["material_ready"])
        elif trig == "drawings approved":
            hold = sub[(sub["holds"] == m.milestone_id) & (sub["project_id"] == m.project_id)]
            if len(hold):
                h = hold.iloc[0]
                if str(h["status"]).lower().startswith("approved") and pd.notna(h["returned"]):
                    fc = pd.Timestamp(h["returned"])
                else:
                    due = _d(h["due"]) or asof
                    fc = max(due, asof + timedelta(days=14))
        inv = _d(m.invoice_date)
        if inv is not None:
            paid = _d(m.paid_date)
            status = "Paid" if paid is not None else "Invoiced"
            billed = float(m.amount_invoiced) if m.amount_invoiced else amount
        else:
            status = "Due, not invoiced" if fc is not None and fc <= asof else "Planned"
            billed, paid = 0.0, None
        bill_date = inv if inv is not None else fc
        cash_date = paid if paid is not None else (bill_date + terms if bill_date is not None else None)
        mrows.append(dict(project_id=m.project_id, customer=p["customer"], milestone_id=m.milestone_id, name=m.name,
                          trigger=m.trigger, pct=m.pct, amount=amount, planned_date=planned, forecast_date=fc,
                          slip_days=(fc - planned).days if fc is not None and planned is not None else 0,
                          status=status, invoice_no=m.invoice_no, invoice_date=inv, billed=billed, paid_date=paid,
                          expected_cash=cash_date,
                          planned_in_fy=planned is not None and planned <= ye,
                          forecast_in_fy=(bill_date is not None and bill_date <= ye)))
    mil = pd.DataFrame(mrows)

    # ---- receivables
    ar = mil[mil["status"] == "Invoiced"].copy()
    ar["due_date"] = ar["invoice_date"] + terms
    ar["days_overdue"] = (asof - ar["due_date"]).dt.days.clip(lower=0) if len(ar) else []
    ar["bucket"] = [_bucket(d) for d in ar["days_overdue"]] if len(ar) else []
    ar["days_outstanding"] = (asof - ar["invoice_date"]).dt.days if len(ar) else []
    ar = ar[["project_id", "customer", "milestone_id", "name", "invoice_no", "invoice_date", "billed", "due_date",
             "days_outstanding", "days_overdue", "bucket"]].sort_values("days_overdue", ascending=False)

    # ---- per project
    sub["overdue"] = sub["returned"].isna() & (sub["due"] < asof)
    sub["blocked"] = sub["status"].str.lower().isin(["rejected", "resubmit"])
    prow = []
    for pid, g in w.groupby("project_id"):
        p = pj.loc[pid]
        sold = float(p["sell_value"])
        contract = sold + float(co_price.get(pid, 0.0))
        cost_sold, budget, actual, committed, etc, eac = (g[c].sum() for c in ("as_sold", "budget", "actual", "committed", "etc", "eac"))
        poc = actual / eac if eac else 0.0
        earned = poc * contract
        mi = mil[mil["project_id"] == pid] if len(mil) else mil
        billed = float(mi["billed"].sum()) if len(mi) else 0.0
        pending = co[(co["project_id"] == pid) & (co["status"] == "Pending")]
        sp = sub[sub["project_id"] == pid]
        prow.append(dict(
            project_id=pid, customer=p["customer"], product_family=p["product_family"], ctb_status=p["ctb_status"],
            contract_sold=sold, approved_changes=contract - sold, contract=contract,
            pending_changes=float(pending["price_change"].sum()),
            cost_as_sold=cost_sold, budget=budget, actual=actual, committed=committed, etc=etc, eac=eac,
            cost_variance=budget - eac,
            margin_sold_pct=100 * (sold - cost_sold) / sold if sold else np.nan,
            margin_budget_pct=100 * (contract - budget) / contract if contract else np.nan,
            margin_forecast_pct=100 * (contract - eac) / contract if contract else np.nan,
            poc_pct=100 * poc, earned=earned, billed=billed,
            unbilled=max(earned - billed, 0.0), billings_in_excess=max(billed - earned, 0.0),
            ar_open=float(ar.loc[ar["project_id"] == pid, "billed"].sum()) if len(ar) else 0.0,
            ar_overdue=float(ar.loc[(ar["project_id"] == pid) & (ar["days_overdue"] > 0), "billed"].sum()) if len(ar) else 0.0,
            billing_at_risk_fy=float(mi.loc[mi["planned_in_fy"] & ~mi["forecast_in_fy"] & (mi["status"] == "Planned"), "amount"].sum()) if len(mi) else 0.0,
            due_not_invoiced=float(mi.loc[mi["status"] == "Due, not invoiced", "amount"].sum()) if len(mi) else 0.0,
            submittals_overdue=int((sp["overdue"] | sp["blocked"]).sum())))
    fp = pd.DataFrame(prow)
    fp["margin_fade_pts"] = fp["margin_sold_pct"] - fp["margin_forecast_pct"]

    # ---- billing and cash by month
    start = asof.to_period("M").to_timestamp()
    months = pd.period_range(start, ye + pd.DateOffset(months=6), freq="M").to_timestamp()
    bm = []
    for mth in months:
        nxt = mth + pd.DateOffset(months=1)
        open_ = mil[mil["status"].isin(["Planned", "Due, not invoiced"])] if len(mil) else mil
        bm.append(dict(month=mth,
                       billing_planned=float(open_.loc[(open_["planned_date"].clip(lower=start) >= mth) & (open_["planned_date"].clip(lower=start) < nxt), "amount"].sum()),
                       billing_forecast=float(open_.loc[(open_["forecast_date"].clip(lower=start) >= mth) & (open_["forecast_date"].clip(lower=start) < nxt), "amount"].sum()),
                       cash_forecast=float(mil.loc[(mil["status"] != "Paid") & (mil["expected_cash"].clip(lower=start) >= mth)
                                                   & (mil["expected_cash"].clip(lower=start) < nxt), "amount"].sum())))
    billing_by_month = pd.DataFrame(bm)

    co["age_days"] = np.where(co["status"] == "Pending", (asof - co["submitted"]).dt.days, np.nan)
    co["customer"] = co["project_id"].map(pj["customer"]) if len(co) else []
    subs = sub.assign(days_late=np.where(sub["overdue"], (asof - sub["due"]).dt.days, 0))
    ar_open = float(ar["billed"].sum()) if len(ar) else 0.0
    billed_90 = float(mil.loc[(mil["invoice_date"] > asof - timedelta(days=90)) & (mil["invoice_date"] <= asof), "billed"].sum()) if len(mil) else 0.0
    kpis = dict(
        contract=float(fp["contract"].sum()), eac=float(fp["eac"].sum()),
        margin_sold_pct=100 * (fp["contract_sold"].sum() - fp["cost_as_sold"].sum()) / fp["contract_sold"].sum(),
        margin_forecast_pct=100 * (fp["contract"].sum() - fp["eac"].sum()) / fp["contract"].sum(),
        projects_fading=int((fp["margin_fade_pts"] >= s.margin_fade_alert_pts).sum()),
        unbilled=float(fp["unbilled"].sum()), billings_in_excess=float(fp["billings_in_excess"].sum()),
        ar_open=ar_open, ar_overdue=float(ar.loc[ar["days_overdue"] > 0, "billed"].sum()) if len(ar) else 0.0,
        ar_over_60=float(ar.loc[ar["days_overdue"] > 60, "billed"].sum()) if len(ar) else 0.0,
        dso=ar_open / billed_90 * 90 if billed_90 else np.nan,
        billing_fy_planned=float(mil.loc[mil["planned_in_fy"] & (mil["status"] == "Planned"), "amount"].sum()) if len(mil) else 0.0,
        billing_fy_forecast=float(mil.loc[mil["forecast_in_fy"] & (mil["status"].isin(["Planned", "Due, not invoiced"])), "amount"].sum()) if len(mil) else 0.0,
        billing_at_risk_fy=float(fp["billing_at_risk_fy"].sum()),
        due_not_invoiced=float(fp["due_not_invoiced"].sum()),
        due_not_invoiced_count=int((mil["status"] == "Due, not invoiced").sum()) if len(mil) else 0,
        cos_pending=int((co["status"] == "Pending").sum()), cos_pending_value=float(co.loc[co["status"] == "Pending", "price_change"].sum()),
        cos_stale=int((co["age_days"] > 30).sum()),
        submittals_overdue=int((subs["overdue"] | subs["blocked"]).sum()))
    return FinancialResult(fp, w, mil, ar, billing_by_month, co, subs, kpis)
