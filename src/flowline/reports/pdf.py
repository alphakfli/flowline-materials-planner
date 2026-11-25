"""PDF export: a weekly materials review pack (landscape letter)."""

from __future__ import annotations

import io

import numpy as np
import pandas as pd
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing, Line, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from flowline.engine import Result, fmt_money

INK = colors.HexColor("#0B0B0B")
MUTED = colors.HexColor("#52514E")
ACCENT = colors.HexColor("#1F3A5F")
LINE = colors.HexColor("#E1E0D9")
SERIES = [colors.HexColor(h) for h in ("#2A78D6", "#EB6834", "#1BAF7A", "#EDA100")]
FILL = {"Critical": colors.HexColor("#F6D5D5"), "Warning": colors.HexColor("#FBEBC8"), "Info": colors.HexColor("#DCE8F7"),
        "Late": colors.HexColor("#F6D5D5"), "At risk": colors.HexColor("#FBEBC8"),
        "Clear to build": colors.HexColor("#D8EFD8"), "Clear by start": colors.HexColor("#E8F4E8")}

ss = getSampleStyleSheet()
H1 = ParagraphStyle("h1", parent=ss["Heading1"], fontName="Helvetica-Bold", fontSize=18, textColor=INK, spaceAfter=2)
H2 = ParagraphStyle("h2", parent=ss["Heading2"], fontName="Helvetica-Bold", fontSize=13, textColor=INK, spaceBefore=6, spaceAfter=4)
BODY = ParagraphStyle("b", parent=ss["BodyText"], fontName="Helvetica", fontSize=9, leading=12, textColor=INK)
SMALL = ParagraphStyle("s", parent=BODY, fontSize=7.5, leading=9.5, textColor=MUTED)
CELL = ParagraphStyle("c", parent=BODY, fontSize=7.5, leading=9.5)


def _t(rows, widths, fills=None, font=7.5):
    t = Table(rows, colWidths=[w * inch for w in widths], repeatRows=1)
    st = [("FONT", (0, 0), (-1, -1), "Helvetica", font), ("TEXTCOLOR", (0, 0), (-1, -1), INK),
          ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LINEBELOW", (0, 0), (-1, -1), .3, LINE),
          ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
          ("BACKGROUND", (0, 0), (-1, 0), ACCENT), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
          ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", font)]
    for (r, c), color in (fills or {}).items():
        st.append(("BACKGROUND", (c, r), (c, r), color))
    t.setStyle(TableStyle(st))
    return t


def _n(v, kind="n"):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "–"
    if kind == "pct":
        return f"{v:.0f}%"
    if kind == "x":
        return f"{v:.1f}"
    return f"{v:,.0f}"


def _d(v):
    return "" if v is None or v != v else f"{v:%d %b}"


def _kpis(items):
    cells = [[Paragraph(f"<font size=7.5 color='#52514E'>{k}</font><br/><font size=14><b>{v}</b></font>", BODY)
              for k, v in items]]
    t = Table(cells, colWidths=[10 * inch / len(items)] * len(items))
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), .5, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    return t


