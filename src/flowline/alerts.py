"""One prioritized action list across clear-to-build, inventory, contract manufacturers and suppliers."""

from __future__ import annotations

import numpy as np
import pandas as pd

COLUMNS = ["severity", "area", "ref", "due", "message", "action", "owner", "value"]
SEVERITY_ORDER = {"Critical": 0, "Warning": 1, "Info": 2}


def build_alerts(r) -> pd.DataFrame:   # r: engine.Result
    s = r.settings
    cur = s.currency
    a: list[dict] = []

    def add(sev, area, ref, due, msg, act, owner, value=0.0):
        a.append(dict(zip(COLUMNS, [sev, area, ref, due, msg, act, owner, float(value or 0)], strict=True)))

    # ---- Clear to build
    pj = r.ctb.projects
    for p in pj.itertuples():
        if p.ctb_status == "Late":
            add("Critical", "Clear to build", p.project_id, p.planned_build_start,
                f"{p.project_id} {p.customer}: material complete {p.material_ready:%d %b}, can ship {p.forecast_ship:%d %b}, "
                f"{p.days_late} days after the customer date ({p.required_ship_date:%d %b}). Gating part: {p.gating_item}.",
                "Expedite the gating part, look for a substitute or a part from a later project, or agree a new date with the customer.",
                "Materials manager", p.sell_value)
        elif p.ctb_status == "At risk":
            add("Warning", "Clear to build", p.project_id, p.planned_build_start,
                f"{p.project_id} {p.customer}: build start slips {(p.forecast_build_start - p.planned_build_start).days} days "
                f"(gating part {p.gating_item}); still ships on time with {p.float_days} days float.",
                "Expedite the gating part and re-sequence the build schedule.", "Planner", p.sell_value)
        elif p.ctb_status in ("In build", "Built") and p.days_late > 0:
            add("Warning", "Clear to build", p.project_id, p.forecast_finish,
                f"{p.project_id} {p.customer}: build finishes {p.days_late} days after the customer date.",
                "Confirm the ship date with the customer.", "Planner", p.sell_value)
    ll = r.ctb.long_lead
    for x in ll[ll["status"].isin(["Order overdue", "Order now"])].itertuples():
        sev = "Critical" if x.status == "Order overdue" else "Warning"
        when = f"should have been ordered by {x.order_by:%d %b}" if x.status == "Order overdue" else f"order by {x.order_by:%d %b}"
        add(sev, "Clear to build", f"{x.project_id} {x.item_id}", x.order_by,
            f"Long-lead part {x.item_id} {x.description} ({x.lead_time_days:.0f} days) for {x.project_id}: "
            f"{x.short_qty:,.0f} not on order, {when}.",
            "Place the order now and ask the supplier for its best date.", "Buyer")
    sh = r.ctb.shortages
    if len(sh):
        hit = set(pj.loc[pj["ctb_status"].isin(["At risk", "Late"]), "project_id"])
        lead = sh[(sh["issue"] == "Late supply") & (sh["days_late"] > 0) & sh["project_id"].isin(hit)]
        for (item, sup), g in lead.groupby(["item_id", "supplier"]):
            add("Warning", "Clear to build", item, g["need_date"].min(),
                f"{item}: supply for {g['project_id'].nunique()} project(s) arrives up to {g['days_late'].max()} days after it is needed.",
                f"Expedite with {sup or 'the supplier'}; confirm dates in writing.", "Buyer", g["value_at_risk"].sum())

    # ---- PO exceptions
    pa = r.ctb.po_actions
    if len(pa):
        pd_ = pa[pa["past_due"]]
        for sup, g in pd_.groupby("supplier"):
            add("Warning", "Suppliers", sup, s.as_of_date,
                f"{sup}: {len(g)} past-due PO line(s) worth {cur}{g['value'].sum():,.0f}.",
                "Get a confirmed ship date for each line; update the promise date in the ERP.", "Buyer", g["value"].sum())
        po = pa[pa["year_end_impact"] > 0]
        if len(po):
            add("Warning", "Inventory", f"{len(po)} PO lines", s.year_end,
                f"{len(po)} PO line(s) arrive before year end but are not needed until after it, or not at all "
                f"({cur}{po['year_end_impact'].sum():,.0f} of year-end inventory).",
                "Ask the suppliers to push out or cancel; see the Push out / Cancel list.", "Buyer", po["year_end_impact"].sum())

    # ---- Inventory landing
    k = r.inventory.kpis
    if not np.isnan(k["year_end_gap"]) and k["year_end_gap"] > 0:
        add("Critical" if k["year_end_gap"] > 0.05 * k["year_end_target"] else "Warning", "Inventory", "Year-end landing",
            s.year_end,
            f"Year-end inventory projected at {cur}{k['year_end']:,.0f}, {cur}{k['year_end_gap']:,.0f} over the "
            f"{cur}{k['year_end_target']:,.0f} target (turns {k['turns_year_end']:.1f} vs {s.turns_target:.1f}).",
            f"Work the levers list: push-outs and cancellations ({cur}{k['push_out_value']:,.0f}) and excess "
            f"({cur}{k['excess_value']:,.0f}).", "Materials manager", k["year_end_gap"])
    for row in r.inventory.landing.itertuples():
        if row.stock_type != "Total" and not np.isnan(row.gap) and row.gap > 0 and row.target:
            add("Info", "Inventory", row.stock_type, s.year_end,
                f"{row.stock_type}: year-end {cur}{row.year_end:,.0f} vs target {cur}{row.target:,.0f}.",
                "Review the drivers in the Inventory tab.", "Materials manager", row.gap)
    ex = r.ctb.excess
    big = ex[(ex["excess_value"] >= 25_000) | ex["no_demand"]] if len(ex) else ex
    for x in big.itertuples():
        if x.excess_value <= 0:
            continue
        add("Info" if not x.no_demand else "Warning", "Inventory", x.item_id, None,
            f"{x.item_id} {x.description}: {cur}{x.excess_value:,.0f} on hand that no open project needs"
            + (" (no demand at all)." if x.no_demand else "."),
            "Check upcoming quotes; return to supplier, use as spares, or reserve for E&O.", "Planner", x.excess_value)

    # ---- Contract manufacturers
    cm = r.cm
    for p in cm.plan.itertuples():
        if p.capacity_hours and not np.isnan(p.capacity_hours) and p.load_pct > 100:
            add("Critical" if p.in_commit_window else "Warning", "Contract manufacturers", p.cm_id, p.month,
                f"{p.name or p.cm_id} is loaded at {p.load_pct:.0f}% of capacity in {p.month:%b %Y} "
                f"({p.demand_now_hours:,.0f} of {p.capacity_hours:,.0f} hours).",
                "Level the load: pull work into earlier months, split with a second source, or ask for overtime.",
                "CM manager")
        if p.in_commit_window and p.forecast_hours > 0 and p.commit_pct < 95:
            add("Warning", "Contract manufacturers", p.cm_id, p.month,
                f"{p.name or p.cm_id} has committed {p.commit_pct:.0f}% of the forecast for {p.month:%b %Y}.",
                "Get the gap confirmed or escalate at the weekly CM call.", "CM manager")
    for x in cm.performance.itertuples():
        if not np.isnan(x.forecast_change_pct) and abs(x.forecast_change_pct) >= s.cm_forecast_change_pct:
            add("Warning", "Contract manufacturers", x.cm_id, s.as_of_date,
                f"{x.name}: demand has changed {x.forecast_change_pct:+.0f}% since the last forecast was sent"
                + (f" ({x.last_forecast_sent:%d %b})." if pd.notna(x.last_forecast_sent) else "."),
                "Send an updated forecast now.", "Planner")
        if not np.isnan(x.otd_pct) and x.otd_pct < s.otd_target_pct:
            add("Warning", "Contract manufacturers", x.cm_id, None,
                f"{x.name}: on-time delivery {x.otd_pct:.0f}% over {s.history_months} months (target {s.otd_target_pct:.0f}%).",
                "Agree a recovery plan with dates; review at the monthly business review.", "CM manager")

    # ---- Suppliers
    sc = r.suppliers.scorecard
    if len(sc):
        for x in sc[(sc["supplier_type"].str.lower() != "cm") & (sc["receipt_lines"] > 0)].itertuples():
            if x.otd_pct < s.otd_target_pct - 15:
                add("Warning", "Suppliers", x.supplier_id, None,
                    f"{x.name}: on-time delivery {x.otd_pct:.0f}% (grade {x.grade}); {x.open_po_lines} open lines.",
                    "Escalate: ask for a recovery plan, add buffer lead time for open projects.", "Buyer")
            if x.ppv_pct >= 3:
                add("Info", "Suppliers", x.supplier_id, None,
                    f"{x.name}: purchase price variance +{x.ppv_pct:.1f}% ({cur}{x.ppv:,.0f}) over 12 months.",
                    "Review prices against the contract; update standard cost at the next cost roll if it is lasting.",
                    "Buyer", x.ppv)
    so = r.suppliers.sourcing
    if len(so):
        for x in so[(so["risk_level"] == "High")].itertuples():
            add("Warning" if x.dual_status == "None identified" else "Info", "Suppliers", x.item_id, x.target_date,
                f"Single-source risk: {x.item_id} {x.description} from {x.supplier} ({x.lead_time_days:.0f} days lead, "
                f"{x.projects_exposed} open projects). Dual sourcing: {x.dual_status.lower()}"
                + (f", {x.alternate}" if x.alternate else "") + ".",
                "Start or speed up qualification of a second source; hold a strategic buffer meanwhile.",
                "Materials manager", x.spend_12m)

    # ---- Supply risk and safety stock
    rk = getattr(r, "risk", None)
    if rk is not None:
        reg = rk.register
        for x in reg[(reg["level"] == "High") & (reg["source"] == "Register") & (reg["status"].str.lower() != "closed")].itertuples():
            add("Warning", "Supply risk", x.risk_id, x.due, f"High risk ({x.score:.0f}): {x.risk}.",
                f"Mitigation: {x.mitigation or 'none recorded'}. Review progress.", "Materials manager")
        ss = rk.safety_stock
        low = ss[ss["recommendation"].isin(["Raise", "Set safety stock"]) & (ss["current_ss"] < 0.5 * ss["recommended_ss"])] if len(ss) else ss
        if len(low):
            top3 = ", ".join(f"{x.item_id} {x.current_ss:,.0f} to {x.recommended_ss:,.0f}" for x in low.head(3).itertuples())
            add("Warning", "Supply risk", f"{len(low)} parts", None,
                f"{len(low)} repeat part(s) hold less than half the safety stock needed for {s.service_level_pct:.0f}% "
                f"service ({cur}{low['change_value'].sum():,.0f} to add). Largest: {top3}.",
                "Review and raise safety stock in SAP (MARC-EISBE); see Supply risk tab.", "Inventory control",
                low["change_value"].sum())
        lo = ss[ss["recommendation"] == "Lower"] if len(ss) else ss
        if len(lo):
            add("Info", "Supply risk", f"{len(lo)} parts", None,
                f"{len(lo)} repeat part(s) carry more safety stock than needed ({cur}{-lo['change_value'].sum():,.0f}).",
                "Lower safety stock to the recommended level.", "Inventory control", -lo["change_value"].sum())
        for x in rk.logistics[rk.logistics["otd_pct"] < s.lsp_otd_target_pct - 5].itertuples() if len(rk.logistics) else []:
            add("Info", "Supply risk", x.lsp, None, f"Logistics provider {x.lsp}: on time {x.otd_pct:.0f}% ({x.shipments} shipments).",
                "Review the lanes at the next carrier review.", "Buyer")
        dp = rk.dual_plan
        for x in dp[dp["plan_status"] == "Overdue"].itertuples() if len(dp) else []:
            add("Warning", "Supply risk", x.item_id, x.target_date,
                f"Second-source qualification for {x.item_id} is past its target date ({x.alternate}).",
                "Escalate the qualification with Engineering and Quality.", "Materials manager")

    # ---- Cost reduction
    co = getattr(r, "cost", None)
    if co is not None:
        for x in co.pipeline[co.pipeline["overdue"]].itertuples():
            add("Info", "Cost", x.project_id, x.target_date,
                f"Savings project {x.project_id} '{x.title}' is past its target date ({x.stage.lower()}).",
                "Update the plan or re-forecast the savings.", "Buyer", x.annual_savings)
        k2 = co.kpis
        if k2["target"] and k2["realized"] < 0.9 * k2["target_to_date"]:
            add("Warning", "Cost", "Savings target", s.year_end,
                f"Savings realized {cur}{k2['realized']:,.0f} vs {cur}{k2['target_to_date']:,.0f} expected by now "
                f"(annual target {cur}{k2['target']:,.0f}).",
                "Move validated projects into implementation; pick up the opportunities list.", "Materials manager",
                k2["target_to_date"] - k2["realized"])

    # ---- Shop floor: blocked shipments, safety, cells behind plan, quality, single points of failure, ERP hygiene
    sf = getattr(r, "shop", None)
    if sf is not None:
        tdy = sf.today.date()
        if len(sf.safety):
            for x in sf.safety[(sf.safety["date"] == sf.today) & sf.safety["type"].isin(["Recordable", "Lost time", "First aid"])].itertuples():
                add("Critical", "Shop floor", x.wc_id, tdy, f"{x.type} today at {x.wc_id}: {x.description}.",
                    "Make the area safe, report it, and agree the countermeasure at Tier 1.", "Production supervisor")
        erp = sf.erp
        if len(erp):
            for x in erp[erp["kind"].str.contains("Completion", case=False, na=False) & (erp["value"] > 0)].itertuples():
                add("Critical" if x.overdue else "Warning", "Shop floor", x.ref, tdy,
                    f"{x.project_id}: production order completion not posted for {x.age_days} days ({cur}{x.value:,.0f}). {x.note}.",
                    "Post the final confirmation today (SAP CO11N) so finished goods can be received and shipped.",
                    "Production supervisor", x.value)
            rest = erp[erp["overdue"] & ~erp["kind"].str.contains("Completion", case=False, na=False)]
            if len(rest):
                add("Warning", "Shop floor", "ERP", tdy, f"{len(rest)} ERP items older than {s.erp_max_age_days} days: "
                    + ", ".join(f"{x.kind.lower()} {x.ref}" for x in rest.itertuples()) + ".",
                    "Clear them before the end of the shift (COGI, MI07, scrap and order closing).", "Production supervisor",
                    rest["value"].sum())
        for x in sf.plan[sf.plan["status"] == "Red"].itertuples():
            add("Warning", "Shop floor", x.wc_id, tdy, f"{x.work_center} is at {x.attainment_pct:.0f}% of plan at "
                f"{int(sf.now_hour)}:00" + (f" ({x.downtime_reason.lower()})" if x.downtime_reason else "")
                + (f", {x.people_short:.0f} person short" if x.people_short else "") + ".",
                "Recover in the shift (move people, overtime) or re-plan; log the countermeasure.", "Production supervisor")
        if len(sf.coverage):
            for x in sf.coverage[sf.coverage["qualified"] < s.skills_min_qualified].itertuples():
                add("Warning", "Shop floor", x.wc_id, None, f"{x.work_center} ({x.shift.lower()} shift) has {x.qualified} qualified "
                    f"person: one absence stops the station.", "Cross-train a second person (see the training plan).",
                    "Production supervisor")

    # ---- Weekly capacity: orders the machines and people cannot finish by the customer date
    cp = getattr(r, "capacity", None)
    if cp is not None and len(cp.orders):
        adv = cp.advice
        fix = ("; ".join(f"{x.work_center}: {x.detail} a week" for x in adv.itertuples())
               if adv is not None and len(adv) else "")
        for x in cp.orders[(cp.orders["status"] == "Late") & (cp.orders["held_by"] != "MATERIAL")].itertuples():
            add("Warning", "Weekly capacity", x.order_id, x.due.date() if pd.notna(x.due) else None,
                f"{x.order_id} ({x.project_id}, {x.qty:g} units) finishes {x.days_late:.0f} days after the customer date: "
                f"held back by {x.held_by_name}.",
                ("Overtime that brings it back: " + fix + "." if fix else "Re-sequence, split the order, or add capacity."),
                "Production supervisor")

    # ---- Value stream: the biggest wait is the first place to improve flow
    v = getattr(r, "vsm", None)
    if v is not None and v.kpis.get("biggest_wait"):
        k = v.kpis
        row = v.steps[v.steps["name"] == k["biggest_wait"]].iloc[0]
        tgt = v.future.loc[row.name, "target_days"]
        how = {"Raw materials": "Buy closer to the need date: lower the raw cover, use call-offs and push out early POs.",
               "WIP": "Kit closer to the build start and finish one lineup before kitting the next; cut the time a kit waits.",
               "Semi-finished": "Balance fabrication with assembly so sections do not wait.",
               "Finished goods": "Plan the build finish to the ship date and ship complete lineups as soon as they pass test."}
        add("Warning" if row.days > tgt + 0.5 else "Info", "Value stream", f"{v.family}: {row['name']}", None,
            f"Value stream {v.family}: the biggest wait is {row['name']}, {row.days:.0f} of {k['lead_time_days']:.0f} days "
            f"lead time ({cur}{row.value:,.0f}); value-added {k['va_pct']:.0f}%."
            + (f" Target {tgt:.0f} days frees {cur}{(row.days - tgt) * v.daily_cogs:,.0f}." if row.days > tgt + 0.5 else ""),
            how.get(row.stock_type, "Start the flow improvement here."), "Materials manager", row.value)

    # ---- Project financials
    fi = getattr(r, "financials", None)
    if fi is not None:
        fp = fi.projects
        for x in fp[fp["margin_fade_pts"] >= s.margin_fade_alert_pts].itertuples():
            worst = fi.wbs[(fi.wbs["project_id"] == x.project_id)].sort_values("variance").iloc[0]
            add("Warning", "Project financials", x.project_id, None,
                f"{x.project_id} {x.customer}: forecast margin {x.margin_forecast_pct:.1f}% vs {x.margin_sold_pct:.1f}% as sold "
                f"({x.margin_fade_pts:.1f} points fade; EAC {cur}{x.eac:,.0f}). Largest overrun: {worst.cost_element} "
                f"({cur}{-worst.variance:,.0f}).",
                "Review the estimate to complete with the project manager; look for a change order or recovery.",
                "Project controller", x.contract * x.margin_fade_pts / 100)
        ms = fi.milestones
        for x in ms[ms["status"] == "Due, not invoiced"].itertuples() if len(ms) else []:
            add("Critical", "Project financials", x.project_id, x.forecast_date,
                f"{x.project_id} milestone {x.milestone_id} '{x.name}' ({cur}{x.amount:,.0f}) was reached on "
                f"{x.forecast_date:%d %b} but has not been invoiced.", "Raise the invoice today (SAP billing plan, VF01).",
                "Project controller", x.amount)
        late = ms[ms["planned_in_fy"] & ~ms["forecast_in_fy"] & (ms["status"] == "Planned")] if len(ms) else ms
        for x in late.itertuples() if len(late) else []:
            add("Warning", "Project financials", x.project_id, x.planned_date,
                f"{x.project_id} milestone '{x.name}' ({cur}{x.amount:,.0f}) moves from {x.planned_date:%d %b} to "
                f"{x.forecast_date:%d %b}: out of this fiscal year.",
                "Recover the date (see the gating part), or tell Finance the billing forecast changed.", "Project controller", x.amount)
        ar = fi.receivables
        for x in ar[ar["days_overdue"] > 30].itertuples() if len(ar) else []:
            add("Critical" if x.days_overdue > 60 else "Warning", "Project financials", x.project_id, x.due_date,
                f"Invoice {x.invoice_no} to {x.customer} ({cur}{x.billed:,.0f}) is {x.days_overdue} days overdue.",
                "Call the customer's accounts payable; check for a dispute or missing document.", "Project controller", x.billed)
        co = fi.change_orders
        for x in co[co["age_days"] > 30].itertuples() if len(co) else []:
            add("Warning", "Project financials", x.project_id, None,
                f"Change order {x.co_id} '{x.description}' ({cur}{x.price_change:,.0f}) has waited {x.age_days:.0f} days for the "
                f"customer's decision.", "Chase the decision; do not start the extra work without an approved change.",
                "Project controller", x.price_change)
        sb = fi.submittals
        for x in sb[sb["overdue"] | sb["blocked"]].itertuples() if len(sb) else []:
            what = "returned for resubmission" if x.blocked else f"{x.days_late:.0f} days overdue"
            hold = " It holds a billing milestone." if x.holds.startswith("M") else (" It holds a release." if x.holds else "")
            add("Warning", "Project financials", x.project_id, x.due,
                f"{x.direction} submittal {x.submittal_id} '{x.document}' ({x.party}) is {what}.{hold}",
                "Agree a date with the reviewer; escalate if it blocks billing or manufacturing.", "Project controller")

    # ---- Action log
    mt = getattr(r, "meetings", None)
    if mt is not None and len(mt.actions):
        for x in mt.actions[mt.actions["overdue"]].itertuples():
            add("Warning", "Actions", x.action_id, x.due,
                f"Action {x.action_id} overdue since {x.due:%d %b} ({x.stakeholder}): {x.action}",
                "Close it, or agree a new date at the weekly meeting.", "Materials manager")

    df = pd.DataFrame(a, columns=COLUMNS)
    df["_s"] = df["severity"].map(SEVERITY_ORDER)
    df["due"] = pd.to_datetime(df["due"], errors="coerce")
    df["_d"] = df["due"]
    df = df.sort_values(["_s", "_d", "value"], ascending=[True, True, False], na_position="last").drop(columns=["_s", "_d"])
    df.insert(0, "alert_id", [f"A{i:03d}" for i in range(1, len(df) + 1)])
    return df.reset_index(drop=True)
