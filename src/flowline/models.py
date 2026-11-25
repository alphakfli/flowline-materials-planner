"""Input tables, settings and the container that holds them.

Every table is a pandas DataFrame with the columns listed in ``SCHEMA``. Only ``items``, ``bom`` and
``projects`` are required; each optional table switches on more of the dashboard.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields, replace
from datetime import date

import pandas as pd

STOCK_TYPES = ["Raw materials", "Semi-finished", "WIP", "Finished goods"]
ITEM_STOCK_TYPE = {"RM": "Raw materials", "SFG": "Semi-finished", "FG": "Finished goods"}
HISTORY_COLS = {"raw_materials": "Raw materials", "semi_finished": "Semi-finished", "wip": "WIP",
                "finished_goods": "Finished goods"}

# table -> {column: kind}. kind: str, num, date, month
SCHEMA: dict[str, dict[str, str]] = {
    "items": {"item_id": "str", "description": "str", "item_type": "str", "make_buy": "str", "uom": "str",
              "std_cost": "num", "lead_time_days": "num", "supplier_id": "str", "commodity": "str", "buyer": "str",
              "on_hand": "num", "safety_stock": "num", "cm_hours_per_unit": "num"},
    "bom": {"parent_item": "str", "component_item": "str", "qty_per": "num"},
    "projects": {"project_id": "str", "customer": "str", "product_family": "str", "top_item": "str", "qty": "num",
                 "status": "str", "planned_build_start": "date", "build_days": "num", "required_ship_date": "date",
                 "sell_value": "num", "priority": "num"},
    "purchase_orders": {"po_number": "str", "po_line": "num", "item_id": "str", "supplier_id": "str", "qty_open": "num",
                        "unit_price": "num", "order_date": "date", "promised_date": "date", "project_id": "str"},
    "receipts": {"po_number": "str", "item_id": "str", "supplier_id": "str", "promised_date": "date",
                 "receipt_date": "date", "qty": "num", "qty_rejected": "num", "unit_price": "num", "std_cost": "num"},
    "suppliers": {"supplier_id": "str", "name": "str", "supplier_type": "str", "region": "str", "commodity": "str"},
    "item_sources": {"item_id": "str", "supplier_id": "str", "status": "str", "share_pct": "num",
                     "target_date": "date", "notes": "str"},
    "cm_forecast": {"cm_id": "str", "item_id": "str", "month": "month", "forecast_qty": "num", "committed_qty": "num",
                    "sent_date": "date"},
    "cm_capacity": {"cm_id": "str", "month": "month", "capacity_hours": "num"},
    "inventory_history": {"month": "month", "raw_materials": "num", "semi_finished": "num", "wip": "num",
                          "finished_goods": "num", "cogs": "num"},
    "inventory_targets": {"stock_type": "str", "year_end_target": "num"},
    # --- team, meetings, risk and cost (all optional)
    "team": {"person_id": "str", "name": "str", "role": "str", "scope": "str"},
    "objectives": {"owner": "str", "kpi": "str", "target": "num", "direction": "str"},
    "kpi_history": {"month": "month", "kpi": "str", "value": "num"},
    "actions": {"action_id": "str", "opened": "date", "stakeholder": "str", "owner": "str", "ref": "str",
                "action": "str", "due": "date", "status": "str", "closed": "date", "notes": "str"},
    "consumption_history": {"item_id": "str", "month": "month", "qty": "num"},
    "risk_register": {"risk_id": "str", "risk": "str", "category": "str", "likelihood": "num", "impact": "num",
                      "mitigation": "str", "owner": "str", "status": "str", "due": "date"},
    "shipments": {"shipment_id": "str", "lsp": "str", "mode": "str", "ship_date": "date", "promised_date": "date",
                  "delivered_date": "date", "cost": "num", "weight_kg": "num", "premium": "str", "reason": "str"},
    "savings_projects": {"project_id": "str", "title": "str", "category": "str", "item_id": "str", "supplier_id": "str",
                         "owner": "str", "stage": "str", "baseline_spend": "num", "annual_savings": "num",
                         "start_date": "date", "target_date": "date", "realized_to_date": "num"},
    # --- project financials (all optional)
    "wbs_budget": {"project_id": "str", "cost_element": "str", "as_sold": "num", "budget": "num"},
    "cost_actuals": {"project_id": "str", "cost_element": "str", "cost_to_date": "num", "etc_override": "num"},
    "change_orders": {"co_id": "str", "project_id": "str", "description": "str", "price_change": "num",
                      "cost_change": "num", "cost_element": "str", "status": "str", "submitted": "date", "decided": "date"},
    "billing_milestones": {"project_id": "str", "milestone_id": "str", "name": "str", "trigger": "str", "pct": "num",
                           "planned_date": "date", "invoice_no": "str", "invoice_date": "date", "amount_invoiced": "num",
                           "paid_date": "date"},
    "process_steps": {"product_family": "str", "seq": "num", "kind": "str", "name": "str", "stock_type": "str",
                      "cycle_time_hours": "num", "changeover_hours": "num", "uptime_pct": "num", "operators": "num",
                      "target_days": "num", "target_changeover_hours": "num"},
    "submittals": {"submittal_id": "str", "project_id": "str", "direction": "str", "document": "str", "party": "str",
                   "submitted": "date", "due": "date", "returned": "date", "status": "str", "holds": "str"},
    "settings": {"key": "str", "value": "str"},
}
SCHEMA["item_sources"]["quoted_price"] = "num"
REQUIRED_TABLES = ("items", "bom", "projects")
REQUIRED_COLUMNS = {
    "items": ["item_id", "item_type", "make_buy", "std_cost", "lead_time_days"],
    "bom": ["parent_item", "component_item", "qty_per"],
    "projects": ["project_id", "top_item", "qty", "status", "planned_build_start", "required_ship_date"],
}
ACTIVE_STATUSES = ("planned", "released")   # projects still waiting for material
IN_BUILD, BUILT = "in build", "built"


@dataclass(frozen=True)
class Settings:
    company: str = "Your company"
    as_of_date: date = field(default_factory=date.today)
    fiscal_year_end: date | None = None          # default: 31 December of the as-of year
    currency: str = "$"
    turns_target: float = 4.0
    past_due_arrival_days: int = 7               # when a past-due PO is assumed to arrive
    otd_early_days: int = 5                      # on-time window: up to N days early ...
    otd_late_days: int = 0                       # ... and up to N days late
    long_lead_days: int = 90                     # parts with this lead time or more are long-lead
    conversion_cost_pct: float = 25.0            # labour + overhead added to material when a build finishes
    push_out_tolerance_days: int = 30            # a PO this many days earlier than needed gets a push-out message
    receive_before_need_days: int = 5            # target arrival this many days before the need date
    cm_commit_horizon_months: int = 3            # CM commitments inside this window must cover the forecast
    otd_target_pct: float = 95.0
    cm_forecast_change_pct: float = 20.0         # flag the CM forecast as stale above this change
    history_months: int = 12                     # look-back for supplier and CM performance
    frozen_window_days: int = 14                 # builds starting inside this window are released or held
    service_level_pct: float = 95.0              # target service level for safety stock on repeat parts
    safety_stock_tolerance_pct: float = 25.0     # recommend a change when current differs more than this
    carrying_cost_pct: float = 20.0              # annual cost of holding inventory, % of its value
    savings_target: float = 0.0                  # annual cost-reduction target
    lsp_otd_target_pct: float = 95.0             # on-time target for logistics providers
    payment_terms_days: int = 45                 # customer payment terms for billing and cash forecasts
    commissioning_days: int = 45                 # commissioning milestone = ship date + this
    margin_fade_alert_pts: float = 1.5           # flag projects whose forecast margin is this many points below as sold
    vsm_family: str = ""                         # product family for the value stream map; blank = first in process_steps
    vsm_hours_per_day: float = 16.0              # available hours per working day (shifts x hours)
    vsm_working_days: int = 250                  # working days per year, for takt time

    @property
    def year_end(self) -> date:
        return self.fiscal_year_end or date(self.as_of_date.year, 12, 31)

    @classmethod
    def from_table(cls, df: pd.DataFrame | None) -> Settings:
        s = cls()
        if df is None or df.empty:
            return s
        kinds = {f.name: f.type for f in fields(cls)}
        upd = {}
        for k, v in zip(df["key"].astype(str).str.strip(), df["value"], strict=False):
            if k not in kinds or v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() == "":
                continue
            t = str(kinds[k])
            if "date" in t:
                upd[k] = pd.Timestamp(v).date()
            elif "int" in t:
                upd[k] = int(float(v))
            elif "float" in t:
                upd[k] = float(v)
            else:
                upd[k] = str(v)
        return replace(s, **upd)

    def to_table(self) -> pd.DataFrame:
        rows = [(f.name, getattr(self, f.name)) for f in fields(self)]
        return pd.DataFrame(rows, columns=["key", "value"])


def empty(table: str) -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype="object" if k == "str" else "float64" if k == "num" else "datetime64[ns]")
                         for c, k in SCHEMA[table].items()})


@dataclass
class Dataset:
    items: pd.DataFrame
    bom: pd.DataFrame
    projects: pd.DataFrame
    purchase_orders: pd.DataFrame = field(default_factory=lambda: empty("purchase_orders"))
    receipts: pd.DataFrame = field(default_factory=lambda: empty("receipts"))
    suppliers: pd.DataFrame = field(default_factory=lambda: empty("suppliers"))
    item_sources: pd.DataFrame = field(default_factory=lambda: empty("item_sources"))
    cm_forecast: pd.DataFrame = field(default_factory=lambda: empty("cm_forecast"))
    cm_capacity: pd.DataFrame = field(default_factory=lambda: empty("cm_capacity"))
    inventory_history: pd.DataFrame = field(default_factory=lambda: empty("inventory_history"))
    inventory_targets: pd.DataFrame = field(default_factory=lambda: empty("inventory_targets"))
    team: pd.DataFrame = field(default_factory=lambda: empty("team"))
    objectives: pd.DataFrame = field(default_factory=lambda: empty("objectives"))
    kpi_history: pd.DataFrame = field(default_factory=lambda: empty("kpi_history"))
    actions: pd.DataFrame = field(default_factory=lambda: empty("actions"))
    consumption_history: pd.DataFrame = field(default_factory=lambda: empty("consumption_history"))
    risk_register: pd.DataFrame = field(default_factory=lambda: empty("risk_register"))
    shipments: pd.DataFrame = field(default_factory=lambda: empty("shipments"))
    savings_projects: pd.DataFrame = field(default_factory=lambda: empty("savings_projects"))
    wbs_budget: pd.DataFrame = field(default_factory=lambda: empty("wbs_budget"))
    cost_actuals: pd.DataFrame = field(default_factory=lambda: empty("cost_actuals"))
    change_orders: pd.DataFrame = field(default_factory=lambda: empty("change_orders"))
    billing_milestones: pd.DataFrame = field(default_factory=lambda: empty("billing_milestones"))
    submittals: pd.DataFrame = field(default_factory=lambda: empty("submittals"))
    process_steps: pd.DataFrame = field(default_factory=lambda: empty("process_steps"))
    settings: Settings = field(default_factory=Settings)

    def tables(self) -> dict[str, pd.DataFrame]:
        out = {t: getattr(self, t) for t in SCHEMA if t != "settings"}
        out["settings"] = self.settings.to_table()
        return out

    def supplier_names(self) -> dict[str, str]:
        if self.suppliers.empty:
            return {}
        return dict(zip(self.suppliers["supplier_id"], self.suppliers["name"], strict=False))


def normalize(table: str, df: pd.DataFrame) -> pd.DataFrame:
    """Add missing schema columns and coerce types. Unknown columns are kept."""
    df = df.copy()
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    for col, kind in SCHEMA[table].items():
        if col not in df.columns:
            df[col] = pd.NA if kind == "str" else (0.0 if kind == "num" else pd.NaT)
        if kind == "num":
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0).astype(float)
        elif kind == "date":
            df[col] = pd.to_datetime(df[col], errors="coerce").dt.normalize()
        elif kind == "month":
            df[col] = pd.to_datetime(df[col].astype(str).str.slice(0, 7), format="%Y-%m", errors="coerce")
        else:
            df[col] = df[col].astype("object").where(df[col].notna(), "").astype(str).str.strip()
            df.loc[df[col].isin(["nan", "None", "NaT", "<NA>"]), col] = ""
    if table == "items":
        df["item_type"] = df["item_type"].str.upper()
        df["make_buy"] = df["make_buy"].str.lower()
    if table == "projects":
        df["status_key"] = df["status"].str.lower()
        df.loc[df["build_days"] <= 0, "build_days"] = 10.0
    return df
