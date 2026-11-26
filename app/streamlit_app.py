"""FlowLine Materials Planner dashboard.  Run:  streamlit run app/streamlit_app.py"""

from __future__ import annotations

import sys
from pathlib import Path

# Let the app find the package without installing it (Streamlit Community Cloud runs this file directly).
_SRC = Path(__file__).resolve().parents[1] / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from dataclasses import replace as _replace

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from flowline.capacity import plan_capacity
from flowline.engine import Scenario, fmt_money, run
from flowline.io.importer import load_files, workbook_bytes
from flowline.io.template import template_bytes
from flowline.meetings import STAKEHOLDERS, alerts_to_actions
from flowline.models import normalize
from flowline.reports import (
    excel_report,
    meeting_pack_pdf,
    pdf_report,
    powerquery_workbook,
    project_review_pdf,
    tier_board_pdf,
)
from flowline.reports.vsm_iso import vsm_iso_html
from flowline.sample import build_sample
from flowline.shopfloor import TIERS as TIER_LETTERS
from flowline.team import KPI
from flowline.vsm import future_state

st.set_page_config(page_title="FlowLine Materials Planner", page_icon="🏭", layout="wide")
# informational deltas ("target 4.0", "of 15") show without an arrow where Streamlit supports it
import inspect as _inspect  # noqa: E402

NOARROW = {"delta_arrow": "off"} if "delta_arrow" in _inspect.signature(st.metric).parameters else {}

# Palette: categorical slots in fixed order, status colors reserved for state (always shown with a label)
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
GOOD, WARN, SERIOUS, CRIT, NEUTRAL = "#0ca30c", "#fab219", "#ec835a", "#d03b3b", "#9a9893"
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e1e0d9"
STATUS_COLOR = {"Clear to build": GOOD, "Clear by start": "#6cc46c", "At risk": WARN, "Late": CRIT,
                "In build": NEUTRAL, "Built": "#c3c2b7"}