def _stacked(r: Result, width=10 * inch, height=2.3 * inch):
    p = r.inventory.projection
    piv = p.pivot_table(index="month", columns="stock_type", values="value", aggfunc="sum").fillna(0)
    piv = piv.tail(14)
    cols = [c for c in ("Raw materials", "Semi-finished", "WIP", "Finished goods") if c in piv]
    d = Drawing(width, height)
    bc = VerticalBarChart()
    bc.x, bc.y, bc.width, bc.height = 48, 30, width - 170, height - 45
    bc.data = [[float(v) / 1e6 for v in piv[c]] for c in cols]
    bc.categoryAxis.style = "stacked"
    bc.categoryAxis.categoryNames = [f"{m:%b %y}" for m in piv.index]
    bc.categoryAxis.labels.fontSize = 6.5
    bc.categoryAxis.labels.fontName = "Helvetica"
    bc.valueAxis.labels.fontSize = 7
    bc.valueAxis.labels.fontName = "Helvetica"
    bc.valueAxis.valueMin = 0
    bc.valueAxis.labelTextFormat = "%.1fM"
    bc.valueAxis.gridStrokeColor = LINE
    bc.valueAxis.visibleGrid = True
    bc.barSpacing = 0
    bc.groupSpacing = 6
    for i in range(len(cols)):
        bc.bars[i].fillColor = SERIES[i]
        bc.bars[i].strokeColor = colors.white
        bc.bars[i].strokeWidth = 0.6
    d.add(bc)
    tgt = r.inventory.kpis["year_end_target"]
    top = bc.valueAxis.valueMax if bc.valueAxis.valueMax else None
    if tgt and not np.isnan(tgt):
        bc.valueAxis.valueMax = max(float(piv[cols].sum(axis=1).max()) / 1e6 * 1.1, tgt / 1e6 * 1.1)
        top = bc.valueAxis.valueMax
        y = bc.y + bc.height * (tgt / 1e6) / top
        d.add(Line(bc.x, y, bc.x + bc.width, y, strokeColor=INK, strokeWidth=0.8, strokeDashArray=[3, 2]))
        d.add(String(bc.x + bc.width + 4, y - 2, f"Year-end target {fmt_money(tgt)}", fontSize=7, fontName="Helvetica",
                     fillColor=INK))
    for i, c in enumerate(cols):
        yy = height - 20 - i * 12
        d.add(Line(width - 110, yy + 3, width - 100, yy + 3, strokeColor=SERIES[i], strokeWidth=6))
        d.add(String(width - 95, yy, c, fontSize=7, fontName="Helvetica", fillColor=INK))
    return d


