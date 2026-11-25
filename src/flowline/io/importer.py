"""Read and write the input tables: one Excel workbook with a sheet per table, or one CSV per table."""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from flowline.models import REQUIRED_COLUMNS, REQUIRED_TABLES, SCHEMA, Dataset, Settings, normalize


@dataclass
class Issue:
    severity: str     # error | warning
    table: str
    message: str


def _frames_from_files(files: dict[str, bytes]) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    for name, blob in files.items():
        low = name.lower()
        if low.endswith((".xlsx", ".xlsm")):
            book = pd.read_excel(io.BytesIO(blob), sheet_name=None)
            for sheet, df in book.items():
                key = sheet.strip().lower().replace(" ", "_")
                if key in SCHEMA:
                    frames[key] = df
        elif low.endswith(".csv"):
            key = Path(low).stem.strip().replace(" ", "_")
            if key in SCHEMA:
                frames[key] = pd.read_csv(io.BytesIO(blob))
    return frames


def build_dataset(frames: dict[str, pd.DataFrame]) -> tuple[Dataset, list[Issue]]:
    issues: list[Issue] = []
    for t in REQUIRED_TABLES:
        if t not in frames:
            issues.append(Issue("error", t, f"Missing table '{t}'."))
            frames[t] = pd.DataFrame(columns=list(SCHEMA[t]))
    for t, cols in REQUIRED_COLUMNS.items():
        have = [str(c).strip().lower().replace(" ", "_") for c in frames[t].columns]
        miss = [c for c in cols if c not in have]
        if miss:
            issues.append(Issue("error", t, f"Missing column(s): {', '.join(miss)}."))
    norm = {t: normalize(t, df) for t, df in frames.items() if t != "settings"}
    settings = Settings.from_table(frames.get("settings"))
    kw = {t: norm[t] for t in norm if t in SCHEMA}
    data = Dataset(settings=settings, **kw)
    issues += validate(data)
    return data, issues


def validate(d: Dataset) -> list[Issue]:
    out: list[Issue] = []
    ids = set(d.items["item_id"])
    dup = d.items["item_id"][d.items["item_id"].duplicated()].unique()
    if len(dup):
        out.append(Issue("error", "items", f"Duplicate item_id: {', '.join(dup[:10])}."))
    bad_type = d.items.loc[~d.items["item_type"].isin(["RM", "SFG", "FG"]), "item_id"]
    if len(bad_type):
        out.append(Issue("warning", "items", f"item_type should be RM, SFG or FG ({len(bad_type)} rows, treated as RM)."))
    bad_mb = d.items.loc[~d.items["make_buy"].isin(["make", "buy", "cm"]), "item_id"]
    if len(bad_mb):
        out.append(Issue("warning", "items", f"make_buy should be make, buy or cm ({len(bad_mb)} rows)."))
    miss = set(d.bom["parent_item"]) | set(d.bom["component_item"])
    miss -= ids
    if miss:
        out.append(Issue("warning", "bom", f"{len(miss)} BOM item(s) not in items, costed at zero: {', '.join(sorted(miss)[:8])}."))
    no_top = set(d.projects["top_item"]) - set(d.bom["parent_item"])
    if no_top:
        out.append(Issue("warning", "projects", f"Top item without a BOM: {', '.join(sorted(no_top)[:8])}."))
    st = set(d.projects["status"].str.lower()) - {"planned", "released", "in build", "built"}
    if st:
        out.append(Issue("warning", "projects", f"Unknown status {', '.join(sorted(st))}; use Planned, Released, In build or Built."))
    if d.projects["planned_build_start"].isna().any():
        out.append(Issue("warning", "projects", "Some projects have no planned_build_start; they are planned for today."))
    if not d.purchase_orders.empty:
        unk = set(d.purchase_orders["item_id"]) - ids
        if unk:
            out.append(Issue("warning", "purchase_orders", f"PO lines for unknown items: {', '.join(sorted(unk)[:8])}."))
        if d.purchase_orders["promised_date"].isna().any():
            out.append(Issue("warning", "purchase_orders", "PO lines without promised_date are treated as due today."))
    buy_no_sup = d.items[(d.items["make_buy"].isin(["buy", "cm"])) & (d.items["supplier_id"] == "")]
    if len(buy_no_sup):
        out.append(Issue("warning", "items", f"{len(buy_no_sup)} bought item(s) have no supplier_id."))
    # loops
    kids: dict[str, list[str]] = {}
    for r in d.bom.itertuples():
        kids.setdefault(r.parent_item, []).append(r.component_item)

    def walk(i, seen):
        if i in seen:
            raise ValueError(i)
        for c in kids.get(i, []):
            walk(c, seen | {i})

    try:
        for top in kids:
            walk(top, set())
    except ValueError as e:
        out.append(Issue("error", "bom", f"BOM loop at {e}."))
    return out


def load_files(files: dict[str, bytes]) -> tuple[Dataset, list[Issue]]:
    return build_dataset(_frames_from_files(files))


def load_path(path: str | Path) -> tuple[Dataset, list[Issue]]:
    p = Path(path)
    if p.is_dir():
        files = {f.name: f.read_bytes() for f in p.glob("*.csv")}
    else:
        files = {p.name: p.read_bytes()}
    return load_files(files)


def _clean(df: pd.DataFrame, table: str) -> pd.DataFrame:
    out = df[[c for c in SCHEMA[table] if c in df.columns]].copy()
    for c, k in SCHEMA[table].items():
        if c in out and k == "month":
            out[c] = pd.to_datetime(out[c]).dt.strftime("%Y-%m")
        elif c in out and k == "date":
            out[c] = pd.to_datetime(out[c]).dt.date
    return out


def workbook_bytes(d: Dataset) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        for name, df in d.tables().items():
            (_clean(df, name) if name != "settings" else df.astype(str)).to_excel(xw, sheet_name=name, index=False)
    return buf.getvalue()


def write_workbook(d: Dataset, path: str | Path) -> None:
    Path(path).write_bytes(workbook_bytes(d))
