"""Blank input template with one sheet per table and a README sheet that explains every column."""

from __future__ import annotations

import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from flowline.models import REQUIRED_COLUMNS, SCHEMA, Settings

HELP = {
    "items": ("Every part number: finished goods (FG, one per customer project), sub-assemblies (SFG) and bought or "
              "contract-manufactured parts (RM).", {
        "item_type": "RM, SFG or FG", "make_buy": "make, buy or cm (made for you by a contract manufacturer)",
        "std_cost": "Standard cost per unit (inventory is valued at this)", "lead_time_days": "Purchase lead time, or build time for make items",
        "supplier_id": "Primary supplier or CM", "buyer": "Buyer or planner code, shown on the shortage list for filtering",
        "on_hand": "Unrestricted stock today", "safety_stock": "Stock to keep; not counted as excess",
        "cm_hours_per_unit": "CM capacity hours per unit (cm items only)"}),
    "bom": ("Multi-level bill of materials. Each project's top item lists its sub-assemblies and parts.", {
        "qty_per": "Quantity of the component per one parent"}),
    "projects": ("Customer orders. Planned and Released projects are checked for material; In build and Built ones "
                 "are already in WIP or finished goods.", {
        "status": "Planned, Released, In build or Built", "planned_build_start": "Date the final build is planned to start",
        "build_days": "Calendar days from build start to ready to ship", "required_ship_date": "Customer date",
        "sell_value": "Order value (for prioritizing)", "priority": "Lower number = allocated first when start dates tie"}),
    "purchase_orders": ("Open PO lines and CM orders.", {
        "qty_open": "Quantity still to be received", "promised_date": "Supplier's confirmed date (the latest confirmation)",
        "project_id": "Optional: the project this line is reserved for (project stock / account assignment)"}),
    "receipts": ("Goods receipts for the last 12 months, for on-time delivery, quality and PPV.", {
        "qty_rejected": "Quantity rejected at incoming inspection", "unit_price": "Price paid", "std_cost": "Standard cost at receipt"}),
    "suppliers": ("Supplier and CM master.", {"supplier_type": "Supplier or CM"}),
    "item_sources": ("Approved and pending sources per part (source list).", {
        "status": "Approved, In qualification or Candidate", "target_date": "Date the second source should be approved",
        "quoted_price": "Optional: unit price quoted by this source, for cost opportunities"}),
    "cm_forecast": ("The last forecast sent to each CM and what they committed.", {
        "month": "YYYY-MM", "sent_date": "When the forecast was sent"}),
    "cm_capacity": ("CM capacity in hours per month.", {"month": "YYYY-MM"}),
    "inventory_history": ("Month-end inventory value by stock type and monthly COGS, closed months.", {
        "month": "YYYY-MM", "cogs": "Cost of goods sold in the month"}),
    "inventory_targets": ("Year-end inventory target by stock type (Raw materials, Semi-finished, WIP, Finished goods).", {}),
    "team": ("Your buyers, planners and inventory analysts. Scope ties each person to their part of the model.", {
        "role": "Buyer, Planner, Inventory analyst or Materials manager",
        "scope": "Buyer: the buyer code used in items.buyer. Planner: a product family. Others: All"}),
    "objectives": ("Targets for each person and for the department (owner = Department).", {
        "owner": "person_id, or Department", "kpi": "KPI key, e.g. supplier_otd_pct, ctb_pct, excess_value (see docs/logic.md)",
        "direction": "higher or lower (which way is better)"}),
    "kpi_history": ("Department KPIs for closed months, long format: one row per month and KPI.", {"month": "YYYY-MM"}),
    "actions": ("The running action log from the weekly meetings.", {
        "stakeholder": "Production, Engineering, Contracts, Finance, Suppliers and CMs, Materials team",
        "owner": "person_id from the team table", "status": "Open, In progress or Done"}),
    "consumption_history": ("Monthly consumption of repeat parts, for safety-stock recommendations.", {"month": "YYYY-MM"}),
    "risk_register": ("Supply risks you track. The app adds the risks it detects.", {
        "likelihood": "1 (rare) to 5 (almost certain)", "impact": "1 (minor) to 5 (severe)",
        "status": "Open, Mitigating or Closed"}),
    "shipments": ("Inbound shipments by logistics provider, last 12 months.", {
        "premium": "Y for expedited or premium freight", "reason": "Why it was expedited"}),
    "savings_projects": ("Cost-reduction projects.", {
        "category": "Alternative source, Negotiation, VA/VE, Consolidation, Packaging, Logistics",
        "stage": "Idea, Validated, In implementation or Realized", "annual_savings": "Expected savings per year",
        "realized_to_date": "Savings booked this fiscal year"}),
    "wbs_budget": ("Project cost by element: as sold (the bid) and the current budget. Turns on Project financials.", {
        "cost_element": "Material, Labour, Engineering, Freight, Commissioning or Contingency",
        "as_sold": "Cost in the bid", "budget": "Current approved budget (as sold plus approved changes)"}),
    "cost_actuals": ("Actual cost booked to date per project and element.", {
        "cost_to_date": "Actual cost posted", "etc_override": "Optional estimate to complete for non-material elements; "
        "blank uses budget minus actual. Material ETC comes from the material plan."}),
    "change_orders": ("Customer change orders.", {
        "price_change": "Change to the contract price", "cost_change": "Change to cost",
        "status": "Pending, Approved or Rejected", "submitted": "Date sent to the customer", "decided": "Date of decision"}),
    "billing_milestones": ("Billing plan per project and invoices raised.", {
        "trigger": "Order, Drawings approved, Build start, Material ready, Shipment, Commissioning or Date",
        "pct": "Percent of the contract", "planned_date": "Planned billing date",
        "invoice_no": "Blank until invoiced", "amount_invoiced": "Blank uses pct x contract", "paid_date": "Blank until paid"}),
    "submittals": ("Drawings and documents sent for approval (customer) or received for approval (supplier).", {
        "direction": "Customer or Supplier", "status": "Open, Approved, Approved as noted or Resubmit",
        "holds": "Billing milestone it holds (M2), 'release' for a supplier production release, or blank"}),
    "work_centers": ("Shop floor: work centres (cells or bays). Turns on the Shop floor tab with shop_schedule.", {
        "product_family": "Family or Both", "shift_hours": "Hours per shift", "shifts": "Shifts a day (1 or 2)",
        "people_needed": "People needed per shift"}),
    "shop_schedule": ("Daily build plan by work centre: one row per job or per work centre and day. Today's rows show "
                      "progress to the current hour; older rows give the trend.", {
        "planned_hours": "Standard hours planned for the day", "earned_hours": "Standard hours of work completed",
        "actual_hours": "Hours clocked by the people", "people_needed": "People the plan needs",
        "people_assigned": "People actually there", "overtime_hours": "Overtime hours (history)"}),
    "hourly_output": ("Today's output by hour: planned and earned standard hours per work centre.", {
        "hour": "Hour starting (7 = 07:00-08:00)"}),
    "downtime": ("Downtime events.", {"reason": "Waiting for material, Machine breakdown, Changeover, Waiting for drawings, "
                                               "Quality hold, No operator ...", "minutes": "Minutes lost"}),
    "quality_checks": ("Inspections and tests: units inspected and passed first time.", {"defect": "What failed"}),
    "safety_events": ("Safety events.", {"type": "Recordable, Lost time, First aid or Near miss"}),
    "operators": ("Production people.", {"shift": "Day or Evening", "home_wc": "Usual work centre"}),
    "skills": ("Skills matrix: one row per person and work centre.", {
        "level": "0 not trained, 1 in training, 2 can do it with help, 3 independent, 4 can train others"}),
    "erp_open_items": ("ERP items to clear: completions not posted, backflush errors, count variances, scrap, open orders.", {
        "kind": "Completion not posted, Backflush error, Count variance, Scrap not posted, Order past finish, Shipping labels",
        "created": "Date it appeared", "value": "Value at stake"}),
    "countermeasures": ("Tier 1 and 2 countermeasure log for missed goals.", {
        "tier": "Tier 1 or Tier 2", "metric": "Safety, Quality, Delivery, Cost or Cash", "status": "Open or Done"}),
    "resources": ("Weekly capacity: machines and labour pools. Turns on the Weekly capacity tab with routings and production_orders.", {
        "kind": "Machine or Labour", "wc_id": "Work centre", "units": "Number of machines, or people in the pool (per shift)",
        "shifts_per_day": "Shifts worked a day", "hours_per_shift": "Paid hours per shift", "days_per_week": "Working days",
        "efficiency_pct": "Share of the hours that produce: availability for machines, efficiency for people",
        "overtime_hours": "Extra hours a week for the whole pool"}),
    "routings": ("Steps per product family with machine and labour hours per unit.", {
        "seq": "Order of the steps", "machine_id": "Machine resource used (blank = none)", "machine_hours": "Machine hours per unit",
        "labour_id": "Labour pool used", "labour_hours": "Labour hours per unit",
        "lag_weeks": "Weeks a unit waits after the previous step (drying, curing, transfer)"}),
    "production_orders": ("Orders to plan: one per project (or more).", {
        "qty": "Units to make (sections, transformers ...)", "due_date": "Blank = the project's customer date",
        "priority": "1 = highest", "from_step": "First step still to do (for orders already in progress)"}),
    "capacity_calendar": ("Weeks with less capacity: holidays, shutdowns, maintenance.", {
        "week_start": "Monday of the week", "resource_id": "Resource, or ALL", "available_pct": "Share of normal capacity"}),
    "process_steps": ("Value stream map for one product family: its route in order, process steps and the stock points "
                      "between them. Turns on the Value stream tab.", {
        "product_family": "Family as in projects.product_family (set vsm_family in settings if there are several)",
        "seq": "Order along the flow (10, 20, 30 ...)", "kind": "Process or Stock",
        "name": "Step or stock point name", "stock_type": "Stock rows: Raw materials, Semi-finished, WIP or Finished goods",
        "cycle_time_hours": "Process rows: hours per unit", "changeover_hours": "Process rows: hours per changeover",
        "uptime_pct": "Process rows: % of time the step is available", "operators": "Process rows: people on the step",
        "target_days": "Stock rows: future-state days of stock (blank = today's)",
        "target_changeover_hours": "Process rows: future-state changeover (blank = today's)"}),
    "settings": ("Optional settings. Leave a value blank to use the default.", {}),
}


