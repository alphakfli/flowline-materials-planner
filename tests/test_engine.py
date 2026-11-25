from datetime import date, timedelta

import pandas as pd
import pytest

from flowline.ctb import rolled_cost, run_ctb
from flowline.engine import Scenario, run
from flowline.models import Dataset, Settings, normalize

ASOF = date(2027, 3, 1)


def tiny(on_hand_part=0.0, pos=None, receipts=None, sa_stock=0.0, start_in=30, ship_slack=10) -> Dataset:
    """One project: top item TOP <- 2 x SA (make, 5 days) <- 3 x PART (buy, 20 days lead, 100 each)."""
    items = pd.DataFrame([
        dict(item_id="TOP", item_type="FG", make_buy="make", std_cost=0, lead_time_days=10, on_hand=0),
        dict(item_id="SA", item_type="SFG", make_buy="make", std_cost=300, lead_time_days=5, on_hand=sa_stock),
        dict(item_id="PART", item_type="RM", make_buy="buy", std_cost=100, lead_time_days=20, supplier_id="S1",
             on_hand=on_hand_part, description="Widget"),
    ])
    bom = pd.DataFrame([dict(parent_item="TOP", component_item="SA", qty_per=2),
                        dict(parent_item="SA", component_item="PART", qty_per=3)])
    start = ASOF + timedelta(days=start_in)
    projects = pd.DataFrame([dict(project_id="P1", customer="C", top_item="TOP", qty=1, status="Released",
                                  planned_build_start=start, build_days=10,
                                  required_ship_date=start + timedelta(days=10 + ship_slack))])
    d = Dataset(normalize("items", items), normalize("bom", bom), normalize("projects", projects),
                settings=Settings(as_of_date=ASOF, fiscal_year_end=date(2027, 12, 31)))
    if pos is not None:
        d.purchase_orders = normalize("purchase_orders", pd.DataFrame(pos))
    if receipts is not None:
        d.receipts = normalize("receipts", pd.DataFrame(receipts))
    return d


def po(qty, days, project="", n="1"):
    return dict(po_number=n, po_line=10, item_id="PART", supplier_id="S1", qty_open=qty, unit_price=100,
                promised_date=ASOF + timedelta(days=days), project_id=project)


def test_rolled_cost():
    assert rolled_cost(tiny())["TOP"] == pytest.approx(600)


def test_clear_to_build_from_stock():
    r = run_ctb(tiny(on_hand_part=6), tiny().settings)
    p = r.projects.iloc[0]
    assert p.ctb_status == "Clear to build"
    assert p.on_hand_pct == pytest.approx(100)
    assert r.shortages.empty


def test_sub_assembly_stock_is_netted_first():
    r = run_ctb(tiny(sa_stock=2), tiny().settings)
    assert r.projects.iloc[0].ctb_status == "Clear to build"
    assert "PART" not in set(r.requirements["item_id"])   # nothing to build, so no parts needed


def test_po_in_time_is_clear_by_start():
    d = tiny(pos=[po(6, 10)])
    r = run_ctb(d, d.settings)
    p = r.projects.iloc[0]
    assert p.ctb_status == "Clear by start"
    assert p.material_ready == ASOF + timedelta(days=15)      # PO + 5 days to build the sub-assembly


def test_late_po_makes_project_late_and_names_gating_part():
    d = tiny(pos=[po(6, 40)], ship_slack=5)
    r = run_ctb(d, d.settings)
    p = r.projects.iloc[0]
    assert p.material_ready == ASOF + timedelta(days=45)
    assert p.gating_item == "PART"
    assert p.ctb_status == "Late" and p.days_late == 10          # can start day 45, ship day 55, due day 45
    assert r.po_actions.iloc[0].action == "Expedite"


def test_float_absorbs_small_slip():
    d = tiny(pos=[po(6, 28)], ship_slack=10)   # ready day 33, start was day 30, ships day 43 vs due 50
    r = run_ctb(d, d.settings)
    assert r.projects.iloc[0].ctb_status == "At risk"


def test_no_supply_uses_lead_time_from_today():
    d = tiny(start_in=10)
    r = run_ctb(d, d.settings)
    p = r.projects.iloc[0]
    assert p.material_ready == ASOF + timedelta(days=25)          # buy today (20) + build sub-assembly (5)
    assert r.shortages.iloc[0].short_qty == 6
    assert r.shortages.iloc[0].issue == "No supply, late"