STATUS_ICON = {"Clear to build": "✅", "Clear by start": "🟢", "At risk": "🟠", "Late": "🔴", "In build": "🔧", "Built": "📦"}
SEV_ICON = {"Critical": "🔴", "Warning": "🟠", "Info": "🔵"}
st.markdown("""<style>
.block-container{padding-top:1.3rem}
div[data-testid="stMetricValue"]{font-size:1.55rem}
div[data-testid="stMetricLabel"] p{font-size:.82rem;color:#52514e}
</style>""", unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def _sample():
    return build_sample()


@st.cache_data(show_spinner=False)
def _upload(files: tuple[tuple[str, bytes], ...]):
    return load_files(dict(files))


def _fig(fig, height=330, **kw):
    fig.update_layout(height=height, margin=dict(l=8, r=8, t=36, b=8), plot_bgcolor="#fcfcfb", paper_bgcolor="rgba(0,0,0,0)",
                      font=dict(size=12, color=INK), legend=dict(orientation="h", y=1.1, x=0, title=None),
                      hoverlabel=dict(bgcolor="white"), **kw)
    fig.update_xaxes(showgrid=False, linecolor=GRID)
    fig.update_yaxes(gridcolor=GRID, zeroline=False)
    return fig


def _d(v):
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else pd.Timestamp(v)


def table(df: pd.DataFrame, config: dict | None = None, **kw):
    """st.dataframe with readable column headers (snake_case -> Sentence case) and blank instead of None."""
    cfg = {c: st.column_config.Column(c.replace("_", " ").capitalize().replace(" pct", " %").replace("Otd", "OTD")
                                      .replace("Ppv", "PPV").replace("Doi", "DOI").replace("Cm ", "CM ").replace("Po ", "PO "))
           for c in df.columns}
    cfg.update(config or {})
    st.dataframe(df, hide_index=True, width="stretch", column_config=cfg, **kw)


def money_cols(cur, *cols):
    return {c: st.column_config.NumberColumn(c.replace("_", " ").capitalize(), format=f"{cur}%,.0f") for c in cols}


# ---------------- sidebar ----------------
with st.sidebar:
    st.header("Data")
    src = st.radio("Source", ["Sample company", "Upload Excel or CSV"], label_visibility="collapsed")
    issues = []
    if src == "Sample company":
        data = _sample()
        st.caption("Corvane Grid Equipment (fictional): an engineer-to-order plant building MV switchgear and "
                   "transformers. 14 customer projects, 4 contract manufacturers, 15 suppliers.")
    else:
        up = st.file_uploader("One .xlsx workbook (a sheet per table) or CSV files named items.csv, bom.csv …",
                              type=["xlsx", "xlsm", "csv"], accept_multiple_files=True)
        st.download_button("Download blank template", template_bytes(), "flowline_template.xlsx", width="stretch")
        if not up:
            st.info("Upload your data to start, or switch back to the sample company.")
            st.stop()
        data, issues = _upload(tuple((f.name, f.getvalue()) for f in up))
        if any(i.severity == "error" for i in issues):
            st.error("The data has errors. See Data and exports.")

    # the action log is edited in the app: keep the edits for this data source during the session
    akey = "sample" if src == "Sample company" else "|".join(sorted(f.name for f in up))
    if st.session_state.get("actions_key") != akey:
        st.session_state["actions_key"] = akey
        st.session_state["actions_df"] = data.actions.copy()
        st.session_state["cm_df"] = data.countermeasures.copy()
    data = _replace(data, actions=normalize("actions", st.session_state["actions_df"]),
                    countermeasures=normalize("countermeasures", st.session_state["cm_df"]))

    st.header("What-if")
    sup_names = data.supplier_names()
    sups = sorted(set(data.purchase_orders["supplier_id"]) - {""})
    slip_sup = st.selectbox("Supplier slips or recovers", ["(none)"] + sups,
                            format_func=lambda x: x if x == "(none)" else f"{x} {sup_names.get(x, '')}")
    slip_days = 0
    if slip_sup != "(none)":
        slip_days = st.slider("Days later (+) or earlier (–) on all open lines", -30, 60, 21, 1)
    pdays = st.slider("Past-due POs arrive in (days)", 0, 45, int(data.settings.past_due_arrival_days),
                      help="Open PO lines whose promised date has passed are assumed to arrive this many days from today.")
    push = st.checkbox("Apply all push-outs and cancellations",
                       help="Move every PO to its suggested date and cancel quantity no open project needs. "
                            "Shows what the year-end landing would be if the suppliers agree.")
    name = "Base case"
    if slip_days or push or pdays != data.settings.past_due_arrival_days:
        parts = ([f"{slip_sup} {slip_days:+d} days"] if slip_days else []) + (["push-outs applied"] if push else []) + \
                ([f"past due in {pdays}d"] if pdays != data.settings.past_due_arrival_days else [])
        name = "What-if: " + ", ".join(parts)
    scen = Scenario(name=name, supplier_delay={slip_sup: slip_days} if slip_days else {}, past_due_arrival_days=pdays,
                    apply_push_outs=push)
    st.caption("Built for an engineer-to-order materials team. Open source, MIT licence.")

try:
    r = run(data, scen)
    base = run(data) if scen.name != "Base case" else r
except Exception as e:     # show data problems instead of a stack trace
    st.error(f"The model could not run on this data: {e}")
    st.stop()
S, B = r.summary(), base.summary()
s = r.settings
cur = s.currency


def delta(key, fmt=lambda v: f"{v:+,.0f}", inverse=False):
    if scen.name == "Base case":
        return None
    dv = S[key] - B[key]
    if abs(dv) < 1e-9:
        return None
    return fmt(dv)


# ---------------- header ----------------
st.title("FlowLine Materials Planner")
st.caption(f"{s.company} · as of {s.as_of_date:%A %d %B %Y} · fiscal year end {s.year_end:%d %b %Y} · **{scen.name}**")
c = st.columns(6)
c[0].metric("Projects clear to build", f"{S['projects_clear']} of {S['projects_open']}",
            delta("projects_clear"), help="Clear now, or all material arrives before the planned build start.")
c[1].metric("Projects late to customer", S["projects_late"], delta("projects_late"), delta_color="inverse")
c[2].metric("Inventory now", fmt_money(S["inventory_now"], cur), help="Raw materials, semi-finished, WIP and finished goods at standard cost.")
c[3].metric("Year-end landing", fmt_money(S["year_end"], cur),
            delta(("year_end"), lambda v: fmt_money(v, cur)), delta_color="inverse",
            help=f"Projected inventory on {s.year_end:%d %b}; target {fmt_money(S['year_end_target'], cur)}.")
c[4].metric("Year-end turns vs target", f"{S['turns_year_end']:.1f} vs {S['turns_target']:.1f}", delta(("turns_year_end"), lambda v: f"{v:+.1f}"),
            help="Fiscal-year COGS (closed months plus projection) divided by year-end inventory.")
c[5].metric("Critical alerts", S["alerts_critical"], delta("alerts_critical"), delta_color="inverse")

tabs = st.tabs(["Overview", "Clear to build", "Shop floor", "Weekly capacity", "Inventory & working capital", "Contract manufacturers", "Suppliers",
                "Supply risk", "Cost reduction", "Project financials", "Team & KPIs", "Meetings & actions", "Alerts", "Data and exports",
                "Value stream"])

# ---------------- Overview ----------------
with tabs[0]:
    left, right = st.columns([1.05, 1])
    with left:
        st.subheader("Where each customer project stands")
        pj = r.ctb.projects.copy()
        order = ["Late", "At risk", "Clear by start", "Clear to build", "In build", "Built"]
        cnt = pj["ctb_status"].value_counts().reindex(order).dropna()
        fig = go.Figure(go.Bar(x=cnt.values, y=[f"{STATUS_ICON[k]} {k}" for k in cnt.index], orientation="h",
                               marker_color=[STATUS_COLOR[k] for k in cnt.index], text=cnt.values, textposition="outside",
                               hovertemplate="%{y}: %{x} projects<extra></extra>"))
        fig.update_yaxes(autorange="reversed", showgrid=False)
        fig.update_xaxes(visible=False)
        st.plotly_chart(_fig(fig, 250, showlegend=False), width="stretch")
        k = r.inventory.kpis
        st.subheader("Year-end working capital")
        g = st.columns(3)
        g[0].metric("Gap to target", fmt_money(k["year_end_gap"], cur), delta_color="off", **NOARROW)
        g[1].metric("Push-out / cancel lever", fmt_money(k["push_out_value"], cur))
        g[2].metric("Excess stock", fmt_money(k["excess_value"], cur))
        if k["year_end_gap"] > 0:
            covered = min(1.0, (k["push_out_value"] + k["excess_value"]) / k["year_end_gap"])
            st.progress(covered, text=f"Identified levers cover {covered:.0%} of the gap")
    with right:
        st.subheader("Top actions")
        top = r.alerts.head(10)
        for a in top.itertuples():
            st.markdown(f"{SEV_ICON[a.severity]} **{a.area}** · {a.message}  \n<span style='color:{INK2}'>→ {a.action} "
                        f"*({a.owner})*</span>", unsafe_allow_html=True)
        st.caption(f"{len(r.alerts)} alerts in total. See the Alerts tab.")
    g = st.columns(4)
    g[0].metric("CM commitment (commit window)", "–" if np.isnan(S["cm_commit_pct"]) else f"{S['cm_commit_pct']:.0f}%")
    g[1].metric("CM on-time delivery", "–" if np.isnan(S["cm_otd_pct"]) else f"{S['cm_otd_pct']:.0f}%")
    g[2].metric("Supplier on-time delivery", "–" if np.isnan(S["supplier_otd_pct"]) else f"{S['supplier_otd_pct']:.0f}%",
                help=f"Window: {s.otd_early_days} days early to {s.otd_late_days} days late, last {s.history_months} months.")
    g[3].metric("Purchase price variance, 12 months", fmt_money(S["ppv"], cur),
                "–" if np.isnan(S["ppv_pct"]) else f"{S['ppv_pct']:+.1f}% vs standard", delta_color="inverse")
    g = st.columns(4)
    g[0].metric("Department KPIs on target", f"{S['dept_kpis_met']} of {S['dept_kpis']}", help="See Team & KPIs.")
    g[1].metric("Savings realized vs target", fmt_money(S["savings_realized"], cur),
                f"target {fmt_money(S['savings_target'], cur)}" if S["savings_target"] else None, delta_color="off", **NOARROW)
    g[2].metric("Overdue actions", S["actions_overdue"], f"{S['actions_open']} open", delta_color="off", **NOARROW)
    g[3].metric("High supply risks", S["risks_high"], help="Entered and detected risks with likelihood x impact of 15 or more.")
    if r.financials is not None:
        g = st.columns(4)
        g[0].metric("Project margin forecast", f"{S['fin_margin_forecast_pct']:.1f}%",
                    f"{S['fin_margin_forecast_pct'] - S['fin_margin_sold_pct']:+.1f} pts vs sold", help="See Project financials.")
        g[1].metric("Invoices not raised", S["fin_due_not_invoiced_count"], fmt_money(S["fin_due_not_invoiced"], cur),
                    delta_color="off", **NOARROW)
        g[2].metric("Receivables overdue", fmt_money(S["fin_ar_overdue"], cur), f"DSO {S['fin_dso']:.0f} days", delta_color="off", **NOARROW)
        g[3].metric("FY billing at risk", fmt_money(S["fin_billing_at_risk_fy"], cur))

# ---------------- Clear to build ----------------
with tabs[1]:
    pj = r.ctb.projects.copy()
    st.subheader("Clear-to-build by customer project")
    st.caption("Projects are allocated stock and open POs in build-start order. *Material ready* is when the last part "
               "(or sub-assembly) is available; *can ship* adds the build time.")
    fig = go.Figure()
    for p in pj.itertuples():
        y = f"{p.project_id} {p.customer[:22]}"
        fig.add_trace(go.Scatter(x=[p.planned_build_start, p.planned_build_start + pd.Timedelta(days=p.build_days)], y=[y, y],
                                 mode="lines", line=dict(color=GRID, width=12), showlegend=False,
                                 hovertemplate=f"{p.project_id} planned build<extra></extra>"))
        fig.add_trace(go.Scatter(x=[p.forecast_build_start, p.forecast_finish], y=[y, y], mode="lines",
                                 line=dict(color=STATUS_COLOR.get(p.ctb_status, NEUTRAL), width=6), showlegend=False,
                                 hovertemplate=f"{p.project_id}: {p.ctb_status}<br>Build {p.forecast_build_start:%d %b} to "
                                               f"{p.forecast_finish:%d %b}<extra></extra>"))
        fig.add_trace(go.Scatter(x=[p.required_ship_date], y=[y], mode="markers", showlegend=False,
                                 marker=dict(symbol="line-ns", size=14, line=dict(width=2, color=INK)),
                                 hovertemplate=f"Customer date {p.required_ship_date:%d %b}<extra></extra>"))
    fig.add_vline(x=pd.Timestamp(s.as_of_date), line=dict(color=INK2, dash="dot", width=1))
    fig.update_yaxes(autorange="reversed", showgrid=False)
    st.plotly_chart(_fig(fig, 40 + 26 * len(pj)), width="stretch")
    st.caption("Grey bar: planned build. Colored bar: forecast build from material availability "
               "(green clear, amber at risk, red late, grey in build). Black tick: customer date. Dotted line: today.")
    show = pj.assign(status=[f"{STATUS_ICON.get(x, '')} {x}" for x in pj["ctb_status"]])
    table(show[["project_id", "customer", "product_family", "status", "planned_build_start", "material_ready",
                       "gating_item", "forecast_build_start", "forecast_ship", "required_ship_date", "days_late",
                       "late_lines", "on_hand_pct", "sell_value"]], {"on_hand_pct": st.column_config.ProgressColumn("Material on hand", format="%.0f%%",
                                                                               min_value=0, max_value=100),
                                **money_cols(cur, "sell_value")})

    st.subheader("Drill into a project")
    active = pj.loc[~pj["ctb_status"].isin(["In build", "Built"]), "project_id"].tolist()
    if active:
        default = pj.loc[pj["ctb_status"] == "Late", "project_id"]
        sel = st.selectbox("Project", active, index=active.index(default.iloc[0]) if len(default) else 0)
        p = pj[pj["project_id"] == sel].iloc[0]
        a = st.columns(4)
        a[0].metric("Status", f"{STATUS_ICON.get(p.ctb_status, '')} {p.ctb_status}")
        a[1].metric("Material ready", f"{p.material_ready:%d %b %Y}", f"{(p.material_ready - p.planned_build_start).days:+d} days vs start",
                    delta_color="inverse")
        a[2].metric("Can ship", f"{p.forecast_ship:%d %b %Y}", f"{-p.float_days:+d} days vs customer", delta_color="inverse")
        a[3].metric("Gating part", p.gating_item or "none")
        rq = r.ctb.requirements[r.ctb.requirements["project_id"] == sel].copy()
        rq["part"] = ["    " * int(lv) + i for lv, i in zip(rq["level"], rq["item_id"], strict=False)]
        rq["flag"] = np.where(rq["short_qty"] > 0, "🔴 not on order",
                              np.where(rq["days_late"] > 0, "🟠 late", np.where(rq["to_build"] > 0, "🔧 build", "")))
        table(rq[["part", "description", "qty_required", "from_stock", "from_po", "to_build", "short_qty", "need_date",
                         "ready_date", "days_late", "flag", "sources"]], height=420,
              config={"part": st.column_config.TextColumn("Part (indented by BOM level)")})
    st.subheader("Late and missing parts")
    sh = r.ctb.shortages
    f1, f2 = st.columns(2)
    issue = f1.multiselect("Issue", sorted(sh["issue"].unique()), default=[x for x in sh["issue"].unique() if x != "Not yet ordered"])
    buyer = f2.multiselect("Buyer", sorted(sh["buyer"].dropna().unique()))
    v = sh[sh["issue"].isin(issue)] if issue else sh
    v = v[v["buyer"].isin(buyer)] if buyer else v
    table(v, money_cols(cur, "value_at_risk"))
    st.subheader("Long-lead parts")
    st.caption(f"Parts with a lead time of {s.long_lead_days} days or more, with the date they must be on order.")
    table(r.ctb.long_lead)

# ---------------- Shop floor ----------------
with tabs[2]:
    sf = r.shop
    if sf is None:
        st.info("Add the optional shop floor tables (work_centers and shop_schedule, plus hourly_output, downtime, "
                "quality_checks, safety_events, operators, skills, erp_open_items, countermeasures) to see the daily build "
                "plan, the SQDCC tier board and the skills matrix. The sample company has them.")
    else:
        k = sf.kpis
        st.markdown(f"**{sf.today:%A %d %B %Y}, day shift at {int(sf.now_hour)}:00** ({sf.elapsed * 100:.0f}% of the shift gone). "
                    "Materials, then production, then delivery: today's builds use the kits from Clear to build.")
        a = st.columns(6)
        a[0].metric("Schedule attainment", f"{k['attainment_pct']:.0f}%", f"target {s.attainment_target_pct:.0f}%", delta_color="off",
                    **NOARROW, help="Earned standard hours / hours planned to this hour.")
        a[1].metric("First-pass yield", f"{k['fpy_pct']:.0f}%", f"target {s.fpy_target_pct:.0f}%", delta_color="off", **NOARROW)
        a[2].metric("Labour productivity", f"{k['productivity_pct']:.0f}%", f"target {s.productivity_target_pct:.0f}%",
                    delta_color="off", **NOARROW, help="Earned standard hours / hours clocked.")
        a[3].metric("People short", f"{k['people_short']:.0f}")
        a[4].metric("Downtime today", f"{k['downtime_min_today']:.0f} min")
        a[5].metric("ERP items overdue", k["erp_overdue"], fmt_money(k["unposted_value"], cur) + " not posted", delta_color="off",
                    **NOARROW)

        st.subheader("SQDCC tier board")
        icon = {"Green": "🟢 Green", "Amber": "🟠 Amber", "Red": "🔴 Red", "No data": "⚪ No data"}
        tb = sf.tier.copy()
        tb["today"] = [fmt_money(v, cur) if t_ == "Cash" else (f"{v:.0f}" if t_ == "Safety" else f"{v:.0f}%") if pd.notna(v) else "–"
                       for t_, v in zip(tb["tier"], tb["value"], strict=True)]
        tb["goal"] = [fmt_money(v, cur) if t_ == "Cash" else (f"{v:.0f}" if t_ == "Safety" else f"{v:.0f}%")
                      for t_, v in zip(tb["tier"], tb["target"], strict=True)]
        tb["status"] = tb["status"].map(icon)
        st.dataframe(tb[["tier", "metric", "today", "goal", "status", "trend", "detail"]], hide_index=True, width="stretch",
                     column_config={"tier": st.column_config.TextColumn("Letter", width="small"),
                                    "metric": st.column_config.TextColumn("Measure", width="medium"),
                                    "today": "Today", "goal": "Target", "status": "Status",
                                    "trend": st.column_config.LineChartColumn("Last 10 days", width="small"),
                                    "detail": st.column_config.TextColumn("Detail", width="large")})
        st.caption("Tier 1 is the cell huddle at the start of the shift; Tier 2 is the supervisor and support functions "
                   "(materials, quality, engineering) at mid-morning. Red needs a countermeasure; amber is within 5 points.")

        st.subheader("Today's build plan by work centre")
        pl = sf.plan
        if True:
            table(pl[["work_center", "operation", "planned_hours", "planned_to_now", "earned_hours", "actual_hours",
                      "attainment_pct", "productivity_pct", "people_needed", "people_assigned", "downtime_min", "downtime_reason"]],
                  {"work_center": st.column_config.TextColumn("Work centre"), "operation": st.column_config.TextColumn("Job", width="medium"),
                   "planned_hours": st.column_config.NumberColumn("Shift plan h", format="%.0f"),
                   "planned_to_now": st.column_config.NumberColumn("Plan to now h", format="%.1f"),
                   "earned_hours": st.column_config.NumberColumn("Earned h", format="%.1f"),
                   "actual_hours": st.column_config.NumberColumn("Clocked h", format="%.1f"),
                   "attainment_pct": st.column_config.ProgressColumn("Attainment", format="%.0f%%", min_value=0, max_value=110),
                   "productivity_pct": st.column_config.NumberColumn("Productivity", format="%.0f%%"),
                   "people_needed": st.column_config.NumberColumn("Need", format="%.0f"),
                   "people_assigned": st.column_config.NumberColumn("Here", format="%.0f"),
                   "downtime_min": st.column_config.NumberColumn("Down min", format="%.0f"),
                   "downtime_reason": st.column_config.TextColumn("Reason")})
        short = pl[pl["people_short"] > 0]
        if len(short):
            st.warning("People: " + "; ".join(f"{x.work_center} has {x.people_assigned:.0f} of {x.people_needed:.0f}"
                                               for x in short.itertuples())
                       + ". Check the skills matrix below for who can cover.", icon="👷")

        st.subheader("Output and losses")
        g1, g2 = st.columns(2)
        with g1:
            st.markdown(f"**Plan vs earned to {int(sf.now_hour)}:00, by work centre**")
            fig = go.Figure()
            fig.add_trace(go.Bar(y=pl["work_center"], x=pl["planned_to_now"], orientation="h", name="Plan to now",
                                 marker_color="#c9c7bf", hovertemplate="%{y}: plan %{x:.1f} h<extra></extra>"))
            fig.add_trace(go.Bar(y=pl["work_center"], x=pl["earned_hours"], orientation="h", name="Earned",
                                 marker_color=[CRIT if x_ == "Red" else WARN if x_ == "Amber" else SERIES[0] for x_ in pl["status"]],
                                 showlegend=False, hovertemplate="%{y}: earned %{x:.1f} h<extra></extra>"))
            fig.add_trace(go.Bar(y=[None], x=[None], orientation="h", name="Earned (red = behind plan)", marker_color=SERIES[0]))
            fig.update_layout(barmode="group", bargap=.3, yaxis=dict(autorange="reversed"))
            fig.update_xaxes(title="standard hours", showgrid=True, gridcolor=GRID)
            st.plotly_chart(_fig(fig, 330), width="stretch")
        with g2:
            st.markdown("**Output by hour today (cumulative)**")
            wcs = ["All work centres"] + pl["work_center"].tolist()
            pick = st.selectbox("Work centre", wcs, key="sf_wc")
            hh = sf.hourly
            if pick != "All work centres":
                wid = pl.loc[pl["work_center"] == pick, "wc_id"].iloc[0]
                hh = hh[hh["wc_id"] == wid]
            agg = hh.groupby("hour")[["planned_hours", "earned_hours"]].sum().cumsum().reset_index()
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=agg["hour"], y=agg["planned_hours"], name="Plan", mode="lines",
                                     line=dict(color=INK2, width=2, dash="dash"), hovertemplate="%{x}:00 plan %{y:.1f} h<extra></extra>"))
            fig.add_trace(go.Scatter(x=agg["hour"], y=agg["earned_hours"], name="Earned", mode="lines+markers",
                                     line=dict(color=SERIES[0], width=2), marker=dict(size=8),
                                     hovertemplate="%{x}:00 earned %{y:.1f} h<extra></extra>"))
            fig.update_xaxes(title="hour starting", dtick=1)
            fig.update_yaxes(title="cumulative standard hours", showgrid=True, gridcolor=GRID)
            st.plotly_chart(_fig(fig, 270), width="stretch")
        h2, h3 = st.columns(2)
        with h2:
            dp = sf.downtime
            st.markdown("**Downtime by reason, last 7 working days**")
            fig = go.Figure(go.Bar(x=dp["reason"], y=dp["minutes"], marker_color=[CRIT if i == 0 else SERIES[0] for i in range(len(dp))],
                                   hovertemplate="%{x}: %{y:.0f} min<extra></extra>"))
            fig.update_yaxes(title="minutes", showgrid=True, gridcolor=GRID)
            st.plotly_chart(_fig(fig, 300), width="stretch")
        with h3:
            fp = sf.fpy
            st.markdown("**First-pass yield by work centre**")
            fig = go.Figure()
            fig.add_trace(go.Bar(x=fp["work_center"], y=fp["fpy_4w_pct"], name="4 weeks", marker_color="#c9c7bf",
                                 hovertemplate="%{x} 4 weeks: %{y:.1f}%<extra></extra>"))
            fig.add_trace(go.Bar(x=fp["work_center"], y=fp["fpy_today_pct"], name="Today",
                                 marker_color=[CRIT if v_ < s.fpy_target_pct else SERIES[2] for v_ in fp["fpy_today_pct"].fillna(100)],
                                 hovertemplate="%{x} today: %{y:.1f}%<extra></extra>"))
            fig.add_hline(y=s.fpy_target_pct, line=dict(color=INK2, dash="dash", width=1))
            fig.update_layout(barmode="group")
            fig.update_yaxes(range=[60, 102], ticksuffix="%", showgrid=True, gridcolor=GRID)
            st.plotly_chart(_fig(fig, 300), width="stretch")
        if len(sf.downtime_today):
            st.caption("Downtime today: " + "; ".join(f"{x.work_center} {x.minutes:.0f} min, {x.reason.lower()} ({x.note})"
                                                     for x in sf.downtime_today.itertuples()))

        st.subheader("Misses and countermeasures")
        ms = sf.misses
        if len(ms):
            table(ms[["metric", "miss", "countermeasure", "needs", "detail"]],
                  {"metric": st.column_config.TextColumn("Letter", width="small"),
                   "miss": st.column_config.TextColumn("Miss", width="medium"),
                   "countermeasure": st.column_config.TextColumn("Open countermeasure", width="medium"),
                   "needs": st.column_config.TextColumn("Next step", width="medium"), "detail": "Cause seen"})
        st.caption("The log below works like the action log: edit in place, Save, and download the input workbook to keep it.")
        cm_base = st.session_state["cm_df"].copy()
        for c in ("date", "due"):
            cm_base[c] = pd.to_datetime(cm_base[c], errors="coerce")
        cm_cols = ["cm_id", "date", "tier", "metric", "wc_id", "miss", "cause", "countermeasure", "owner", "due", "status"]
        cm_ed = st.data_editor(cm_base[cm_cols], hide_index=True, width="stretch", num_rows="dynamic", key="cm_editor",
                               column_config={"cm_id": "Id", "date": st.column_config.DateColumn("Date"),
                                              "tier": st.column_config.SelectboxColumn("Tier", options=["Tier 1", "Tier 2"]),
                                              "metric": st.column_config.SelectboxColumn("Letter", options=TIER_LETTERS),
                                              "wc_id": st.column_config.SelectboxColumn("Work centre", options=pl["wc_id"].tolist()),
                                              "miss": st.column_config.TextColumn("Miss", width="medium"),
                                              "cause": st.column_config.TextColumn("Cause", width="medium"),
                                              "countermeasure": st.column_config.TextColumn("Countermeasure", width="large"),
                                              "due": st.column_config.DateColumn("Due"),
                                              "status": st.column_config.SelectboxColumn("Status", options=["Open", "Done"])})
        m1, m2, m3 = st.columns(3)
        if m1.button("Add today's misses to the log", width="stretch", help="One row per miss that has no countermeasure yet."):
            new = ms[ms["countermeasure"] == ""]
            log = st.session_state["cm_df"].copy()
            n0 = len(log)
            rows_ = [dict(cm_id=f"CM-{100 + n0 + i}", date=pd.Timestamp(s.as_of_date), tier="Tier 1", metric=x.metric, wc_id=x.wc_id,
                          miss=x.miss, cause=x.detail, countermeasure="", owner="Production supervisor",
                          due=pd.Timestamp(s.as_of_date) + pd.Timedelta(days=1), status="Open") for i, x in enumerate(new.itertuples())]
            st.session_state["cm_df"] = pd.concat([log, pd.DataFrame(rows_)], ignore_index=True) if rows_ else log
            st.rerun()
        if m2.button("Save edits to the log", width="stretch"):
            st.session_state["cm_df"] = cm_ed.copy()
            st.rerun()
        m3.download_button("Tier 2 board (PDF)", tier_board_pdf(r), f"tier2_board_{s.as_of_date:%Y%m%d}.pdf", "application/pdf",
                           width="stretch", help="One page for the Tier 2 meeting: SQDCC, today's plan, misses, kits short.")

        st.subheader("Skills matrix and training")
        k1, k2 = st.columns([1.35, 1])
        with k1:
            mx = sf.skills
            if len(mx):
                order = [w for w in pl["wc_id"].tolist() if w in mx.columns] + \
                        [c for c in mx.columns if c not in pl["wc_id"].tolist() and c not in ("operator_id", "name", "shift", "home_wc")]
                rank = {w: i for i, w in enumerate(order)}
                mx = mx.assign(_r=mx["home_wc"].map(rank).fillna(99)).sort_values(["shift", "_r", "name"])
                labels = mx["name"] + " (" + mx["shift"].str[0] + ", " + mx["home_wc"] + ")"
                z = mx[order].values
                txt = [[{0: "", 1: "1", 2: "2", 3: "3", 4: "4"}[int(v)] for v in row] for row in z]
                fig = go.Figure(go.Heatmap(z=z, x=order, y=labels, zmin=0, zmax=4, text=txt, texttemplate="%{text}",
                                           colorscale=[[0, "#f4f3ef"], [.25, "#dbe8f8"], [.5, "#9fc3ee"], [.75, "#2a78d6"], [1, "#1f3a5f"]],
                                           colorbar=dict(title="Level", tickvals=[0, 1, 2, 3, 4],
                                                         ticktext=["0 not trained", "1 in training", "2 with help", "3 independent",
                                                                   "4 can train"]),
                                           xgap=2, ygap=2, hovertemplate="%{y} at %{x}: level %{z}<extra></extra>"))
                fig.update_yaxes(autorange="reversed", tickfont=dict(size=10))
                fig.update_xaxes(side="top")
                st.plotly_chart(_fig(fig, max(380, 17 * len(mx) + 90)), width="stretch")
        with k2:
            cv = sf.coverage
            if len(cv):
                st.markdown("**Coverage: qualified people (level 3-4) per shift**")
                table(cv[["work_center", "shift", "qualified", "minimum", "gap", "trainers", "in_training"]],
                      {"work_center": "Work centre", "qualified": "Qualified", "minimum": "Need", "gap": "Gap",
                       "trainers": "Can train", "in_training": "In training"})
            if len(sf.training):
                st.markdown("**Training plan**")
                table(sf.training, {"from_level": "From", "to_level": "To", "target": st.column_config.DateColumn("Target")})

        st.subheader("ERP to clear today")
        e1, e2 = st.columns([1.4, 1])
        with e1:
            er = sf.erp
            if len(er):
                table(er[["ref", "kind", "work_center", "project_id", "age_days", "overdue", "value", "owner", "note"]],
                      {**money_cols(cur, "value"), "age_days": st.column_config.NumberColumn("Age (days)", format="%d"),
                       "overdue": st.column_config.CheckboxColumn("Overdue"),
                       "note": st.column_config.TextColumn("What it blocks", width="large")})
                st.caption(f"Overdue = older than {s.erp_max_age_days} days. In SAP: CO11N confirmations, COGI backflush errors, "
                           "MI07 count differences, MB1A scrap, TECO and closing orders.")
        with e2:
            st.markdown(f"**Kits short for builds in the next {s.kit_horizon_days} days** (from Clear to build)")
            kt = sf.kits
            if len(kt):
                table(kt[["project_id", "build_start", "item_id", "description", "qty", "po_number", "supply_date"]],
                      {"build_start": st.column_config.DateColumn("Build start"), "supply_date": st.column_config.DateColumn("Due in"),
                       "po_number": "PO"})
            else:
                st.success("Every build starting soon has its full kit in stock.")