def pdf_report(r: Result) -> bytes:
    s, S, cur = r.settings, r.summary(), r.settings.currency
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(letter), leftMargin=.5 * inch, rightMargin=.5 * inch,
                            topMargin=.45 * inch, bottomMargin=.45 * inch, title="Materials review pack")
    el = []

    def header(title):
        el.append(Paragraph(title, H1))
        el.append(Paragraph(f"{s.company} · as of {s.as_of_date:%d %b %Y} · scenario: {r.scenario.name}", SMALL))
        el.append(Spacer(1, 6))

    # 1. Clear to build
    header("Materials review: clear to build")
    el.append(_kpis([("Open projects", S["projects_open"]), ("Clear (now or by start)", S["projects_clear"]),
                     ("At risk", S["projects_at_risk"]), ("Late to customer", S["projects_late"]),
                     ("Late project value", fmt_money(S["late_value"], cur)), ("Critical alerts", S["alerts_critical"])]))
    el.append(Spacer(1, 6))
    pj = r.ctb.projects
    rows = [["Project", "Customer", "Family", "Status", "Planned start", "Material ready", "Gating part", "Can ship",
             "Customer date", "Days late", "On hand %"]]
    fills = {}
    for i, p in enumerate(pj.itertuples(), start=1):
        rows.append([p.project_id, Paragraph(p.customer, CELL), p.product_family, p.ctb_status, _d(p.planned_build_start),
                     _d(p.material_ready), p.gating_item, _d(p.forecast_ship), _d(p.required_ship_date),
                     p.days_late or "", _n(p.on_hand_pct, "pct")])
        if p.ctb_status in FILL:
            fills[(i, 3)] = FILL[p.ctb_status]
    el.append(_t(rows, [.65, 2.0, .85, .9, .8, .85, 1.0, .75, .85, .6, .65], fills))
    ll = r.ctb.long_lead
    ll = ll[ll["status"] != "Covered"].head(12)
    if len(ll):
        el.append(Paragraph("Long-lead parts that need action", H2))
        rows = [["Project", "Part", "Description", "Lead days", "Need", "Order by", "Short qty", "Status", "Supplier"]]
        for x in ll.itertuples():
            rows.append([x.project_id, x.item_id, Paragraph(str(x.description), CELL), _n(x.lead_time_days), _d(x.need_date),
                         _d(x.order_by), _n(x.short_qty), x.status, x.supplier])
        el.append(_t(rows, [.7, 1.0, 2.6, .7, .7, .7, .7, 1.0, 1.9]))
    el.append(PageBreak())

    # 2. Inventory
    header("Inventory and working capital")
    k = r.inventory.kpis
    el.append(_kpis([("Inventory now", fmt_money(k["inventory_now"], cur)), ("Turns now", _n(k["turns_now"], "x")),
                     ("Days of inventory", _n(k["doi_now"])), ("Year-end landing", fmt_money(k["year_end"], cur)),
                     ("Target", fmt_money(k["year_end_target"], cur)), ("Gap", fmt_money(k["year_end_gap"], cur)),
                     ("Year-end turns", f"{_n(k['turns_year_end'], 'x')} vs {s.turns_target:.1f}")]))
    el.append(_stacked(r))
    rows = [["Stock type", f"Now ({cur})", f"Year end ({cur})", f"Target ({cur})", f"Gap ({cur})", "DOI now", "DOI year end"]]
    for x in r.inventory.landing.itertuples():
        rows.append([x.stock_type, _n(x.now), _n(x.year_end), _n(x.target), _n(x.gap), _n(x.doi_now), _n(x.doi_year_end)])
    el.append(_t(rows, [1.5, 1.1, 1.1, 1.1, 1.1, .8, .9]))
    lv = r.inventory.levers.head(8)
    if len(lv):
        el.append(Paragraph("Biggest levers on the year-end landing", H2))
        rows = [["Lever", "Ref", "Part", "Supplier", "Detail", f"Year-end impact ({cur})"]]
        for x in lv.itertuples():
            rows.append([x.lever, x.ref, x.item_id, x.supplier, Paragraph(x.detail, CELL), _n(x.year_end_impact)])
        el.append(_t(rows, [1.1, 1.2, 1.1, 1.6, 3.6, 1.3]))
    el.append(PageBreak())

    # 3. CMs and suppliers
    header("Contract manufacturers and suppliers")
    rows = [["CM", "Name", "OTD %", "Commit % (window)", "Peak load %", "Demand change vs forecast", "Open orders", "Late"]]
    for x in r.cm.performance.itertuples():
        rows.append([x.cm_id, x.name, _n(x.otd_pct, "pct"), _n(x.commit_pct_window, "pct"), _n(x.peak_load_pct, "pct"),
                     "–" if np.isnan(x.forecast_change_pct) else f"{x.forecast_change_pct:+.0f}%", x.open_orders, x.late_open_orders])
    el.append(_t(rows, [.7, 2.0, .7, 1.2, 1.0, 1.6, .9, .6]))
    el.append(Spacer(1, 6))
    sc = r.suppliers.scorecard
    sc = sc[sc["receipt_lines"] > 0].head(14)
    rows = [["Supplier", "Type", "Spend 12m", "OTD %", "Quality ppm", "PPV %", "Single-source items", "Open lines", "Score", "Grade"]]
    fills = {}
    for i, x in enumerate(sc.itertuples(), start=1):
        rows.append([x.name, x.supplier_type, _n(x.spend_12m), _n(x.otd_pct, "pct"), _n(x.quality_ppm),
                     "–" if np.isnan(x.ppv_pct) else f"{x.ppv_pct:+.1f}%", x.single_source_items, x.open_po_lines,
                     _n(x.score), x.grade])
        if x.grade == "C":
            fills[(i, 9)] = FILL["Critical"]
    el.append(_t(rows, [2.2, .7, 1.0, .7, .9, .7, 1.2, .8, .6, .6], fills))
    el.append(PageBreak())

    # 4. Team, risk and cost
    if r.team is not None:
        header("Team, supply risk and cost")
        rows = [["Person", "Role", "Scope", "KPIs met", "Open actions", "Overdue", "Open alerts"]]
        for x in r.team.people.itertuples():
            rows.append([x.name, x.role, x.scope, f"{x.kpis_met} of {x.kpis_with_target}", x.open_actions,
                         x.overdue_actions, x.open_alerts])
        el.append(_t(rows, [1.6, 1.4, 1.6, .9, .9, .8, .9]))
        reg = r.risk.register.head(8)
        el.append(Paragraph("Top supply risks", H2))
        rows = [["Risk", "Category", "L x I", "Mitigation"]]
        for x in reg.itertuples():
            rows.append([Paragraph(x.risk, CELL), x.category, f"{x.likelihood:.0f} x {x.impact:.0f} = {x.score:.0f}",
                         Paragraph(str(x.mitigation), CELL)])
        el.append(_t(rows, [4.0, 1.4, .9, 3.7]))
        c = r.cost.kpis
        el.append(Paragraph(f"Cost reduction: realized {fmt_money(c['realized'], cur)} of {fmt_money(c['target'], cur)} "
                            f"target (expected by now {fmt_money(c['target_to_date'], cur)}); weighted pipeline "
                            f"{fmt_money(c['weighted_pipeline'], cur)}; new opportunities {fmt_money(c['opportunity_value'], cur)}.", BODY))
        el.append(PageBreak())

    # 5. Value stream (one product family)
    v = getattr(r, "vsm", None)
    if v is not None:
        from flowline.reports.vsm_draw import shapes, supplier_note, to_drawing
        k, fk = v.kpis, v.future_kpis
        header(f"Value stream: {v.family}")
        el.append(Paragraph(f"Where our inventory days come from, for one product family ({v.family}). Lead time "
                            f"{k['lead_time_days']:,.0f} days: {k['wait_days']:,.0f} waiting, {k['process_days']:,.1f} process; "
                            f"value-added {k['va_pct']:,.0f}%. Takt {v.takt_hours:,.0f} h per unit. Biggest wait: "
                            f"<b>{k['biggest_wait']}</b> ({k['biggest_wait_days']:,.0f} days, "
                            f"{fmt_money(k['biggest_wait_value'], cur)}).", BODY))
        el.append(Spacer(1, 4))
        el.append(to_drawing(shapes(v, "current", cur, supplier_note(r.data)), 10 * inch))
        el.append(Paragraph(f"Future state with the targets in process_steps: lead time {fk['lead_time_days']:,.0f} days "
                            f"({fk['lead_time_change_days']:+,.0f}), working capital freed {fmt_money(fk['freed_value'], cur)}, "
                            f"value-added {fk['va_pct']:,.0f}%.", BODY))
        el.append(PageBreak())

    # 6. Alerts
    header("Action list")
    al = r.alerts.head(30)
    rows = [["#", "Severity", "Area", "Ref", "Message", "Action", "Owner"]]
    fills = {}
    for i, x in enumerate(al.itertuples(), start=1):
        rows.append([x.alert_id, x.severity, x.area, Paragraph(str(x.ref), CELL), Paragraph(x.message, CELL),
                     Paragraph(x.action, CELL), x.owner])
        fills[(i, 1)] = FILL.get(x.severity, colors.white)
    el.append(_t(rows, [.45, .65, 1.2, 1.0, 3.6, 2.2, .9], fills))
    doc.build(el)
    return buf.getvalue()


