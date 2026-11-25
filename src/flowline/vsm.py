"""Value stream map for one product family: where the inventory days come from and what better flow is worth.

The map is a flow of rows from `process_steps`: *Process* rows (cycle time, changeover, uptime, operators) and
*Stock* rows (the triangles). Each triangle takes its value from the inventory the app already calculates, split
to the family: raw and semi-finished stock by where the parts are used, WIP from the family's projects in build,
finished goods from its built projects. Days of stock = value / the family's daily COGS, so the triangles add up
to the family's days of inventory.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from flowline.ctb import CTBResult
from flowline.inventory import InventoryResult
from flowline.models import ITEM_STOCK_TYPE, Dataset, Settings

STOCK_LABEL = {"Raw materials": "Raw material", "Semi-finished": "Semi-finished", "WIP": "Work in process",
               "Finished goods": "Finished goods"}
COLS = ["seq", "kind", "name", "stock_type", "value", "days", "target_days", "cycle_time_hours", "changeover_hours",
        "uptime_pct", "operators", "effective_ct_hours", "load_pct", "process_days", "target_changeover_hours", "over_takt"]


@dataclass
class VSMResult:
    family: str
    steps: pd.DataFrame                      # one row per process box or stock triangle, in flow order
    takt_hours: float                        # available hours per unit of customer demand
    demand_units: float                      # family units (top items) a year: next six months' customer dates x 2
    hours_per_day: float
    daily_cogs: float                        # family COGS per calendar day
    family_share: float                      # family share of material cost, used to split COGS
    kpis: dict = field(default_factory=dict)
    future: pd.DataFrame | None = None       # the steps with targets applied
    future_kpis: dict = field(default_factory=dict)


def _family_items(data: Dataset, family: str) -> dict[str, float]:
    """Share of each part that belongs to the family: from the clear-to-build requirements, else the BOM."""
    pj = data.projects
    fam_tops = set(pj.loc[pj["product_family"] == family, "top_item"])
    tops_by_fam = pj.groupby("product_family")["top_item"].apply(set).to_dict()
    children = data.bom.groupby("parent_item")["component_item"].apply(list).to_dict()

    def explode(tops):
        seen, stack = set(), list(tops)
        while stack:
            for c in children.get(stack.pop(), []):
                if c not in seen:
                    seen.add(c)
                    stack.append(c)
        return seen

    used = {f: explode(t) for f, t in tops_by_fam.items()}
    mine = explode(fam_tops)
    share = {}
    for it in mine:
        n = sum(1 for f in used if it in used[f])
        share[it] = 1.0 / n if n else 0.0
    return share


def _family_inventory(data: Dataset, ctb: CTBResult, s: Settings, family: str) -> dict[str, float]:
    val = {t: 0.0 for t in STOCK_LABEL}
    # Raw and semi-finished: split by the requirements of open projects; parts with no open demand by the BOM
    req = ctb.allocations.merge(ctb.projects[["project_id", "product_family"]], on="project_id", how="left") \
        if len(ctb.allocations) else pd.DataFrame(columns=["item_id", "qty", "product_family"])
    by = req.groupby(["item_id", "product_family"])["qty"].sum().unstack(fill_value=0.0) if len(req) else pd.DataFrame()
    bom_share = _family_items(data, family)
    for it in data.items.itertuples():
        t = ITEM_STOCK_TYPE.get(it.item_type, "Raw materials")
        if t not in ("Raw materials", "Semi-finished") or not it.on_hand:
            continue
        if len(by) and it.item_id in by.index and by.loc[it.item_id].sum() > 0:
            sh = float(by.loc[it.item_id].get(family, 0.0) / by.loc[it.item_id].sum())
        else:
            sh = bom_share.get(it.item_id, 0.0)
        val[t] += it.on_hand * it.std_cost * sh
    conv = 1 + s.conversion_cost_pct / 100
    pj = ctb.projects[ctb.projects["product_family"] == family]
    val["WIP"] = float(pj.loc[pj["ctb_status"] == "In build", "material_cost"].sum())
    val["Finished goods"] = float(pj.loc[pj["ctb_status"] == "Built", "material_cost"].sum() * conv)
    return val


def _evaluate(st: pd.DataFrame, takt: float, hpd: float, daily: float, days_col: str, co_col: str) -> tuple[pd.DataFrame, dict]:
    st = st.copy()
    proc = st["kind"] == "Process"
    up = (st["uptime_pct"].where(st["uptime_pct"] > 0, 100.0) / 100).astype(float)
    co = st[co_col].astype(float).fillna(0.0)
    st["effective_ct_hours"] = np.where(proc, (st["cycle_time_hours"].fillna(0.0) + co) / up, np.nan)
    st["process_days"] = np.where(proc, st["effective_ct_hours"] / hpd if hpd else np.nan, 0.0)
    ok = bool(takt) and not np.isnan(takt)
    st["load_pct"] = st["effective_ct_hours"] / takt * 100 if ok else np.nan
    st["over_takt"] = proc & (st["effective_ct_hours"] > takt) if ok else False
    wait = float(st.loc[~proc, days_col].sum())
    process = float(st.loc[proc, "process_days"].sum())
    lt = wait + process
    stock = st[~proc]
    big = stock.loc[stock[days_col].idxmax()] if len(stock) and stock[days_col].max() > 0 else None
    k = dict(wait_days=wait, process_days=process, lead_time_days=lt,
             va_pct=process / lt * 100 if lt else np.nan,
             inventory=float(stock[days_col].sum() * daily),
             biggest_wait=None if big is None else big["name"],
             biggest_wait_days=0.0 if big is None else float(big[days_col]),
             biggest_wait_value=0.0 if big is None else float(big[days_col] * daily),
             steps_over_takt=int(st["over_takt"].sum()) if proc.any() else 0)
    return st, k


def run_vsm(data: Dataset, ctb: CTBResult, inv: InventoryResult, s: Settings) -> VSMResult | None:
    ps = data.process_steps
    if ps is None or ps.empty:
        return None
    family = s.vsm_family or str(ps["product_family"].iloc[0])
    st = ps[ps["product_family"] == family].sort_values("seq").reset_index(drop=True)
    if st.empty:
        return None
    st["kind"] = st["kind"].str.strip().str.capitalize().replace({"Inventory": "Stock"})

    # Family share of COGS: its share of the material in all projects
    pj = ctb.projects
    tot = float(pj["material_cost"].sum())
    share = float(pj.loc[pj["product_family"] == family, "material_cost"].sum() / tot) if tot else 0.0
    daily = inv.kpis["cogs_t12m"] * share / 365 if inv.kpis.get("cogs_t12m") else np.nan

    fam_inv = _family_inventory(data, ctb, s, family)
    st["value"] = [fam_inv.get(t, 0.0) if k == "Stock" else np.nan for k, t in zip(st["kind"], st["stock_type"], strict=True)]
    st["days"] = st["value"] / daily if daily else np.nan

    # Takt: available hours a year / family units a year (customer dates in the next six months, x 2)
    p = data.projects
    start = pd.Timestamp(s.as_of_date)
    due = pd.to_datetime(p["required_ship_date"])
    fam = p[(p["product_family"] == family) & (due >= start) & (due < start + pd.DateOffset(months=6))]
    demand = float(fam["qty"].sum()) * 2
    takt = s.vsm_working_days * s.vsm_hours_per_day / demand if demand else np.nan

    # A blank (or zero) target keeps the current value
    st["target_days"] = st["target_days"].where(st["target_days"] > 0, st["days"])
    st["target_changeover_hours"] = st["target_changeover_hours"].where(st["target_changeover_hours"] > 0,
                                                                         st["changeover_hours"])
    cur, k = _evaluate(st, takt, s.vsm_hours_per_day, daily, "days", "changeover_hours")
    k.update(family_inventory=float(sum(fam_inv.values())), takt_hours=takt, demand_units=demand)
    r = VSMResult(family, cur[COLS], takt, demand, s.vsm_hours_per_day, daily, share, k)
    return future_state(r, None, None)


def future_state(r: VSMResult, target_days: dict | None, target_changeover: dict | None) -> VSMResult:
    """Apply stock-day and changeover targets (by step name; None keeps the table's targets)."""
    st = r.steps.copy()
    if target_days:
        st["target_days"] = [target_days.get(n, t) for n, t in zip(st["name"], st["target_days"], strict=True)]
    if target_changeover:
        st["target_changeover_hours"] = [target_changeover.get(n, t)
                                         for n, t in zip(st["name"], st["target_changeover_hours"], strict=True)]
    st["target_days"] = pd.to_numeric(st["target_days"], errors="coerce")
    st["target_changeover_hours"] = pd.to_numeric(st["target_changeover_hours"], errors="coerce")
    fut, fk = _evaluate(st, r.takt_hours, r.hours_per_day, r.daily_cogs, "target_days", "target_changeover_hours")
    fut["freed_value"] = np.where(fut["kind"] == "Stock", (fut["days"] - fut["target_days"]) * r.daily_cogs, 0.0)
    fut["lead_time_change_days"] = np.where(fut["kind"] == "Stock", fut["target_days"] - fut["days"],
                                            fut["process_days"] - r.steps["process_days"])
    fk.update(freed_value=float(fut["freed_value"].sum()),
              lead_time_change_days=fk["lead_time_days"] - r.kpis["lead_time_days"])
    r.steps = r.steps.assign(target_days=st["target_days"], target_changeover_hours=st["target_changeover_hours"])
    r.future, r.future_kpis = fut, fk
    return r


def vsm_table(r: VSMResult) -> pd.DataFrame:
    """Flat table for exports and Power Query: current and future state per step."""
    f = r.future
    out = r.steps[["seq", "kind", "name", "stock_type", "value", "days", "cycle_time_hours", "changeover_hours",
                   "uptime_pct", "operators", "effective_ct_hours", "load_pct", "process_days", "over_takt"]].copy()
    out.insert(0, "product_family", r.family)
    out["target_days"] = f["target_days"]
    out["target_changeover_hours"] = f["target_changeover_hours"]
    out["future_process_days"] = f["process_days"]
    out["lead_time_change_days"] = f["lead_time_change_days"]
    out["working_capital_freed"] = f["freed_value"]
    out["takt_hours"] = r.takt_hours
    return out
