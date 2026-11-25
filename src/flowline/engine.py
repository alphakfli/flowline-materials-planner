"""Run every view in one call."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd

from flowline.alerts import build_alerts
from flowline.cost import CostResult, run_cost
from flowline.ctb import CTBResult, run_ctb
from flowline.financials import FinancialResult, run_financials
from flowline.inventory import InventoryResult, project_inventory
from flowline.meetings import MeetingResult, build_agenda, run_meetings
from flowline.models import Dataset, Settings
from flowline.risk import RiskResult, run_risk
from flowline.suppliers import CMResult, SupplierResult, cm_view, score_suppliers
from flowline.team import TeamResult, run_team
from flowline.vsm import VSMResult, run_vsm


@dataclass
class Scenario:
    """What-if levers. Leave all at default for the base case."""
    name: str = "Base case"
    supplier_delay: dict[str, int] = field(default_factory=dict)   # supplier -> days later (+) or earlier (-)
    past_due_arrival_days: int | None = None
    apply_push_outs: bool = False      # move POs to their suggested dates and cancel unneeded lines


@dataclass
class Result:
    data: Dataset
    settings: Settings
    scenario: Scenario
    ctb: CTBResult
    inventory: InventoryResult
    suppliers: SupplierResult
    cm: CMResult
    risk: RiskResult | None = None
    cost: CostResult | None = None
    meetings: MeetingResult | None = None
    team: TeamResult | None = None
    financials: FinancialResult | None = None
    vsm: VSMResult | None = None
    alerts: pd.DataFrame = field(default_factory=pd.DataFrame)

    def summary(self) -> dict:
        p = self.ctb.projects
        act = p[p["ctb_status"].isin(["Clear to build", "Clear by start", "At risk", "Late"])]
        k = self.inventory.kpis
        al = self.alerts
        return dict(
            projects_open=len(act),
            projects_clear=int(act["ctb_status"].isin(["Clear to build", "Clear by start"]).sum()),
            projects_clear_now=int((act["ctb_status"] == "Clear to build").sum()),
            projects_at_risk=int((act["ctb_status"] == "At risk").sum()),
            projects_late=int((act["ctb_status"] == "Late").sum()),
            late_value=float(act.loc[act["ctb_status"] == "Late", "sell_value"].sum()),
            shortage_lines=len(self.ctb.shortages),
            short_value=float(act["short_value"].sum()),
            inventory_now=k["inventory_now"], turns_now=k["turns_now"], doi_now=k["doi_now"],
            year_end=k["year_end"], year_end_target=k["year_end_target"], year_end_gap=k["year_end_gap"],
            turns_year_end=k["turns_year_end"], turns_target=k["turns_target"],
            push_out_value=k["push_out_value"], excess_value=k["excess_value"],
            cm_commit_pct=self.cm.kpis["commit_pct"], cm_otd_pct=self.cm.kpis["otd_pct"],
            supplier_otd_pct=self.suppliers.kpis["otd_pct"], ppv=self.suppliers.kpis["ppv"],
            ppv_pct=self.suppliers.kpis["ppv_pct"], single_source_items=self.suppliers.kpis["single_source_items"],
            alerts_critical=int((al["severity"] == "Critical").sum()) if len(al) else 0,
            alerts_warning=int((al["severity"] == "Warning").sum()) if len(al) else 0,
            risks_high=self.risk.kpis["risks_high"] if self.risk else 0,
            ss_raise=self.risk.kpis["ss_raise"] if self.risk else 0,
            premium_freight=self.risk.kpis["premium_freight"] if self.risk else 0.0,
            savings_target=self.cost.kpis["target"] if self.cost else 0.0,
            savings_realized=self.cost.kpis["realized"] if self.cost else 0.0,
            savings_pipeline=self.cost.kpis["weighted_pipeline"] if self.cost else 0.0,
            actions_open=self.meetings.kpis["open"] if self.meetings else 0,
            actions_overdue=self.meetings.kpis["overdue"] if self.meetings else 0,
            dept_kpis_met=self.team.kpis["dept_met"] if self.team else 0,
            dept_kpis=self.team.kpis["dept_with_target"] if self.team else 0,
            **({f"fin_{k}": v for k, v in self.financials.kpis.items()} if self.financials else {}),
            **({f"vsm_{k}": v for k, v in self.vsm.kpis.items()} if self.vsm else {}),
        )


def _apply_push_outs(data: Dataset, s: Settings, scen: Scenario) -> Dataset:
    """Re-run once, then move every PO with a push-out to its suggested date and drop unneeded quantity."""
    base = run_ctb(data, s, scen.supplier_delay)
    pa = base.po_actions.set_index(["po_number", "po_line"])
    po = data.purchase_orders.copy()
    keep = []
    for i, r in po.iterrows():
        key = (r["po_number"], int(r["po_line"]))
        if key not in pa.index:
            keep.append(i)
            continue
        x = pa.loc[key]
        if str(x["action"]).startswith("Push out") and x["suggested_date"] is not None:
            po.at[i, "promised_date"] = pd.Timestamp(x["suggested_date"])
        if x["qty_needed"] <= 1e-9:
            continue      # cancelled
        if x["qty_needed"] < r["qty_open"]:
            po.at[i, "qty_open"] = x["qty_needed"]
        keep.append(i)
    return replace(data, purchase_orders=po.loc[keep].reset_index(drop=True))


def run(data: Dataset, scenario: Scenario | None = None, settings: Settings | None = None) -> Result:
    scen = scenario or Scenario()
    s = settings or data.settings
    if scen.past_due_arrival_days is not None:
        s = replace(s, past_due_arrival_days=int(scen.past_due_arrival_days))
    if scen.apply_push_outs:
        data = _apply_push_outs(data, s, scen)
    ctb = run_ctb(data, s, scen.supplier_delay)
    inv = project_inventory(data, ctb, s)
    sup = score_suppliers(data, ctb, s)
    cm = cm_view(data, ctb, s, sup)
    r = Result(data, s, scen, ctb, inv, sup, cm)
    r.risk = run_risk(data, ctb, sup, cm, s)
    r.cost = run_cost(data, sup, inv, r.risk, s)
    r.meetings = run_meetings(r)
    r.financials = run_financials(data, ctb, s)
    r.vsm = run_vsm(data, ctb, inv, s)
    r.alerts = build_alerts(r)
    r.team = run_team(r)
    r.meetings.agenda = build_agenda(r)
    return r


def fmt_money(v: float, cur: str = "$") -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "–"
    a = abs(v)
    sign = "-" if v < 0 else ""
    if a >= 1e6:
        return f"{sign}{cur}{a / 1e6:,.2f}M"
    if a >= 1e3:
        return f"{sign}{cur}{a / 1e3:,.0f}k"
    return f"{sign}{cur}{a:,.0f}"
