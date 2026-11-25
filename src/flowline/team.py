"""Team scorecards and department KPIs.

Each person has a role and a scope: a buyer code (matches ``items.buyer``), a product family (planners) or
``All`` (inventory control, materials manager). Their KPIs are calculated from the same model as the dashboard and
compared with the targets in ``objectives``. Department KPIs are trended from ``kpi_history`` plus this month.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

# kpi -> (label, unit, better)
KPI = {
    "turns": ("Inventory turns", "x", "higher"),
    "doi": ("Days of inventory", "days", "lower"),
    "year_end_gap": ("Year-end gap to target", "$", "lower"),
    "ctb_pct": ("Projects clear to build", "%", "higher"),
    "late_projects": ("Projects late to customer", "count", "lower"),
    "at_risk_projects": ("Projects at risk", "count", "lower"),
    "shortage_lines": ("Late or missing part lines", "count", "lower"),
    "supplier_otd_pct": ("Supplier on-time delivery", "%", "higher"),
    "cm_otd_pct": ("CM on-time delivery", "%", "higher"),
    "cm_commit_pct": ("CM commitment in window", "%", "higher"),
    "past_due_lines": ("Past-due PO lines", "count", "lower"),
    "expedite_lines": ("PO lines to expedite", "count", "lower"),
    "late_part_lines": ("Late part lines on own items", "count", "lower"),
    "ppv_pct": ("Purchase price variance", "%", "lower"),
    "excess_value": ("Excess stock", "$", "lower"),
    "no_demand_items": ("Items with no demand", "count", "lower"),
    "ss_actions": ("Safety-stock changes to make", "count", "lower"),
    "savings_realized": ("Savings realized", "$", "higher"),
    "actions_overdue": ("Overdue actions", "count", "lower"),
    "risks_high": ("High supply risks", "count", "lower"),
    "invoices_not_raised": ("Milestones reached but not invoiced", "count", "lower"),
    "ar_overdue_value": ("Receivables overdue", "$", "lower"),
    "margin_fade_pts": ("Portfolio margin fade (points)", "pts", "lower"),
    "billing_at_risk_fy": ("Billing slipping out of the fiscal year", "$", "lower"),
    "submittals_overdue": ("Submittals overdue or rejected", "count", "lower"),
    "cos_stale": ("Change orders waiting over 30 days", "count", "lower"),
}


@dataclass
class TeamResult:
    people: pd.DataFrame          # one row per person: KPIs met, score, actions, alerts
    scorecards: pd.DataFrame      # person x KPI: value, target, met
    department: pd.DataFrame      # department KPI now vs target
    trend: pd.DataFrame           # month x KPI (history + this month) with target
    alert_owner: pd.Series        # alert_id -> person_id
    kpis: dict


def _met(value, target, better) -> bool | None:
    if target is None or value is None or (isinstance(value, float) and np.isnan(value)) or pd.isna(target):
        return None
    return bool(value >= target) if better == "higher" else bool(value <= target)


def department_values(r) -> dict:
    S = r.summary()
    pa = r.ctb.po_actions
    k = r.inventory.kpis
    act = r.meetings.actions if r.meetings is not None else pd.DataFrame()
    return dict(
        turns=k["turns_now"], doi=k["doi_now"], year_end_gap=k["year_end_gap"],
        ctb_pct=100 * S["projects_clear"] / S["projects_open"] if S["projects_open"] else np.nan,
        late_projects=S["projects_late"], at_risk_projects=S["projects_at_risk"], shortage_lines=S["shortage_lines"],
        supplier_otd_pct=S["supplier_otd_pct"], cm_otd_pct=S["cm_otd_pct"], cm_commit_pct=S["cm_commit_pct"],
        past_due_lines=int(pa["past_due"].sum()) if len(pa) else 0,
        expedite_lines=int(pa["action"].str.startswith("Expedite").sum()) if len(pa) else 0,
        ppv_pct=S["ppv_pct"], excess_value=k["excess_value"],
        no_demand_items=int(r.ctb.excess["no_demand"].sum()) if len(r.ctb.excess) else 0,
        ss_actions=r.risk.kpis["ss_raise"] + r.risk.kpis["ss_lower"],
        savings_realized=r.cost.kpis["realized"],
        actions_overdue=int(act["overdue"].sum()) if len(act) else 0,
        risks_high=r.risk.kpis["risks_high"],
        **_fin_values(r))


def _fin_values(r) -> dict:
    f = getattr(r, "financials", None)
    if f is None:
        return {}
    k = f.kpis
    return dict(invoices_not_raised=k["due_not_invoiced_count"], ar_overdue_value=k["ar_overdue"],
                margin_fade_pts=k["margin_sold_pct"] - k["margin_forecast_pct"], billing_at_risk_fy=k["billing_at_risk_fy"],
                submittals_overdue=k["submittals_overdue"], cos_stale=k["cos_stale"])


def person_values(r, role: str, scope: str, person_id: str) -> dict:
    role = role.lower()
    data = r.data
    act = r.meetings.actions if r.meetings is not None else pd.DataFrame()
    mine = act[act["owner"] == person_id] if len(act) else act
    base = dict(actions_overdue=int(mine["overdue"].sum()) if len(mine) else 0)
    if role.startswith("buyer"):
        items = set(data.items.loc[data.items["buyer"] == scope, "item_id"])
        rec = r.suppliers.receipts
        rec = rec[rec["item_id"].isin(items)] if len(rec) else rec
        pa = r.ctb.po_actions
        pa = pa[pa["item_id"].isin(items)] if len(pa) else pa
        sh = r.ctb.shortages
        sh = sh[sh["item_id"].isin(items) & (sh["issue"] != "Not yet ordered")] if len(sh) else sh
        sp = r.cost.pipeline
        base.update(
            supplier_otd_pct=100 * rec["on_time"].mean() if len(rec) else np.nan,
            past_due_lines=int(pa["past_due"].sum()) if len(pa) else 0,
            expedite_lines=int(pa["action"].str.startswith("Expedite").sum()) if len(pa) else 0,
            late_part_lines=len(sh),
            ppv_pct=100 * rec["ppv"].sum() / rec["std_value"].sum() if len(rec) and rec["std_value"].sum() else np.nan,
            savings_realized=float(sp.loc[sp["owner"] == person_id, "realized_to_date"].sum()) if len(sp) else 0.0)
    elif role.startswith("planner"):
        pj = r.ctb.projects
        pj = pj[pj["product_family"] == scope] if scope.lower() != "all" else pj
        open_ = pj[pj["ctb_status"].isin(["Clear to build", "Clear by start", "At risk", "Late"])]
        sh = r.ctb.shortages
        sh = sh[sh["project_id"].isin(open_["project_id"]) & (sh["issue"] != "Not yet ordered")] if len(sh) else sh
        base.update(
            ctb_pct=100 * open_["ctb_status"].isin(["Clear to build", "Clear by start"]).mean() if len(open_) else np.nan,
            late_projects=int((open_["ctb_status"] == "Late").sum()),
            at_risk_projects=int((open_["ctb_status"] == "At risk").sum()),
            shortage_lines=len(sh))
    elif role.startswith("project"):
        base.update(_fin_values(r))
    else:   # inventory analyst, materials manager: department-wide numbers
        d = department_values(r)
        fin = set(_fin_values(r))
        keep = (["excess_value", "no_demand_items", "ss_actions", "year_end_gap"] if "inventory" in role
                else [k for k in d if k not in fin])
        base.update({k: d[k] for k in keep})
        base["actions_overdue"] = int(mine["overdue"].sum()) if len(mine) else 0
    return base


def _alert_owner(r, team: pd.DataFrame) -> pd.Series:
    """Give each alert to a person: buyer by the part in its reference, planner by the project's family."""
    al = r.alerts
    if not len(al) or not len(team):
        return pd.Series(dtype=object)
    buyer_of = dict(zip(r.data.items["item_id"], r.data.items["buyer"], strict=False))
    family_of = dict(zip(r.data.projects["project_id"], r.data.projects["product_family"], strict=False))
    sup_buyer = r.data.items[r.data.items["supplier_id"] != ""].groupby("supplier_id")["buyer"].agg(
        lambda x: x.value_counts().index[0])
    name_to_id = dict(zip(r.data.suppliers["name"], r.data.suppliers["supplier_id"], strict=False)) if len(r.data.suppliers) else {}
    by_scope = {(row.role.lower().split()[0], row.scope): row.person_id for row in team.itertuples()}
    out = {}
    for a in al.itertuples():
        pid = None
        if a.area == "Project financials":
            out[a.alert_id] = next((p for (role, _), p in by_scope.items() if role == "project"), "")
            if out[a.alert_id]:
                continue
        toks = str(a.ref).replace(",", " ").split()
        for t in toks:
            if t in buyer_of and buyer_of[t]:
                pid = by_scope.get(("buyer", buyer_of[t]))
                break
        if pid is None:
            for t in toks:
                if t in family_of:
                    pid = by_scope.get(("planner", family_of[t]))
                    break
        if pid is None:
            sid = a.ref if a.ref in sup_buyer.index else name_to_id.get(a.ref)
            if sid in sup_buyer.index:
                pid = by_scope.get(("buyer", sup_buyer[sid]))
        if a.area == "Project financials":
            pid = next((p for (role, _), p in by_scope.items() if role == "project"), pid)
        if pid is None and a.area == "Inventory":
            pid = next((p for (role, _), p in by_scope.items() if role == "inventory"), None)
        if pid is None:
            pid = next((p for (role, _), p in by_scope.items() if role == "materials"), None)
        out[a.alert_id] = pid or ""
    return pd.Series(out)


