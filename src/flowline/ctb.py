"""Clear-to-build: explode each customer project through its multi-level BOM and allocate stock and open
purchase orders in project priority order.

The logic follows what a materials planner does with a missing-parts list (SAP CO24 / MD04 style):

* Projects are taken in order of planned build start, then priority.
* Each project's top item is exploded level by level. Make items (sub-assemblies) are netted against
  their own stock first; the rest is built, so its components are needed ``lead_time_days`` earlier.
* Buy and contract-manufactured parts are covered from supply lots: stock (available now), then open
  PO lines in date order. A PO line pegged to a project is used for that project only.
* Anything still uncovered is a shortage; its earliest date is today plus the part's lead time.
* The date a project can start building is the latest ready date of its top-level components.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd

from flowline.models import ACTIVE_STATUSES, BUILT, IN_BUILD, Dataset, Settings

DAY = timedelta(days=1)


@dataclass
class Lot:
    lot_id: str
    item_id: str
    kind: str                 # Stock | PO
    qty: float
    date: date                # when it is (or is expected to be) available
    promised_date: date | None = None
    supplier_id: str = ""
    project_id: str = ""      # pegged project, blank = free
    unit_price: float = 0.0
    po_number: str = ""
    po_line: int = 0
    past_due: bool = False
    remaining: float = field(init=False)

    def __post_init__(self):
        self.remaining = float(self.qty)


@dataclass
class CTBResult:
    projects: pd.DataFrame        # one row per project with dates and status
    requirements: pd.DataFrame    # one row per project x item x parent
    allocations: pd.DataFrame     # one row per requirement x supply lot
    shortages: pd.DataFrame       # requirement rows that are late or uncovered
    po_actions: pd.DataFrame      # exception message per open PO line
    excess: pd.DataFrame          # stock and open orders no open project needs
    long_lead: pd.DataFrame       # long-lead requirements and their order-by dates
    lots: list[Lot]


def _d(x) -> date | None:
    if x is None or pd.isna(x):
        return None
    return pd.Timestamp(x).date()


def build_lots(data: Dataset, s: Settings, supplier_delay: dict[str, int] | None = None) -> dict[str, list[Lot]]:
    """Stock and open PO lines per item, in the order they will be used."""
    supplier_delay = supplier_delay or {}
    lots: dict[str, list[Lot]] = {}
    for it in data.items.itertuples():
        if it.on_hand > 0:
            lots.setdefault(it.item_id, []).append(Lot(f"STOCK-{it.item_id}", it.item_id, "Stock", it.on_hand, s.as_of_date))
    po = data.purchase_orders
    for p in po[po["qty_open"] > 0].itertuples():
        promised = _d(p.promised_date) or s.as_of_date
        past_due = promised < s.as_of_date
        eff = s.as_of_date + timedelta(days=s.past_due_arrival_days) if past_due else promised
        eff = eff + timedelta(days=int(supplier_delay.get(p.supplier_id, 0)))
        eff = max(eff, s.as_of_date)
        lots.setdefault(p.item_id, []).append(Lot(
            f"{p.po_number}-{int(p.po_line)}", p.item_id, "PO", p.qty_open, eff, promised, p.supplier_id,
            p.project_id, p.unit_price, p.po_number, int(p.po_line), past_due))
    for v in lots.values():
        v.sort(key=lambda lt: (lt.kind != "Stock", lt.date, lt.lot_id))
    return lots


def _children(bom: pd.DataFrame) -> dict[str, list[tuple[str, float]]]:
    out: dict[str, list[tuple[str, float]]] = {}
    for r in bom.itertuples():
        out.setdefault(r.parent_item, []).append((r.component_item, float(r.qty_per)))
    return out


def rolled_cost(data: Dataset) -> dict[str, float]:
    """Material cost per unit of every item, rolled up through the BOM (standard cost for bought parts)."""
    kids = _children(data.bom)
    std = dict(zip(data.items["item_id"], data.items["std_cost"], strict=False))
    memo: dict[str, float] = {}

    def cost(item: str, depth: int = 0) -> float:
        if item in memo:
            return memo[item]
        if depth > 20:
            raise ValueError(f"BOM loop at {item}")
        if item in kids:
            v = sum(q * cost(c, depth + 1) for c, q in kids[item])
        else:
            v = float(std.get(item, 0.0))
        memo[item] = v
        return v

    for i in set(std) | set(kids):
        cost(i)
    return memo


def run_ctb(data: Dataset, s: Settings, supplier_delay: dict[str, int] | None = None) -> CTBResult:
    items = data.items.set_index("item_id")
    kids = _children(data.bom)
    lots = build_lots(data, s, supplier_delay)
    roll = rolled_cost(data)
    asof = s.as_of_date
    reqs: list[dict] = []
    allocs: list[dict] = []

    def info(item, col, default=None):
        return items.at[item, col] if item in items.index else default

    def need(prj: str, item: str, qty: float, need_date: date, parent: str, level: int, top: bool = False):
        """Cover ``qty`` of ``item`` for ``prj`` by ``need_date``. Returns (ready_date, gating_item)."""
        rid = len(reqs)
        row = dict(req_id=rid, project_id=prj, item_id=item, parent_item=parent, level=level, need_date=need_date,
                   qty_required=qty, from_stock=0.0, from_po=0.0, to_build=0.0, short_qty=0.0)
        reqs.append(row)
        make = str(info(item, "make_buy", "buy")) == "make" or (item in kids and item not in items.index)
        lead = float(info(item, "lead_time_days", 0) or 0)
        remaining = qty
        ready, gate = asof, ""
        sources = []
        pool = lots.get(item, [])
        if not top:   # project top items are engineered per order: never netted against stock
            usable = [lt for lt in pool if lt.remaining > 1e-9 and (lt.project_id in ("", prj))
                      and (not make or lt.kind == "Stock")]
            usable.sort(key=lambda lt: (lt.project_id != prj, lt.kind != "Stock", lt.date))
            for lt in usable:
                if remaining <= 1e-9:
                    break
                take = min(lt.remaining, remaining)
                lt.remaining -= take
                remaining -= take
                row["from_stock" if lt.kind == "Stock" else "from_po"] += take
                allocs.append(dict(req_id=rid, project_id=prj, item_id=item, lot_id=lt.lot_id, kind=lt.kind,
                                   po_number=lt.po_number, po_line=lt.po_line, supplier_id=lt.supplier_id, qty=take,
                                   supply_date=lt.date, need_date=need_date, past_due=lt.past_due))
                sources.append(lt.lot_id)
                if lt.date > ready:
                    ready, gate = lt.date, item
        if remaining > 1e-9 and (make or top) and item in kids:
            row["to_build"] = remaining
            start_by = need_date if top else need_date - timedelta(days=lead)
            child_ready, child_gate = asof, ""
            for c, q in kids[item]:
                r, g = need(prj, c, remaining * q, start_by, item, level + 1)
                if r > child_ready:
                    child_ready, child_gate = r, g
            # the top item's own build time is handled at project level
            built = child_ready if top else child_ready + timedelta(days=lead)
            if built > ready:
                ready, gate = built, child_gate
        elif remaining > 1e-9:
            row["short_qty"] = remaining
            earliest = asof + timedelta(days=lead)
            sources.append("NO SUPPLY")
            allocs.append(dict(req_id=rid, project_id=prj, item_id=item, lot_id="", kind="Shortage", po_number="",
                               po_line=0, supplier_id=str(info(item, "supplier_id", "") or ""), qty=remaining,
                               supply_date=earliest, need_date=need_date, past_due=False))
            if earliest > ready:
                ready, gate = earliest, item
        row["ready_date"] = ready
        row["sources"] = ", ".join(sources)
        return ready, gate

    pj = data.projects.copy()
    pj["_order"] = pj["planned_build_start"].fillna(pd.Timestamp.max)
    pj = pj.sort_values(["_order", "priority", "project_id"])
    out = []
    for p in pj.itertuples():
        start = _d(p.planned_build_start) or asof
        req_ship = _d(p.required_ship_date) or start + timedelta(days=int(p.build_days))
        mat = roll.get(p.top_item, 0.0) * p.qty
        rec = dict(project_id=p.project_id, customer=p.customer, product_family=p.product_family, top_item=p.top_item,
                   qty=p.qty, status=p.status, planned_build_start=start, build_days=int(p.build_days),
                   required_ship_date=req_ship, sell_value=p.sell_value, material_cost=mat)
        sk = p.status_key
        if sk in ACTIVE_STATUSES:
            first = len(reqs)
            clear, gate = need(p.project_id, p.top_item, p.qty, start, "", 0, top=True)
            mine = reqs[first:]
            leaf = [r for r in mine if r["level"] > 0 and r["to_build"] == 0]
            all_stock = all(r["from_stock"] + r["to_build"] >= r["qty_required"] - 1e-9 for r in mine if r["level"] > 0)
            late_lines = [r for r in leaf if r["ready_date"] > r["need_date"]]
            short_lines = [r for r in leaf if r["short_qty"] > 0]
            ctb_start = max(start, clear, asof)
            finish = ctb_start + timedelta(days=int(p.build_days))
            days_late = (finish - req_ship).days
            if all_stock:
                status = "Clear to build"
            elif clear <= start:
                status = "Clear by start"
            elif days_late <= 0:
                status = "At risk"
            else:
                status = "Late"
            leaf_val = sum(r["qty_required"] * roll.get(r["item_id"], 0) for r in leaf)
            stock_val = sum((r["from_stock"]) * roll.get(r["item_id"], 0) for r in mine if r["level"] > 0)
            rec.update(material_ready=clear, gating_item=gate if clear > start else "", ctb_status=status,
                       forecast_build_start=ctb_start, forecast_finish=finish,
                       forecast_ship=max(finish, req_ship), days_late=max(days_late, 0), float_days=-days_late,
                       late_lines=len(late_lines), short_lines=len(short_lines),
                       short_value=sum(r["short_qty"] * roll.get(r["item_id"], 0) for r in short_lines),
                       on_hand_pct=100 * stock_val / leaf_val if leaf_val else 100.0)
        else:
            finish = start + timedelta(days=int(p.build_days)) if sk == IN_BUILD else min(asof, start + timedelta(days=int(p.build_days)))
            label = {IN_BUILD: "In build", BUILT: "Built"}.get(sk, p.status or "Other")
            rec.update(material_ready=None, gating_item="", ctb_status=label, forecast_build_start=start,
                       forecast_finish=finish, forecast_ship=max(finish, req_ship, asof),
                       days_late=max((finish - req_ship).days, 0), float_days=(req_ship - finish).days,
                       late_lines=0, short_lines=0, short_value=0.0, on_hand_pct=100.0)
        out.append(rec)

    projects = pd.DataFrame(out)
    requirements = pd.DataFrame(reqs)
    allocations = pd.DataFrame(allocs, columns=["req_id", "project_id", "item_id", "lot_id", "kind", "po_number", "po_line",
                                                "supplier_id", "qty", "supply_date", "need_date", "past_due"])
    flat = [lt for v in lots.values() for lt in v]
    res = CTBResult(projects, requirements, allocations, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), flat)
    _post(res, data, s, roll)
    return res


def _post(res: CTBResult, data: Dataset, s: Settings, roll: dict[str, float]) -> None:
    items = data.items.set_index("item_id")
    desc = items["description"].to_dict() if "description" in items else {}
    std = items["std_cost"].to_dict()
    lead = items["lead_time_days"].to_dict()
    names = data.supplier_names()
    rq = res.requirements
    if rq.empty:
        rq = pd.DataFrame(columns=["req_id", "project_id", "item_id", "parent_item", "level", "need_date", "qty_required",
                                   "from_stock", "from_po", "to_build", "short_qty", "ready_date", "sources"])
        res.requirements = rq
    rq["description"] = rq["item_id"].map(desc)
    rq["unit_cost"] = rq["item_id"].map(roll)
    # a need date already in the past cannot be met by anything earlier than today
    rq["days_late"] = [(r - max(n, s.as_of_date)).days if r and n else 0
                       for r, n in zip(rq["ready_date"], rq["need_date"], strict=False)]
    leaf = rq[(rq["level"] > 0) & (rq["to_build"] == 0)]

    # Shortages and late parts
    sh = leaf[(leaf["days_late"] > 0) | (leaf["short_qty"] > 0)].copy()
    sh["supplier_id"] = sh["item_id"].map(items["supplier_id"].to_dict() if "supplier_id" in items else {})
    sh["supplier"] = sh["supplier_id"].map(names).astype(object).fillna("")
    sh["buyer"] = sh["item_id"].map(items["buyer"].to_dict() if "buyer" in items else {})
    sh["lead_time_days"] = sh["item_id"].map(lead)
    sh["issue"] = [("No supply, late" if d > 0 else "Not yet ordered") if q > 0 else "Late supply"
                   for q, d in zip(sh["short_qty"], sh["days_late"], strict=False)]
    sh["value_at_risk"] = (sh["short_qty"].where(sh["short_qty"] > 0, sh["from_po"])) * sh["unit_cost"]
    res.shortages = sh[["project_id", "item_id", "description", "parent_item", "need_date", "qty_required", "from_stock",
                        "from_po", "short_qty", "ready_date", "days_late", "issue", "supplier", "buyer",
                        "lead_time_days", "value_at_risk", "sources"]].sort_values(["need_date", "project_id", "days_late"],
                                                                                     ascending=[True, True, False])

    # PO exception messages
    al = res.allocations
    po_need = al[al["kind"] == "PO"].groupby("lot_id").agg(earliest_need=("need_date", "min"), qty_needed=("qty", "sum"),
                                                           projects=("project_id", lambda x: ", ".join(sorted(set(x)))))
    ye = s.year_end
    rows = []
    for lt in res.lots:
        if lt.kind != "PO":
            continue
        n = po_need.loc[lt.lot_id] if lt.lot_id in po_need.index else None
        needed = float(n["qty_needed"]) if n is not None else 0.0
        earliest = n["earliest_need"] if n is not None else None
        target = earliest - timedelta(days=s.receive_before_need_days) if earliest else None
        c = float(std.get(lt.item_id, 0.0))
        action, shift, new_date, ye_impact = "OK", 0, None, 0.0
        if needed <= 1e-9:
            action, ye_impact = "Cancel", lt.qty * c if lt.date <= ye else 0.0
        else:
            if earliest and lt.date > max(earliest, s.as_of_date):
                action, shift, new_date = "Expedite", -(lt.date - target).days, target
            elif target and (target - lt.date).days >= s.push_out_tolerance_days:
                action, shift, new_date = "Push out", (target - lt.date).days, target
                if lt.date <= ye < target:
                    ye_impact = needed * c
            if needed < lt.qty - 1e-9:
                extra = lt.qty - needed
                action = "Reduce" if action == "OK" else action + " + reduce"
                if lt.date <= ye:
                    ye_impact += extra * c
        if lt.past_due and action == "OK":
            action = "Past due"
        rows.append(dict(po_number=lt.po_number, po_line=lt.po_line, item_id=lt.item_id, description=desc.get(lt.item_id, ""),
                         supplier_id=lt.supplier_id, supplier=names.get(lt.supplier_id, lt.supplier_id),
                         pegged_project=lt.project_id, qty_open=lt.qty, qty_needed=needed,
                         value=lt.qty * lt.unit_price, promised_date=lt.promised_date, expected_date=lt.date,
                         past_due=lt.past_due, earliest_need=earliest, used_by=n["projects"] if n is not None else "",
                         action=action, shift_days=shift, suggested_date=new_date, year_end_impact=ye_impact))
    res.po_actions = pd.DataFrame(rows, columns=["po_number", "po_line", "item_id", "description", "supplier_id", "supplier",
                                                 "pegged_project", "qty_open", "qty_needed", "value", "promised_date",
                                                 "expected_date", "past_due", "earliest_need", "used_by", "action",
                                                 "shift_days", "suggested_date", "year_end_impact"])

    # Excess: stock and open orders that no open project needs
    ex = []
    used_stock = al[al["kind"] == "Stock"].groupby("item_id")["qty"].sum()
    for it in data.items.itertuples():
        on_order = sum(lt.qty for lt in res.lots if lt.kind == "PO" and lt.item_id == it.item_id)
        unneeded_po = sum(lt.remaining for lt in res.lots if lt.kind == "PO" and lt.item_id == it.item_id)
        free = it.on_hand - float(used_stock.get(it.item_id, 0.0))
        excess = max(free - it.safety_stock, 0.0)
        if excess <= 1e-9 and unneeded_po <= 1e-9:
            continue
        ex.append(dict(item_id=it.item_id, description=it.description, item_type=it.item_type, on_hand=it.on_hand,
                       allocated=float(used_stock.get(it.item_id, 0.0)), safety_stock=it.safety_stock,
                       excess_qty=excess, excess_value=excess * it.std_cost, on_order=on_order,
                       unneeded_on_order=unneeded_po, unneeded_on_order_value=unneeded_po * it.std_cost,
                       no_demand=float(used_stock.get(it.item_id, 0.0)) == 0 and it.item_id not in set(rq["item_id"])))
    res.excess = pd.DataFrame(ex, columns=["item_id", "description", "item_type", "on_hand", "allocated", "safety_stock",
                                           "excess_qty", "excess_value", "on_order", "unneeded_on_order",
                                           "unneeded_on_order_value", "no_demand"]).sort_values("excess_value", ascending=False)

    # Long-lead parts: when must they be ordered?
    ll = leaf[leaf["item_id"].map(lead).fillna(0) >= s.long_lead_days].copy()
    ll["lead_time_days"] = ll["item_id"].map(lead)
    ll["order_by"] = [n - timedelta(days=int(d)) for n, d in zip(ll["need_date"], ll["lead_time_days"], strict=False)]
    ll["covered_qty"] = ll["from_stock"] + ll["from_po"]

    def _st(r):
        if r.short_qty <= 0:
            return "Late supply" if r.days_late > 0 else "Covered"
        return "Order overdue" if r.order_by < s.as_of_date else ("Order now" if (r.order_by - s.as_of_date).days <= 14 else "Order by date")

    ll["status"] = [_st(r) for r in ll.itertuples()]
    ll["supplier"] = ll["item_id"].map(items["supplier_id"].to_dict()).map(names).astype(object).fillna("")
    res.long_lead = ll[["project_id", "item_id", "description", "qty_required", "need_date", "lead_time_days", "order_by",
                        "covered_qty", "short_qty", "ready_date", "days_late", "status", "supplier"]].sort_values("order_by")
