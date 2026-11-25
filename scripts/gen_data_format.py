"""Regenerate docs/data-format.md from the schema, so the documentation always matches the code.

    python scripts/gen_data_format.py
"""

from __future__ import annotations

import sys
from dataclasses import fields
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from flowline.io.template import HELP  # noqa: E402
from flowline.models import REQUIRED_COLUMNS, REQUIRED_TABLES, SCHEMA, Settings  # noqa: E402
from flowline.team import KPI  # noqa: E402

KIND = {"str": "text", "num": "number", "date": "date (YYYY-MM-DD)", "month": "month (YYYY-MM)"}
MEANING = {
    "company": "Name shown on screens and reports", "as_of_date": "Today for the model (default: the real today)",
    "fiscal_year_end": "Year-end date for the landing (default 31 Dec of the as-of year)", "currency": "Currency symbol",
    "turns_target": "Target turns at year end", "past_due_arrival_days": "When a past-due PO is assumed to arrive",
    "otd_early_days": "On-time window: days early allowed", "otd_late_days": "On-time window: days late allowed",
    "long_lead_days": "Lead time from which a part is long-lead",
    "conversion_cost_pct": "Labour and overhead added to material at build finish",
    "push_out_tolerance_days": "Earliness that triggers a push-out message",
    "receive_before_need_days": "Target arrival before the need date",
    "cm_commit_horizon_months": "Months in which CM commitments must cover the forecast",
    "otd_target_pct": "On-time delivery target", "cm_forecast_change_pct": "Demand change that makes a CM forecast stale",
    "history_months": "Look-back for supplier and CM performance",
    "frozen_window_days": "Builds starting inside this window are released or held in the meeting agenda",
    "service_level_pct": "Target service level for safety stock on repeat parts",
    "safety_stock_tolerance_pct": "Suggest a safety-stock change when the current level is this far off",
    "carrying_cost_pct": "Annual cost of holding inventory, % of its value",
    "savings_target": "Annual cost-reduction target", "lsp_otd_target_pct": "On-time target for logistics providers",
}


def main() -> None:
    out = ["# Data format", "",
           "Upload **one Excel workbook** with a sheet per table (sheet names as below), or **one CSV per table** named",
           "`<table>.csv`. Column names are matched case-insensitively; spaces become underscores. Extra columns are kept and ignored.", "",
           "Required tables: " + ", ".join(f"`{t}`" for t in REQUIRED_TABLES) +
           ". Every other table is optional and switches on more of the dashboard.", "",
           "Download a blank template from the sidebar (**Upload Excel or CSV → Download blank template**) or run "
           "`flowline template`. The **Input data workbook** export on the Data and exports tab gives you the sample in "
           "the same format, a good starting point.", "",
           "This page is generated from the code by `scripts/gen_data_format.py`.", ""]
    for t, cols in SCHEMA.items():
        desc, notes = HELP.get(t, ("", {}))
        out += [f"## {t}", "", desc, "", "| Column | Type | Required | Notes |", "| --- | --- | --- | --- |"]
        for c, k in cols.items():
            out.append(f"| `{c}` | {KIND[k]} | {'yes' if c in REQUIRED_COLUMNS.get(t, []) else ''} | {notes.get(c, '')} |")
        out.append("")
        if t == "objectives":
            out += ["KPI keys for `objectives` and `kpi_history`:", "", "| Key | KPI | Unit | Better |", "| --- | --- | --- | --- |"]
            out += [f"| `{k}` | {lab} | {u} | {b} |" for k, (lab, u, b) in KPI.items()]
            out.append("")
        if t == "settings":
            out += ["Keys and defaults:", "", "| Key | Default | Meaning |", "| --- | --- | --- |"]
            for f in fields(Settings):
                d = getattr(Settings(), f.name)
                d = "today" if f.name == "as_of_date" else ("" if d is None else d)
                out.append(f"| `{f.name}` | {d} | {MEANING.get(f.name, '')} |")
            out.append("")
    out += ["## Rules the importer checks", "",
            "* Required tables and columns present (error).",
            "* Duplicate `item_id` (error); BOM loops (error).",
            "* `item_type` is RM, SFG or FG and `make_buy` is make, buy or cm (warning).",
            "* BOM items missing from `items`, project top items without a BOM, unknown project status, PO lines for "
            "unknown items, POs without a promised date, bought items without a supplier (warnings).", ""]
    (ROOT / "docs" / "data-format.md").write_text("\n".join(out), encoding="utf-8")
    print("docs/data-format.md written")


if __name__ == "__main__":
    main()
