"""Cost reduction: the savings-project pipeline against the annual target, and opportunities the model finds
(price variance, cheaper qualified sources, premium freight, inventory carrying cost)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from flowline.inventory import InventoryResult
from flowline.models import Dataset, Settings
from flowline.risk import RiskResult
from flowline.suppliers import SupplierResult

STAGES = ["Idea", "Validated", "In implementation", "Realized"]
STAGE_WEIGHT = {"Idea": 0.1, "Validated": 0.5, "In implementation": 0.8, "Realized": 1.0}


@dataclass
class CostResult:
    pipeline: pd.DataFrame        # savings projects with weighted value and status
    by_stage: pd.DataFrame        # count and savings per stage
    opportunities: pd.DataFrame   # found by the model, not yet a project
    kpis: dict


def run_cost(data: Dataset, sup: SupplierResult, inv: InventoryResult, risk: RiskResult, s: Settings) -> CostResult:
    asof = pd.Timestamp(s.as_of_date)
    names = data.supplier_names()
    sp = data.savings_projects.copy()
    stage_key = {k.lower(): k for k in STAGES}
    sp["stage"] = sp["stage"].str.strip().str.lower().map(stage_key).fillna("Idea")
    sp["weight"] = pd.to_numeric(sp["stage"].map(STAGE_WEIGHT), errors="coerce").fillna(0.1).astype(float)
    sp["weighted_savings"] = sp["annual_savings"] * sp["weight"]
    sp["savings_pct"] = np.where(sp["baseline_spend"] > 0, 100 * sp["annual_savings"] / sp["baseline_spend"], np.nan)
    sp["supplier"] = sp["supplier_id"].map(names).astype(object).fillna("")
    sp["overdue"] = (sp["target_date"] < asof) & (sp["stage"] != "Realized")
    team = dict(zip(data.team["person_id"], data.team["name"], strict=False)) if len(data.team) else {}
    sp["owner_name"] = sp["owner"].map(team).astype(object).fillna(sp["owner"])
    by_stage = (sp.groupby("stage").agg(projects=("project_id", "count"), annual_savings=("annual_savings", "sum"),
                                        weighted_savings=("weighted_savings", "sum"))
                .reindex(STAGES).fillna(0).reset_index())

    # ---- opportunities the model finds
    ops = []
    covered = set(zip(sp["item_id"], sp["category"], strict=False))
    rec = sup.receipts
    if len(rec):
        by_item = rec.groupby("item_id").agg(spend=("spend", "sum"), ppv=("ppv", "sum"), std_value=("std_value", "sum"),
                                             qty=("qty", "sum"), supplier_id=("supplier_id", "first"))
        by_item["ppv_pct"] = 100 * by_item["ppv"] / by_item["std_value"]
        for item, r in by_item[(by_item["ppv_pct"] >= 3) & (by_item["ppv"] >= 5000)].iterrows():
            if (item, "Negotiation") in covered:
                continue
            ops.append(dict(category="Negotiation", item_id=item, supplier=names.get(r["supplier_id"], r["supplier_id"]),
                            finding=f"Paid {r['ppv_pct']:+.1f}% over standard on {s.currency}{r['spend']:,.0f} spend",
                            action="Renegotiate against the contract or index; update standard cost if lasting",
                            annual_value=float(r["ppv"])))
        src = data.item_sources
        if len(src):
            q = src[(src["quoted_price"] > 0)]
            for x in q.itertuples():
                paid = rec.loc[rec["item_id"] == x.item_id]
                if paid.empty:
                    continue
                avg = paid["spend"].sum() / paid["qty"].sum()
                gap = avg - x.quoted_price
                if gap <= 0 or (x.item_id, "Alternative source") in covered:
                    continue
                ops.append(dict(category="Alternative source", item_id=x.item_id, supplier=names.get(x.supplier_id, x.supplier_id),
                                finding=f"Quote {s.currency}{x.quoted_price:,.2f} vs {s.currency}{avg:,.2f} paid "
                                        f"({100 * gap / avg:.0f}% lower); source status: {x.status}",
                                action="Complete qualification and move share to the cheaper source",
                                annual_value=float(gap * paid["qty"].sum())))
    if risk.kpis["premium_freight"] > 0 and ("", "Logistics") not in covered:
        ops.append(dict(category="Logistics", item_id="", supplier="",
                        finding=f"{s.currency}{risk.kpis['premium_freight']:,.0f} of premium freight in 12 months",
                        action="Remove the causes: release long-lead parts earlier, expedite by date not by air",
                        annual_value=risk.kpis["premium_freight"] * 0.6))
    k = inv.kpis
    wc = k["push_out_value"] + k["excess_value"]
    if wc > 0:
        ops.append(dict(category="Inventory carrying cost", item_id="", supplier="",
                        finding=f"{s.currency}{wc:,.0f} of push-outs, cancellations and excess on the levers list",
                        action="Work the levers; each dollar of inventory removed saves the carrying cost every year",
                        annual_value=wc * s.carrying_cost_pct / 100))
    opps = pd.DataFrame(ops, columns=["category", "item_id", "supplier", "finding", "action", "annual_value"])
    opps = opps.sort_values("annual_value", ascending=False).reset_index(drop=True)

    fy_start = (pd.Timestamp(s.year_end) - pd.DateOffset(years=1) + pd.Timedelta(days=1))
    elapsed = min(max((asof - fy_start).days / 365, 0), 1)
    realized = float(sp["realized_to_date"].sum())
    target = float(s.savings_target)
    kpis = dict(target=target, realized=realized, target_to_date=target * elapsed,
                weighted_pipeline=float(sp["weighted_savings"].sum()),
                pipeline_total=float(sp["annual_savings"].sum()),
                realized_pct_target=100 * realized / target if target else np.nan,
                overdue_projects=int(sp["overdue"].sum()), projects=len(sp),
                opportunity_value=float(opps["annual_value"].sum()) if len(opps) else 0.0)
    pipe = sp[["project_id", "title", "category", "item_id", "supplier", "owner", "owner_name", "stage", "baseline_spend",
               "annual_savings", "savings_pct", "weight", "weighted_savings", "realized_to_date", "start_date",
               "target_date", "overdue"]].assign(_o=sp["stage"].map({k: i for i, k in enumerate(STAGES)})).sort_values(
        ["_o", "annual_savings"], ascending=[False, False]).drop(columns="_o")
    return CostResult(pipe, by_stage, opps, kpis)
