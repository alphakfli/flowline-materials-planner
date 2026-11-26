"""Excel exports.

* ``excel_report``: a formatted workbook for people (summary, alerts and every view, with colors).
* ``powerquery_workbook``: the same data as plain Excel Tables (``tbl_alerts`` ...), one per sheet, with no
  title rows or merged cells, so Power Query / Power BI can load and refresh them directly.
"""

from __future__ import annotations

import io
from datetime import datetime

import numpy as np
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

from flowline.engine import Result
from flowline.reports.tables import output_tables

HEAD = PatternFill("solid", fgColor="1F3A5F")
WHITE = Font(bold=True, color="FFFFFF")
SEV_FILL = {"Critical": PatternFill("solid", fgColor="F6D5D5"), "Warning": PatternFill("solid", fgColor="FBEBC8"),
            "Info": PatternFill("solid", fgColor="DCE8F7")}
STATUS_FILL = {"Late": SEV_FILL["Critical"], "At risk": SEV_FILL["Warning"],
               "Clear to build": PatternFill("solid", fgColor="D8EFD8"), "Clear by start": PatternFill("solid", fgColor="E8F4E8")}
MONEY_HINTS = ("value", "cost", "spend", "ppv", "impact", "now", "year_end", "target", "gap", "cogs")


def _val(v):
    if v is None:
        return None
    if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
        return None
    if isinstance(v, pd.Timestamp):
        return None if pd.isna(v) else v.to_pydatetime()
    if v is pd.NaT:
        return None
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return None if np.isnan(v) else float(v)
    return v


def _write(ws, df: pd.DataFrame, start_row: int = 1):
    ws.append(list(df.columns)) if start_row == 1 else None
    for row in df.itertuples(index=False):
        ws.append([_val(v) for v in row])
    for j, col in enumerate(df.columns, start=1):
        letter = get_column_letter(j)
        sample = df[col].head(200).map(lambda v: len(str(v))) if len(df) else pd.Series([0])
        ws.column_dimensions[letter].width = min(70, max(10, len(str(col)) + 2, int(sample.quantile(.9)) + 2))
        kind = df[col].dtype
        fmt = None
        if pd.api.types.is_datetime64_any_dtype(kind):
            fmt = "yyyy-mm-dd"
        elif pd.api.types.is_float_dtype(kind):
            fmt = "0.0" if col.endswith(("_pct", "_days")) or col in ("score", "risk_score") else "#,##0"
            if any(h in col for h in MONEY_HINTS) and not col.endswith("_pct"):
                fmt = "#,##0"
        if fmt:
            for cell in ws[letter][1:]:
                cell.number_format = fmt


def _styled_sheet(wb, title, df, widths=None):
    ws = wb.create_sheet(title[:31])
    _write(ws, df)
    for c in ws[1]:
        c.font, c.fill = WHITE, HEAD
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for k, w in (widths or {}).items():
        if k in df.columns:
            ws.column_dimensions[get_column_letter(list(df.columns).index(k) + 1)].width = w
    ws.freeze_panes = "B2"
    if len(df):
        ws.auto_filter.ref = ws.dimensions
    return ws


