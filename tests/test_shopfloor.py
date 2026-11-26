"""Shop floor: today's plan vs capacity, the SQDCC board, misses, skills coverage, ERP items and kits short."""

from datetime import timedelta

import pandas as pd
import pytest
from test_engine import ASOF, tiny

from flowline.engine import run
from flowline.models import normalize
from flowline.reports import tier_board_pdf
from flowline.reports.tables import output_tables
from flowline.sample import build_sample

T = pd.Timestamp(ASOF)


def shop(**kw):
    d = tiny(on_hand_part=kw.get("on_hand", 10), start_in=kw.get("start_in", 30))
    d.work_centers = normalize("work_centers", pd.DataFrame([
        dict(wc_id="A", name="Assembly", shift_hours=8, shifts=1, people_needed=2),
        dict(wc_id="T", name="Test", shift_hours=8, shifts=1, people_needed=1)]))
    d.shop_schedule = normalize("shop_schedule", pd.DataFrame([
        dict(date=T - timedelta(days=1), wc_id="A", planned_hours=16, earned_hours=16, actual_hours=17, people_needed=2,
             people_assigned=2, overtime_hours=1),
        dict(date=T, wc_id="A", project_id="P1", operation="Build P1", planned_hours=16, earned_hours=kw.get("earned", 6),
             actual_hours=8, people_needed=2, people_assigned=kw.get("here", 1)),
        dict(date=T, wc_id="T", planned_hours=8, earned_hours=4, actual_hours=4, people_needed=1, people_assigned=1)]))
    d.hourly_output = normalize("hourly_output", pd.DataFrame(
        [dict(date=T, hour=h, wc_id="A", planned_hours=2, earned_hours=1.5) for h in (7, 8, 9, 10)]))
    d.quality_checks = normalize("quality_checks", pd.DataFrame([dict(date=T, wc_id="T", inspected=5, passed=kw.get("passed", 4),
                                                                      defect="Hi-pot fail")]))
    d.safety_events = normalize("safety_events", pd.DataFrame(kw.get("safety", [dict(date=T - timedelta(days=30), wc_id="A",
                                                                                      type="Recordable", description="x")])))
    d.operators = normalize("operators", pd.DataFrame([dict(operator_id="O1", name="Ann", shift="Day", home_wc="A"),
                                                       dict(operator_id="O2", name="Ben", shift="Day", home_wc="A"),
                                                       dict(operator_id="O3", name="Cy", shift="Day", home_wc="T")]))
    d.skills = normalize("skills", pd.DataFrame([dict(operator_id="O1", wc_id="A", level=4), dict(operator_id="O2", wc_id="A", level=3),
                                                 dict(operator_id="O3", wc_id="T", level=3), dict(operator_id="O2", wc_id="T", level=2)]))
    d.erp_open_items = normalize("erp_open_items", pd.DataFrame([
        dict(ref="C1", kind="Completion not posted", wc_id="T", project_id="P1", created=T - timedelta(days=3), value=500,
             note="blocks shipment"),
        dict(ref="S1", kind="Scrap not posted", wc_id="A", created=T, value=10)]))
    d.countermeasures = normalize("countermeasures", pd.DataFrame(kw.get("cms", [])) if kw.get("cms") else pd.DataFrame(
        columns=["cm_id"]))
    return d


def test_no_tables_means_no_module():
    assert run(tiny()).shop is None


def test_attainment_to_the_current_hour():
    f = run(shop()).shop
    assert f.now_hour == 11 and f.elapsed == pytest.approx(0.5)
    a = f.plan.set_index("wc_id").loc["A"]
    assert a.planned_to_now == pytest.approx(8)
    assert a.attainment_pct == pytest.approx(75)
    assert a.productivity_pct == pytest.approx(75)
    assert a.people_short == 1
    assert f.kpis["attainment_pct"] == pytest.approx(10 / 12 * 100)


def test_tier_board_letters_and_status():
    f = run(shop()).shop
    t = f.tier.set_index("tier")
    assert list(f.tier["tier"]) == ["Safety", "Quality", "Delivery", "Cost", "Cash"]
    assert t.at["Safety", "status"] == "Green" and "30 days" in t.at["Safety", "detail"]
    assert t.at["Quality", "value"] == pytest.approx(80) and t.at["Quality", "status"] == "Red"
    assert t.at["Cash", "value"] == pytest.approx(500) and t.at["Cash", "status"] == "Red"


def test_incident_today_is_red_and_critical():
    r = run(shop(safety=[dict(date=T, wc_id="A", type="First aid", description="cut")]))
    assert r.shop.tier.set_index("tier").at["Safety", "status"] == "Red"
    al = r.alerts[(r.alerts["area"] == "Shop floor") & (r.alerts["severity"] == "Critical")]
    assert al["message"].str.contains("First aid").any()


def test_misses_link_to_open_countermeasures():
    cms = [dict(cm_id="CM1", date=T - timedelta(days=2), tier="Tier 1", metric="Quality", wc_id="T", miss="FPY", cause="torque",
                countermeasure="Torque check", owner="Lead", due=T + timedelta(days=2), status="Open")]
    m = run(shop(cms=cms)).shop.misses
    q = m[m["metric"] == "Quality"].iloc[0]
    assert q.cm_id == "CM1" and q.needs.startswith("Escalate")
    d = m[(m["metric"] == "Delivery") & (m["wc_id"] == "A")].iloc[0]
    assert d.countermeasure == "" and d.needs == "Needs a countermeasure today"


def test_skills_coverage_and_training_plan():
    f = run(shop()).shop
    c = f.coverage.set_index("wc_id")
    assert c.at["A", "qualified"] == 2 and c.at["A", "gap"] == 0
    assert c.at["T", "qualified"] == 1 and c.at["T", "minimum"] == 2 and c.at["T", "gap"] == 1
    tr = f.training.iloc[0]
    assert tr.operator == "Ben" and tr.work_center == "Test"


def test_erp_age_and_completion_alert():
    r = run(shop())
    e = r.shop.erp.set_index("ref")
    assert e.at["C1", "age_days"] == 3 and bool(e.at["C1", "overdue"])
    assert not bool(e.at["S1", "overdue"])
    al = r.alerts[(r.alerts["area"] == "Shop floor") & (r.alerts["ref"] == "C1")]
    assert al.iloc[0].severity == "Critical"


def test_kits_short_come_from_clear_to_build():
    f = run(shop(on_hand=2, start_in=5)).shop      # build in 5 days, 4 of 6 parts missing
    assert len(f.kits) >= 1 and f.kits["qty"].sum() == pytest.approx(4)
    assert run(shop()).shop.kits.empty                # full kit, build in 30 days
    assert len(f.kits) >= 1 and set(f.kits["project_id"]) == {"P1"}


def test_sample_story_and_exports():
    r = run(build_sample())
    f = r.shop
    t = f.tier.set_index("tier")["status"]
    assert t["Delivery"] == "Red" and t["Cash"] == "Red" and t["Safety"] == "Green"
    red = set(f.plan.loc[f.plan["status"] == "Red", "wc_id"])
    assert red == {"KIT", "SWA", "TST"}
    assert f.downtime.iloc[0]["reason"] == "Waiting for material"
    assert set(f.kits["item_id"]) == {"CORE-2500", "RAD-1200"}
    assert f.coverage.set_index(["wc_id", "shift"]).at[("TST", "Day"), "qualified"] == 1
    assert {"tier_board", "shop_plan", "skills_matrix", "erp_to_clear", "kits_short"} <= set(output_tables(r))
    assert tier_board_pdf(r)[:4] == b"%PDF"
