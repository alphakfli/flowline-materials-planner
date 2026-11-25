"""Value stream map: stock days from inventory, takt, lead time ladder, future state."""

import pandas as pd
import pytest
from test_engine import ASOF, tiny

from flowline.engine import run
from flowline.models import normalize
from flowline.reports.tables import output_tables
from flowline.reports.vsm_draw import vsm_svg
from flowline.sample import build_sample
from flowline.vsm import future_state


def steps(**target):
    rows = [dict(seq=10, kind="Stock", name="Raw", stock_type="Raw materials", target_days=target.get("Raw")),
            dict(seq=20, kind="Process", name="Build", cycle_time_hours=12, changeover_hours=4, uptime_pct=80, operators=2,
                 target_changeover_hours=target.get("Build")),
            dict(seq=30, kind="Stock", name="FG", stock_type="Finished goods")]
    return normalize("process_steps", pd.DataFrame(rows).assign(product_family="F"))


def data(**target):
    d = tiny(on_hand_part=10)          # 10 parts x std 100 = 1,000 of raw stock, all used by P1
    d.projects = normalize("projects", d.projects.assign(product_family="F"))
    d.inventory_history = normalize("inventory_history", pd.DataFrame(
        [dict(month=pd.Timestamp(ASOF).to_period("M").to_timestamp() - pd.DateOffset(months=i), cogs=3650 / 12)
         for i in range(1, 13)]))
    d.process_steps = steps(**target)
    return d


def test_no_table_means_no_map():
    assert run(tiny()).vsm is None


def test_stock_days_process_days_and_value_added():
    v = run(data()).vsm
    raw = v.steps.set_index("name").loc["Raw"]
    assert v.daily_cogs == pytest.approx(10.0)          # 3,650 a year, one family
    assert raw.value == pytest.approx(1000)
    assert raw.days == pytest.approx(100)
    b = v.steps.set_index("name").loc["Build"]
    assert b.effective_ct_hours == pytest.approx(20)    # (12 + 4) / 0.8
    assert b.process_days == pytest.approx(20 / 16)
    k = v.kpis
    assert k["lead_time_days"] == pytest.approx(100 + 1.25)
    assert k["va_pct"] == pytest.approx(1.25 / 101.25 * 100)
    assert k["biggest_wait"] == "Raw"


def test_takt_from_customer_demand():
    v = run(data()).vsm
    # one unit due inside six months, doubled = 2 a year; 250 days x 16 h / 2
    assert v.demand_units == 2
    assert v.takt_hours == pytest.approx(2000)
    assert v.steps.set_index("name").loc["Build", "load_pct"] == pytest.approx(1.0)


def test_future_state_frees_cash_and_cuts_lead_time():
    v = run(data(Raw=40, Build=1)).vsm
    f = v.future.set_index("name")
    assert f.at["Raw", "freed_value"] == pytest.approx(600)        # 60 days x 10 a day
    assert f.at["Raw", "lead_time_change_days"] == pytest.approx(-60)
    assert f.at["Build", "effective_ct_hours"] == pytest.approx(16.25)
    assert v.future_kpis["freed_value"] == pytest.approx(600)
    assert v.future_kpis["lead_time_change_days"] == pytest.approx(-60 - (20 - 16.25) / 16)


def test_future_state_overrides_from_the_page():
    v = future_state(run(data()).vsm, {"Raw": 10}, {"Build": 0.5})
    assert v.future_kpis["freed_value"] == pytest.approx(900)


def test_biggest_wait_alert_and_exports():
    r = run(data(Raw=40))
    al = r.alerts[r.alerts["area"] == "Value stream"]
    assert len(al) == 1 and al.iloc[0].severity == "Warning"
    assert "Raw" in al.iloc[0].message
    assert "vsm" in output_tables(r)
    assert vsm_svg(r).startswith("<svg") and "Start here" in vsm_svg(r)


def test_sample_story():
    r = run(build_sample())
    v = r.vsm
    assert v.family == "Switchgear"
    assert v.kpis["biggest_wait"] == "Work in process"
    assert round(v.kpis["lead_time_days"]) == 130
    assert round(v.kpis["va_pct"]) == 12
    assert v.future_kpis["freed_value"] == pytest.approx(685_000, rel=0.01)
    # triangles add up to the family's share of today's inventory
    assert v.kpis["family_inventory"] <= r.inventory.kpis["inventory_now"]


def test_isometric_plant_view():
    from flowline.reports.vsm_iso import iso_svg, vsm_iso_html
    r = run(build_sample())
    geo = {}
    svg = iso_svg(r.vsm, "current", "$", "", geo)
    assert svg.startswith("<svg") and "Start here" in svg and "hotring" in svg
    assert len(geo["pt"]) == len(r.vsm.steps) and len(geo["wait"]) == len(r.vsm.steps)
    fut = iso_svg(r.vsm, "future")
    assert 'id="c1"' in svg and 'id="f1"' in fut and 'id="c1"' not in fut     # gradient ids differ per layer
    h = vsm_iso_html(r)
    assert "__SVG_" not in h and "importmap" not in h