# ---------------- Weekly capacity ----------------
with tabs[3]:
    if r.capacity is None:
        st.info("Add the optional tables resources (machines and labour pools), routings (hours per unit by step) and "
                "production_orders to plan labour and machines week by week. The sample company has them.")
    else:
        st.markdown("**Plan labour and machines week by week.** Orders are loaded in sequence onto each step of their routing; "
                    "a step uses machine hours and labour hours at the same time, so whichever runs out first sets how many "
                    "units get done that week. Change people, shifts, overtime or the orders below and the plan re-runs.")
        dkey = st.session_state.get("actions_key", "")
        if st.session_state.get("cap_key") != dkey:
            st.session_state["cap_key"] = dkey
            st.session_state["cap_res"] = data.resources.copy()
            st.session_state["cap_orders"] = data.production_orders.assign(include=True)
            st.session_state["cap_ver"] = 0
        ver = st.session_state["cap_ver"]
        o1, o2, o3, o4 = st.columns([1, 1.2, 1.2, 1])
        horizon = o1.slider("Weeks", 8, 26, int(s.capacity_weeks), key="cap_weeks")
        rule = o2.radio("Load orders by", ["Due date", "Priority", "Material ready"], horizontal=True, key="cap_rule")
        not_early = o3.checkbox("Not before the planned start", value=True, key="cap_not_early",
                                help="Off: an order may start as soon as its material is ready (pulls work forward, adds WIP).")
        if o4.button("Reset to the data", width="stretch"):
            st.session_state["cap_key"] = None
            st.rerun()
        e1, e2 = st.columns([1.15, 1])
        with e1:
            st.markdown("**Resources: machines and labour pools**")
            res_ed = st.data_editor(
                st.session_state["cap_res"][["resource_id", "name", "kind", "wc_id", "units", "shifts_per_day", "hours_per_shift",
                                             "days_per_week", "efficiency_pct", "overtime_hours"]],
                hide_index=True, width="stretch", key=f"cap_res_ed_{ver}", disabled=["resource_id", "name", "kind", "wc_id"],
                column_config={"resource_id": "Id", "name": "Resource", "kind": "Kind", "wc_id": "Work centre",
                               "units": st.column_config.NumberColumn("Machines / people", min_value=0, step=1),
                               "shifts_per_day": st.column_config.NumberColumn("Shifts", min_value=0, max_value=3, step=1),
                               "hours_per_shift": st.column_config.NumberColumn("h / shift", min_value=0, max_value=12),
                               "days_per_week": st.column_config.NumberColumn("Days", min_value=0, max_value=7, step=1),
                               "efficiency_pct": st.column_config.NumberColumn("Efficiency %", min_value=0, max_value=100),
                               "overtime_hours": st.column_config.NumberColumn("Overtime h / week", min_value=0)})
        with e2:
            st.markdown("**Production orders**")
            ord_ed = st.data_editor(
                st.session_state["cap_orders"][["include", "order_id", "project_id", "product_family", "qty", "priority", "due_date",
                                                "from_step"]],
                hide_index=True, width="stretch", key=f"cap_ord_ed_{ver}", disabled=["order_id", "project_id", "product_family"],
                column_config={"include": st.column_config.CheckboxColumn("Plan"), "order_id": "Order", "project_id": "Project",
                               "product_family": "Family", "qty": st.column_config.NumberColumn("Qty (units)", min_value=0),
                               "priority": st.column_config.NumberColumn("Priority", min_value=1, step=1),
                               "due_date": st.column_config.DateColumn("Due"), "from_step": "Starts at step"})
        ords = ord_ed.copy()
        ords["due_date"] = pd.to_datetime(ords["due_date"], errors="coerce")
        cp = plan_capacity(data, r.ctb, s, res_ed, ords, rule, not_early, horizon)
        kc = cp.kpis
        a = st.columns(6)
        a[0].metric("Orders in the plan", kc["orders"] - kc["beyond"], f"{kc['beyond']} after the horizon", delta_color="off", **NOARROW)
        a[1].metric("On time", kc["on_time"])
        a[2].metric("Late: capacity", kc["late_capacity"], help="Held back by a machine or labour pool.")
        a[3].metric("Late: material", kc["late_material"], help="Cannot start early enough because material arrives late (Clear to build).")
        a[4].metric("Busiest resource", f"{kc['bottleneck_util']:.0f}% load", kc["bottleneck_name"], delta_color="off", **NOARROW)
        a[5].metric("Average load", f"labour {kc['avg_util_labour']:.0f}%", f"machines {kc['avg_util_machine']:.0f}%", delta_color="off", **NOARROW)

        if cp.advice is not None and len(cp.advice):
            adv = cp.advice
            st.warning("**To bring the capacity-late orders back:** " + "; ".join(
                f"{x.work_center} ({x.detail} per week)" for x in adv.itertuples())
                + (". That puts every order back on time." if adv.attrs.get("fixed") else
                   ". That is not enough on its own: re-sequence, split the order or move the date."), icon="⏱️")
            if st.button("Apply the suggested overtime"):
                newres = res_ed.copy()
                ot = adv.attrs.get("overtime", {})
                newres["overtime_hours"] = newres["resource_id"].map(ot).fillna(newres["overtime_hours"])
                st.session_state["cap_res"] = newres
                st.session_state["cap_orders"] = ord_ed.copy()
                st.session_state["cap_ver"] = ver + 1
                st.rerun()

        st.subheader("Schedule by order")
        sp = cp.steps
        if len(sp):
            ordr = cp.orders.set_index("order_id")
            order_list = [o for o in cp.orders["order_id"] if o in set(sp["order_id"])]
            labels = {o: f"{o} · {ordr.at[o, 'project_id']}" for o in order_list}
            steps_order = list(dict.fromkeys(data.routings.sort_values(["product_family", "seq"])["step"]))
            palette = SERIES + ["#8f6bd6", "#d6a26b", "#6bb7d6", "#b5b5b5"]
            colors = {st_: palette[i % len(palette)] for i, st_ in enumerate(steps_order)}
            # each week cell is shared by the steps working on the order that week, side by side in routing order
            cells = sp.groupby(["order_id", "week", "seq", "step"])["units"].sum().reset_index().sort_values(["order_id", "week", "seq"])
            cells["k"] = cells.groupby(["order_id", "week"]).cumcount()
            cells["n"] = cells.groupby(["order_id", "week"])["seq"].transform("count")
            day = 24 * 3600 * 1000
            cells["base"] = cells["week"] + pd.to_timedelta(cells["k"] * 7 / cells["n"], unit="D")
            cells["width"] = 7 * day / cells["n"] * 0.94
            fig = go.Figure()
            for st_ in steps_order:
                c_ = cells[cells["step"] == st_]
                if not len(c_):
                    continue
                fig.add_trace(go.Bar(y=c_["order_id"].map(labels), x=c_["width"], base=c_["base"], orientation="h", name=st_,
                                     marker_color=colors[st_], customdata=np.c_[c_["units"], c_["week"].dt.strftime("%d %b")],
                                     hovertemplate="%{y}: " + st_ + ", week of %{customdata[1]}: %{customdata[0]:.1f} units<extra></extra>"))
            fig.update_layout(barmode="overlay", bargap=.35)
            dues = cp.orders[cp.orders["order_id"].isin(order_list)]
            fig.add_trace(go.Scatter(x=dues["due"], y=dues["order_id"] + " · " + dues["project_id"], mode="markers", name="Due",
                                     marker=dict(symbol="line-ns", size=18, line=dict(width=3, color=INK)),
                                     hovertemplate="%{y}: due %{x|%d %b}<extra></extra>"))
            late = dues[dues["status"] == "Late"]
            if len(late):
                fig.add_trace(go.Scatter(x=late["finish"], y=late["order_id"] + " · " + late["project_id"], mode="markers", name="Late finish",
                                         marker=dict(symbol="x", size=11, color=CRIT),
                                         hovertemplate="%{y}: finishes %{x|%d %b}<extra></extra>"))
            fig.add_vline(x=pd.Timestamp(s.as_of_date), line=dict(color=INK2, dash="dot", width=1))
            fig.update_yaxes(categoryorder="array", categoryarray=[labels[o] for o in order_list][::-1], title=None)
            fig.update_xaxes(type="date", dtick=7 * day, tickformat="%d %b", showgrid=True, gridcolor=GRID)
            st.plotly_chart(_fig(fig, max(320, 30 * len(order_list) + 110)), width="stretch")
            st.caption("Each week is shared by the steps working on the order that week, in routing order. Black tick: customer "
                       "date. ✕: finish after the customer date.")

        st.subheader("Load by resource and week")
        h1, h2 = st.columns([1.2, 1])
        with h1:
            u = cp.utilization.copy()
            rn = cp.resources.set_index("resource_id")
            u.index = [f"{rn.at[i, 'name']} ({rn.at[i, 'kind'][0]})" for i in u.index]
            fig = go.Figure(go.Heatmap(z=u.values, x=[w.strftime("%d %b") for w in u.columns], y=u.index, zmin=0, zmax=100,
                                       text=u.round(0).astype(int).astype(str).values, texttemplate="%{text}",
                                       colorscale=[[0, "#f4f3ef"], [.6, "#9fc3ee"], [.85, "#2a78d6"], [1, "#1f3a5f"]],
                                       colorbar=dict(title="Load %"), xgap=2, ygap=2,
                                       hovertemplate="%{y}, week of %{x}: %{z:.0f}%<extra></extra>"))
            fig.update_yaxes(autorange="reversed", tickfont=dict(size=10))
            st.plotly_chart(_fig(fig, 30 * len(u) + 110), width="stretch")
            st.caption("M = machine, L = labour. 100% = every available hour planned. The Christmas weeks run at 60% capacity.")
        with h2:
            pick = st.selectbox("Resource", list(rn.index), format_func=lambda i: f"{rn.at[i, 'name']} ({rn.at[i, 'kind']})",
                                index=list(rn.index).index(kc["bottleneck"]) if kc["bottleneck"] in rn.index else 0, key="cap_pick")
            col = "machine" if rn.at[pick, "kind"] == "Machine" else "labour"
            ld = sp[sp[f"{col}_id"] == pick].groupby(["week", "order_id"])[f"{col}_hours"].sum().reset_index()
            fig = go.Figure()
            for i, (oid, gg) in enumerate(ld.groupby("order_id")):
                fig.add_trace(go.Bar(x=gg["week"], y=gg[f"{col}_hours"], name=oid, marker_color=palette[i % len(palette)],
                                     hovertemplate=oid + ", %{x|%d %b}: %{y:.0f} h<extra></extra>"))
            fig.add_trace(go.Scatter(x=list(cp.capacity.columns), y=cp.capacity.loc[pick].values, name="Capacity", mode="lines",
                                     line=dict(color=INK, width=2, shape="hv"), hovertemplate="%{x|%d %b}: %{y:.0f} h<extra></extra>"))
            fig.update_layout(barmode="stack", bargap=.25)
            fig.update_yaxes(title="hours", showgrid=True, gridcolor=GRID)
            fig.update_xaxes(tickformat="%d %b")
            st.plotly_chart(_fig(fig, 340), width="stretch")

        st.subheader("Orders")
        table(cp.orders[["order_id", "project_id", "product_family", "qty", "priority", "material_ready", "earliest_start", "start_week",
                         "finish", "due", "days_late", "status", "held_by_name"]],
              {"material_ready": st.column_config.DateColumn("Material ready"), "earliest_start": st.column_config.DateColumn("Earliest start"),
               "start_week": st.column_config.DateColumn("Starts (week)"), "finish": st.column_config.DateColumn("Finishes"),
               "due": st.column_config.DateColumn("Due"), "days_late": st.column_config.NumberColumn("Days late", format="%d"),
               "held_by_name": "Held back by"})
        st.caption("Earliest start = material ready from Clear to build (and the planned start if ticked). Finish = Friday of the week "
                   "the last step finishes. 'After horizon' = due after the last planned week. Held back by = the last resource that ran out of hours "
                   "for that order (or material).")