def meeting_pack_pdf(r: Result, stakeholders: list[str] | None = None) -> bytes:
    """Weekly meeting pack: agenda by stakeholder group, then the open action log."""
    s = r.settings
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(letter), leftMargin=.5 * inch, rightMargin=.5 * inch,
                            topMargin=.45 * inch, bottomMargin=.45 * inch, title="Materials meeting pack")
    el = [Paragraph(f"Materials meeting, week of {s.as_of_date:%d %b %Y}", H1),
          Paragraph(f"{s.company} · scenario: {r.scenario.name}", SMALL), Spacer(1, 6)]
    S = r.summary()
    el.append(_kpis([("Projects late", S["projects_late"]), ("Clear to build", f"{S['projects_clear']} of {S['projects_open']}"),
                     ("Year-end gap", fmt_money(S["year_end_gap"], s.currency)), ("Overdue actions", S["actions_overdue"]),
                     ("Savings realized", fmt_money(S["savings_realized"], s.currency)),
                     ("Dept KPIs on target", f"{S['dept_kpis_met']} of {S['dept_kpis']}")]))
    ag = r.meetings.agenda
    groups = stakeholders or list(dict.fromkeys(ag["stakeholder"]))
    for g in groups:
        x = ag[ag["stakeholder"] == g]
        if not len(x):
            continue
        rows = [["Topic", "Detail", "Decision or ask"]]
        for it in x.itertuples():
            rows.append([Paragraph(it.topic, CELL), Paragraph(it.detail, CELL), Paragraph(it.decision_needed, CELL)])
        el.append(KeepTogether([Paragraph(g, H2), _t(rows, [2.2, 4.6, 3.2])]))
    act = r.meetings.actions
    if len(act):
        el.append(PageBreak())
        el.append(Paragraph("Action log", H1))
        open_ = act[act["status"].str.lower() != "done"]
        rows = [["#", "Stakeholder", "Owner", "Ref", "Action", "Due", "Status"]]
        fills = {}
        for i, x in enumerate(open_.itertuples(), start=1):
            rows.append([x.action_id, x.stakeholder, getattr(x, "owner_name", x.owner), Paragraph(str(x.ref), CELL),
                         Paragraph(x.action, CELL), _d(x.due) if pd.notna(x.due) else "",
                         "Overdue" if x.overdue else x.status])
            if x.overdue:
                fills[(i, 6)] = FILL["Critical"]
        el.append(_t(rows, [.6, 1.3, 1.0, 1.1, 4.4, .7, .9], fills))
    doc.build(el)
    return buf.getvalue()


