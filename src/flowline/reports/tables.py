"""Tidy output tables shared by the Excel, Power Query and PDF exports."""

from __future__ import annotations

import pandas as pd

from flowline.engine import Result


def output_tables(r: Result) -> dict[str, tuple[pd.DataFrame, str]]:
    """name -> (table, description). Columns are snake_case, one fact per row, ISO dates."""
    c, inv, s = r.ctb, r.inventory, r.suppliers
    proj = c.projects.drop(columns=[], errors="ignore")
    t = {
        "alerts": (r.alerts, "Prioritized alerts with suggested action and owner"),
        "projects": (proj, "Clear-to-build status and forecast dates per customer project"),
        "shortages": (c.shortages, "Parts that are late or not on order, per project"),
        "long_lead": (c.long_lead, "Long-lead requirements with order-by dates"),
        "requirements": (c.requirements.drop(columns=["req_id"], errors="ignore"), "Full multi-level requirement and allocation detail"),
        "po_actions": (c.po_actions, "Exception message per open PO line (expedite, push out, cancel, reduce)"),
        "excess": (c.excess, "Stock and open orders that no open project needs"),
        "inventory_landing": (inv.landing, "Inventory now, year-end projection and target by stock type"),
        "inventory_by_month": (inv.projection, "Month-end inventory by stock type (actuals and projection), long format"),
        "cogs_by_month": (inv.cogs, "Cost of goods sold by month (actuals and projection)"),
        "inventory_events": (inv.events, "Every projected inventory movement"),
        "year_end_levers": (inv.levers, "Actions that would lower the year-end landing"),
        "cm_plan": (r.cm.plan, "CM hours by month: demand now, forecast sent, committed, capacity"),
        "cm_by_item": (r.cm.by_item, "CM quantities by item and month"),
        "cm_performance": (r.cm.performance, "CM delivery, quality, commitment and forecast change"),
        "supplier_scorecard": (s.scorecard, "Supplier OTD, quality, PPV, spend and score"),
        "supplier_otd_by_month": (s.monthly_otd, "On-time delivery % by supplier and month"),
        "sourcing": (s.sourcing, "Sources per bought item, single-source risk and dual-sourcing status"),
        "receipts_scored": (s.receipts, "Receipt lines with on-time flag and PPV"),
    }
    if r.risk is not None:
        t.update({
            "safety_stock": (r.risk.safety_stock, "Recommended vs current safety stock for repeat parts"),
            "risk_register": (r.risk.register, "Entered and detected supply risks, likelihood x impact"),
            "dual_sourcing_plan": (r.risk.dual_plan, "Single-source parts and their second-source plan"),
            "logistics_providers": (r.risk.logistics, "Logistics-provider OTD, cost and premium freight"),
        })
    if r.cost is not None:
        t.update({
            "savings_pipeline": (r.cost.pipeline, "Savings projects with stage, weighted and realized savings"),
            "savings_by_stage": (r.cost.by_stage, "Savings pipeline by stage"),
            "cost_opportunities": (r.cost.opportunities, "Cost-reduction opportunities found by the model"),
        })
    if r.team is not None:
        t.update({
            "department_kpis": (r.team.department, "Department KPIs now vs target"),
            "kpi_trend": (r.team.trend, "Department KPI history plus this month, long format"),
            "team_scorecards": (r.team.scorecards, "Person x KPI: value, target, met"),
            "team_summary": (r.team.people, "One row per person: KPIs met, actions, alerts"),
        })
    if getattr(r, "shop", None) is not None:
        f = r.shop
        tier = f.tier.drop(columns=["trend"])
        t.update({
            "shop_plan": (f.plan, "Today's build plan by work centre: planned, earned, clocked hours, people"),
            "tier_board": (tier, "SQDCC tier board: value, target, status per letter"),
            "shop_history": (f.history, "Daily attainment, productivity, overtime, first-pass yield, incidents"),
            "downtime_pareto": (f.downtime, "Downtime minutes by reason, last 7 working days"),
            "first_pass_yield": (f.fpy, "First-pass yield by work centre, today and 4 weeks"),
            "misses": (f.misses, "Today's misses and their countermeasures"),
            "countermeasure_log": (f.countermeasures, "Tier 1 and 2 countermeasure log"),
            "skills_matrix": (f.skills, "Operators x work centres, skill level 0-4"),
            "skills_coverage": (f.coverage, "Qualified people per work centre and shift"),
            "training_plan": (f.training, "Who to train where, with trainer and target date"),
            "erp_to_clear": (f.erp, "ERP items to clear, with age"),
            "kits_short": (f.kits, "Parts not in stock for builds starting soon"),
        })
    if getattr(r, "vsm", None) is not None:
        from flowline.vsm import vsm_table
        t["vsm"] = (vsm_table(r.vsm), f"Value stream map, {r.vsm.family}: current and future state per step")
    if getattr(r, "financials", None) is not None:
        f = r.financials
        t.update({
            "project_financials": (f.projects, "Contract, budget, actual, committed, ETC, EAC, margin and POC per project"),
            "project_wbs": (f.wbs, "Cost by project and cost element"),
            "billing_milestones": (f.milestones, "Billing milestones with forecast dates and status"),
            "receivables": (f.receivables, "Open invoices with aging"),
            "billing_by_month": (f.billing_by_month, "Planned and forecast billing and forecast cash by month"),
            "change_order_log": (f.change_orders, "Change orders with status and age"),
            "submittal_register": (f.submittals, "Customer and supplier submittals with overdue flags"),
        })
    if r.meetings is not None:
        t.update({
            "meeting_agenda": (r.meetings.agenda, "This week's agenda items by stakeholder"),
            "action_log": (r.meetings.actions, "Action log with overdue flags"),
        })
    out = {}
    for k, (df, desc) in t.items():
        df = df.copy()
        for col in df.columns:
            if df[col].dtype == object and len(df) and df[col].map(lambda v: hasattr(v, "year") and hasattr(v, "day")).any():
                df[col] = pd.to_datetime(df[col], errors="coerce")
        out[k] = (df.reset_index(drop=True), desc)
    return out