# ---------------- Inventory ----------------
with tabs[4]:
    k = r.inventory.kpis
    a = st.columns(5)
    a[0].metric("Inventory now", fmt_money(k["inventory_now"], cur))
    a[1].metric("Turns now", f"{k['turns_now']:.1f}", help="Trailing 12-month COGS / inventory now.")
    a[2].metric("Days of inventory", f"{k['doi_now']:.0f}")
    a[3].metric("Year-end landing", fmt_money(k["year_end"], cur), f"{fmt_money(k['year_end_gap'], cur)} vs target",
                delta_color="inverse")
    a[4].metric(f"Year-end turns (target {s.turns_target:.1f})", f"{k['turns_year_end']:.1f}")

    st.subheader("Inventory by stock type: actuals and projection")
    pr = r.inventory.projection
    fig = go.Figure()
    for i, t in enumerate(["Raw materials", "Semi-finished", "WIP", "Finished goods"]):
        x = pr[pr["stock_type"] == t]
        fig.add_trace(go.Bar(x=x["month"], y=x["value"], name=t, marker_color=SERIES[i],
                             marker_line=dict(color="#fcfcfb", width=1),
                             customdata=x["kind"], hovertemplate=f"{t}<br>%{{x|%b %Y}}: {cur}%{{y:,.0f}} (%{{customdata}})<extra></extra>"))
    tgt = k["year_end_target"]
    if not np.isnan(tgt):
        fig.add_hline(y=tgt, line=dict(color=INK, dash="dash", width=1),
                      annotation_text=f"Year-end target {fmt_money(tgt, cur)}", annotation_position="top left")
    first_proj = pr.loc[pr["kind"] == "Projected", "month"].min()
    if pd.notna(first_proj):
        fig.add_vrect(x0=first_proj - pd.Timedelta(days=15), x1=pr["month"].max() + pd.Timedelta(days=15),
                      fillcolor="#e1e0d9", opacity=0.25, line_width=0, annotation_text="Projection", annotation_position="top right", layer="below")
    fig.update_layout(barmode="stack", bargap=0.25)
    fig.update_yaxes(tickprefix=cur)
    st.plotly_chart(_fig(fig, 380), width="stretch")
    st.caption("The projection follows the material plan: PO receipts in, material issued to WIP when each project can "
               "actually start, WIP to finished goods at build finish, out at shipment. It covers the open order book only.")
    l1, l2 = st.columns([1, 1.15])
    with l1:
        st.subheader("Landing by stock type")
        table(r.inventory.landing, {**money_cols(cur, "now", "year_end", "target", "gap"),
                                    "doi_now": st.column_config.NumberColumn("DOI now", format="%.0f"),
                                    "doi_year_end": st.column_config.NumberColumn("DOI year end", format="%.0f")})
    with l2:
        st.subheader("Bridge: landing to target")
        lv = r.inventory.levers
        po_lev = float(lv.loc[~lv["lever"].eq("Excess stock"), "year_end_impact"].sum()) if len(lv) else 0.0
        ex_lev = float(lv.loc[lv["lever"].eq("Excess stock"), "year_end_impact"].sum()) if len(lv) else 0.0
        after = k["year_end"] - po_lev - ex_lev
        fig = go.Figure(go.Waterfall(
            x=["Year-end landing", "Push out / cancel POs", "Sell down excess", "After levers", "Target"],
            measure=["absolute", "relative", "relative", "total", "absolute"],
            y=[k["year_end"], -po_lev, -ex_lev, 0, tgt if not np.isnan(tgt) else 0],
            text=[fmt_money(v, cur) for v in [k["year_end"], -po_lev, -ex_lev, after, tgt]], textposition="outside",
            increasing=dict(marker_color=SERIOUS), decreasing=dict(marker_color=SERIES[2]),
            totals=dict(marker_color=SERIES[0]), connector=dict(line=dict(color=GRID))))
        fig.update_yaxes(tickprefix=cur)
        st.plotly_chart(_fig(fig, 320, showlegend=False), width="stretch")
    st.subheader("Levers on the year-end landing")
    table(r.inventory.levers, money_cols(cur, "year_end_impact"))
    st.subheader("PO exception messages")
    pa = r.ctb.po_actions
    acts = st.multiselect("Action", sorted(pa["action"].unique()), default=[x for x in pa["action"].unique() if x != "OK"])
    table(pa[pa["action"].isin(acts)] if acts else pa, money_cols(cur, "value", "year_end_impact"))
    st.subheader("Excess: not needed by any open project")
    table(r.ctb.excess, money_cols(cur, "excess_value", "unneeded_on_order_value"))