def template_bytes() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "README"
    ws["A1"] = "FlowLine Materials Planner: input template"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = "Fill one sheet per table. Required tables: items, bom, projects. Column names must match row 1 of each sheet."
    row = 4
    for t, cols in SCHEMA.items():
        desc, notes = HELP.get(t, ("", {}))
        ws.cell(row, 1, t).font = Font(bold=True, size=12)
        ws.cell(row, 2, desc)
        row += 1
        for c, kind in cols.items():
            req = c in REQUIRED_COLUMNS.get(t, [])
            ws.cell(row, 1, c)
            ws.cell(row, 2, {"str": "text", "num": "number", "date": "date (YYYY-MM-DD)", "month": "month (YYYY-MM)"}[kind])
            ws.cell(row, 3, "required" if req else "")
            ws.cell(row, 4, notes.get(c, ""))
            row += 1
        row += 1
    for col, w in zip("ABCD", (26, 60, 10, 70), strict=True):
        ws.column_dimensions[col].width = w
    fill = PatternFill("solid", fgColor="1F3A5F")
    for t, cols in SCHEMA.items():
        sh = wb.create_sheet(t)
        sh.append(list(cols))
        for cell in sh[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = fill
            cell.alignment = Alignment(horizontal="center")
            sh.column_dimensions[cell.column_letter].width = max(14, len(str(cell.value)) + 2)
        if t == "settings":
            for k, v in Settings().to_table().itertuples(index=False):
                sh.append([k, "" if k == "as_of_date" else str(v) if v is not None else ""])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
