"""Inventory turns, days of inventory and the year-end working-capital landing, by stock type.

The projection is driven by the material plan itself, so it moves when clear-to-build dates move:

* PO receipts add to raw materials (at standard cost) on their expected date; uncovered shortages are
  assumed to be bought now and arrive after their lead time.
* When a project starts building (its clear-to-build start, not its planned start) its material moves
  from raw materials and semi-finished stock into WIP.
* When the build finishes, WIP moves to finished goods and conversion cost (labour and overhead) is added.
* When it ships, finished goods leave inventory and become cost of goods sold.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

from flowline.ctb import CTBResult, rolled_cost
from flowline.models import HISTORY_COLS, ITEM_STOCK_TYPE, STOCK_TYPES, Dataset, Settings


@dataclass
class InventoryResult:
    current: pd.DataFrame          # stock type, value now
    projection: pd.DataFrame       # month-end x stock type (actuals and projection)
    cogs: pd.DataFrame             # month, cogs, kind (Actual | Projected)
    landing: pd.DataFrame          # by stock type: now, year-end projection, target, gap, DOI
    kpis: dict
    events: pd.DataFrame           # every projected movement (for drill-down and exports)
    levers: pd.DataFrame           # actions that would lower the year-end landing


def month_end(d: date) -> date:
    nxt = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return nxt - timedelta(days=1)


def project_inventory(data: Dataset, ctb: CTBResult, s: Settings, horizon_days: int = 75) -> InventoryResult:
    items = data.items.set_index("item_id")
    stype = items["item_type"].map(ITEM_STOCK_TYPE).fillna("Raw materials")
    std = items["std_cost"]
    roll = rolled_cost(data)
    conv = 1 + s.conversion_cost_pct / 100
    asof = s.as_of_date
    end = max(month_end(s.year_end), month_end(asof + timedelta(days=horizon_days)))

    # Starting balances
    cur = {t: 0.0 for t in STOCK_TYPES}
    for it in data.items.itertuples():
        t = ITEM_STOCK_TYPE.get(it.item_type, "Raw materials")
        cur[t] += it.on_hand * it.std_cost
    pj = ctb.projects
    for p in pj.itertuples():
        if p.ctb_status == "In build":
            cur["WIP"] += p.material_cost
        elif p.ctb_status == "Built":
            cur["Finished goods"] += p.material_cost * conv

    ev: list[dict] = []

    def add(d, t, v, kind, ref):
        if d is not None and asof <= d <= end and abs(v) > 0:
            ev.append(dict(date=d, stock_type=t, value=v, kind=kind, ref=ref))

    # Receipts
    for lt in ctb.lots:
        if lt.kind == "PO":
            add(lt.date, stype.get(lt.item_id, "Raw materials"), lt.qty * float(std.get(lt.item_id, 0)), "PO receipt",
                f"{lt.po_number}-{lt.po_line}")
    al = ctb.allocations
    for a in al[al["kind"] == "Shortage"].itertuples():
        add(a.supply_date, stype.get(a.item_id, "Raw materials"), a.qty * float(std.get(a.item_id, 0)), "New buy (shortage)",
            f"{a.project_id} {a.item_id}")

    # Consumption at clear-to-build start; per project: stock and PO lots consumed + new buys
    leaf_cons = al.groupby(["project_id", "item_id"])["qty"].sum().reset_index() if not al.empty else pd.DataFrame(
        columns=["project_id", "item_id", "qty"])
    for p in pj.itertuples():
        if p.ctb_status in ("In build", "Built"):
            if p.ctb_status == "In build":
                add(p.forecast_finish, "WIP", -p.material_cost, "Build finish", p.project_id)
                add(p.forecast_finish, "Finished goods", p.material_cost * conv, "Build finish", p.project_id)
            add(p.forecast_ship, "Finished goods", -p.material_cost * conv, "Shipment", p.project_id)
            continue
        if p.ctb_status not in ("Clear to build", "Clear by start", "At risk", "Late"):
            continue
        cons = leaf_cons[leaf_cons["project_id"] == p.project_id]
        for c in cons.itertuples():
            t = stype.get(c.item_id, "Raw materials")
            add(p.forecast_build_start, t, -c.qty * float(std.get(c.item_id, roll.get(c.item_id, 0))), "Issue to build",
                p.project_id)
        mat = p.material_cost
        add(p.forecast_build_start, "WIP", mat, "Issue to build", p.project_id)
        add(p.forecast_finish, "WIP", -mat, "Build finish", p.project_id)
        add(p.forecast_finish, "Finished goods", mat * conv, "Build finish", p.project_id)
        add(p.forecast_ship, "Finished goods", -mat * conv, "Shipment", p.project_id)

    events = pd.DataFrame(ev, columns=["date", "stock_type", "value", "kind", "ref"])
    events["month"] = pd.to_datetime(events["date"]).dt.to_period("M").dt.to_timestamp()

    # Month-end balances
    months = pd.period_range(pd.Timestamp(asof), pd.Timestamp(end), freq="M").to_timestamp()
    rows = []
    for t in STOCK_TYPES:
        bal = cur[t]
        g = events[events["stock_type"] == t].groupby("month")["value"].sum()
        for m in months:
            bal += float(g.get(m, 0.0))
            rows.append(dict(month=m, stock_type=t, value=bal, kind="Projected"))
    proj = pd.DataFrame(rows)

    hist = data.inventory_history.copy()
    hist_rows, cogs_rows = [], []
    if not hist.empty:
        hist = hist[hist["month"] < pd.Timestamp(asof).to_period("M").to_timestamp()].sort_values("month")
        for r in hist.itertuples():
            for col, t in HISTORY_COLS.items():
                hist_rows.append(dict(month=r.month, stock_type=t, value=float(getattr(r, col)), kind="Actual"))
            cogs_rows.append(dict(month=r.month, cogs=float(r.cogs), kind="Actual"))
    ship = events[events["kind"] == "Shipment"].groupby("month")["value"].sum()
    for m in months:
        cogs_rows.append(dict(month=m, cogs=-float(ship.get(m, 0.0)), kind="Projected"))
    projection = pd.concat([pd.DataFrame(hist_rows, columns=proj.columns), proj], ignore_index=True) if hist_rows else proj
    cogs = pd.DataFrame(cogs_rows)

    # KPIs
    now_total = sum(cur.values())
    act = cogs[cogs["kind"] == "Actual"].sort_values("month")
    t12 = float(act["cogs"].tail(12).sum()) if len(act) else float("nan")
    if len(act) and len(act) < 12:
        t12 = t12 * 12 / len(act)
    ye_m = pd.Timestamp(s.year_end).to_period("M").to_timestamp()
    fy_start = (pd.Timestamp(s.year_end) - pd.DateOffset(years=1) + pd.Timedelta(days=1)).to_period("M").to_timestamp()
    fy_cogs = float(cogs[(cogs["month"] >= fy_start) & (cogs["month"] <= ye_m)]["cogs"].sum())
    ye = proj[proj["month"] == ye_m].set_index("stock_type")["value"].reindex(STOCK_TYPES).fillna(0.0)
    ye_total = float(ye.sum())
    targets = dict(zip(data.inventory_targets["stock_type"], data.inventory_targets["year_end_target"], strict=False))
    daily = t12 / 365 if t12 and not np.isnan(t12) else float("nan")
    fy_daily = fy_cogs / 365 if fy_cogs else float("nan")
    land = []
    for t in STOCK_TYPES:
        tgt = targets.get(t)
        land.append(dict(stock_type=t, now=cur[t], year_end=float(ye[t]), target=tgt if tgt is not None else np.nan,
                         gap=float(ye[t]) - tgt if tgt is not None else np.nan,
                         doi_now=cur[t] / daily if daily else np.nan,
                         doi_year_end=float(ye[t]) / fy_daily if fy_daily else np.nan))
    landing = pd.DataFrame(land)
    tot_target = float(landing["target"].sum()) if landing["target"].notna().any() else np.nan
    if "Total" in targets:
        tot_target = float(targets["Total"])
    landing.loc[len(landing)] = dict(stock_type="Total", now=now_total, year_end=ye_total, target=tot_target,
                                     gap=ye_total - tot_target if not np.isnan(tot_target) else np.nan,
                                     doi_now=now_total / daily if daily else np.nan,
                                     doi_year_end=ye_total / fy_daily if fy_daily else np.nan)

    # Levers that lower the year-end landing
    lev = []
    pa = ctb.po_actions
    if not pa.empty:
        for r in pa[pa["year_end_impact"] > 0].itertuples():
            lev.append(dict(lever=r.action, ref=f"{r.po_number}-{r.po_line}", item_id=r.item_id, supplier=r.supplier,
                            detail=f"{r.action}: due {r.expected_date:%d %b}, first needed "
                                   + (f"{r.earliest_need:%d %b}" if r.earliest_need else "by no open project"),
                            year_end_impact=r.year_end_impact))
    ex = ctb.excess
    if not ex.empty:
        for r in ex[ex["excess_value"] > 0].itertuples():
            lev.append(dict(lever="Excess stock", ref=r.item_id, item_id=r.item_id, supplier="",
                            detail=f"{r.excess_qty:,.0f} on hand not needed by any open project"
                                   + (" (no demand at all)" if r.no_demand else ""),
                            year_end_impact=r.excess_value))
    levers = pd.DataFrame(lev, columns=["lever", "ref", "item_id", "supplier", "detail", "year_end_impact"])
    levers = levers.sort_values("year_end_impact", ascending=False)

    kpis = dict(inventory_now=now_total, cogs_t12m=t12, turns_now=t12 / now_total if now_total else np.nan,
                doi_now=now_total / daily if daily else np.nan, year_end=ye_total, year_end_target=tot_target,
                year_end_gap=ye_total - tot_target if not np.isnan(tot_target) else np.nan, fy_cogs=fy_cogs,
                turns_year_end=fy_cogs / ye_total if ye_total else np.nan, turns_target=s.turns_target,
                inventory_for_target_turns=fy_cogs / s.turns_target if s.turns_target else np.nan,
                push_out_value=float(levers.loc[levers["lever"].str.startswith(("Push", "Cancel", "Reduce", "Expedite +")),
                                                 "year_end_impact"].sum()) if len(levers) else 0.0,
                excess_value=float(ex["excess_value"].sum()) if not ex.empty else 0.0,
                excess_on_order_value=float(ex["unneeded_on_order_value"].sum()) if not ex.empty else 0.0)
    cur_df = pd.DataFrame({"stock_type": STOCK_TYPES, "value": [cur[t] for t in STOCK_TYPES]})
    return InventoryResult(cur_df, projection, cogs, landing, kpis, events, levers)