def project_review_pdf(r: Result, project_ids: list[str] | None = None) -> bytes:
    """Monthly project review pack: a portfolio page, then one page per project (cost, margin, billing, changes, submittals)."""
    s, cur = r.settings, r.settings.currency
    f = r.financials
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(letter), leftMargin=.5 * inch, rightMargin=.5 * inch,
                            topMargin=.45 * inch, bottomMargin=.45 * inch, title="Project review pack")
    el = [Paragraph(f"Project review, {s.as_of_date:%B %Y}", H1),
          Paragraph(f"{s.company} · as of {s.as_of_date:%d %b %Y} · scenario: {r.scenario.name}", SMALL), Spacer(1, 6)]
    if f is None:
        el.append(Paragraph("No project financial data loaded (wbs_budget, cost_actuals, billing_milestones).", BODY))
        doc.build(el)
        return buf.getvalue()
    k = f.kpis
    m = lambda v: fmt_money(v, cur)  # noqa: E731
    el.append(_kpis([("Contract value", m(k["contract"])), ("Margin sold / forecast", f"{k['margin_sold_pct']:.1f}% / {k['margin_forecast_pct']:.1f}%"),
                     ("Unbilled revenue", m(k["unbilled"])), ("Receivables overdue", m(k["ar_overdue"])),
                     ("DSO", f"{k['dso']:.0f} days"), ("FY billing at risk", m(k["billing_at_risk_fy"]))]))
    el.append(Paragraph("Portfolio", H2))
    rows = [["Project", "Customer", "Status", "Contract", "EAC", "Margin sold", "Forecast", "Fade", "POC", "Unbilled", "AR overdue"]]
    fills = {}
    for i, p in enumerate(f.projects.itertuples(), start=1):
        rows.append([p.project_id, Paragraph(p.customer, CELL), p.ctb_status, _n(p.contract), _n(p.eac),
                     f"{p.margin_sold_pct:.1f}%", f"{p.margin_forecast_pct:.1f}%", f"{p.margin_fade_pts:+.1f}",
                     f"{p.poc_pct:.0f}%", _n(p.unbilled), _n(p.ar_overdue)])
        if p.margin_fade_pts >= s.margin_fade_alert_pts:
            fills[(i, 7)] = FILL["Warning"]
        if p.ar_overdue > 0:
            fills[(i, 10)] = FILL["Warning"]
        if p.ctb_status in FILL:
            fills[(i, 2)] = FILL[p.ctb_status]
    el.append(_t(rows, [.7, 2.0, .9, .85, .85, .8, .75, .55, .55, .85, .85], fills))
    el.append(Paragraph("Fade is margin as sold minus forecast margin, in points. POC is cost-to-cost percent complete. "
                        "In the project pages, a negative variance is a forecast overrun (budget minus EAC).", SMALL))

    ids = project_ids or f.projects["project_id"].tolist()
    for pid in ids:
        p = f.projects[f.projects["project_id"] == pid]
        if not len(p):
            continue
        p = p.iloc[0]
        el.append(PageBreak())
        el.append(Paragraph(f"{pid} · {p.customer}", H1))
        el.append(Paragraph(f"{p.product_family} · material status: {p.ctb_status}", SMALL))
        el.append(Spacer(1, 4))
        el.append(_kpis([("Contract (incl. approved COs)", m(p.contract)), ("EAC", m(p.eac)),
                         ("Margin sold / forecast", f"{p.margin_sold_pct:.1f}% / {p.margin_forecast_pct:.1f}%"),
                         ("Percent complete", f"{p.poc_pct:.0f}%"), ("Earned / billed", f"{m(p.earned)} / {m(p.billed)}"),
                         ("Receivables open", m(p.ar_open))]))
        w = f.wbs[f.wbs["project_id"] == pid]
        rows = [["Cost element", "As sold", "Budget", "Actual", "Committed", "ETC", "EAC", "Variance"]]
        fills = {}
        for i, x in enumerate(w.itertuples(), start=1):
            rows.append([x.cost_element, _n(x.as_sold), _n(x.budget), _n(x.actual), _n(x.committed), _n(x.etc), _n(x.eac), _n(x.variance)])
            if x.variance < -0.02 * max(x.budget, 1):
                fills[(i, 7)] = FILL["Warning"]
        rows.append(["Total", _n(w["as_sold"].sum()), _n(w["budget"].sum()), _n(w["actual"].sum()), _n(w["committed"].sum()),
                     _n(w["etc"].sum()), _n(w["eac"].sum()), _n(w["variance"].sum())])
        ms = f.milestones[f.milestones["project_id"] == pid]
        mrows = [["#", "Milestone", "Amount", "Planned", "Forecast", "Status", "Invoice"]]
        mf = {}
        for i, x in enumerate(ms.itertuples(), start=1):
            mrows.append([x.milestone_id, Paragraph(x.name, CELL), _n(x.amount), _d(x.planned_date), _d(x.forecast_date),
                          x.status, x.invoice_no or ""])
            if x.status == "Due, not invoiced":
                mf[(i, 5)] = FILL["Critical"]
            elif x.slip_days > 0 and x.status == "Planned":
                mf[(i, 4)] = FILL["Warning"]
        left = [Paragraph("Cost to complete", H2), _t(rows, [.95, .55, .55, .55, .6, .55, .6, .55])]
        right = [Paragraph("Billing milestones", H2), _t(mrows, [.3, 1.2, .6, .5, .55, 1.0, .85], mf)]
        two = Table([[left, right]], colWidths=[5.05 * inch, 5.15 * inch])
        two.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        el.append(two)
        co = f.change_orders[f.change_orders["project_id"] == pid]
        if len(co):
            rows = [["Change order", "Description", "Price", "Cost", "Status", "Age (days)"]]
            for x in co.itertuples():
                rows.append([x.co_id, Paragraph(x.description, CELL), _n(x.price_change), _n(x.cost_change), x.status,
                             _n(x.age_days) if x.status == "Pending" else ""])
            el.append(KeepTogether([Paragraph("Change orders", H2), _t(rows, [1.0, 4.6, .9, .9, .9, .8])]))
        sb = f.submittals[f.submittals["project_id"] == pid]
        if len(sb):
            rows = [["Submittal", "Direction", "Document", "Party", "Due", "Returned", "Status", "Holds"]]
            sf = {}
            for i, x in enumerate(sb.itertuples(), start=1):
                rows.append([x.submittal_id, x.direction, Paragraph(x.document, CELL), Paragraph(x.party, CELL), _d(x.due),
                             _d(x.returned) if pd.notna(x.returned) else "", "Overdue" if x.overdue else x.status, x.holds])
                if x.overdue or x.blocked:
                    sf[(i, 6)] = FILL["Warning"]
            el.append(KeepTogether([Paragraph("Submittals", H2), _t(rows, [1.0, .8, 2.4, 1.6, .6, .7, 1.1, .9], sf)]))
    doc.build(el)
    return buf.getvalue()