def run_team(r) -> TeamResult:
    data = r.data
    team = data.team
    obj = data.objectives.copy()
    obj["direction"] = obj["direction"].str.lower().replace({"": None})
    tgt = {(o.owner, o.kpi): (o.target, o.direction or KPI.get(o.kpi, ("", "", "higher"))[2]) for o in obj.itertuples()}

    # department
    dv = department_values(r)
    drow = []
    for k, v in dv.items():
        label, unit, better = KPI[k]
        t, b = tgt.get(("Department", k), (None, better))
        drow.append(dict(kpi=k, label=label, unit=unit, value=v, target=t, better=b, met=_met(v, t, b)))
    department = pd.DataFrame(drow)

    # people
    owner = _alert_owner(r, team)
    sc_rows, ppl = [], []
    for p in team.itertuples():
        vals = person_values(r, p.role, p.scope, p.person_id)
        mets = []
        for k, v in vals.items():
            label, unit, better = KPI[k]
            t, b = tgt.get((p.person_id, k), (None, better))
            if t is None and p.role.lower().startswith("materials"):   # the manager owns the department targets
                t, b = tgt.get(("Department", k), (None, better))
            m = _met(v, t, b)
            if m is not None:
                mets.append(m)
            sc_rows.append(dict(person_id=p.person_id, name=p.name, role=p.role, kpi=k, label=label, unit=unit,
                                value=v, target=t, better=b, met=m))
        act = r.meetings.actions if r.meetings is not None else pd.DataFrame()
        mine = act[act["owner"] == p.person_id] if len(act) else act
        ppl.append(dict(person_id=p.person_id, name=p.name, role=p.role, scope=p.scope,
                        kpis_with_target=len(mets), kpis_met=int(sum(mets)),
                        score_pct=100 * sum(mets) / len(mets) if mets else np.nan,
                        open_actions=int((mine["status"] != "Done").sum()) if len(mine) else 0,
                        overdue_actions=int(mine["overdue"].sum()) if len(mine) else 0,
                        open_alerts=int((owner == p.person_id).sum()) if len(owner) else 0))
    people = pd.DataFrame(ppl, columns=["person_id", "name", "role", "scope", "kpis_with_target", "kpis_met", "score_pct",
                                        "open_actions", "overdue_actions", "open_alerts"])
    scorecards = pd.DataFrame(sc_rows, columns=["person_id", "name", "role", "kpi", "label", "unit", "value", "target",
                                                "better", "met"])

    # trend
    h = data.kpi_history[["month", "kpi", "value"]].copy()
    h["kind"] = "Actual"
    now_m = pd.Timestamp(r.settings.as_of_date).to_period("M").to_timestamp()
    cur = pd.DataFrame([dict(month=now_m, kpi=k, value=dv[k], kind="This month") for k in h["kpi"].unique() if k in dv])
    trend = pd.concat([h[h["month"] < now_m], cur], ignore_index=True) if len(cur) else h
    trend["target"] = [tgt.get(("Department", k), (np.nan, None))[0] for k in trend["kpi"]]
    trend["label"] = trend["kpi"].map(lambda k: KPI.get(k, (k,))[0])

    met = department["met"].dropna()
    kpis = dict(dept_met=int(met.sum()), dept_with_target=len(met), people=len(people),
                people_below_70=int((people["score_pct"] < 70).sum()) if len(people) else 0)
    return TeamResult(people, scorecards, department, trend.sort_values(["kpi", "month"]), owner, kpis)
