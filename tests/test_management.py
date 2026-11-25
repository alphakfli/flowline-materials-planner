from datetime import date, timedelta
from math import sqrt
from statistics import NormalDist

import pandas as pd
import pytest

from flowline import build_sample, run
from flowline.engine import Scenario
from flowline.io.importer import load_files, workbook_bytes
from flowline.meetings import alerts_to_actions, prepare_actions
from flowline.models import Dataset, Settings, normalize
from flowline.reports import meeting_pack_pdf

ASOF = date(2027, 3, 1)


@pytest.fixture(scope="module")
def res():
    return run(build_sample())


def small(**tables) -> Dataset:
    items = pd.DataFrame([dict(item_id="TOP", item_type="FG", make_buy="make", lead_time_days=5),
                          dict(item_id="NUT", item_type="RM", make_buy="buy", std_cost=2, lead_time_days=30,
                               supplier_id="S1", buyer="B1", safety_stock=10, description="Nut")])
    bom = pd.DataFrame([dict(parent_item="TOP", component_item="NUT", qty_per=1)])
    pj = pd.DataFrame([dict(project_id="P1", top_item="TOP", qty=1, status="Built", product_family="F",
                            planned_build_start=ASOF - timedelta(days=30), required_ship_date=ASOF + timedelta(days=5))])
    d = Dataset(normalize("items", items), normalize("bom", bom), normalize("projects", pj),
                settings=Settings(as_of_date=ASOF, fiscal_year_end=date(2027, 12, 31)))
    for k, v in tables.items():
        setattr(d, k, normalize(k, pd.DataFrame(v)))
    return d


def test_safety_stock_formula():
    use = [100, 120, 80, 100, 110, 90]       # mean 100, sample sd ~14.14
    d = small(consumption_history=[dict(item_id="NUT", month=f"2027-0{i + 1}" if i < 2 else f"2026-{i + 5:02d}", qty=q)
                                   for i, q in enumerate(use)])
    r = run(d)
    row = r.risk.safety_stock.iloc[0]
    sd = pd.Series(use, dtype=float).std(ddof=1)
    z = NormalDist().inv_cdf(0.95)
    expected = z * sqrt(30 / 30.4 * sd ** 2)   # no receipts, so no delivery-delay variance
    assert row.recommended_ss == pytest.approx(int(expected) + 1)
    assert row.recommendation == "Raise"       # current 10, recommended ~24


def test_risk_register_scores_and_detection(res):
    reg = res.risk.register
    assert set(reg["source"]) == {"Register", "Detected"}
    assert (reg["score"] == reg["likelihood"] * reg["impact"]).all()
    assert reg.iloc[0]["score"] >= reg.iloc[-1]["score"]
    assert reg["risk"].str.contains("Long-lead part not ordered: OLTC-75 for P-2613").any()


def test_logistics_and_premium_freight(res):
    lsp = res.risk.logistics.set_index("lsp")
    assert lsp.loc["Cascade Expedite", "premium_shipments"] == lsp.loc["Cascade Expedite", "shipments"]
    assert res.risk.kpis["premium_freight"] == pytest.approx(lsp["premium_cost"].sum())


def test_cost_pipeline_weights_and_quote_opportunity(res):
    sp = res.cost.pipeline
    assert res.cost.kpis["weighted_pipeline"] == pytest.approx((sp["annual_savings"] * sp["weight"]).sum())
    assert res.cost.kpis["realized"] == pytest.approx(186000)
    op = res.cost.opportunities
    core = op[(op["category"] == "Alternative source") & (op["item_id"] == "CORE-2500")]
    assert len(core) == 1 and core.iloc[0].annual_value > 0
    # the breaker second source is already a savings project, so it is not listed again
    assert not ((op["category"] == "Alternative source") & (op["item_id"] == "VCB-15-1200")).any()


def test_team_scorecards_use_each_scope(res):
    sc = res.team.scorecards
    maya = sc[(sc["name"] == "Maya") & (sc["kpi"] == "savings_realized")].iloc[0]
    assert maya.value == pytest.approx(6000 + 66000)            # SP-01 and SP-09 realized
    leah = sc[(sc["name"] == "Leah") & (sc["kpi"] == "late_projects")].iloc[0]
    assert leah.value == 0                                       # switchgear has no late project
    tomas = sc[(sc["name"] == "Tomas") & (sc["kpi"] == "late_projects")].iloc[0]
    assert tomas.value == 2                                      # both late projects are transformers
    mgr = res.team.people.set_index("person_id").loc["P00"]
    assert mgr.kpis_with_target == res.team.kpis["dept_with_target"]


def test_alerts_are_given_to_people(res):
    own = res.team.alert_owner
    assert len(own) == len(res.alerts)
    al = res.alerts.set_index("alert_id")
    p2606 = al[al["ref"] == "P-2606"].index[0]
    assert own[p2606] == "P06"                                   # transformer planner


def test_action_log_overdue_and_add_from_alerts(res):
    acts = res.meetings.actions
    assert set(acts.loc[acts["overdue"], "action_id"]) == {"A-102", "A-104", "A-106"}
    log = res.data.actions
    sel = res.alerts.head(3)
    new = alerts_to_actions(sel, log, ASOF, res.team.alert_owner)
    assert len(new) == len(log) + 3
    assert new.iloc[-1]["action_id"] == "A-113"
    again = alerts_to_actions(sel, normalize("actions", new), ASOF)
    assert len(again) == len(new)                                # same alerts are not added twice
    p = prepare_actions(normalize("actions", new), ASOF + timedelta(days=30))
    assert p["overdue"].sum() >= 3


def test_agenda_covers_each_stakeholder(res):
    ag = res.meetings.agenda
    assert {"Production", "Engineering", "Contracts", "Finance", "Suppliers and CMs"} <= set(ag["stakeholder"])
    prod = ag[ag["stakeholder"] == "Production"]
    assert prod["topic"].str.contains("Release P-2605").any()
    assert ag[ag["stakeholder"] == "Contracts"]["topic"].str.contains("P-2606").any()


def test_new_tables_round_trip_and_pack(res):
    data, issues = load_files({"in.xlsx": workbook_bytes(build_sample())})
    assert not [i for i in issues if i.severity == "error"]
    for t in ("team", "objectives", "kpi_history", "actions", "consumption_history", "risk_register", "shipments",
              "savings_projects"):
        assert len(getattr(data, t)) == len(getattr(res.data, t)), t
    again = run(data).summary()
    for k in ("dept_kpis_met", "actions_overdue", "risks_high", "savings_realized"):
        assert again[k] == pytest.approx(res.summary()[k])
    assert meeting_pack_pdf(res)[:4] == b"%PDF"


def test_scenario_flows_into_team_kpis():
    d = build_sample()
    base = run(d).team.department.set_index("kpi")
    slip = run(d, Scenario(supplier_delay={"S100": 30})).team.department.set_index("kpi")
    assert slip.loc["late_projects", "value"] > base.loc["late_projects", "value"]