# ---------------- Contract manufacturers ----------------
with tabs[5]:
    perf = r.cm.performance
    st.subheader("Contract manufacturer summary")
    table(perf, {"otd_pct": st.column_config.NumberColumn("OTD %", format="%.0f%%"),
                                "commit_pct_window": st.column_config.NumberColumn("Commit % (window)", format="%.0f%%"),
                                "peak_load_pct": st.column_config.NumberColumn("Peak load", format="%.0f%%"),
                                "forecast_change_pct": st.column_config.NumberColumn("Demand change since forecast", format="%+.0f%%"),
                                "quality_ppm": st.column_config.NumberColumn("Quality ppm", format="%,.0f"),
                                "avg_days_late": st.column_config.NumberColumn("Avg days late (when late)", format="%.1f")})
    cms = perf["cm_id"].tolist()
    if cms:
        names = dict(zip(perf["cm_id"], perf["name"], strict=False))
        cm = st.selectbox("Contract manufacturer", cms, format_func=lambda x: f"{x} {names.get(x, '')}")
        pl = r.cm.plan[r.cm.plan["cm_id"] == cm]
        fig = go.Figure()
        for i, (col, nm) in enumerate([("forecast_hours", "Forecast sent"), ("committed_hours", "Committed by CM"),
                                       ("demand_now_hours", "Our demand now")]):
            fig.add_trace(go.Bar(x=pl["month"], y=pl[col], name=nm, marker_color=SERIES[[0, 2, 1][i]],
                                 hovertemplate=f"{nm}<br>%{{x|%b %Y}}: %{{y:,.0f}} h<extra></extra>"))
        fig.add_trace(go.Scatter(x=pl["month"], y=pl["capacity_hours"], name="CM capacity", mode="lines+markers",
                                 line=dict(color=INK, width=2, dash="dash"), marker=dict(size=8),
                                 hovertemplate="Capacity %{x|%b %Y}: %{y:,.0f} h<extra></extra>"))
        win = pl[pl["in_commit_window"]]["month"]
        if len(win):
            fig.add_vrect(x0=win.min() - pd.Timedelta(days=15), x1=win.max() + pd.Timedelta(days=15), fillcolor="#e1e0d9",
                          opacity=0.25, line_width=0, annotation_text=f"Commit window ({s.cm_commit_horizon_months} months)",
                          annotation_position="top left", layer="below")
        fig.update_layout(barmode="group", bargap=0.25, bargroupgap=0.08)
        fig.update_yaxes(title="Hours")
        st.plotly_chart(_fig(fig, 360), width="stretch")
        st.caption("Forecast sent: the last forecast we gave the CM. Committed: what the CM has confirmed. "
                   "Our demand now: today's requirement from open projects, so a gap to the forecast means it is stale.")
        table(r.cm.by_item[r.cm.by_item["cm_id"] == cm])
        rec = r.suppliers.receipts
        rec = rec[rec["supplier_id"] == cm] if len(rec) else rec
        if len(rec):
            m = rec.groupby("month").agg(otd=("on_time", "mean"), lines=("on_time", "size")).reset_index()
            fig = go.Figure(go.Bar(x=m["month"], y=100 * m["otd"], marker_color=SERIES[0], customdata=m["lines"],
                                   hovertemplate="%{x|%b %Y}: %{y:.0f}% on time (%{customdata} lines)<extra></extra>"))
            fig.add_hline(y=s.otd_target_pct, line=dict(color=INK, dash="dash", width=1),
                          annotation_text=f"Target {s.otd_target_pct:.0f}%")
            fig.update_yaxes(range=[0, 105], ticksuffix="%")
            st.plotly_chart(_fig(fig, 260, title=dict(text="On-time delivery by month", font=dict(size=14))), width="stretch")

# ---------------- Suppliers ----------------
with tabs[6]:
    sc = r.suppliers.scorecard
    k = r.suppliers.kpis
    a = st.columns(4)
    a[0].metric("Supplier OTD (12 months)", "–" if np.isnan(k["otd_pct"]) else f"{k['otd_pct']:.0f}%")
    a[1].metric("Spend (12 months)", fmt_money(k["spend_12m"], cur))
    a[2].metric("PPV", fmt_money(k["ppv"], cur), "–" if np.isnan(k["ppv_pct"]) else f"{k['ppv_pct']:+.1f}%", delta_color="inverse")
    a[3].metric("Single-source items", k["single_source_items"],
                help=f"{k['dual_in_progress']} of them have a second source in qualification or identified.")
    a[3].caption(f"{k['dual_in_progress']} with a second source in progress")
    st.subheader("Scorecard")
    st.caption("Score = 50% on-time delivery + 30% quality (rejects in ppm) + 20% price (PPV). A ≥ 85, B ≥ 70, C below.")
    live = sc[sc["receipt_lines"] > 0].sort_values("otd_pct")
    fig = go.Figure(go.Bar(x=live["otd_pct"], y=live["name"], orientation="h",
                           marker_color=[CRIT if v < s.otd_target_pct - 15 else WARN if v < s.otd_target_pct else GOOD for v in live["otd_pct"]],
                           customdata=np.stack([live["grade"], live["receipt_lines"]], axis=1),
                           hovertemplate="%{y}: %{x:.0f}% on time, grade %{customdata[0]} (%{customdata[1]} lines)<extra></extra>"))
    fig.add_vline(x=s.otd_target_pct, line=dict(color=INK, dash="dash", width=1), annotation_text=f"Target {s.otd_target_pct:.0f}%")
    fig.update_xaxes(range=[0, 105], ticksuffix="%", showgrid=True, gridcolor=GRID)
    fig.update_yaxes(showgrid=False)
    st.plotly_chart(_fig(fig, 30 + 22 * len(live), title=dict(text="On-time delivery, last 12 months (red: more than 15 points below target)", font=dict(size=14))),
                    width="stretch")
    table(sc, {**money_cols(cur, "spend_12m", "ppv", "open_po_value", "single_source_spend"),
                                "otd_pct": st.column_config.NumberColumn("OTD %", format="%.0f%%"),
                                "avg_days_late": st.column_config.NumberColumn("Avg days late (when late)", format="%.1f"),
                                "early_pct": st.column_config.NumberColumn("Early %", format="%.0f%%"),
                                "ppv_pct": st.column_config.NumberColumn("PPV %", format="%+.1f%%"),
                                "quality_ppm": st.column_config.NumberColumn("Quality ppm", format="%,.0f"),
                                "score": st.column_config.ProgressColumn("Score", format="%.0f", min_value=0, max_value=100)})
    st.subheader("Single-source risk and dual sourcing")
    so = r.suppliers.sourcing
    pipe = so[so["single_source"]]["dual_status"].value_counts()
    b = st.columns(len(pipe) or 1)
    for i, (kk, vv) in enumerate(pipe.items()):
        b[i].metric(kk, vv)
    only = st.toggle("Single-source items only", True)
    table(so[so["single_source"]] if only else so, {**money_cols(cur, "spend_12m", "open_po_value"),
                                "risk_score": st.column_config.ProgressColumn("Risk", format="%.0f", min_value=0, max_value=100)})
    st.caption("Risk score (single-source items): lead time 40, 12-month spend 30, open projects exposed 20, current shortage 10.")


