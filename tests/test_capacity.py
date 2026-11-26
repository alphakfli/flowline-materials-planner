"""Weekly capacity plan: finite loading of machines and labour, lateness, and the overtime advice."""

import pandas as pd
import pytest
from test_engine import ASOF, tiny

from flowline.capacity import plan_capacity, weekly_capacity
from flowline.engine import run
from flowline.models import normalize
from flowline.reports.tables import output_tables
from flowline.sample import build_sample

T = pd.Timestamp(ASOF)


def cap_data(qty=10, due_days=21, units=1, lag=0, start_in=0):
    d = tiny(on_hand_part=100, start_in=start_in)
    d.resources = normalize("resources", pd.DataFrame([
        dict(resource_id="M1", name="Machine", kind="Machine", wc_id="A", units=1, shifts_per_day=1, hours_per_shift=8,
             days_per_week=5, efficiency_pct=100, overtime_hours=0),
        dict(resource_id="L1", name="People", kind="Labour", wc_id="A", units=units, shifts_per_day=1, hours_per_shift=8,
             days_per_week=5, efficiency_pct=100, overtime_hours=0)]))
    d.routings = normalize("routings", pd.DataFrame([
        dict(product_family="F", seq=10, step="Make", wc_id="A", machine_id="M1", machine_hours=2, labour_id="L1", labour_hours=8),
        dict(product_family="F", seq=20, step="Pack", wc_id="A", machine_id="", machine_hours=0, labour_id="", labour_hours=0,
             lag_weeks=lag)]))
    d.projects = normalize("projects", d.projects.assign(product_family="F"))
    d.production_orders = normalize("production_orders", pd.DataFrame([
        dict(order_id="O1", project_id="P1", product_family="F", qty=qty, due_date=T + pd.Timedelta(days=due_days), priority=1)]))
    return d


def test_capacity_formula_and_calendar():
    d = cap_data()
    wk = [T - pd.Timedelta(days=T.weekday()) + pd.Timedelta(weeks=i) for i in range(2)]
    cal = normalize("capacity_calendar", pd.DataFrame([dict(week_start=wk[1], resource_id="ALL", available_pct=50)]))
    c = weekly_capacity(d.resources, wk, cal)
    assert c.loc["M1", wk[0]] == pytest.approx(40) and c.loc["M1", wk[1]] == pytest.approx(20)


def test_labour_binds_before_machine():
    d = cap_data(qty=10)                # 10 units x 8 labour h = 80 h; 40 h a week -> 2 weeks
    r = run(d)
    p = plan_capacity(d, r.ctb, d.settings, respect_planned=False, weeks=6)
    st = p.steps[p.steps["step"] == "Make"].groupby("week")["units"].sum()
    assert list(st.round(3)) == [5.0, 5.0]
    w0 = p.weeks[0]
    assert p.utilization.loc["L1", w0] == pytest.approx(100) and p.utilization.loc["M1", w0] == pytest.approx(25)


def test_late_order_held_by_labour_and_advice_fixes_it():
    d = cap_data(qty=10, due_days=5)    # needs 2 weeks, due this week
    r = run(d)
    p = plan_capacity(d, r.ctb, d.settings, respect_planned=False, weeks=6)
    o = p.orders.iloc[0]
    assert o.status == "Late" and o.held_by == "L1"
    assert p.advice is not None and len(p.advice) >= 1          # Saturdays help, but 16 h is not enough for 40 h short
    assert p.advice.iloc[-1]["units_late_after"] < p.advice.iloc[0]["units_late_before"]


def test_more_people_finishes_on_time():
    d = cap_data(qty=10, due_days=5, units=2)
    r = run(d)
    p = plan_capacity(d, r.ctb, d.settings, respect_planned=False, weeks=6)
    assert p.orders.iloc[0].status == "On time"


def test_lag_weeks_delay_the_next_step():
    d = cap_data(qty=2, lag=1)
    r = run(d)
    p = plan_capacity(d, r.ctb, d.settings, respect_planned=False, weeks=6)
    weeks = p.steps.groupby("step")["week"].min()
    assert (weeks["Pack"] - weeks["Make"]).days == 7


def test_material_holds_the_start():
    d = cap_data(qty=1, due_days=3, start_in=20)
    d.items.loc[:, "on_hand"] = 0
    r = run(d)
    p = plan_capacity(d, r.ctb, d.settings, weeks=8)
    o = p.orders.iloc[0]
    assert o.earliest_start >= T + pd.Timedelta(days=20)
    assert o.status == "Late" and o.held_by == "MATERIAL"


def test_sample_story_and_exports():
    r = run(build_sample())
    c = r.capacity
    o = c.orders.set_index("order_id")
    assert o.at["MO-2608", "status"] == "Late" and o.at["MO-2608", "held_by"] == "L-TRA"
    assert o.at["MO-2606", "held_by"] == "MATERIAL"
    assert c.advice.attrs["fixed"] and c.advice.iloc[0]["work_center"] == "TRA"
    assert {"capacity_orders", "resource_load"} <= set(output_tables(r))
    a = r.alerts
    assert (a["area"] == "Weekly capacity").sum() == 1
