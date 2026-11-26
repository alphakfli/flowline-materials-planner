"""Weekly meeting packs and the action log.

``agenda`` builds the items each stakeholder group needs to discuss this week (engineering, production,
contracts, finance, suppliers and CMs, the materials team), straight from the model. ``actions`` is the running
action log: carried from week to week in the input workbook, with overdue actions flagged.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

import pandas as pd

STAKEHOLDERS = ["Production", "Engineering", "Contracts", "Finance", "Suppliers and CMs", "Materials team"]
AGENDA_COLS = ["stakeholder", "topic", "detail", "decision_needed", "ref", "owner_role"]


@dataclass
class MeetingResult:
    agenda: pd.DataFrame      # stakeholder x item
    actions: pd.DataFrame     # action log with overdue flag and age
    kpis: dict


def prepare_actions(actions: pd.DataFrame, asof) -> pd.DataFrame:
    a = actions.copy()
    if a.empty:
        return a.assign(overdue=pd.Series(dtype=bool), days_open=pd.Series(dtype=float))
    a["status"] = a["status"].replace("", "Open")
    t = pd.Timestamp(asof)
    a["overdue"] = (a["status"].str.lower() != "done") & (a["due"] < t)
    a["days_open"] = ((a["closed"].fillna(t)) - a["opened"]).dt.days
    return a.sort_values(["overdue", "due"], ascending=[False, True]).reset_index(drop=True)


def build_agenda(r) -> pd.DataFrame:
    s, cur = r.settings, r.settings.currency
    asof = pd.Timestamp(s.as_of_date)
    win_end = asof + timedelta(days=s.frozen_window_days)
    pj = r.ctb.projects
    rows: list[dict] = []

    def add(st, topic, detail, decision, ref="", role=""):
        rows.append(dict(zip(AGENDA_COLS, [st, topic, detail, decision, ref, role], strict=True)))

    # Production
    rel = pj[(pd.to_datetime(pj["planned_build_start"]) <= win_end) & pj["ctb_status"].isin(["Clear to build", "Clear by start", "At risk", "Late"])]
    for p in rel.itertuples():
        go = p.ctb_status == "Clear to build" or (p.ctb_status == "Clear by start")
        add("Production", f"Release {p.project_id}" if go else f"Hold {p.project_id}",
            f"{p.customer}: planned start {p.planned_build_start:%d %b}, {p.ctb_status.lower()}"
            + (f", material complete {p.material_ready:%d %b}" if p.material_ready else ""),
            "Release to the floor and kit it" if go else f"Hold: gating part {p.gating_item}", p.project_id, "Planner")
    moved = pj[pj["ctb_status"].isin(["At risk", "Late"])]
    for p in moved.itertuples():
        add("Production", f"Sequence change {p.project_id}",
            f"Build moves from {p.planned_build_start:%d %b} to {p.forecast_build_start:%d %b} ({p.gating_item})",
            "Re-plan bay and crew; check for overlaps with other builds", p.project_id, "Production planner")
    for x in r.cm.plan[(r.cm.plan["load_pct"] > 100)].itertuples():
        add("Production", f"CM overload {x.name}", f"{x.load_pct:.0f}% of capacity in {x.month:%b %Y}",
            "Pull work forward or into the next month", x.cm_id, "CM manager")

    # Engineering
    for p in pj[pj["ctb_status"].isin(["Late", "At risk"])].itertuples():
        if p.gating_item:
            add("Engineering", f"Substitute for {p.gating_item}?",
                f"Gating part for {p.project_id} ({p.customer}), {p.ctb_status.lower()}",
                "Is an approved alternate part acceptable?", p.gating_item, "Engineering")
    ex = r.ctb.excess
    for x in ex[ex["no_demand"]].itertuples() if len(ex) else []:
        add("Engineering", f"Disposition of {x.item_id}", f"{x.description}: {cur}{x.excess_value:,.0f} on hand, no demand",
            "Use in a future design, sell as spares, return or scrap", x.item_id, "Engineering")
    dp = r.risk.dual_plan
    for x in dp[dp["plan_status"].isin(["In qualification", "Candidate found", "Overdue"])].itertuples() if len(dp) else []:
        add("Engineering", f"Second source for {x.item_id}", f"{x.alternate}: {x.plan_status.lower()}"
            + (f", target {x.target_date:%d %b}" if pd.notna(x.target_date) else ""),
            "Engineering approval and first-article sign-off", x.item_id, "Engineering")
    ll = r.ctb.long_lead
    for x in ll[ll["status"].isin(["Order overdue", "Order now"])].itertuples() if len(ll) else []:
        add("Engineering", f"Early release {x.item_id} for {x.project_id}", f"{x.lead_time_days:.0f}-day part, order by {x.order_by:%d %b}",
            "Release the long-lead part from the BOM now", x.project_id, "Engineering")

    # Contracts (customer and supplier commercial)
    for p in pj[pj["ctb_status"] == "Late"].itertuples():
        add("Contracts", f"Customer date at risk: {p.project_id}",
            f"{p.customer}: can ship {p.forecast_ship:%d %b} vs {p.required_ship_date:%d %b} ({p.days_late} days late), "
            f"order value {cur}{p.sell_value:,.0f}", "Warn the customer; check penalty clauses; agree a recovery date",
            p.project_id, "Contracts")
    for p in pj[(pj["ctb_status"] == "At risk") & (pj["float_days"] <= 7)].itertuples():
        add("Contracts", f"Low float: {p.project_id}", f"{p.customer}: {p.float_days} days of float left",
            "Prepare the customer conversation if the gating part slips", p.project_id, "Contracts")
    sc = r.suppliers.scorecard
    for x in sc[(sc["receipt_lines"] > 0) & (sc["ppv_pct"] >= 3)].itertuples() if len(sc) else []:
        add("Contracts", f"Supplier price review: {x.name}", f"PPV {x.ppv_pct:+.1f}% ({cur}{x.ppv:,.0f}) over 12 months",
            "Check prices against the contract; plan the renegotiation", x.supplier_id, "Buyer")

    # Finance
    k = r.inventory.kpis
    add("Finance", "Year-end inventory landing",
        f"{cur}{k['year_end']:,.0f} vs target {cur}{k['year_end_target']:,.0f} (gap {cur}{k['year_end_gap']:,.0f}); "
        f"levers {cur}{k['push_out_value'] + k['excess_value']:,.0f}", "Agree the number to commit to", "", "Materials manager")
    c = r.cost.kpis
    if c["target"]:
        add("Finance", "Cost reduction", f"Realized {cur}{c['realized']:,.0f} of {cur}{c['target']:,.0f} target; "
            f"weighted pipeline {cur}{c['weighted_pipeline']:,.0f}", "Confirm savings to book this quarter", "", "Materials manager")
    S = r.summary()
    add("Finance", "Purchase price variance", f"{cur}{S['ppv']:,.0f} ({S['ppv_pct']:+.1f}%) over 12 months",
        "Standard-cost update at the next cost roll?", "", "Materials manager")
    if r.risk.kpis["ss_value_change"]:
        add("Finance", "Safety-stock changes", f"Recommended changes add {cur}{r.risk.kpis['ss_value_change']:,.0f} of inventory",
            "Approve the safety-stock policy change", "", "Inventory control")

    # Shop floor (Tier 2): the SQDCC letters, misses without a countermeasure, and kits short for the next builds
    sf = getattr(r, "shop", None)
    if sf is not None:
        reds = sf.tier[sf.tier["status"].isin(["Red", "Amber"])]
        if len(reds):
            add("Production", "SQDCC board", "; ".join(f"{x.tier} {x.status.lower()}" for x in reds.itertuples()),
                "Agree the countermeasure and owner for each red letter", "", "Production supervisor")
        for x in sf.misses[sf.misses["countermeasure"] == ""].itertuples():
            add("Production", f"Miss without a countermeasure: {x.metric}" + (f" {x.wc_id}" if x.wc_id else ""),
                x.miss + (f" ({x.detail})" if x.detail else ""), "Name the countermeasure, owner and date", x.wc_id,
                "Production supervisor")
        for pid, g in sf.kits.groupby("project_id") if len(sf.kits) else []:
            add("Production", f"Kit short: {pid}", ", ".join(f"{x.item_id} due {pd.Timestamp(x.supply_date):%d %b}"
                                                           for x in g.itertuples()),
                "Kit what is here; confirm the build start", pid, "Planner")

    # Project financials: billing and cash for finance, changes and collections for contracts, submittals for engineering
    fi = getattr(r, "financials", None)
    if fi is not None:
        k = fi.kpis
        add("Finance", "Project billing this fiscal year",
            f"{cur}{k['billing_fy_forecast']:,.0f} forecast vs {cur}{k['billing_fy_planned']:,.0f} planned; "
            f"{cur}{k['billing_at_risk_fy']:,.0f} moving into next year", "Update the revenue and cash forecast", "", "Project controller")
        add("Finance", "Unbilled revenue and receivables",
            f"Unbilled {cur}{k['unbilled']:,.0f}; billings in excess {cur}{k['billings_in_excess']:,.0f}; receivables "
            f"{cur}{k['ar_open']:,.0f} ({cur}{k['ar_overdue']:,.0f} overdue, DSO {k['dso']:.0f} days)",
            "Agree the month-end revenue recognition and collection actions", "", "Project controller")
        for x in fi.milestones[fi.milestones["status"] == "Due, not invoiced"].itertuples():
            add("Finance", f"Invoice not raised: {x.project_id} {x.milestone_id}", f"{x.name}, {cur}{x.amount:,.0f}, reached {x.forecast_date:%d %b}",
                "Raise the invoice today", x.project_id, "Project controller")
        for x in fi.projects[fi.projects["margin_fade_pts"] >= s.margin_fade_alert_pts].itertuples():
            add("Finance", f"Margin fade: {x.project_id}", f"{x.margin_sold_pct:.1f}% as sold, {x.margin_forecast_pct:.1f}% forecast",
                "Accept the new EAC or agree recovery actions", x.project_id, "Project controller")
        for x in fi.receivables[fi.receivables["days_overdue"] > 30].itertuples():
            add("Contracts", f"Overdue invoice {x.invoice_no}", f"{x.customer}: {cur}{x.billed:,.0f}, {x.days_overdue} days overdue",
                "Escalate with the customer; resolve any dispute", x.project_id, "Project controller")
        co = fi.change_orders
        for x in co[co["status"] == "Pending"].itertuples():
            add("Contracts", f"Change order {x.co_id}", f"{x.description}: {cur}{x.price_change:,.0f}, waiting {x.age_days:.0f} days",
                "Get the customer's decision before the work starts", x.project_id, "Project controller")
        sb = fi.submittals
        for x in sb[sb["overdue"] | sb["blocked"]].itertuples():
            add("Engineering", f"Submittal {x.submittal_id}", f"{x.document} ({x.party}): " + ("resubmit" if x.blocked else f"{x.days_late:.0f} days overdue"),
                "Resubmit or agree the review date" + ("; it holds a billing milestone" if x.holds.startswith("M") else ""),
                x.project_id, "Engineering")

    # Suppliers and CMs: the ten most important supplier and CM alerts
    sup_al = r.alerts[(r.alerts["area"].isin(["Suppliers", "Contract manufacturers", "Supply risk"])) & (r.alerts["severity"] != "Info")]
    for x in sup_al.drop_duplicates("ref").head(10).itertuples():
        add("Suppliers and CMs", x.ref, x.message, x.action, x.ref, x.owner)

    # Materials team
    tm = r.team
    if tm is not None and len(tm.people):
        for p in tm.people.itertuples():
            if p.overdue_actions or (p.score_pct == p.score_pct and p.score_pct < 70):
                add("Materials team", f"{p.name} ({p.role})", f"KPIs met {p.kpis_met} of {p.kpis_with_target}; "
                    f"{p.overdue_actions} overdue actions; {p.open_alerts} open alerts", "Support needed? Re-prioritize?",
                    p.person_id, "Materials manager")
    return pd.DataFrame(rows, columns=AGENDA_COLS).drop_duplicates(["stakeholder", "topic"]).reset_index(drop=True)


def run_meetings(r) -> MeetingResult:
    acts = prepare_actions(r.data.actions, r.settings.as_of_date)
    team = dict(zip(r.data.team["person_id"], r.data.team["name"], strict=False)) if len(r.data.team) else {}
    if len(acts):
        acts["owner_name"] = acts["owner"].map(team).astype(object).fillna(acts["owner"])
    kpis = dict(open=int((acts["status"].str.lower() != "done").sum()) if len(acts) else 0,
                overdue=int(acts["overdue"].sum()) if len(acts) else 0,
                done=int((acts["status"].str.lower() == "done").sum()) if len(acts) else 0)
    return MeetingResult(pd.DataFrame(columns=AGENDA_COLS), acts, kpis)


def alerts_to_actions(alerts: pd.DataFrame, existing: pd.DataFrame, asof, owner_of: pd.Series | None = None,
                      days: int = 7) -> pd.DataFrame:
    """Turn selected alerts into new open actions, skipping alerts already in the log (same ref and message)."""
    stake = {"Clear to build": "Production", "Inventory": "Finance", "Contract manufacturers": "Suppliers and CMs",
             "Suppliers": "Suppliers and CMs", "Team": "Materials team", "Supply risk": "Suppliers and CMs",
             "Cost": "Finance", "Actions": "Materials team"}
    have = set(existing["notes"]) if len(existing) else set()
    nums = pd.to_numeric(existing["action_id"].str.extract(r"(\d+)$")[0], errors="coerce") if len(existing) else pd.Series(dtype=float)
    n = int(nums.max()) if len(nums.dropna()) else 100
    rows = []
    t = pd.Timestamp(asof)
    for a in alerts.itertuples():
        tag = f"from alert: {a.message[:60]}"
        if tag in have:
            continue
        n += 1
        rows.append(dict(action_id=f"A-{n}", opened=t, stakeholder=stake.get(a.area, "Materials team"),
                         owner=(owner_of.get(a.alert_id, "") if owner_of is not None else ""), ref=str(a.ref),
                         action=a.action, due=t + timedelta(days=days), status="Open", closed=pd.NaT, notes=tag))
    new = pd.DataFrame(rows, columns=list(existing.columns) if len(existing.columns) else None)
    base = existing[[c for c in existing.columns if c in new.columns]] if len(existing) else existing
    if not len(base):
        return new
    if not len(new):
        return base.reset_index(drop=True)
    out = pd.concat([base, new.dropna(axis=1, how="all")], ignore_index=True)   # all-empty columns (closed) stay typed
    return out[list(base.columns)]