# ---------------- Supply risk ----------------
with tabs[7]:
    rk = r.risk
    a = st.columns(4)
    a[0].metric("High risks", rk.kpis["risks_high"], f"of {rk.kpis['risks_total']}", delta_color="off", **NOARROW)
    a[1].metric("Safety-stock changes", rk.kpis["ss_raise"] + rk.kpis["ss_lower"],
                f"{fmt_money(rk.kpis['ss_value_change'], cur)} net", delta_color="off", **NOARROW)
    a[2].metric("Logistics on time", "–" if np.isnan(rk.kpis["lsp_otd_pct"]) else f"{rk.kpis['lsp_otd_pct']:.0f}%")
    a[3].metric("Premium freight, 12 months", fmt_money(rk.kpis["premium_freight"], cur))

    st.subheader("Risk register")
    st.caption("Risks you entered plus risks the model detects (single source with no second source or a shortage, "
               "unreliable suppliers, CM overload, long-lead parts not ordered, late carriers, low safety stock). "
               "Score = likelihood x impact, each 1 to 5. High is 15 or more.")
    reg = rk.register
    hm = reg[reg["status"].str.lower() != "closed"].groupby(["likelihood", "impact"]).size()
    z = [[int(hm.get((lk, im), 0)) for im in range(1, 6)] for lk in range(1, 6)]
    sev = [[lk * im for im in range(1, 6)] for lk in range(1, 6)]
    fig = go.Figure(go.Heatmap(z=sev, x=[1, 2, 3, 4, 5], y=[1, 2, 3, 4, 5], showscale=False, xgap=3, ygap=3,
                               colorscale=[[0, "#eef5ee"], [0.3, "#fbf0cf"], [0.6, "#f8d9c6"], [1, "#f1c0c0"]],
                               text=[[str(v) if v else "" for v in row] for row in z], texttemplate="%{text}",
                               textfont=dict(size=16, color=INK),
                               hovertemplate="Likelihood %{y}, impact %{x}: %{text} open risk(s)<extra></extra>"))
    fig.update_xaxes(title="Impact", dtick=1)
    fig.update_yaxes(title="Likelihood", dtick=1, showgrid=False)
    h1, h2 = st.columns([1, 1.6])
    with h1:
        st.plotly_chart(_fig(fig, 330, showlegend=False), width="stretch")
        st.caption("Number of open risks per cell. Shading: green low, amber medium, red high.")
    with h2:
        table(reg, height=330, config={"risk": st.column_config.TextColumn(width="large"),
                                       "mitigation": st.column_config.TextColumn(width="medium")})

    st.subheader("Safety stock for repeat parts")
    st.caption(f"Recommended = z x sqrt(lead time / 30 x demand variance + (demand / 30)^2 x delivery-delay variance), "
               f"at {s.service_level_pct:.0f}% service. Engineered, project-specific parts carry no safety stock. "
               f"A change is suggested when the current level is more than {s.safety_stock_tolerance_pct:.0f}% off.")
    ssd = rk.safety_stock
    if len(ssd):
        fig = go.Figure()
        fig.add_trace(go.Bar(y=ssd["item_id"], x=ssd["current_ss"] / ssd["avg_monthly_use"] * 30.4, orientation="h",
                             name="Current", marker_color=SERIES[0],
                             hovertemplate="%{y}: current covers %{x:.0f} days<extra></extra>"))
        fig.add_trace(go.Bar(y=ssd["item_id"], x=ssd["recommended_ss"] / ssd["avg_monthly_use"] * 30.4, orientation="h",
                             name="Recommended", marker_color=SERIES[2],
                             hovertemplate="%{y}: recommended covers %{x:.0f} days<extra></extra>"))
        fig.update_layout(barmode="group", bargap=0.3)
        fig.update_xaxes(title="Days of demand covered by safety stock", showgrid=True, gridcolor=GRID)
        fig.update_yaxes(autorange="reversed", showgrid=False)
        st.plotly_chart(_fig(fig, 60 + 34 * len(ssd)), width="stretch")
        table(ssd, {**money_cols(cur, "change_value"),
                    "avg_monthly_use": st.column_config.NumberColumn("Avg monthly use", format="%,.1f"),
                    "demand_cv": st.column_config.NumberColumn("Demand CV", format="%.2f"),
                    "lead_time_sd_days": st.column_config.NumberColumn("Delivery delay SD (days)", format="%.1f"),
                    "days_of_cover_ss": st.column_config.NumberColumn("Days covered", format="%.0f")})
    else:
        st.info("Add a consumption_history table to get safety-stock recommendations.")

    st.subheader("Dual-sourcing plan")
    table(rk.dual_plan, {**money_cols(cur, "spend_12m"),
                         "risk_score": st.column_config.ProgressColumn("Risk", format="%.0f", min_value=0, max_value=100)})

    st.subheader("Logistics providers")
    if len(rk.logistics):
        table(rk.logistics, {**money_cols(cur, "cost_12m", "premium_cost"),
                             "otd_pct": st.column_config.NumberColumn("OTD %", format="%.0f%%"),
                             "cost_per_kg": st.column_config.NumberColumn("Cost per kg", format=f"{cur}%.2f")})
        prem = rk.shipments[rk.shipments["is_premium"]] if len(rk.shipments) else rk.shipments
        if len(prem):
            st.caption(f"Premium shipments and their reasons ({len(prem)}, {fmt_money(prem['cost'].sum(), cur)}):")
            table(prem[["shipment_id", "lsp", "ship_date", "weight_kg", "cost", "reason"]], money_cols(cur, "cost"))
    else:
        st.info("Add a shipments table to see logistics-provider performance.")

# ---------------- Cost reduction ----------------
with tabs[8]:
    co = r.cost
    k = co.kpis
    a = st.columns(4)
    a[0].metric("Realized savings", fmt_money(k["realized"], cur),
                None if not k["target"] else f"{k['realized_pct_target']:.0f}% of {fmt_money(k['target'], cur)} target",
                delta_color="off", **NOARROW)
    a[1].metric("Expected by now", fmt_money(k["target_to_date"], cur),
                None if not k["target"] else fmt_money(k["realized"] - k["target_to_date"], cur))
    a[2].metric("Weighted pipeline", fmt_money(k["weighted_pipeline"], cur), f"{k['projects']} projects", delta_color="off", **NOARROW)
    a[3].metric("New opportunities found", fmt_money(k["opportunity_value"], cur), f"{len(co.opportunities)} items",
                delta_color="off", **NOARROW)
    c1, c2 = st.columns([1, 1.2])
    with c1:
        st.subheader("Pipeline by stage")
        bs = co.by_stage
        fig = go.Figure()
        fig.add_trace(go.Bar(x=bs["stage"], y=bs["annual_savings"], name="Annual savings", marker_color=SERIES[0],
                             hovertemplate="%{x}: " + cur + "%{y:,.0f} a year<extra></extra>"))
        fig.add_trace(go.Bar(x=bs["stage"], y=bs["weighted_savings"], name="Weighted by stage", marker_color=SERIES[2],
                             hovertemplate="%{x}: " + cur + "%{y:,.0f} weighted<extra></extra>"))
        fig.update_layout(barmode="group", bargap=0.3)
        fig.update_yaxes(tickprefix=cur)
        st.plotly_chart(_fig(fig, 320), width="stretch")
        st.caption("Weights: idea 10%, validated 50%, in implementation 80%, realized 100%.")
    with c2:
        st.subheader("Realized against target")
        if k["target"]:
            fig = go.Figure()
            fig.add_trace(go.Bar(x=[k["realized"]], y=["Savings"], orientation="h", name="Realized", marker_color=SERIES[2],
                                 hovertemplate="Realized " + cur + "%{x:,.0f}<extra></extra>"))
            fig.add_trace(go.Bar(x=[max(k["weighted_pipeline"] - k["realized"], 0)], y=["Savings"], orientation="h",
                                 name="Weighted pipeline still to come", marker_color=SERIES[0], opacity=0.5,
                                 hovertemplate="Still to come " + cur + "%{x:,.0f}<extra></extra>"))
            fig.add_vline(x=k["target"], line=dict(color=INK, dash="dash", width=1),
                          annotation_text=f"Annual target {fmt_money(k['target'], cur)}")
            fig.add_vline(x=k["target_to_date"], line=dict(color=INK2, dash="dot", width=1),
                          annotation_text="Expected by now", annotation_position="bottom right")
            fig.update_layout(barmode="stack")
            fig.update_xaxes(tickprefix=cur, showgrid=True, gridcolor=GRID)
            st.plotly_chart(_fig(fig, 220), width="stretch")
        else:
            st.info("Set savings_target in settings to track against a target.")
    st.subheader("Savings projects")
    table(co.pipeline, {**money_cols(cur, "baseline_spend", "annual_savings", "weighted_savings", "realized_to_date"),
                        "savings_pct": st.column_config.NumberColumn("Savings %", format="%.1f%%"),
                        "weight": st.column_config.NumberColumn("Stage weight", format="%.1f")})
    st.subheader("Opportunities found by the model")
    st.caption("Price paid well over standard, cheaper quotes from qualified or qualifying sources, premium freight, and the "
               f"carrying cost ({s.carrying_cost_pct:.0f}% a year) of the inventory levers. Items already covered by a "
               "savings project in the same category are left out.")
    table(co.opportunities, {**money_cols(cur, "annual_value"), "finding": st.column_config.TextColumn(width="large")})

# ---------------- Project financials ----------------
with tabs[9]:
    fi = r.financials
    if fi is None:
        st.info("Add the optional tables wbs_budget, cost_actuals and billing_milestones (and change_orders, submittals) "
                "to see project cost, margin, billing and cash. The sample company has them.")
    else:
        k = fi.kpis
        a = st.columns(6)
        a[0].metric("Contract value", fmt_money(k["contract"], cur), help="As sold plus approved change orders, open projects.")
        a[1].metric("Margin forecast", f"{k['margin_forecast_pct']:.1f}%", f"{k['margin_forecast_pct'] - k['margin_sold_pct']:+.1f} pts vs sold",
                    help="(Contract − EAC) / contract. EAC = actual + estimate to complete.")
        a[2].metric("Unbilled revenue", fmt_money(k["unbilled"], cur), f"{fmt_money(k['billings_in_excess'], cur)} billed in excess",
                    delta_color="off", **NOARROW, help="Earned (cost-to-cost percent complete × contract) minus billed.")
        a[3].metric("Receivables overdue", fmt_money(k["ar_overdue"], cur), f"DSO {k['dso']:.0f} days", delta_color="off", **NOARROW)
        a[4].metric("Invoices not raised", k["due_not_invoiced_count"], fmt_money(k["due_not_invoiced"], cur), delta_color="off", **NOARROW,
                    help="Billing milestones whose trigger is reached but no invoice is recorded.")
        a[5].metric("FY billing at risk", fmt_money(k["billing_at_risk_fy"], cur),
                    f"{fmt_money(k['billing_fy_forecast'], cur)} forecast", delta_color="off", **NOARROW,
                    help=f"Milestones planned before {s.year_end:%d %b} whose forecast date is now after it.")
        pj = fi.projects
        c1, c2 = st.columns([1, 1.15])
        with c1:
            st.subheader("Margin: as sold vs forecast")
            v = pj.sort_values("margin_fade_pts", ascending=True)
            fig = go.Figure()
            fig.add_trace(go.Bar(y=v["project_id"], x=v["margin_sold_pct"], orientation="h", name="As sold", marker_color=SERIES[0],
                                 hovertemplate="%{y} as sold: %{x:.1f}%<extra></extra>"))
            fig.add_trace(go.Bar(y=v["project_id"], x=v["margin_forecast_pct"], orientation="h", name="Forecast", marker_color=SERIES[1],
                                 hovertemplate="%{y} forecast: %{x:.1f}%<extra></extra>"))
            fig.update_layout(barmode="group", bargap=0.25, bargroupgap=0.08)
            fig.update_xaxes(ticksuffix="%", showgrid=True, gridcolor=GRID)
            st.plotly_chart(_fig(fig, 430), width="stretch")
            st.caption(f"Projects at the top have faded most. Alert at {s.margin_fade_alert_pts:.1f} points or more.")
        with c2:
            st.subheader("Billing and cash by month")
            bm = fi.billing_by_month
            fig = go.Figure()
            fig.add_trace(go.Bar(x=bm["month"], y=bm["billing_planned"], name="Billing planned", marker_color=SERIES[0], opacity=0.45,
                                 hovertemplate="%{x|%b %Y} planned: " + cur + "%{y:,.0f}<extra></extra>"))
            fig.add_trace(go.Bar(x=bm["month"], y=bm["billing_forecast"], name="Billing forecast", marker_color=SERIES[0],
                                 hovertemplate="%{x|%b %Y} forecast: " + cur + "%{y:,.0f}<extra></extra>"))
            fig.add_trace(go.Scatter(x=bm["month"], y=bm["cash_forecast"], name="Cash in (forecast)", mode="lines+markers",
                                     line=dict(color=SERIES[2], width=2), marker=dict(size=8),
                                     hovertemplate="%{x|%b %Y} cash: " + cur + "%{y:,.0f}<extra></extra>"))
            fig.add_vline(x=pd.Timestamp(s.year_end), line=dict(color=INK2, dash="dash", width=1))
            fig.add_annotation(x=pd.Timestamp(s.year_end), y=1, yref="paper", text="Fiscal year end", showarrow=False,
                               xanchor="left", font=dict(color=INK2, size=11))
            fig.update_layout(barmode="group", bargap=0.3)
            fig.update_yaxes(tickprefix=cur)
            st.plotly_chart(_fig(fig, 300), width="stretch")
            st.caption(f"Cash follows the invoice by the payment terms ({s.payment_terms_days} days); overdue invoices are "
                       "assumed to be paid next month.")
            st.subheader("Receivables aging")
            ar = fi.receivables
            buckets = ["Not due", "1-30", "31-60", "61-90", "90+"]
            ag = ar.groupby("bucket")["billed"].sum().reindex(buckets).fillna(0) if len(ar) else pd.Series(0.0, index=buckets)
            st.dataframe(pd.DataFrame([ag.values], columns=buckets), hide_index=True, width="stretch",
                         column_config={b: st.column_config.NumberColumn(b if b == "Not due" else f"{b} days", format=f"{cur}%,.0f")
                                        for b in buckets})
        st.subheader("Portfolio")
        cols = ["project_id", "customer", "ctb_status", "contract", "pending_changes", "budget", "actual", "committed", "etc", "eac",
                "margin_sold_pct", "margin_forecast_pct", "margin_fade_pts", "poc_pct", "earned", "billed", "unbilled",
                "billings_in_excess", "ar_open", "ar_overdue", "billing_at_risk_fy"]
        pct = {c: st.column_config.NumberColumn(c.replace("_pct", "").replace("_", " ").capitalize() + " %", format="%.1f%%")
               for c in ("margin_sold_pct", "margin_forecast_pct", "poc_pct")}
        table(pj[cols], {**money_cols(cur, "contract", "pending_changes", "budget", "actual", "committed", "etc", "eac", "earned",
                                      "billed", "unbilled", "billings_in_excess", "ar_open", "ar_overdue", "billing_at_risk_fy"),
                         **pct, "ctb_status": st.column_config.TextColumn("Material status"),
                         "etc": st.column_config.NumberColumn("ETC", format=f"{cur}%,.0f"),
                         "eac": st.column_config.NumberColumn("EAC", format=f"{cur}%,.0f"),
                         "margin_fade_pts": st.column_config.NumberColumn("Fade (pts)", format="%+.1f")})
        st.subheader("Project drilldown")
        flagged = pj.sort_values(["due_not_invoiced", "margin_fade_pts"], ascending=False)["project_id"].iloc[0]
        plist = pj["project_id"].tolist()
        pid = st.selectbox("Project", plist, index=plist.index(flagged),
                           format_func=lambda x: f"{x} {pj.set_index('project_id').at[x, 'customer']}", key="fin_project")
        p = pj.set_index("project_id").loc[pid]
        b = st.columns(5)
        b[0].metric("Contract", fmt_money(p["contract"], cur), f"{fmt_money(p['pending_changes'], cur)} pending" if p["pending_changes"] else None,
                    delta_color="off", **NOARROW)
        b[1].metric("EAC", fmt_money(p["eac"], cur), f"{fmt_money(-p['cost_variance'], cur)} vs budget" if p["cost_variance"] else None,
                    delta_color="inverse")
        b[2].metric("Margin forecast", f"{p['margin_forecast_pct']:.1f}%", f"{-p['margin_fade_pts']:+.1f} pts vs sold")
        b[3].metric("Percent complete", f"{p['poc_pct']:.0f}%")
        b[4].metric("Unbilled", fmt_money(p["unbilled"], cur))
        d1, d2 = st.columns([1, 1.1])
        with d1:
            st.markdown("**Cost to complete by element**")
            table(fi.wbs[fi.wbs["project_id"] == pid].drop(columns="project_id"),
                  {**money_cols(cur, "as_sold", "budget", "actual", "committed"),
                   "etc": st.column_config.NumberColumn("ETC", format=f"{cur}%,.0f"),
                   "eac": st.column_config.NumberColumn("EAC", format=f"{cur}%,.0f"),
                   "variance": st.column_config.NumberColumn("Variance (budget − EAC)", format=f"{cur}%,.0f")})
            st.caption("Material committed = open POs pegged to this project at PO price. Material ETC = stock still to issue "
                       "plus shortages at standard cost. Other elements: budget remaining unless an ETC override is entered.")
        with d2:
            st.markdown("**Billing milestones**")
            ms = fi.milestones[fi.milestones["project_id"] == pid]
            table(ms[["milestone_id", "name", "trigger", "pct", "amount", "planned_date", "forecast_date", "slip_days", "status",
                      "invoice_no", "paid_date"]],
                  {**money_cols(cur, "amount"), "pct": st.column_config.NumberColumn("%", format="%.0f%%"),
                   "milestone_id": st.column_config.TextColumn("#"),
                   "planned_date": st.column_config.DateColumn("Planned"), "forecast_date": st.column_config.DateColumn("Forecast"),
                   "paid_date": st.column_config.DateColumn("Paid")})
        e1, e2 = st.columns(2)
        with e1:
            st.markdown("**Change orders**")
            co = fi.change_orders[fi.change_orders["project_id"] == pid]
            if len(co):
                table(co.drop(columns=["project_id", "customer"]), money_cols(cur, "price_change", "cost_change"))
            else:
                st.caption("No change orders.")
        with e2:
            st.markdown("**Submittals**")
            sb = fi.submittals[fi.submittals["project_id"] == pid]
            if len(sb):
                table(sb.drop(columns=["project_id"]))
            else:
                st.caption("No submittals.")
        st.download_button(f"Project review PDF: {pid}", project_review_pdf(r, [pid]), f"project_review_{pid}.pdf", "application/pdf",
                           help="Portfolio page plus this project's page.")
        st.subheader("Change orders and submittals, all projects")
        g1, g2 = st.columns(2)
        with g1:
            table(fi.change_orders, money_cols(cur, "price_change", "cost_change"))
        with g2:
            sb = fi.submittals
            table(sb[sb["overdue"] | sb["blocked"] | sb["returned"].isna()])
            st.caption("Open submittals. A submittal that holds a milestone (M2) delays that invoice; one that holds 'release' "
                       "delays the supplier's production release.")