def excel_report(r: Result) -> bytes:
    s, S, cur = r.settings, r.summary(), r.settings.currency
    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    ws["A1"] = f"FlowLine Materials Planner: {s.company}"
    ws["A1"].font = Font(bold=True, size=16)
    ws["A2"] = f"As of {s.as_of_date:%d %b %Y} · fiscal year end {s.year_end:%d %b %Y} · scenario: {r.scenario.name}"
    rows = [
        ("Clear to build", None),
        ("Open projects", S["projects_open"]), ("Clear to build or by start", S["projects_clear"]),
        ("At risk (start slips, still on time)", S["projects_at_risk"]), ("Late to customer date", S["projects_late"]),
        (f"Sell value of late projects ({cur})", S["late_value"]), ("Shortage and late-part lines", S["shortage_lines"]),
        ("Inventory and working capital", None),
        (f"Inventory now ({cur})", S["inventory_now"]), ("Turns now (trailing 12-month COGS)", S["turns_now"]),
        ("Days of inventory now", S["doi_now"]), (f"Year-end landing ({cur})", S["year_end"]),
        (f"Year-end target ({cur})", S["year_end_target"]), (f"Gap to target ({cur})", S["year_end_gap"]),
        ("Year-end turns (FY COGS / year-end inventory)", S["turns_year_end"]), ("Turns target", S["turns_target"]),
        (f"Push-out and cancel lever ({cur})", S["push_out_value"]), (f"Excess stock ({cur})", S["excess_value"]),
        ("Contract manufacturers and suppliers", None),
        ("CM commitment vs forecast, commit window (%)", S["cm_commit_pct"]), ("CM on-time delivery (%)", S["cm_otd_pct"]),
        ("Supplier on-time delivery (%)", S["supplier_otd_pct"]), (f"Purchase price variance, 12 months ({cur})", S["ppv"]),
        ("Single-source items", S["single_source_items"]),
        ("Team, risk and cost", None),
        ("Department KPIs on target", f"{S['dept_kpis_met']} of {S['dept_kpis']}"), ("Overdue actions", S["actions_overdue"]),
        ("High supply risks", S["risks_high"]), (f"Savings realized ({cur})", S["savings_realized"]),
        (f"Savings target ({cur})", S["savings_target"]), (f"Premium freight, 12 months ({cur})", S["premium_freight"]),
        ("Project financials", None),
        (f"Contract value ({cur})", S.get("fin_contract")), ("Margin as sold (%)", S.get("fin_margin_sold_pct")),
        ("Margin forecast (%)", S.get("fin_margin_forecast_pct")), (f"Unbilled revenue ({cur})", S.get("fin_unbilled")),
        (f"Receivables overdue ({cur})", S.get("fin_ar_overdue")), (f"Billing at risk this fiscal year ({cur})", S.get("fin_billing_at_risk_fy")),
        ("Shop floor", None), ("Schedule attainment today (%)", S.get("shop_attainment_pct")),
        ("First-pass yield today (%)", S.get("shop_fpy_pct")), ("Labour productivity today (%)", S.get("shop_productivity_pct")),
        (f"Completed work not posted ({cur})", S.get("shop_unposted_value")),
        ("Weekly capacity", None), ("Orders late on capacity", S.get("cap_late_capacity")),
        ("Orders late on material", S.get("cap_late_material")), ("Busiest resource", S.get("cap_bottleneck_name")),
        ("Value stream", None), ("Lead time (days)", S.get("vsm_lead_time_days")),
        ("Value-added (%)", S.get("vsm_va_pct")), ("Biggest wait", S.get("vsm_biggest_wait")),
        ("Alerts", None), ("Critical", S["alerts_critical"]), ("Warning", S["alerts_warning"]),
    ]
    for i, (k, v) in enumerate(rows, start=4):
        a = ws.cell(i, 1, k)
        if v is None:
            a.font = Font(bold=True, color="1F3A5F", size=12)
            continue
        b = ws.cell(i, 2, _val(v))
        if isinstance(v, float):
            b.number_format = "#,##0" if abs(v) >= 100 else "0.0"
    ws.column_dimensions["A"].width = 48
    ws.column_dimensions["B"].width = 18

    t = output_tables(r)
    wa = _styled_sheet(wb, "Alerts", t["alerts"][0], {"message": 90, "action": 60})
    for i, sev in enumerate(t["alerts"][0]["severity"], start=2):
        wa.cell(i, 2).fill = SEV_FILL.get(sev, PatternFill())
    wp = _styled_sheet(wb, "Clear to build", t["projects"][0])
    col = list(t["projects"][0].columns).index("ctb_status") + 1
    for i, st in enumerate(t["projects"][0]["ctb_status"], start=2):
        if st in STATUS_FILL:
            wp.cell(i, col).fill = STATUS_FILL[st]
    for name, title in [("shortages", "Shortages"), ("long_lead", "Long-lead parts"), ("po_actions", "PO actions"),
                        ("year_end_levers", "Year-end levers"), ("inventory_landing", "Inventory landing"),
                        ("excess", "Excess"), ("cm_plan", "CM plan"), ("cm_performance", "CM performance"),
                        ("supplier_scorecard", "Supplier scorecard"), ("sourcing", "Sourcing risk"),
                        ("risk_register", "Risk register"), ("safety_stock", "Safety stock"),
                        ("dual_sourcing_plan", "Dual-sourcing plan"), ("logistics_providers", "Logistics"),
                        ("savings_pipeline", "Savings pipeline"), ("cost_opportunities", "Cost opportunities"),
                        ("department_kpis", "Department KPIs"), ("team_summary", "Team"),
                        ("team_scorecards", "Team scorecards"), ("meeting_agenda", "Meeting agenda"),
                        ("action_log", "Action log"), ("project_financials", "Project financials"),
                        ("project_wbs", "Project WBS"), ("billing_milestones", "Billing milestones"),
                        ("receivables", "Receivables"), ("change_order_log", "Change orders"),
                        ("submittal_register", "Submittals"), ("vsm", "Value stream"),
                        ("tier_board", "Tier board"), ("shop_plan", "Shop plan"), ("misses", "Misses"),
                        ("skills_coverage", "Skills coverage"), ("erp_to_clear", "ERP to clear"), ("kits_short", "Kits short"),
                        ("capacity_orders", "Capacity plan"), ("resource_load", "Resource load")]:
        if name not in t:
            continue
        _styled_sheet(wb, title, t[name][0], {"message": 80, "detail": 70, "description": 40})
    # wide month view for people
    pr = r.inventory.projection.pivot_table(index="stock_type", columns="month", values="value", aggfunc="sum")
    pr = pr.reindex(["Raw materials", "Semi-finished", "WIP", "Finished goods"])
    pr.loc["Total"] = pr.sum()
    pr.columns = [f"{c:%b %Y}" for c in pr.columns]
    _styled_sheet(wb, "Inventory by month", pr.reset_index())
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def powerquery_workbook(r: Result) -> bytes:
    """One Excel Table per sheet, named tbl_<name>; an index sheet lists them. Built for Power Query refresh."""
    wb = Workbook()
    idx = wb.active
    idx.title = "index"
    idx.append(["table_name", "sheet", "rows", "description", "as_of_date", "generated_at", "scenario"])
    gen = datetime.now().replace(microsecond=0)
    tables = output_tables(r)
    for name, (df, desc) in tables.items():
        ws = wb.create_sheet(name[:31])
        df = df.copy()
        if df.columns.empty:
            df = pd.DataFrame({"empty": []})
        _write(ws, df)
        last = f"{get_column_letter(len(df.columns))}{max(len(df), 1) + 1}"
        if not len(df):
            ws.append([None] * len(df.columns))
        tab = Table(displayName=f"tbl_{name}", ref=f"A1:{last}")
        tab.tableStyleInfo = TableStyleInfo(name="TableStyleLight9", showRowStripes=True)
        ws.add_table(tab)
        idx.append([f"tbl_{name}", ws.title, len(df), desc, r.settings.as_of_date, gen, r.scenario.name])
    t = Table(displayName="tbl_index", ref=f"A1:G{len(tables) + 1}")
    t.tableStyleInfo = TableStyleInfo(name="TableStyleLight9", showRowStripes=True)
    idx.add_table(t)
    for col, w in zip("ABCDEFG", (28, 24, 8, 70, 12, 20, 16), strict=True):
        idx.column_dimensions[col].width = w
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