def test_pegged_po_is_not_used_by_other_project():
    d = tiny(pos=[po(6, 5, project="OTHER")])
    r = run_ctb(d, d.settings)
    assert r.requirements.query("item_id == 'PART'").iloc[0].short_qty == 6
    assert r.po_actions.iloc[0].action == "Cancel"


def test_past_due_po_arrives_after_set_days():
    d = tiny(pos=[po(6, -10)])
    r = run_ctb(d, d.settings)
    lot = [x for x in r.lots if x.kind == "PO"][0]
    assert lot.past_due and lot.date == ASOF + timedelta(days=d.settings.past_due_arrival_days)


def test_push_out_and_reduce_with_year_end_impact():
    d = tiny(pos=[po(10, 5)], start_in=300)   # needed late next year, arrives now, 4 too many
    d.settings = Settings(as_of_date=ASOF, fiscal_year_end=date(2027, 6, 30))
    r = run_ctb(d, d.settings)
    a = r.po_actions.iloc[0]
    assert a.action == "Push out + reduce"
    assert a.year_end_impact == pytest.approx(10 * 100)        # all 10 leave the year-end balance
    res = run(d, Scenario(apply_push_outs=True))
    lot = [x for x in res.ctb.lots if x.kind == "PO"][0]
    assert lot.qty == 6 and lot.date == a.suggested_date


def test_inventory_flows_and_turns():
    d = tiny(on_hand_part=6)
    d.inventory_history = normalize("inventory_history", pd.DataFrame(
        [dict(month=f"2026-{m:02d}", raw_materials=600, cogs=200) for m in range(3, 13)] +
        [dict(month="2027-01", raw_materials=600, cogs=200), dict(month="2027-02", raw_materials=600, cogs=200)]))
    r = run(d)
    k = r.inventory.kpis
    assert k["inventory_now"] == pytest.approx(600)
    assert k["cogs_t12m"] == pytest.approx(2400)
    assert k["turns_now"] == pytest.approx(4.0)
    ev = r.inventory.events
    assert ev["value"].sum() == pytest.approx(-600)        # everything shipped out by year end
    ship = ev[ev["kind"] == "Shipment"]["value"].sum()
    assert ship == pytest.approx(-600 * 1.25)               # material plus 25% conversion
    assert k["year_end"] == pytest.approx(0)


def test_supplier_otd_window_and_ppv():
    rec = [dict(po_number="a", item_id="PART", supplier_id="S1", promised_date=ASOF - timedelta(days=30),
                receipt_date=ASOF - timedelta(days=30 + e), qty=1, unit_price=p, std_cost=100)
           for e, p in [(0, 100), (5, 100), (6, 110), (-1, 100)]]   # on time, 5 early (ok), 6 early, 1 late
    d = tiny(receipts=rec)
    d.suppliers = pd.DataFrame([dict(supplier_id="S1", name="One", supplier_type="Supplier", region="", commodity="")])
    sc = run(d).suppliers.scorecard.iloc[0]
    assert sc.otd_pct == pytest.approx(50)
    assert sc.ppv == pytest.approx(10)
    assert sc.single_source_items == 1


def test_sample_story_is_stable():
    from flowline import build_sample
    r = run(build_sample())
    s = r.summary()
    assert s["projects_open"] == 11
    assert s["projects_late"] == 2
    late = r.ctb.projects.query("ctb_status == 'Late'")
    assert set(late["gating_item"]) == {"OLTC-75"}
    assert s["year_end_gap"] > 0
    assert s["push_out_value"] + s["excess_value"] > s["year_end_gap"]   # the levers can close the gap
    assert run(build_sample(), Scenario(apply_push_outs=True)).summary()["year_end_gap"] < 0
    assert (r.alerts["severity"] == "Critical").sum() >= 3
    ll = r.ctb.long_lead
    assert "Order overdue" in set(ll.loc[ll["project_id"] == "P-2613", "status"])


def test_supplier_slip_worsens_delivery():
    from flowline import build_sample
    d = build_sample()
    base, slip = run(d).summary(), run(d, Scenario(supplier_delay={"S100": 30})).summary()
    assert slip["projects_late"] > base["projects_late"]