# ---------------- Team & KPIs ----------------
with tabs[10]:
    tm = r.team
    st.subheader("Department KPIs")
    dep = tm.department
    dep_t = dep[dep["target"].notna()]
    cols = st.columns(4)
    for i, x in enumerate(dep_t.itertuples()):
        unit = x.unit
        def _f(v, unit=unit):
            if unit == "$":
                return fmt_money(v, cur)
            if unit == "x":
                return f"{v:.1f}"
            if unit == "%":
                return f"{v:.1f}%" if abs(v) < 10 else f"{v:.0f}%"
            return f"{v:,.0f}"
        val, tgt = _f(x.value), _f(x.target)
        icon = "✅" if x.met else "🔴"
        cols[i % 4].metric(f"{icon} {x.label}", val, f"target {'≥' if x.better == 'higher' else '≤'} {tgt}", delta_color="off", **NOARROW)
    st.subheader("Trend")
    tr = tm.trend
    opts = sorted(tr["kpi"].unique(), key=lambda k: list(KPI).index(k) if k in KPI else 99)
    if opts:
        pick = st.selectbox("KPI", opts, format_func=lambda k: KPI.get(k, (k,))[0])
        x = tr[tr["kpi"] == pick]
        fig = go.Figure(go.Scatter(x=x["month"], y=x["value"], mode="lines+markers", line=dict(color=SERIES[0], width=2),
                                   marker=dict(size=8), name="Actual",
                                   hovertemplate="%{x|%b %Y}: %{y:,.1f}<extra></extra>"))
        if x["target"].notna().any():
            fig.add_hline(y=float(x["target"].dropna().iloc[0]), line=dict(color=INK, dash="dash", width=1),
                          annotation_text="Target")
        st.plotly_chart(_fig(fig, 300, showlegend=False), width="stretch")
        st.caption("Closed months from kpi_history; the last point is this month, calculated live.")
    st.subheader("Team scorecards")
    st.caption("Each person's KPIs are calculated for their own scope: buyers for their parts and suppliers, planners for "
               "their product family, inventory control for the whole stock. Targets come from the objectives table.")
    ppl = tm.people
    table(ppl, {"score_pct": st.column_config.ProgressColumn("KPIs met", format="%.0f%%", min_value=0, max_value=100)})
    if len(ppl):
        who = st.selectbox("Scorecard for", ppl["person_id"].tolist(),
                           format_func=lambda p: f"{ppl.set_index('person_id').at[p, 'name']} ({ppl.set_index('person_id').at[p, 'role']})")
        scx = tm.scorecards[tm.scorecards["person_id"] == who].copy()
        scx["status"] = [("✅ met" if m else "🔴 missed") if m is not None else "no target" for m in scx["met"]]
        table(scx[["label", "unit", "value", "target", "better", "status"]],
              {"value": st.column_config.NumberColumn("Value", format="%,.1f"),
               "target": st.column_config.NumberColumn("Target", format="%,.1f")})
        mine = r.alerts[r.alerts["alert_id"].isin(tm.alert_owner[tm.alert_owner == who].index)]
        st.caption(f"Open alerts for this person: {len(mine)}")
        table(mine[["alert_id", "severity", "area", "ref", "message", "action"]], height=260,
              config={"message": st.column_config.TextColumn(width="large")})

# ---------------- Meetings & actions ----------------
with tabs[11]:
    ag = r.meetings.agenda
    st.subheader("This week's meeting agenda")
    st.caption("Built from the model for each stakeholder group. Use one section per meeting, or run them in order in a "
               "single cross-functional session.")
    groups = [g for g in STAKEHOLDERS if g in set(ag["stakeholder"])]
    pick = st.multiselect("Stakeholders", groups, default=groups)
    for g in pick:
        x = ag[ag["stakeholder"] == g]
        with st.expander(f"{g} ({len(x)} items)", expanded=g in ("Production", "Finance")):
            for it in x.itertuples():
                st.markdown(f"**{it.topic}**: {it.detail}  \n<span style='color:{INK2}'>Decision or ask: {it.decision_needed}</span>",
                            unsafe_allow_html=True)
    m1, m2 = st.columns(2)
    m1.download_button("Meeting pack (PDF)", meeting_pack_pdf(r, pick or groups), f"meeting_pack_{s.as_of_date:%Y%m%d}.pdf",
                       "application/pdf", width="stretch", help="Agenda by stakeholder plus the open action log.")
    md = "\n".join([f"# Materials meeting {s.as_of_date:%d %b %Y}"] + [
        f"\n## {g}\n" + "\n".join(f"- **{i.topic}**: {i.detail}. *Ask:* {i.decision_needed}" for i in ag[ag["stakeholder"] == g].itertuples())
        for g in (pick or groups)])
    m2.download_button("Agenda as text (Markdown)", md.encode(), "agenda.md", width="stretch",
                       help="Paste into an e-mail or Teams post.")

    st.subheader("Action log")
    st.caption("Edit in place: change status to Done, move a due date, add a row. Edits last for this session; "
               "download the log (or the input workbook) to keep them, and upload it next week. "
               "Add alerts to the log from the Alerts tab.")
    act = r.meetings.actions
    a = st.columns(3)
    a[0].metric("Open actions", r.meetings.kpis["open"])
    a[1].metric("Overdue", r.meetings.kpis["overdue"])
    a[2].metric("Done", r.meetings.kpis["done"])
    team_ids = data.team["person_id"].tolist() if len(data.team) else []
    tnames = dict(zip(data.team["person_id"], data.team["name"], strict=False)) if len(data.team) else {}
    edit_cols = ["action_id", "opened", "stakeholder", "owner", "ref", "action", "due", "status", "closed", "notes"]
    base_log = st.session_state["actions_df"].copy()
    for c in ("opened", "due", "closed"):
        base_log[c] = pd.to_datetime(base_log[c], errors="coerce")
    flag = act.set_index("action_id")["overdue"] if len(act) else pd.Series(dtype=bool)
    base_log.insert(0, "overdue", base_log["action_id"].map(flag).fillna(False).astype(bool))
    edited = st.data_editor(
        base_log[["overdue"] + edit_cols], hide_index=True, width="stretch", num_rows="dynamic", key="action_editor",
        column_config={
            "overdue": st.column_config.CheckboxColumn("Overdue", disabled=True),
            "stakeholder": st.column_config.SelectboxColumn("Stakeholder", options=STAKEHOLDERS),
            "owner": st.column_config.SelectboxColumn("Owner", options=team_ids or None,
                                                      help=", ".join(f"{k} {v}" for k, v in tnames.items())),
            "status": st.column_config.SelectboxColumn("Status", options=["Open", "In progress", "Done"]),
            "opened": st.column_config.DateColumn("Opened"), "due": st.column_config.DateColumn("Due"),
            "closed": st.column_config.DateColumn("Closed"),
            "action": st.column_config.TextColumn("Action", width="large"),
            "action_id": st.column_config.TextColumn("Action id"), "ref": st.column_config.TextColumn("Ref"),
            "notes": st.column_config.TextColumn("Notes")})
    b1, b2, b3 = st.columns(3)
    if b1.button("Save edits", width="stretch", help="Apply the edits above to the model (overdue flags, scorecards, alerts)."):
        new_log = edited.drop(columns=["overdue"]).copy()
        done_now = (new_log["status"] == "Done") & new_log["closed"].isna()
        new_log.loc[done_now, "closed"] = pd.Timestamp(s.as_of_date)
        st.session_state["actions_df"] = new_log
        st.rerun()
    b2.download_button("Download action log (CSV)", st.session_state["actions_df"].to_csv(index=False, date_format="%Y-%m-%d").encode(),
                       "actions.csv", "text/csv", width="stretch")
    b3.download_button("Download input workbook with the log", workbook_bytes(data), "flowline_input.xlsx", width="stretch")

