"""Project financials: cost to complete from the material plan, margin, milestones, receivables, changes, submittals."""

from datetime import timedelta

import pandas as pd
import pytest
from test_engine import ASOF, po, tiny

from flowline.engine import run
from flowline.models import normalize
from flowline.sample import build_sample


def fin(pos=None, on_hand_part=0.0, start_in=30, milestones=None, actuals=None, cos=None, subs=None, sell=1000.0):
    d = tiny(pos=pos, on_hand_part=on_hand_part, start_in=start_in)
    d.projects = normalize("projects", d.projects.assign(sell_value=sell))
    d.wbs_budget = normalize("wbs_budget", pd.DataFrame([
        dict(project_id="P1", cost_element="Material", as_sold=600, budget=600),
        dict(project_id="P1", cost_element="Labour", as_sold=100, budget=100)]))
    d.cost_actuals = normalize("cost_actuals", pd.DataFrame(actuals or [
        dict(project_id="P1", cost_element="Labour", cost_to_date=40, etc_override=0)]))
    d.billing_milestones = normalize("billing_milestones", pd.DataFrame(milestones or [
        dict(project_id="P1", milestone_id="M1", name="Order", trigger="Order", pct=10, planned_date=ASOF - timedelta(days=90),
             invoice_no="INV-1", invoice_date=ASOF - timedelta(days=90), amount_invoiced=100, paid_date=ASOF - timedelta(days=50)),
        dict(project_id="P1", milestone_id="M2", name="Build start", trigger="Build start", pct=40,
             planned_date=ASOF + timedelta(days=start_in)),
        dict(project_id="P1", milestone_id="M3", name="Shipment", trigger="Shipment", pct=50,
             planned_date=ASOF + timedelta(days=start_in + 20))]))
    if cos is not None:
        d.change_orders = normalize("change_orders", pd.DataFrame(cos))
    if subs is not None:
        d.submittals = normalize("submittals", pd.DataFrame(subs))
    return d


def test_no_financial_tables_means_no_module():
    assert run(tiny()).financials is None


def test_material_cost_to_complete_comes_from_the_material_plan():
    # 6 parts needed: 2 in stock (std 100), 3 on a pegged PO at 120, 1 still to buy
    d = fin(pos=[{**po(3, 10, project="P1"), "unit_price": 120}], on_hand_part=2)
    f = run(d).financials
    m = f.wbs.set_index("cost_element").loc["Material"]
    assert m.committed == pytest.approx(360)          # PO at PO price
    assert m.etc == pytest.approx(300)                # stock 2 + shortage 1 at standard
    assert m.eac == pytest.approx(660)
    lab = f.wbs.set_index("cost_element").loc["Labour"]
    assert lab.etc == pytest.approx(60)               # budget remaining
    p = f.projects.iloc[0]
    assert p.eac == pytest.approx(760)               # 360 + 300 + labour 40 actual + 60 to go
    assert p.margin_sold_pct == pytest.approx(30.0)
    assert p.margin_forecast_pct == pytest.approx(24.0)
    assert p.margin_fade_pts == pytest.approx(6.0)


def test_etc_override_replaces_budget_remaining():
    d = fin(actuals=[dict(project_id="P1", cost_element="Labour", cost_to_date=40, etc_override=150)])
    lab = run(d).financials.wbs.set_index("cost_element").loc["Labour"]
    assert lab.eac == pytest.approx(190)


def test_milestone_reached_without_invoice_is_critical():
    d = fin(start_in=-5, on_hand_part=6)               # build started 5 days ago, no invoice for M2
    d.projects = normalize("projects", d.projects.assign(status="In build"))
    r = run(d)
    ms = r.financials.milestones.set_index("milestone_id")
    assert ms.at["M2", "status"] == "Due, not invoiced"
    assert r.financials.kpis["due_not_invoiced"] == pytest.approx(400)
    al = r.alerts[r.alerts["area"] == "Project financials"]
    assert (al["severity"] == "Critical").any()


