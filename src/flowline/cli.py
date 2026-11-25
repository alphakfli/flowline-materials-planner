"""Command line:  flowline sample | template | run"""

from __future__ import annotations

import argparse
from pathlib import Path

from flowline.engine import run
from flowline.io.importer import load_path
from flowline.io.template import template_bytes
from flowline.reports import excel_report, pdf_report, powerquery_workbook
from flowline.sample import build_sample, write_sample


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="flowline", description="FlowLine Materials Planner")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sample", help="write the sample data as .xlsx and CSV")
    s.add_argument("folder", nargs="?", default="samples")
    t = sub.add_parser("template", help="write a blank input template")
    t.add_argument("path", nargs="?", default="flowline_template.xlsx")
    r = sub.add_parser("run", help="run on a workbook or CSV folder and write the reports")
    r.add_argument("input", nargs="?", help="workbook or folder of CSVs (default: sample data)")
    r.add_argument("--out", default="output")
    a = ap.parse_args(argv)

    if a.cmd == "sample":
        write_sample(a.folder)
        print(f"Sample written to {a.folder}/")
    elif a.cmd == "template":
        Path(a.path).write_bytes(template_bytes())
        print(f"Template written to {a.path}")
    else:
        if a.input:
            data, issues = load_path(a.input)
            for i in issues:
                print(f"[{i.severity}] {i.table}: {i.message}")
            if any(i.severity == "error" for i in issues):
                return 1
        else:
            data = build_sample()
        res = run(data)
        out = Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "materials_report.xlsx").write_bytes(excel_report(res))
        (out / "materials_review.pdf").write_bytes(pdf_report(res))
        (out / "flowline_powerquery.xlsx").write_bytes(powerquery_workbook(res))
        res.alerts.to_csv(out / "alerts.csv", index=False)
        s_ = res.summary()
        print(f"{s_['projects_clear']} of {s_['projects_open']} projects clear to build, {s_['projects_late']} late; "
              f"year-end landing {s_['year_end']:,.0f} vs target {s_['year_end_target']:,.0f}; "
              f"{s_['alerts_critical']} critical alerts. Reports in {out}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