# ---------------- Alerts ----------------
with tabs[12]:
    al = r.alerts
    f = st.columns(3)
    sev = f[0].multiselect("Severity", ["Critical", "Warning", "Info"], default=["Critical", "Warning"])
    area = f[1].multiselect("Area", sorted(al["area"].unique()))
    owner = f[2].multiselect("Owner", sorted(al["owner"].unique()))
    v = al[al["severity"].isin(sev)] if sev else al
    v = v[v["area"].isin(area)] if area else v
    v = v[v["owner"].isin(owner)] if owner else v
    v = v.assign(severity=[f"{SEV_ICON[x]} {x}" for x in v["severity"]])
    owner_map = r.team.alert_owner if r.team is not None else pd.Series(dtype=object)
    tnames = dict(zip(data.team["person_id"], data.team["name"], strict=False)) if len(data.team) else {}
    v = v.assign(person=v["alert_id"].map(owner_map).map(tnames).fillna(""))
    v.insert(0, "add", False)
    picked = st.data_editor(v, hide_index=True, width="stretch", height=560, key="alert_editor",
                            disabled=[c for c in v.columns if c != "add"],
                            column_config={"add": st.column_config.CheckboxColumn("Add to log"),
                                           "message": st.column_config.TextColumn(width="large"),
                                           "action": st.column_config.TextColumn(width="medium"),
                                           "person": st.column_config.TextColumn("Person"), **money_cols(cur, "value")})
    a1, a2 = st.columns(2)
    if a1.button("Add ticked alerts to the action log", width="stretch"):
        ids = picked.loc[picked["add"], "alert_id"]
        sel = al[al["alert_id"].isin(ids)]
        if len(sel):
            st.session_state["actions_df"] = alerts_to_actions(sel, st.session_state["actions_df"], s.as_of_date, owner_map)
            st.success(f"Added {len(sel)} action(s). See Meetings & actions.")
            st.rerun()
    a2.download_button("Download alerts (CSV)", al.to_csv(index=False).encode(), "alerts.csv", "text/csv", width="stretch")

# ---------------- Data and exports ----------------
with tabs[13]:
    st.subheader("Exports")
    stamp = f"{s.as_of_date:%Y%m%d}"
    e = st.columns(5)
    e[0].download_button("Excel report", excel_report(r), f"materials_report_{stamp}.xlsx", width="stretch",
                         help="Formatted workbook: summary, alerts and every view.")
    e[1].download_button("PDF review pack", pdf_report(r), f"materials_review_{stamp}.pdf", "application/pdf",
                         width="stretch", help="The weekly pack: clear to build, inventory, suppliers and CMs, supply risk, value stream and the action list.")
    e[2].download_button("Power Query workbook", powerquery_workbook(r), f"flowline_pq_{stamp}.xlsx", width="stretch",
                         help="Every output as a named Excel Table (tbl_alerts, tbl_projects …) for Power Query or Power BI.")
    e[3].download_button("Input data workbook", workbook_bytes(data), "flowline_input.xlsx", width="stretch",
                         help="The input tables, in the upload format. Start from the sample and replace the rows.")
    if r.financials is not None:
        e[4].download_button("Project review pack", project_review_pdf(r), f"project_review_{stamp}.pdf", "application/pdf",
                             width="stretch", help="Portfolio page plus a page per project: cost to complete, margin, billing, changes.")
    st.subheader("Data check")
    if issues:
        for i in issues:
            (st.error if i.severity == "error" else st.warning)(f"**{i.table}**: {i.message}")
    else:
        st.success("No data problems found." if src != "Sample company" else "Sample data loaded. Upload your own in the sidebar.")
    st.subheader("Input tables")
    tbls = data.tables()
    t = st.selectbox("Table", list(tbls), format_func=lambda x: f"{x} ({len(tbls[x])} rows)")
    table(tbls[t])

# ---------------- Value stream ----------------
with tabs[14]:
    v = r.vsm
    if v is None:
        st.info("Add the optional table process_steps (one product family's route: process steps and the stock points "
                "between them) to see a value stream map. The sample company has one for switchgear.")
    else:
        k = v.kpis
        st.markdown(f"**Where our inventory days come from, and what better flow is worth.** This map is for **one product "
                    f"family, {v.family}**, which follows a fairly standard route. Other families and one-off projects "
                    "are not on it.")
        a = st.columns(5)
        a[0].metric("Lead time", f"{k['lead_time_days']:,.0f} days", help="Days of stock in the triangles plus process days.")
        a[1].metric("Waiting", f"{k['wait_days']:,.0f} days", help="Family inventory / family COGS per day.")
        a[2].metric("Process", f"{k['process_days']:,.1f} days", help="(C/T + C/O) / uptime, in working days.")
        a[3].metric("Value-added", f"{k['va_pct']:,.0f}%", help="Process days / lead time.")
        a[4].metric(f"Takt ({v.family})", f"{v.takt_hours:,.0f} h per unit",
                    f"{v.demand_units:,.0f} units a year", delta_color="off", **NOARROW,
                    help=f"{s.vsm_working_days} days x {s.vsm_hours_per_day:g} h / units a year (customer dates in the "
                         "next six months, doubled).")
        map_slot = st.container()
        st.caption(f"Each step stands on its own tile. Piles of crates (one per day) are the {v.family} share of today's inventory (raw and semi-finished stock split by where the parts "
                   f"are used; WIP and finished goods from the family's projects), in days of family COGS "
                   f"({fmt_money(v.daily_cogs, cur)} a day). Dashed blue lines are information flow. "
                   f"Data cards: C/T and C/O in hours per unit; 'vs takt' = (C/T + C/O) / uptime / takt. Lineups move through at the "
                   "customer's pace; press Future state on the map to see your targets below.")
        if k.get("biggest_wait"):
            st.warning(f"**Biggest wait: {k['biggest_wait']}**, {k['biggest_wait_days']:,.0f} of {k['lead_time_days']:,.0f} "
                       f"days ({fmt_money(k['biggest_wait_value'], cur)}). Start improving flow here.", icon="🟠")

        st.subheader("Future state")
        st.caption("Set target days for each stock point and target changeover times. Blank keeps today's value. "
                   "Lead time and working capital update below.")
        cur_st = v.steps
        f1, f2 = st.columns(2)
        with f1:
            stock = cur_st[cur_st["kind"] == "Stock"][["name", "days", "target_days"]].reset_index(drop=True)
            stock_ed = st.data_editor(stock, hide_index=True, width="stretch", key="vsm_stock", disabled=["name", "days"],
                                      column_config={"name": "Stock point",
                                                     "days": st.column_config.NumberColumn("Today (days)", format="%.1f"),
                                                     "target_days": st.column_config.NumberColumn("Target (days)", min_value=0.0,
                                                                                                  format="%.1f")})
        with f2:
            proc = cur_st[cur_st["kind"] == "Process"][["name", "changeover_hours", "target_changeover_hours"]].reset_index(drop=True)
            proc_ed = st.data_editor(proc, hide_index=True, width="stretch", key="vsm_co", disabled=["name", "changeover_hours"],
                                     column_config={"name": "Process step",
                                                    "changeover_hours": st.column_config.NumberColumn("C/O today (h)", format="%.1f"),
                                                    "target_changeover_hours": st.column_config.NumberColumn(
                                                        "Target C/O (h)", min_value=0.0, format="%.1f")})
        import copy as _copy
        fv = future_state(_copy.deepcopy(v),
                          {n: (t if pd.notna(t) else d) for n, d, t in zip(stock_ed["name"], stock_ed["days"],
                                                                           stock_ed["target_days"], strict=True)},
                          {n: (t if pd.notna(t) else c) for n, c, t in zip(proc_ed["name"], proc_ed["changeover_hours"],
                                                                           proc_ed["target_changeover_hours"], strict=True)})
        fk = fv.future_kpis
        b = st.columns(4)
        b[0].metric("Future lead time", f"{fk['lead_time_days']:,.0f} days", f"{fk['lead_time_change_days']:+,.0f} days",
                    delta_color="inverse")
        b[1].metric("Working capital freed", fmt_money(fk["freed_value"], cur),
                    help="(Days today − target days) x family COGS per day, summed over the stock points.")
        b[2].metric("Value-added", f"{fk['va_pct']:,.0f}%", f"{fk['va_pct'] - k['va_pct']:+,.0f} pts")
        b[3].metric("Inventory days left", f"{fk['wait_days']:,.0f} days")
        ff = fv.future
        lines = []
        for x, c in zip(ff.itertuples(), cur_st.itertuples(), strict=True):
            if x.kind == "Stock" and abs(x.target_days - c.days) >= 0.05:
                lines.append(f"- **{x.name}**: {'cut' if x.target_days < c.days else 'raise'} cover from {c.days:,.1f} to "
                             f"{x.target_days:,.1f} days → {'frees' if x.freed_value >= 0 else 'adds'} "
                             f"{fmt_money(abs(x.freed_value), cur)}, lead time {x.lead_time_change_days:+,.1f} days")
            elif x.kind == "Process" and abs(x.target_changeover_hours - c.changeover_hours) >= 0.05:
                lines.append(f"- **{x.name}**: changeover from {c.changeover_hours:,.1f} to {x.target_changeover_hours:,.1f} h → "
                             f"lead time {x.lead_time_change_days:+,.2f} days, load vs takt {c.load_pct:,.0f}% → {x.load_pct:,.0f}%")
        if lines:
            st.markdown("\n".join(lines))
        with map_slot:
            html_iso = vsm_iso_html(r, v=fv)
            if hasattr(st, "iframe"):       # Streamlit 1.5x+; components.v1.html is deprecated
                st.iframe(html_iso, height=760)
            else:
                import streamlit.components.v1 as _components
                _components.html(html_iso, height=760)   # the map scales itself to fit this frame
        st.download_button("Download the map (HTML)", html_iso, f"value_stream_{v.family.lower()}.html", "text/html",
                           help="One file that opens in any browser, offline. Good for a presentation.")
        st.caption("Shorter changeovers mostly free capacity (lower load vs takt); the lead time and the cash are in the "
                   "stock points. A target only counts once the change behind it (buying closer to need, kitting later, "
                   "shipping on completion) is in place.")
        st.subheader("Steps")
        g1, g2 = st.columns([1, 1.6])
        with g1:
            table(cur_st[cur_st["kind"] == "Stock"][["seq", "name", "stock_type", "value", "days"]],
                  {**money_cols(cur, "value"), "days": st.column_config.NumberColumn("Days", format="%.1f")})
        with g2:
            table(cur_st[cur_st["kind"] == "Process"][["seq", "name", "cycle_time_hours", "changeover_hours", "uptime_pct",
                                                       "operators", "effective_ct_hours", "load_pct", "process_days"]],
                  {"cycle_time_hours": st.column_config.NumberColumn("C/T (h)", format="%.0f"),
                   "changeover_hours": st.column_config.NumberColumn("C/O (h)", format="%.1f"),
                   "uptime_pct": st.column_config.NumberColumn("Uptime", format="%.0f%%"),
                   "effective_ct_hours": st.column_config.NumberColumn("Effective C/T (h)", format="%.1f"),
                   "load_pct": st.column_config.NumberColumn("vs takt", format="%.0f%%"),
                   "process_days": st.column_config.NumberColumn("Process days", format="%.2f")})
