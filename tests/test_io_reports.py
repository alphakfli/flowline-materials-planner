import io
from pathlib import Path

import openpyxl
import pandas as pd
import pytest

from flowline import build_sample, run
from flowline.io.importer import build_dataset, load_files, workbook_bytes
from flowline.io.template import template_bytes
from flowline.models import SCHEMA
from flowline.reports import excel_report, pdf_report, powerquery_workbook


@pytest.fixture(scope="module")
def result():
    return run(build_sample())


def test_workbook_round_trip_gives_same_answer(result):
    data, issues = load_files({"in.xlsx": workbook_bytes(build_sample())})
    assert not [i for i in issues if i.severity == "error"]
    again = run(data).summary()
    for k in ("projects_late", "projects_clear", "shortage_lines", "alerts_critical"):
        assert again[k] == result.summary()[k]
    assert again["year_end"] == pytest.approx(result.summary()["year_end"])


def test_csv_upload(tmp_path: Path):
    files = {}
    for name, df in build_sample().tables().items():
        files[f"{name}.csv"] = df.to_csv(index=False).encode()
    data, issues = load_files(files)
    assert not [i for i in issues if i.severity == "error"]
    assert len(data.projects) == 14


def test_missing_table_and_bom_loop_are_errors():
    frames = {"items": pd.DataFrame({"item_id": ["A", "B"], "item_type": ["FG", "RM"], "make_buy": ["make", "buy"],
                                     "std_cost": [0, 1], "lead_time_days": [1, 1]}),
              "bom": pd.DataFrame({"parent_item": ["A", "B"], "component_item": ["B", "A"], "qty_per": [1, 1]})}
    _, issues = build_dataset(frames)
    msgs = " ".join(i.message for i in issues if i.severity == "error")
    assert "projects" in msgs and "loop" in msgs


def test_template_has_every_table():
    wb = openpyxl.load_workbook(io.BytesIO(template_bytes()))
    assert set(SCHEMA) <= set(wb.sheetnames)
    assert [c.value for c in wb["projects"][1]] == list(SCHEMA["projects"])


def test_excel_report(result):
    wb = openpyxl.load_workbook(io.BytesIO(excel_report(result)))
    for sheet in ("Summary", "Alerts", "Clear to build", "Shortages", "PO actions", "Inventory landing", "CM plan",
                  "Supplier scorecard", "Sourcing risk", "Inventory by month"):
        assert sheet in wb.sheetnames


def test_powerquery_workbook_has_named_tables(result):
    wb = openpyxl.load_workbook(io.BytesIO(powerquery_workbook(result)))
    names = {t for ws in wb for t in ws.tables}
    assert {"tbl_index", "tbl_alerts", "tbl_projects", "tbl_inventory_by_month", "tbl_supplier_scorecard"} <= names
    ws = wb["projects"]
    assert ws["A1"].value == "project_id"            # header in row 1, no title rows
    assert ws.max_row == len(result.ctb.projects) + 1


def test_pdf(result):
    pdf = pdf_report(result)
    assert pdf[:4] == b"%PDF" and len(pdf) > 10_000


def test_app_smoke():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py"), default_timeout=120)
    at.run()
    assert not at.exception
    labels = [m.label for m in at.metric]
    assert "Projects clear to build" in labels
    at.sidebar.checkbox[0].check().run()
    assert not at.exception