def test_shipment_milestone_follows_the_forecast_ship_date():
    # no parts and only 5 days to start with a 20-day lead time: the build is late, so the shipment milestone slips
    r = run(fin(start_in=5))
    ms = r.financials.milestones.set_index("milestone_id")
    p = r.ctb.projects.iloc[0]
    assert ms.at["M3", "forecast_date"] == pd.Timestamp(p.forecast_ship)
    assert ms.at["M3", "slip_days"] > 0


def test_billing_slipping_past_year_end_is_at_risk():
    from dataclasses import replace
    d = fin(start_in=5)                                     # late: build start and shipment both move about 3 weeks
    d.settings = replace(d.settings, fiscal_year_end=ASOF + timedelta(days=20))   # shipment planned day 25 -> in FY? no; start day 5 -> yes
    r = run(d)
    k = r.financials.kpis
    ms = r.financials.milestones.set_index("milestone_id")
    expected = sum(ms.at[m, "amount"] for m in ms.index if ms.at[m, "planned_in_fy"] and not ms.at[m, "forecast_in_fy"])
    assert expected > 0
    assert k["billing_at_risk_fy"] == pytest.approx(expected)


def test_receivables_aging_and_overdue_alert():
    ms = [dict(project_id="P1", milestone_id="M1", name="Order", trigger="Order", pct=100, planned_date=ASOF - timedelta(days=120),
               invoice_no="INV-9", invoice_date=ASOF - timedelta(days=120), amount_invoiced=1000)]
    r = run(fin(milestones=ms))
    ar = r.financials.receivables.iloc[0]
    assert ar.days_overdue == 120 - r.settings.payment_terms_days
    assert ar.bucket == "61-90"
    al = r.alerts[(r.alerts["area"] == "Project financials") & r.alerts["message"].str.contains("INV-9")]
    assert al.iloc[0].severity == "Critical"


def test_approved_change_order_adds_to_contract_and_pending_is_tracked():
    cos = [dict(co_id="CO1", project_id="P1", description="Extra", price_change=200, cost_change=120, cost_element="Labour",
                status="Approved", submitted=ASOF - timedelta(days=60), decided=ASOF - timedelta(days=40)),
           dict(co_id="CO2", project_id="P1", description="More", price_change=50, cost_change=30, cost_element="Labour",
                status="Pending", submitted=ASOF - timedelta(days=45))]
    f = run(fin(cos=cos)).financials
    p = f.projects.iloc[0]
    assert p.contract == pytest.approx(1200)
    assert p.pending_changes == pytest.approx(50)
    assert f.kpis["cos_stale"] == 1


def test_open_drawing_submittal_holds_the_drawings_milestone():
    subs = [dict(submittal_id="S1", project_id="P1", direction="Customer", document="GA drawings", party="C",
                 submitted=ASOF - timedelta(days=30), due=ASOF - timedelta(days=5), status="Open", holds="M2")]
    ms = [dict(project_id="P1", milestone_id="M2", name="Drawings approved", trigger="Drawings approved", pct=20,
               planned_date=ASOF - timedelta(days=5))]
    f = run(fin(milestones=ms, subs=subs)).financials
    assert f.submittals.iloc[0].overdue
    m = f.milestones.iloc[0]
    assert m.status == "Planned" and m.forecast_date > pd.Timestamp(ASOF)


def test_sample_story():
    r = run(build_sample())
    f = r.financials
    ms = f.milestones
    late = ms[ms["status"] == "Due, not invoiced"]
    assert list(zip(late["project_id"], late["milestone_id"], strict=True)) == [("P-2602", "M2")]
    assert f.kpis["contract"] == pytest.approx(10_632_500, rel=0.01)
    assert f.kpis["margin_forecast_pct"] < f.kpis["margin_sold_pct"]
    assert f.kpis["billing_at_risk_fy"] > 0
    assert f.kpis["submittals_overdue"] == 3
    assert r.summary()["alerts_critical"] == 6
