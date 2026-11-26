"""Sample data: Corvane Grid Equipment, a fictional engineer-to-order plant that builds medium-voltage
switchgear lineups and pad-mount / substation transformers.

All company, customer and supplier names are invented. Any resemblance to a real business is coincidental.
The data is generated from a fixed seed and a fixed as-of date, so numbers in the docs and tests are stable.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

import numpy as np
import pandas as pd

from flowline.models import SCHEMA, Dataset, Settings, normalize

AS_OF = date(2026, 11, 23)
COMPANY = "Corvane Grid Equipment (fictional)"

SUPPLIERS = [
    ("S100", "Veltrano Breakers", "Supplier", "EU", "Vacuum breakers"),
    ("S101", "Marlowe Switch Components", "Supplier", "North America", "Vacuum breakers"),
    ("S110", "Qorvane Protection Systems", "Supplier", "North America", "Protection relays and P&C"),
    ("S120", "Brightmere Instruments", "Supplier", "North America", "Instrument transformers"),
    ("S121", "Kestavo Metering", "Supplier", "Mexico", "Instrument transformers"),
    ("S130", "Tarnwick Bushings", "Supplier", "EU", "Bushings"),
    ("S140", "Ellerby Tap Changers", "Supplier", "EU", "Tap changers"),
    ("S150", "Copperfen Wire", "Supplier", "North America", "Magnet wire"),
    ("S151", "Nordvale Wire", "Supplier", "North America", "Magnet wire"),
    ("S160", "Greyfen Fluids", "Supplier", "North America", "Dielectric fluid"),
    ("S170", "Ashcombe Radiators", "Supplier", "North America", "Radiators"),
    ("S180", "Boltwright Supply", "Supplier", "North America", "Hardware and gaskets"),
    ("S181", "Harrowgate Industrial", "Supplier", "North America", "Hardware and gaskets"),
    ("S190", "Insulcraft Materials", "Supplier", "North America", "Insulation"),
    ("CM200", "Ironvale Fabrication", "CM", "North America", "Enclosures and tanks"),
    ("CM210", "Busmark Assemblies", "CM", "North America", "Copper bus assemblies"),
    ("CM220", "Lattix Harness", "CM", "Mexico", "Control wiring harnesses"),
    ("CM230", "Corefield Lamination", "CM", "North America", "Transformer cores"),
    ("CM240", "Stellmark Cores", "CM", "North America", "Transformer cores"),
]

# item_id, description, type, make_buy, uom, std_cost, lead_days, supplier, commodity, buyer, on_hand, safety, cm_hours
ITEMS = [
    ("VCB-15-1200", "Vacuum circuit breaker 15 kV 1200 A", "RM", "buy", "EA", 28000, 112, "S100", "Breakers", "B1 Electrical", 8, 0, 0),
    ("VCB-15-2000", "Vacuum circuit breaker 15 kV 2000 A", "RM", "buy", "EA", 36000, 126, "S100", "Breakers", "B1 Electrical", 2, 0, 0),
    ("RLY-FDR", "Feeder protection relay", "RM", "buy", "EA", 6500, 84, "S110", "Protection", "B1 Electrical", 8, 2, 0),
    ("RLY-MAIN", "Main protection relay", "RM", "buy", "EA", 9800, 84, "S110", "Protection", "B1 Electrical", 2, 1, 0),
    ("RLY-LEGACY", "Feeder relay, previous model (superseded)", "RM", "buy", "EA", 4800, 84, "S110", "Protection", "B1 Electrical", 14, 0, 0),
    ("CT-600", "Current transformer 600:5", "RM", "buy", "EA", 650, 56, "S120", "Instrument transformers", "B1 Electrical", 40, 6, 0),
    ("CT-2000", "Current transformer 2000:5", "RM", "buy", "EA", 1100, 56, "S120", "Instrument transformers", "B1 Electrical", 6, 0, 0),
    ("PT-15", "Voltage transformer 15 kV", "RM", "buy", "EA", 2400, 70, "S120", "Instrument transformers", "B1 Electrical", 4, 0, 0),
    ("ENC-SWG-36", "Switchgear enclosure 36 in, welded and painted", "RM", "cm", "EA", 9500, 35, "CM200", "Fabrication", "B2 Fabrication", 10, 0, 22),
    ("BUS-CU-1200", "Copper bus assembly 1200 A", "RM", "cm", "EA", 4200, 28, "CM210", "Copper bus", "B2 Fabrication", 8, 0, 10),
    ("BUS-CU-2000", "Copper bus assembly 2000 A", "RM", "cm", "EA", 6800, 28, "CM210", "Copper bus", "B2 Fabrication", 2, 0, 14),
    ("WIRE-KIT-SWG", "Control wiring harness kit", "RM", "cm", "EA", 1300, 21, "CM220", "Harnesses", "B2 Fabrication", 10, 2, 6),
    ("HW-KIT-SWG", "Hardware kit, switchgear section", "RM", "buy", "EA", 380, 14, "S180", "Hardware", "B3 Raw materials", 30, 10, 0),
    ("CORE-2500", "Core assembly 2.5 MVA", "RM", "cm", "EA", 18500, 49, "CM230", "Cores", "B2 Fabrication", 2, 0, 40),
    ("CORE-7500", "Core assembly 7.5 MVA", "RM", "cm", "EA", 42000, 63, "CM230", "Cores", "B2 Fabrication", 0, 0, 85),
    ("TANK-2500", "Transformer tank 2.5 MVA", "RM", "cm", "EA", 7800, 42, "CM200", "Fabrication", "B2 Fabrication", 4, 0, 30),
    ("TANK-7500", "Transformer tank 7.5 MVA", "RM", "cm", "EA", 16500, 49, "CM200", "Fabrication", "B2 Fabrication", 0, 0, 60),
    ("DETC-25", "De-energized tap changer 25 kV", "RM", "buy", "EA", 3900, 98, "S140", "Tap changers", "B4 Transformer parts", 5, 0, 0),
    ("OLTC-75", "On-load tap changer 7.5 MVA", "RM", "buy", "EA", 48000, 154, "S140", "Tap changers", "B4 Transformer parts", 0, 0, 0),
    ("BUSH-HV-25", "HV bushing 25 kV", "RM", "buy", "EA", 1450, 98, "S130", "Bushings", "B4 Transformer parts", 14, 0, 0),
    ("BUSH-HV-69", "HV bushing 69 kV", "RM", "buy", "EA", 6800, 126, "S130", "Bushings", "B4 Transformer parts", 0, 0, 0),
    ("BUSH-LV", "LV bushing", "RM", "buy", "EA", 420, 56, "S130", "Bushings", "B4 Transformer parts", 90, 8, 0),
    ("CU-MAG", "Copper magnet wire", "RM", "buy", "KG", 14.5, 42, "S150", "Copper", "B3 Raw materials", 4600, 1000, 0),
    ("INS-KIT-2500", "Insulation kit 2.5 MVA", "RM", "buy", "EA", 2900, 35, "S190", "Insulation", "B4 Transformer parts", 3, 0, 0),
    ("INS-KIT-7500", "Insulation kit 7.5 MVA", "RM", "buy", "EA", 6400, 35, "S190", "Insulation", "B4 Transformer parts", 0, 0, 0),
    ("FLUID-ESTER", "Natural ester dielectric fluid", "RM", "buy", "L", 4.2, 21, "S160", "Fluids", "B3 Raw materials", 9000, 2000, 0),
    ("RAD-1200", "Radiator panel", "RM", "buy", "EA", 1150, 63, "S170", "Radiators", "B4 Transformer parts", 10, 0, 0),
    ("GSK-KIT", "Gasket kit", "RM", "buy", "EA", 260, 14, "S180", "Hardware", "B3 Raw materials", 12, 4, 0),
    ("SA-SWG-BKR", "Breaker section 15 kV 1200 A", "SFG", "make", "EA", 0, 10, "", "Sub-assembly", "", 0, 0, 0),
    ("SA-SWG-INC", "Incomer section 15 kV 2000 A", "SFG", "make", "EA", 0, 10, "", "Sub-assembly", "", 0, 0, 0),
    ("COIL-2500", "Coil set 2.5 MVA", "SFG", "make", "EA", 0, 12, "", "Sub-assembly", "", 4, 0, 0),
    ("COIL-7500", "Coil set 7.5 MVA", "SFG", "make", "EA", 0, 15, "", "Sub-assembly", "", 0, 0, 0),
]

STD_BOM = [
    ("SA-SWG-BKR", "VCB-15-1200", 1), ("SA-SWG-BKR", "ENC-SWG-36", 1), ("SA-SWG-BKR", "BUS-CU-1200", 1),
    ("SA-SWG-BKR", "RLY-FDR", 1), ("SA-SWG-BKR", "CT-600", 3), ("SA-SWG-BKR", "WIRE-KIT-SWG", 1),
    ("SA-SWG-BKR", "HW-KIT-SWG", 1),
    ("SA-SWG-INC", "VCB-15-2000", 1), ("SA-SWG-INC", "ENC-SWG-36", 1), ("SA-SWG-INC", "BUS-CU-2000", 1),
    ("SA-SWG-INC", "RLY-MAIN", 1), ("SA-SWG-INC", "CT-2000", 3), ("SA-SWG-INC", "PT-15", 2),
    ("SA-SWG-INC", "WIRE-KIT-SWG", 1), ("SA-SWG-INC", "HW-KIT-SWG", 1),
    ("COIL-2500", "CU-MAG", 1100), ("COIL-2500", "INS-KIT-2500", 1),
    ("COIL-7500", "CU-MAG", 3600), ("COIL-7500", "INS-KIT-7500", 1),
]
TX_BOM = {
    "2.5": [("CORE-2500", 1), ("COIL-2500", 1), ("TANK-2500", 1), ("DETC-25", 1), ("BUSH-HV-25", 3), ("BUSH-LV", 4),
            ("FLUID-ESTER", 2200), ("RAD-1200", 4), ("GSK-KIT", 1)],
    "7.5": [("CORE-7500", 1), ("COIL-7500", 1), ("TANK-7500", 1), ("OLTC-75", 1), ("BUSH-HV-69", 3), ("BUSH-LV", 4),
            ("FLUID-ESTER", 6500), ("RAD-1200", 10), ("GSK-KIT", 2)],
}

# project, customer, kind, spec, qty, status, start offset, build days, ship slack, priority, package cost
PROJECTS = [
    ("P-2601", "Varnley Municipal Utility", "SWG", (2, 6), 1, "Built", -25, 15, 12, 1, 52000),
    ("P-2602", "Quillfield Data Campus", "SWG", (2, 10), 1, "In build", -8, 15, 6, 1, 68000),
    ("P-2603", "Orrindale Wind LP", "TX", "7.5", 2, "In build", -6, 20, 10, 1, 0),
    ("P-2604", "Tessmoor Water Authority", "TX", "2.5", 4, "Released", 6, 20, 8, 2, 0),
    ("P-2605", "Brackenhollow Mine", "SWG", (2, 8), 1, "Released", 12, 15, 10, 2, 61000),
    ("P-2606", "Lumrey Solar 2", "TX", "7.5", 1, "Released", 20, 20, 7, 1, 0),
    ("P-2607", "Elmbrae General Hospital", "SWG", (1, 4), 1, "Released", 28, 12, 14, 2, 39000),
    ("P-2608", "Corrowick Transit", "TX", "2.5", 6, "Released", 35, 22, 10, 3, 0),
    ("P-2609", "Danthorpe Logistics Park", "SWG", (2, 6), 1, "Released", 48, 15, 12, 3, 55000),
    ("P-2610", "Fenwold Co-op Power", "TX", "7.5", 2, "Released", 62, 22, 18, 2, 0),
    ("P-2611", "Quillfield Data Campus Phase 2", "SWG", (2, 12), 1, "Released", 80, 18, 15, 2, 74000),
    ("P-2612", "Varnley Municipal Utility", "TX", "2.5", 3, "Released", 95, 20, 20, 3, 0),
    ("P-2613", "Orrindale Wind LP Phase 2", "TX", "7.5", 1, "Released", 120, 20, 20, 2, 0),
    ("P-2614", "Brackenhollow Mine expansion", "SWG", (1, 6), 1, "Planned", 140, 15, 20, 4, 47000),
]

PROFILES = {  # supplier: (on-time share, mean days late when late, PPV mean, reject probability, receipt lines)
    "S100": (0.68, 18, 0.045, 0.02, 30), "S110": (0.90, 10, 0.010, 0.01, 40), "S120": (0.94, 7, 0.0, 0.03, 45),
    "S121": (0.96, 5, -0.010, 0.01, 15), "S130": (0.78, 21, 0.030, 0.04, 30), "S140": (0.60, 25, 0.060, 0.02, 12),
    "S150": (0.95, 5, 0.065, 0.0, 24), "S151": (0.88, 7, -0.015, 0.0, 16), "S160": (0.97, 4, 0.020, 0.0, 18),
    "S170": (0.85, 10, 0.0, 0.03, 22), "S180": (0.97, 3, -0.010, 0.005, 40), "S181": (0.93, 4, 0.0, 0.01, 15),
    "S190": (0.92, 8, 0.020, 0.02, 20), "CM200": (0.82, 9, 0.010, 0.03, 60), "CM210": (0.93, 5, 0.0, 0.01, 45),
    "CM220": (0.96, 4, 0.0, 0.02, 40), "CM230": (0.90, 8, 0.020, 0.01, 30),
}

SOURCES = [  # item, supplier, status, share, target offset days, notes
    ("VCB-15-1200", "S100", "Approved", 100, None, ""),
    ("VCB-15-1200", "S101", "In qualification", 0, 120, "First article passed; type test booked"),
    ("VCB-15-2000", "S100", "Approved", 100, None, ""),
    ("VCB-15-2000", "S101", "Candidate", 0, 240, "Quote received"),
    ("CT-600", "S120", "Approved", 70, None, ""), ("CT-600", "S121", "Approved", 30, None, ""),
    ("CT-2000", "S120", "Approved", 70, None, ""), ("CT-2000", "S121", "Approved", 30, None, ""),
    ("CU-MAG", "S150", "Approved", 60, None, "Copper index pricing"), ("CU-MAG", "S151", "Approved", 40, None, ""),
    ("HW-KIT-SWG", "S180", "Approved", 80, None, ""), ("HW-KIT-SWG", "S181", "Approved", 20, None, ""),
    ("GSK-KIT", "S180", "Approved", 50, None, ""), ("GSK-KIT", "S181", "Approved", 50, None, ""),
    ("CORE-2500", "CM230", "Approved", 100, None, ""),
    ("CORE-2500", "CM240", "In qualification", 0, 90, "Pilot build of two cores in January"),
    ("CORE-7500", "CM230", "Approved", 100, None, ""),
    ("OLTC-75", "S140", "Approved", 100, None, ""),
    ("OLTC-75", "S101", "Candidate", 0, 300, "Distributor for a second tap-changer maker"),
    ("BUSH-LV", "S130", "Approved", 100, None, ""),
    ("BUSH-LV", "S121", "In qualification", 0, 60, "Samples under test"),
    ("ENC-SWG-36", "CM200", "Approved", 100, None, ""),
    ("TANK-2500", "CM200", "Approved", 100, None, ""),
    ("TANK-7500", "CM200", "Approved", 100, None, ""),
]


QUOTES = {("VCB-15-1200", "S101"): 26300.0, ("CORE-2500", "CM240"): 17600.0, ("BUSH-LV", "S121"): 395.0}

TEAM = [  # first names only; fictional
    ("P00", "Materials manager", "Materials manager", "All"),
    ("P01", "Maya", "Buyer", "B1 Electrical"),
    ("P02", "Daniel", "Buyer", "B2 Fabrication"),
    ("P03", "Sofia", "Buyer", "B3 Raw materials"),
    ("P04", "Arjun", "Buyer", "B4 Transformer parts"),
    ("P05", "Leah", "Planner", "Switchgear"),
    ("P06", "Tomas", "Planner", "Transformers"),
    ("P07", "Grace", "Inventory analyst", "All"),
    ("P08", "Noah", "Project controller", "All"),
]
ROLE_TARGETS = {
    "Buyer": [("supplier_otd_pct", 92, "higher"), ("past_due_lines", 1, "lower"), ("expedite_lines", 2, "lower"),
              ("late_part_lines", 2, "lower"), ("ppv_pct", 1.5, "lower"), ("savings_realized", 40000, "higher"),
              ("actions_overdue", 0, "lower")],
    "Planner": [("ctb_pct", 80, "higher"), ("late_projects", 0, "lower"), ("at_risk_projects", 2, "lower"),
                ("shortage_lines", 6, "lower"), ("actions_overdue", 0, "lower")],
    "Project controller": [("invoices_not_raised", 0, "lower"), ("ar_overdue_value", 100000, "lower"),
                           ("margin_fade_pts", 1.0, "lower"), ("billing_at_risk_fy", 0, "lower"),
                           ("submittals_overdue", 1, "lower"), ("cos_stale", 0, "lower"), ("actions_overdue", 0, "lower")],
    "Inventory analyst": [("excess_value", 75000, "lower"), ("no_demand_items", 1, "lower"), ("ss_actions", 10, "lower"),
                          ("year_end_gap", 0, "lower"), ("actions_overdue", 0, "lower")],
}
DEPT_TARGETS = [("turns", 4.0, "higher"), ("doi", 110, "lower"), ("ctb_pct", 80, "higher"), ("late_projects", 0, "lower"),
                ("supplier_otd_pct", 95, "higher"), ("cm_otd_pct", 95, "higher"), ("cm_commit_pct", 80, "higher"),
                ("past_due_lines", 8, "lower"), ("ppv_pct", 1.0, "lower"), ("excess_value", 75000, "lower"),
                ("year_end_gap", 0, "lower"), ("savings_realized", 220000, "higher"), ("actions_overdue", 3, "lower"),
                ("risks_high", 5, "lower")]
CONSUMPTION = {  # repeat parts: mean monthly use, coefficient of variation
    "HW-KIT-SWG": (9, .35), "GSK-KIT": (4, .5), "CT-600": (18, .4), "CT-2000": (4, .6), "BUSH-LV": (14, .45),
    "CU-MAG": (4200, .35), "FLUID-ESTER": (12000, .4), "WIRE-KIT-SWG": (9, .35), "RLY-FDR": (6, .4),
    "INS-KIT-2500": (2.5, .5), "RAD-1200": (12, .4), "DETC-25": (2.5, .5), "BUSH-HV-25": (7, .45), "PT-15": (3, .5),
}
ACTIONS = [  # id, opened offset, stakeholder, owner, ref, action, due offset, status, closed offset
    ("A-101", -28, "Production", "P06", "P-2604", "Confirm core and radiator deliveries for P-2604", 2, "Open", None),
    ("A-102", -35, "Engineering", "P07", "RLY-LEGACY", "Decide disposition of superseded relay stock (14 pcs)", -10, "Open", None),
    ("A-103", -7, "Finance", "P00", "", "Send year-end push-out lists to each buyer", 4, "Open", None),
    ("A-104", -7, "Contracts", "P06", "P-2606", "Warn Lumrey Solar of the risk to the 9 Jan date", -3, "Open", None),
    ("A-105", -21, "Suppliers and CMs", "P04", "OLTC-75", "Ellerby recovery plan for tap-changer deliveries", -7, "Done", -5),
    ("A-106", -14, "Suppliers and CMs", "P02", "CM200", "Send updated forecast to Ironvale including P-2611", -3, "Open", None),
    ("A-107", -42, "Engineering", "P01", "VCB-15-1200", "Book the type test for the Marlowe 1200 A breaker", 22, "Open", None),
    ("A-108", -7, "Production", "P05", "P-2605", "Kit P-2605 for the 5 Dec start", 8, "Open", None),
    ("A-109", -49, "Finance", "P07", "", "Q3 excess and obsolete reserve review", -24, "Done", -25),
    ("A-110", -14, "Materials team", "P03", "CU-MAG", "Copper index clause in the new magnet-wire contract", 7, "Open", None),
]
RISKS = [  # id, risk, category, likelihood, impact, mitigation, owner, status, due offset
    ("R-01", "Tariff increase on imported vacuum breakers", "Commercial", 3, 4, "Qualify Marlowe (North America) as second source", "P01", "Mitigating", 120),
    ("R-02", "Copper price spike", "Commercial", 4, 3, "Index clause and 3-month forward cover", "P03", "Mitigating", 7),
    ("R-03", "Winter storms disrupt LTL deliveries", "Logistics", 2, 3, "Pre-build buffer of fluid and hardware; backup carrier", "P03", "Open", 30),
    ("R-04", "Welder shortage at Ironvale Fabrication", "Contract manufacturer", 4, 4, "Weekly capacity call; qualify second fabricator for enclosures", "P02", "Open", 45),
    ("R-05", "Ester fluid supplier allocation", "Supply", 2, 2, "Annual contract with volume commitment", "P03", "Closed", -20),
]
LSPS = [  # name, mode, on-time share, mean days late, cost per kg, shipments, premium
    ("Northline Freight", "LTL", 0.93, 2, 0.45, 60, False), ("Tallmark Logistics", "FTL", 0.96, 1, 0.25, 30, False),
    ("Bayport Ocean Logistics", "Ocean", 0.78, 9, 0.35, 20, False), ("Cascade Expedite", "Air / hot shot", 0.97, 1, 4.5, 14, True),
]
SAVINGS = [  # id, title, category, item, supplier, owner, stage, baseline, savings, start offset, target offset, realized
    ("SP-01", "Shift current-transformer share to Kestavo", "Alternative source", "CT-600", "S121", "P01", "In implementation", 120000, 14000, -150, 40, 6000),
    ("SP-02", "Magnet-wire price index renegotiation", "Negotiation", "CU-MAG", "S150", "P03", "Realized", 820000, 64000, -300, -120, 58000),
    ("SP-03", "Second source for 1200 A vacuum breakers", "Alternative source", "VCB-15-1200", "S101", "P01", "Validated", 1100000, 66000, -90, 150, 0),
    ("SP-04", "Enclosure VA/VE: standard 36 in design", "VA/VE", "ENC-SWG-36", "CM200", "P02", "Idea", 240000, 24000, -20, 240, 0),
    ("SP-05", "Hardware kit consolidation", "Consolidation", "HW-KIT-SWG", "S180", "P03", "Realized", 160000, 21000, -260, -150, 19000),
    ("SP-06", "Returnable packaging with Ironvale", "Packaging", "", "CM200", "P02", "In implementation", 90000, 12000, -120, -10, 3000),
    ("SP-07", "Ester fluid annual contract", "Negotiation", "FLUID-ESTER", "S160", "P03", "Realized", 450000, 38000, -280, -170, 34000),
    ("SP-08", "Inbound freight lane tender", "Logistics", "", "", "P03", "Validated", 260000, 22000, -60, 60, 0),
    ("SP-09", "Relay framework agreement", "Negotiation", "RLY-FDR", "S110", "P01", "Realized", 600000, 72000, -330, -200, 66000),
]


# billing plan: milestone, trigger, % of contract, planned date offset from (start | ship)
BILLING = [("M1", "Order", "Order", 10, "start", -150), ("M2", "Drawings approved", "Drawings approved", 20, "start", -75),
           ("M3", "Start of manufacturing", "Build start", 20, "start", 0), ("M4", "Shipment", "Shipment", 40, "ship", 0),
           ("M5", "Commissioning", "Commissioning", 10, "ship", 45)]
COST_SHARE = {"Switchgear": dict(Labour=.16, Engineering=.07, Freight=.02, Commissioning=.04, Contingency=.03),
              "Transformers": dict(Labour=.20, Engineering=.05, Freight=.025, Commissioning=.02, Contingency=.03)}
CHANGE_ORDERS = [  # id, project, description, price, cost, element, status, submitted offset, decided offset
    ("CO-2602-01", "P-2602", "Add one feeder section", 95000, 58000, "Material", "Approved", -70, -55),
    ("CO-2604-01", "P-2604", "Factory witness test", 8000, 5000, "Engineering", "Approved", -40, -32),
    ("CO-2606-01", "P-2606", "Change HV bushing specification", 6500, 4000, "Material", "Approved", -30, -20),
    ("CO-2605-01", "P-2605", "Arc-flash relay upgrade", 22000, 14000, "Material", "Pending", -12, None),
    ("CO-2611-01", "P-2611", "Second incomer and tie breaker", 140000, 88000, "Material", "Pending", -41, None),
    ("CO-2609-01", "P-2609", "Extended warranty to 5 years", 12000, 0, "Contingency", "Rejected", -50, -35),
]


def _financials(data: Dataset) -> Dataset:
    """WBS budgets, actual costs, change orders, billing plans and submittals for the 14 projects."""
    from flowline.ctb import rolled_cost

    roll = rolled_cost(data)
    d = lambda off: AS_OF + timedelta(days=int(off))  # noqa: E731
    pj = data.projects
    wbs, acts, bills, subs = [], [], [], []
    co_cost = {}
    for c in CHANGE_ORDERS:
        if c[6] == "Approved":
            co_cost[(c[1], c[5])] = co_cost.get((c[1], c[5]), 0) + c[4]
    for p in pj.itertuples():
        pid, status = p.project_id, p.status_key
        mat = roll[p.top_item] * p.qty
        start = p.planned_build_start.date()
        ship = p.required_ship_date.date()
        so = (start - AS_OF).days
        sold = {"Material": round(mat * 0.985 - co_cost.get((pid, "Material"), 0), -2)}
        for el, sh in COST_SHARE[p.product_family].items():
            sold[el] = round(mat * sh, -2)
        for el, v in sold.items():
            wbs.append(dict(project_id=pid, cost_element=el, as_sold=v, budget=v + co_cost.get((pid, el), 0)))
        bud = {el: v + co_cost.get((pid, el), 0) for el, v in sold.items()}
        a = {el: 0.0 for el in sold}
        if status == "built":
            a.update(Material=mat, Labour=bud["Labour"] * 1.04, Engineering=bud["Engineering"] * 0.98, Freight=bud["Freight"] * 0.4)
        elif status == "in build":
            a.update(Material=mat + (18000 if pid == "P-2603" else 0), Labour=bud["Labour"] * 0.55,
                     Engineering=bud["Engineering"] * 1.05)
        elif status == "released":
            a["Engineering"] = bud["Engineering"] * (0.9 if so <= 30 else 0.5)
        else:
            a["Engineering"] = bud["Engineering"] * 0.15
        for el, v in a.items():
            etc = bud["Labour"] * 0.6 if (pid == "P-2602" and el == "Labour") else 0.0
            acts.append(dict(project_id=pid, cost_element=el, cost_to_date=round(v, -1), etc_override=round(etc, -1)))
        # submittals: customer drawings (hold M2), plus supplier documents
        sub_d = so - 110
        ga = dict(submittal_id=f"S-{pid[2:]}-GA", project_id=pid, direction="Customer", document="General arrangement and single-line drawings",
                  party=p.customer, submitted=d(sub_d) if sub_d <= 0 else None, due=d(sub_d + 21), returned=None,
                  status="Draft" if sub_d > 0 else "Submitted", holds="M2")
        if sub_d + 17 <= 0:
            ga.update(returned=d(sub_d + 17), status="Approved")
        if pid == "P-2611":
            ga.update(submitted=d(-40), due=d(-19), returned=d(-22), status="Resubmit")
        if pid == "P-2609":
            ga.update(submitted=d(-30), due=d(-9), returned=None, status="Submitted")
        subs.append(ga)
        # billing plan
        for mid, name, trig, pct, base, off in BILLING:
            planned = (start if base == "start" else ship) + timedelta(days=off)
            inv = paid = None
            if trig == "Order" and planned <= AS_OF:
                inv = planned
            if trig == "Drawings approved" and ga["status"] == "Approved" and ga["returned"] + timedelta(days=3) <= AS_OF and pid != "P-2602":
                inv = ga["returned"] + timedelta(days=3)
            if trig == "Build start" and status in ("in build", "built"):
                inv = start + timedelta(days=2)
            if inv is not None and inv + timedelta(days=40) <= AS_OF:
                paid = inv + timedelta(days=40)
            if (pid, mid) in {("P-2603", "M2"), ("P-2612", "M1"), ("P-2610", "M1")}:
                paid = None          # unpaid: a disputed drawings invoice and two slow payers
            bills.append(dict(project_id=pid, milestone_id=mid, name=name, trigger=trig, pct=pct, planned_date=planned,
                              invoice_no=f"INV-{pid[2:]}-{mid}" if inv else "", invoice_date=inv, amount_invoiced=0.0,
                              paid_date=paid))
    subs += [
        dict(submittal_id="S-2605-VCB", project_id="P-2605", direction="Supplier", document="Breaker type-test report",
             party="Veltrano Breakers", submitted=d(-45), due=d(-30), returned=d(-33), status="Approved", holds=""),
        dict(submittal_id="S-2606-OLTC", project_id="P-2606", direction="Supplier", document="Tap changer outline drawing",
             party="Ellerby Tap Changers", submitted=d(-60), due=d(-45), returned=d(-47), status="Approved", holds=""),
        dict(submittal_id="S-2613-OLTC", project_id="P-2613", direction="Supplier", document="Tap changer datasheet",
             party="Ellerby Tap Changers", submitted=None, due=d(-5), returned=None, status="Draft", holds="release"),
    ]
    cos = pd.DataFrame([dict(co_id=i, project_id=pj_, description=t, price_change=pc, cost_change=cc, cost_element=el, status=st,
                             submitted=d(so_), decided=d(de) if de is not None else None)
                        for i, pj_, t, pc, cc, el, st, so_, de in CHANGE_ORDERS])
    return replace(data, wbs_budget=normalize("wbs_budget", pd.DataFrame(wbs)),
                   cost_actuals=normalize("cost_actuals", pd.DataFrame(acts)),
                   change_orders=normalize("change_orders", cos),
                   billing_milestones=normalize("billing_milestones", pd.DataFrame(bills)),
                   submittals=normalize("submittals", pd.DataFrame(subs)))


def _extras(data: Dataset, rng) -> Dataset:
    """Team, objectives, KPI history, action log, consumption, risks, shipments and savings projects."""
    from flowline.engine import run
    from flowline.team import department_values

    d = lambda off: AS_OF + timedelta(days=int(off))  # noqa: E731
    team = pd.DataFrame(TEAM, columns=["person_id", "name", "role", "scope"])
    obj = [dict(owner="Department", kpi=k, target=t, direction=b) for k, t, b in DEPT_TARGETS]
    for pid, _, role, _ in TEAM:
        for k, t, b in ROLE_TARGETS.get(role, []):
            obj.append(dict(owner=pid, kpi=k, target=t, direction=b))
    months = pd.period_range(end=pd.Timestamp(AS_OF).to_period("M") - 1, periods=12, freq="M").to_timestamp()
    cons = []
    for item, (mu, cv) in CONSUMPTION.items():
        for m in months:
            cons.append(dict(item_id=item, month=m.strftime("%Y-%m"), qty=max(0.0, round(rng.normal(mu, mu * cv), 0 if mu < 100 else -2))))
    acts = pd.DataFrame([dict(action_id=a, opened=d(o), stakeholder=st, owner=ow, ref=rf, action=ac, due=d(du), status=stt,
                              closed=d(c) if c is not None else None, notes="") for a, o, st, ow, rf, ac, du, stt, c in ACTIONS])
    risks = pd.DataFrame([dict(risk_id=i, risk=t, category=c, likelihood=lk, impact=im, mitigation=mi, owner=ow, status=st,
                               due=d(du)) for i, t, c, lk, im, mi, ow, st, du in RISKS])
    ship = []
    reasons = ["Tap changer late for P-2603", "Breaker past due", "HV bushing shortage", "CT rework", "Relay for P-2602"]
    for name, mode, p_on, late, rate, n, prem in LSPS:
        for i in range(n):
            sd = AS_OF - timedelta(days=int(rng.integers(5, 360)))
            transit = 2 if prem else (28 if mode == "Ocean" else 4)
            promised = sd + timedelta(days=transit)
            delay = 0 if rng.random() < p_on else 1 + int(rng.exponential(late))
            w = float(rng.integers(200, 900)) if prem else float(rng.integers(400, 9000))
            ship.append(dict(shipment_id=f"SH{len(ship) + 1:04d}", lsp=name, mode=mode, ship_date=sd, promised_date=promised,
                             delivered_date=min(promised + timedelta(days=delay), AS_OF - timedelta(days=1)),
                             cost=round(w * rate * rng.uniform(0.85, 1.2), 0), weight_kg=w, premium="Y" if prem else "N",
                             reason=reasons[i % len(reasons)] if prem else ""))
    sav = pd.DataFrame([dict(project_id=i, title=t, category=c, item_id=it, supplier_id=sp, owner=ow, stage=st, baseline_spend=b,
                             annual_savings=sv, start_date=d(so), target_date=d(to), realized_to_date=rz)
                        for i, t, c, it, sp, ow, st, b, sv, so, to, rz in SAVINGS])
    data = replace(data, team=normalize("team", team), objectives=normalize("objectives", pd.DataFrame(obj)),
                   actions=normalize("actions", acts), consumption_history=normalize("consumption_history", pd.DataFrame(cons)),
                   risk_register=normalize("risk_register", risks), shipments=normalize("shipments", pd.DataFrame(ship)),
                   savings_projects=normalize("savings_projects", sav),
                   settings=replace(data.settings, savings_target=250000.0))
    # KPI history: 11 closed months drifting toward today's values
    now = department_values(run(data))
    start = {"turns": 3.9, "supplier_otd_pct": 88.0, "ctb_pct": 55.0, "past_due_lines": 9.0, "ppv_pct": 2.6,
             "excess_value": 160000.0, "cm_otd_pct": 90.0}
    hist = []
    for k, v0 in start.items():
        v1 = float(now[k])
        for i, m in enumerate(months[1:]):
            f = i / (len(months) - 1)
            v = v0 + (v1 - v0) * f
            noise = rng.normal(0, abs(v1 - v0) * 0.15 + (0.05 if k == "turns" else 1.0))
            val = v + noise
            if k in ("past_due_lines",):
                val = max(0, round(val))
            hist.append(dict(month=m.strftime("%Y-%m"), kpi=k, value=round(val, 2)))
    return replace(data, kpi_history=normalize("kpi_history", pd.DataFrame(hist)))


def _items_and_bom():
    items = [dict(zip(list(SCHEMA["items"]), r, strict=True)) for r in ITEMS]
    bom = [dict(parent_item=p, component_item=c, qty_per=q) for p, c, q in STD_BOM]
    projects = []
    for pid, cust, kind, spec, qty, status, off, bdays, slack, prio, pkg in PROJECTS:
        start = AS_OF + timedelta(days=off)
        n = pid.replace("P-", "")
        if kind == "SWG":
            inc, bkr = spec
            top = f"LU-{n}"
            desc = f"MV switchgear lineup, {inc} incomer + {bkr} feeder sections ({pid})"
            bom += [dict(parent_item=top, component_item="SA-SWG-INC", qty_per=inc),
                    dict(parent_item=top, component_item="SA-SWG-BKR", qty_per=bkr)]
            pkg_id = f"PKG-PC-{n}"
            items.append(dict(item_id=pkg_id, description=f"Engineered protection and SCADA package ({pid})", item_type="RM",
                              make_buy="buy", uom="EA", std_cost=pkg, lead_time_days=70, supplier_id="S110",
                              commodity="Protection", buyer="B1 Electrical", on_hand=1 if pid == "P-2605" else 0,
                              safety_stock=0, cm_hours_per_unit=0))
            bom.append(dict(parent_item=top, component_item=pkg_id, qty_per=1))
            family = "Switchgear"
        else:
            top = f"TX-{n}"
            desc = f"{'Pad-mount transformer 2.5' if spec == '2.5' else 'Substation transformer 7.5'} MVA ({pid})"
            bom += [dict(parent_item=top, component_item=c, qty_per=q) for c, q in TX_BOM[spec]]
            family = "Transformers"
        items.append(dict(item_id=top, description=desc, item_type="FG", make_buy="make", uom="EA", std_cost=0,
                          lead_time_days=bdays, supplier_id="", commodity="Finished goods", buyer="", on_hand=0,
                          safety_stock=0, cm_hours_per_unit=0))
        projects.append(dict(project_id=pid, customer=cust, product_family=family, top_item=top, qty=qty, status=status,
                             planned_build_start=start, build_days=bdays,
                             required_ship_date=start + timedelta(days=bdays + slack), sell_value=0.0, priority=prio))
    return pd.DataFrame(items), pd.DataFrame(bom), pd.DataFrame(projects)


# Value stream for medium-voltage switchgear lineups. Hours per lineup; targets are the future state.
PROCESS_STEPS = [
    # seq, kind, name, stock_type, C/T h, C/O h, uptime %, operators, target days, target C/O h
    (10, "Stock", "Raw material", "Raw materials", None, None, None, None, 25, None),
    (20, "Process", "Kitting", "", 8, 1, 98, 2, None, None),
    (30, "Stock", "Work in process", "WIP", None, None, None, None, 30, None),
    (40, "Process", "Fabrication", "", 72, 6, 88, 3, None, 2),
    (50, "Stock", "Sections waiting", "Semi-finished", None, None, None, None, None, None),
    (60, "Process", "Assembly", "", 112, 4, 95, 5, None, None),
    (70, "Process", "Test & ship", "", 32, 3, 90, 2, None, None),
    (80, "Stock", "Finished goods", "Finished goods", None, None, None, None, 20, None),
]


def _process_steps(data: Dataset) -> Dataset:
    cols = ["seq", "kind", "name", "stock_type", "cycle_time_hours", "changeover_hours", "uptime_pct", "operators",
            "target_days", "target_changeover_hours"]
    df = pd.DataFrame(PROCESS_STEPS, columns=cols).assign(product_family="Switchgear")
    return replace(data, process_steps=normalize("process_steps", df))


# ---- Shop floor: work centres, today's build plan (as of 13:00), 4 weeks of history, people and ERP items ----
WORK_CENTERS = [  # id, name, family, shift hours, shifts, people needed per shift
    ("KIT", "Kitting", "Both", 8, 1, 2),
    ("FAB", "Sheet metal & fabrication", "Switchgear", 8, 2, 3),
    ("BUS", "Bus bar shop", "Switchgear", 8, 1, 2),
    ("SWA", "Switchgear assembly", "Switchgear", 8, 1, 5),
    ("CCW", "Core & coil winding", "Transformers", 8, 2, 4),
    ("TRA", "Transformer assembly", "Transformers", 8, 1, 4),
    ("TST", "Test bay", "Both", 8, 1, 2),
    ("SHP", "Shipping", "Both", 8, 1, 2),
]
# today's plan: wc, project, operation, planned h (full shift), earned h to 13:00, clocked h to 13:00, needed, assigned
TODAY_PLAN = [
    ("KIT", "P-2604", "Kit transformer P-2604 (build starts 29 Nov)", 16, 5.5, 12.0, 2, 2),
    ("FAB", "P-2605", "Enclosures and doors for P-2605", 24, 17.5, 18.0, 3, 3),
    ("BUS", "P-2605", "Copper bus for P-2605", 16, 11.8, 12.0, 2, 2),
    ("SWA", "P-2602", "Wire and assemble sections 4-6, P-2602", 40, 25.2, 24.0, 5, 4),
    ("CCW", "P-2603", "LV and HV windings, P-2603", 32, 23.6, 24.0, 4, 4),
    ("TRA", "P-2603", "Core stacking and tanking prep, P-2603", 32, 22.8, 24.0, 4, 4),
    ("TST", "P-2602", "Routine tests sections 1-3, P-2602", 16, 9.0, 12.0, 2, 2),
    ("SHP", "P-2601", "Crate and load P-2601 (ships 25 Nov)", 16, 12.4, 12.0, 2, 2),
]
OPERATORS = [  # fictional first names and initials
    ("OP01", "Amir K.", "Day", "KIT"), ("OP02", "Bea L.", "Day", "KIT"), ("OP03", "Carlos M.", "Day", "FAB"),
    ("OP04", "Dana P.", "Day", "FAB"), ("OP05", "Eli R.", "Day", "FAB"), ("OP06", "Farah S.", "Day", "BUS"),
    ("OP07", "Gus T.", "Day", "BUS"), ("OP08", "Hana V.", "Day", "SWA"), ("OP09", "Ivan W.", "Day", "SWA"),
    ("OP10", "Jo Y.", "Day", "SWA"), ("OP11", "Kiran Z.", "Day", "SWA"), ("OP12", "Lucia A.", "Day", "SWA"),
    ("OP13", "Marco B.", "Day", "CCW"), ("OP14", "Nadia C.", "Day", "CCW"), ("OP15", "Omar D.", "Day", "CCW"),
    ("OP16", "Pia E.", "Day", "CCW"), ("OP17", "Quinn F.", "Day", "TRA"), ("OP18", "Ravi G.", "Day", "TRA"),
    ("OP19", "Sana H.", "Day", "TRA"), ("OP20", "Theo J.", "Day", "TRA"), ("OP21", "Uma N.", "Day", "TST"),
    ("OP22", "Victor O.", "Day", "TST"), ("OP23", "Wen Q.", "Day", "SHP"), ("OP24", "Xavier U.", "Day", "SHP"),
    ("OP25", "Yara I.", "Evening", "FAB"), ("OP26", "Zane X.", "Evening", "FAB"), ("OP27", "Aiko M.", "Evening", "FAB"),
    ("OP28", "Bruno T.", "Evening", "CCW"), ("OP29", "Chloe R.", "Evening", "CCW"), ("OP30", "Dev S.", "Evening", "CCW"),
    ("OP31", "Esme P.", "Evening", "CCW"),
]
# skill levels: 0 not trained, 1 in training, 2 with help, 3 independent, 4 can train others
SKILL_EXTRA = {  # cross-training beyond the home work centre
    "OP01": {"SHP": 3}, "OP02": {"SHP": 2}, "OP05": {"BUS": 3}, "OP07": {"SWA": 2}, "OP08": {"TST": 2},
    "OP09": {"BUS": 2}, "OP12": {"KIT": 3}, "OP16": {"TRA": 3}, "OP20": {"CCW": 2}, "OP22": {"SWA": 3},
    "OP24": {"KIT": 3}, "OP14": {"TST": 1},
}
SKILL_HOME = {  # home-station level where it is not 3
    "OP01": 4, "OP03": 4, "OP06": 4, "OP08": 4, "OP10": 2, "OP11": 1, "OP13": 4, "OP17": 4, "OP21": 4,
    "OP22": 2, "OP23": 4, "OP25": 4, "OP27": 2, "OP28": 4, "OP31": 1,
}


def _shop_floor(data: Dataset, rng) -> Dataset:
    d = lambda off: AS_OF + timedelta(days=int(off))  # noqa: E731
    wc = pd.DataFrame(WORK_CENTERS, columns=["wc_id", "name", "product_family", "shift_hours", "shifts", "people_needed"])
    # 20 working days of history before today, then today
    days = []
    k = 1
    while len(days) < 20:
        x = d(-k)
        if x.weekday() < 5:
            days.append(x)
        k += 1
    days = sorted(days)
    sched, quality, downtime = [], [], []
    for day in days:
        for w in WORK_CENTERS:
            planned = w[5] * 8.0
            att = float(np.clip(rng.normal(0.95, 0.04), 0.82, 1.04))
            if w[0] == "SWA" and day >= d(-6):
                att -= 0.06                     # assembly has run behind for a week
            prod = float(np.clip(rng.normal(0.92, 0.03), 0.84, 0.99))
            earned = round(planned * att, 1)
            actual = round(earned / prod, 1)
            ot = round(max(0.0, actual - planned) + (rng.uniform(0, 3) if rng.random() < .35 else 0.0), 1)
            sched.append((day, w[0], "", "Daily plan", planned, earned, actual, w[5], w[5] - (1 if rng.random() < .08 else 0), ot))
            if w[0] in ("TST", "FAB", "CCW"):
                insp = int(rng.integers(4, 9))
                fail = int(rng.random() < (0.22 if w[0] == "TST" else 0.10))
                quality.append((day, w[0], "", insp, insp - fail, "" if not fail else
                                {"TST": "Hi-pot fail: bus joint torque", "FAB": "Door gap out of tolerance",
                                 "CCW": "Winding insulation damage"}[w[0]]))
    # downtime: waiting for material leads the Pareto, then the press brake
    reasons = [("Waiting for material", ["KIT", "SWA", "TRA", "BUS"], 0.35, (30, 120)),
               ("Machine breakdown", ["FAB", "CCW"], 0.18, (20, 150)), ("Changeover", ["FAB", "CCW", "BUS"], 0.25, (20, 60)),
               ("Waiting for drawings", ["SWA", "FAB"], 0.10, (30, 90)), ("Quality hold", ["TST", "TRA"], 0.08, (30, 90)),
               ("No operator", ["SWA", "TST"], 0.04, (60, 240))]
    notes = {"Waiting for material": "Kit incomplete at shift start", "Machine breakdown": "Press brake hydraulic fault",
             "Changeover": "Tooling change", "Waiting for drawings": "Revision not released", "Quality hold": "Awaiting NCR decision",
             "No operator": "Absence not covered"}
    for day in days:
        for _ in range(int(rng.integers(1, 4))):
            r_ = reasons[int(rng.choice(len(reasons), p=[x[2] for x in reasons]))]
            downtime.append((day, str(rng.choice(r_[1])), r_[0], float(rng.integers(*r_[3])), notes[r_[0]]))
    # today
    today = AS_OF
    for w, pj, op, pl, ea, ac, need, have in TODAY_PLAN:
        sched.append((today, w, pj, op, pl, ea, ac, need, have, 0.0))
    quality += [(today, "TST", "P-2602", 6, 5, "Hi-pot fail on section 2: bus joint torque"),
                (today, "FAB", "P-2605", 8, 8, ""), (today, "CCW", "P-2603", 3, 3, "")]
    downtime += [(today, "KIT", "Waiting for material", 150.0, "P-2604 core and radiators not in stock (due 25-26 Nov)"),
                 (today, "SWA", "No operator", 240.0, "One assembler absent, not covered"),
                 (today, "FAB", "Changeover", 35.0, "Tooling change for P-2605 doors"),
                 (today, "TST", "Quality hold", 90.0, "Section 2 failed hi-pot: re-torque bus joints and retest")]
    hourly = []
    tot = {w[0]: (w[3], w[4]) for w in TODAY_PLAN}
    shape = [0.10, 0.13, 0.14, 0.13, 0.06, 0.14]      # 07-13, lunch at 11
    for w, (pl, ea) in tot.items():
        plan_h = [pl * 0.75 * x / sum(shape) for x in shape]
        noise = rng.normal(1, 0.08, len(shape))
        earn_h = np.array(plan_h) * noise
        earn_h = earn_h / earn_h.sum() * ea
        for i in range(len(shape)):
            hourly.append((today, 7 + i, w, round(plan_h[i], 2), round(float(earn_h[i]), 2)))
    safety = [(d(-41), "FAB", "Recordable", "Hand laceration on sheet edge, stitches"),
              (d(-9), "TRA", "Near miss", "Crane load swung near walkway"),
              (d(-4), "FAB", "First aid", "Cut on deburring station"),
              (d(-3), "SWA", "Near miss", "Tripping hazard: cable reel in aisle"),
              (d(-1), "SHP", "Near miss", "Forklift reversing without spotter")]
    ops = pd.DataFrame(OPERATORS, columns=["operator_id", "name", "shift", "home_wc"])
    skills = []
    for o in OPERATORS:
        skills.append((o[0], o[3], SKILL_HOME.get(o[0], 3)))
        for w, lv in SKILL_EXTRA.get(o[0], {}).items():
            skills.append((o[0], w, lv))
    erp = [("CO-1000452", "Completion not posted", "TST", "P-2601", d(-3), 633050.0, "Production supervisor",
            "Final confirmation of P-2601 not posted: no finished-goods receipt, so shipping cannot create the delivery"),
           ("COGI-P2602", "Backflush error", "SWA", "P-2602", d(-2), 12400.0, "Production supervisor",
            "4 component lines failed backflush on the P-2602 order"),
           ("MI-26-0118", "Count variance", "BUS", "", d(-5), 3900.0, "Inventory analyst",
            "Copper bus bar BUS-CU-1200: count 14 m below SAP"),
           ("SCRAP-1122", "Scrap not posted", "FAB", "P-2605", d(-1), 640.0, "Production supervisor", "Two sheets scrapped, not posted"),
           ("LBL-P2601", "Shipping labels", "SHP", "P-2601", today, 0.0, "Shipping", "Crate labels for P-2601 not printed"),
           ("TECO-P2598", "Order past finish", "SWA", "", d(-12), 0.0, "Production supervisor",
            "Old order technically complete but not closed")]
    cms = [("CM-031", d(-4), "Tier 1", "Safety", "FAB", "First aid: cut at deburring", "No cut-resistant gloves at the station",
            "Gloves and edge guard at the deburring station", "Production supervisor", d(1), "Done"),
           ("CM-033", d(-3), "Tier 1", "Quality", "TST", "FPY 86% at test", "Bus joint torque not marked",
            "Add torque-and-mark check to the assembly checklist", "Assembly lead", d(2), "Open"),
           ("CM-034", d(-1), "Tier 2", "Delivery", "SWA", "Attainment 88% for the week", "Copper bus kits arrive after assembly starts",
            "Kit bus with the assembly kit two days ahead", "Kitting lead", d(4), "Open")]
    return replace(
        data,
        work_centers=normalize("work_centers", wc),
        shop_schedule=normalize("shop_schedule", pd.DataFrame(sched, columns=["date", "wc_id", "project_id", "operation", "planned_hours",
                                "earned_hours", "actual_hours", "people_needed", "people_assigned", "overtime_hours"])),
        hourly_output=normalize("hourly_output", pd.DataFrame(hourly, columns=["date", "hour", "wc_id", "planned_hours", "earned_hours"])),
        downtime=normalize("downtime", pd.DataFrame(downtime, columns=["date", "wc_id", "reason", "minutes", "note"])),
        quality_checks=normalize("quality_checks", pd.DataFrame(quality, columns=["date", "wc_id", "project_id", "inspected", "passed",
                                 "defect"])),
        safety_events=normalize("safety_events", pd.DataFrame(safety, columns=["date", "wc_id", "type", "description"])),
        operators=normalize("operators", ops),
        skills=normalize("skills", pd.DataFrame(skills, columns=["operator_id", "wc_id", "level"])),
        erp_open_items=normalize("erp_open_items", pd.DataFrame(erp, columns=["ref", "kind", "wc_id", "project_id", "created", "value",
                                 "owner", "note"])),
        countermeasures=normalize("countermeasures", pd.DataFrame(cms, columns=["cm_id", "date", "tier", "metric", "wc_id", "miss",
                                  "cause", "countermeasure", "owner", "due", "status"])),
    )


# ---- Weekly capacity plan: machines and labour pools, routings per unit, production orders ----
RESOURCES = [  # id, name, kind, wc, units, shifts/day, hours/shift, days/week, efficiency %
    ("LAS1", "Laser cutter", "Machine", "FAB", 1, 2, 8, 5, 85), ("PB1", "Press brake", "Machine", "FAB", 1, 2, 8, 5, 80),
    ("CNC1", "Bus CNC punch", "Machine", "BUS", 1, 1, 8, 5, 85), ("WND", "Winding machines", "Machine", "CCW", 2, 2, 8, 5, 85),
    ("OVN1", "Vacuum drying oven", "Machine", "TRA", 1, 3, 8, 5, 90), ("HVT1", "HV test set", "Machine", "TST", 1, 1, 8, 5, 90),
    ("L-KIT", "Kitters", "Labour", "KIT", 2, 1, 8, 5, 90), ("L-FAB", "Fabricators", "Labour", "FAB", 3, 2, 8, 5, 90),
    ("L-BUS", "Bus fitters", "Labour", "BUS", 2, 1, 8, 5, 90), ("L-SWA", "Switchgear assemblers", "Labour", "SWA", 5, 1, 8, 5, 90),
    ("L-CCW", "Winders", "Labour", "CCW", 4, 2, 8, 5, 90), ("L-TRA", "Transformer fitters", "Labour", "TRA", 4, 1, 8, 5, 90),
    ("L-TST", "Testers", "Labour", "TST", 2, 1, 8, 5, 90),
]
ROUTINGS = [  # family, seq, step, wc, machine, machine h/unit, labour pool, labour h/unit, weeks after the previous step
    ("Switchgear", 10, "Kit", "KIT", "", 0, "L-KIT", 1.5, 0), ("Switchgear", 20, "Cut", "FAB", "LAS1", 0.8, "L-FAB", 1.5, 0),
    ("Switchgear", 30, "Bend and weld", "FAB", "PB1", 1.2, "L-FAB", 5.5, 0),
    ("Switchgear", 40, "Bus", "BUS", "CNC1", 0.6, "L-BUS", 3.5, 0),
    ("Switchgear", 50, "Assemble", "SWA", "", 0, "L-SWA", 16, 1), ("Switchgear", 60, "Test", "TST", "HVT1", 1.5, "L-TST", 3, 0),
    ("Transformers", 10, "Kit", "KIT", "", 0, "L-KIT", 6, 0), ("Transformers", 20, "Wind", "CCW", "WND", 50, "L-CCW", 100, 0),
    ("Transformers", 30, "Assemble and dry", "TRA", "OVN1", 30, "L-TRA", 70, 1),
    ("Transformers", 40, "Test", "TST", "HVT1", 12, "L-TST", 20, 1),
]
SECTIONS = {"P-2602": 3, "P-2605": 8, "P-2607": 10, "P-2609": 6, "P-2611": 12, "P-2614": 8}   # switchgear sections per lineup
FROM_STEP = {"P-2602": "Assemble", "P-2603": "Assemble and dry"}                            # in build: what is left


def _capacity(data: Dataset) -> Dataset:
    res = pd.DataFrame(RESOURCES, columns=["resource_id", "name", "kind", "wc_id", "units", "shifts_per_day", "hours_per_shift",
                                           "days_per_week", "efficiency_pct"]).assign(overtime_hours=0.0)
    rt = pd.DataFrame(ROUTINGS, columns=["product_family", "seq", "step", "wc_id", "machine_id", "machine_hours", "labour_id",
                                         "labour_hours", "lag_weeks"])
    rows = []
    for p in data.projects.itertuples():
        if p.status in ("Built", "Shipped"):
            continue
        qty = SECTIONS.get(p.project_id, 8) if p.product_family == "Switchgear" else p.qty
        rows.append((f"MO-{p.project_id[2:]}", p.project_id, p.product_family, p.top_item, qty, p.required_ship_date,
                     p.priority, FROM_STEP.get(p.project_id, "")))
    po = pd.DataFrame(rows, columns=["order_id", "project_id", "product_family", "item", "qty", "due_date", "priority", "from_step"])
    cal = pd.DataFrame([(AS_OF + timedelta(days=28), "ALL", 60.0, "Plant closed 24-25 Dec"),
                        (AS_OF + timedelta(days=35), "ALL", 60.0, "Plant closed 31 Dec-1 Jan")],
                       columns=["week_start", "resource_id", "available_pct", "note"])
    return replace(data, resources=normalize("resources", res), routings=normalize("routings", rt),
                   production_orders=normalize("production_orders", po), capacity_calendar=normalize("capacity_calendar", cal))


def build_sample(as_of: date | None = None) -> Dataset:
    """The full sample dataset. ``as_of`` is accepted for API symmetry; the sample is anchored at ``AS_OF``."""
    from flowline.ctb import rolled_cost, run_ctb
    from flowline.inventory import project_inventory

    rng = np.random.default_rng(7)
    items, bom, projects = _items_and_bom()
    settings = Settings(company=COMPANY, as_of_date=AS_OF, fiscal_year_end=date(2026, 12, 31), turns_target=6.5)
    sup = pd.DataFrame(SUPPLIERS, columns=["supplier_id", "name", "supplier_type", "region", "commodity"])
    base = Dataset(normalize("items", items), normalize("bom", bom), normalize("projects", projects), suppliers=sup,
                   settings=settings)
    roll = rolled_cost(base)
    # std cost of sub-assemblies = rolled material cost; selling price = cost x margin
    items.loc[items["item_type"] == "SFG", "std_cost"] = items.loc[items["item_type"] == "SFG", "item_id"].map(roll).round(0)
    conv = 1 + settings.conversion_cost_pct / 100
    projects["sell_value"] = [round(roll[t] * q * conv * m, -3) for t, q, m in
                              zip(projects["top_item"], projects["qty"], rng.uniform(1.28, 1.42, len(projects)), strict=True)]
    base = replace(base, items=normalize("items", items), projects=normalize("projects", projects))

    # ---- open purchase orders
    std = dict(zip(items["item_id"], items["std_cost"], strict=True))
    sup_of = dict(zip(items["item_id"], items["supplier_id"], strict=True))
    lead = dict(zip(items["item_id"], items["lead_time_days"], strict=True))
    po_rows: list[dict] = []
    po_no = [4500018200]

    def po(item, qty, promised_off, project="", supplier=None, price_f=1.0):
        po_no[0] += 7
        promised = AS_OF + timedelta(days=int(promised_off))
        po_rows.append(dict(po_number=str(po_no[0]), po_line=10, item_id=item, supplier_id=supplier or sup_of[item],
                            qty_open=qty, unit_price=round(std[item] * price_f, 2),
                            order_date=promised - timedelta(days=int(lead[item])), promised_date=promised, project_id=project))

    # scripted situations (the stories in the user guide)
    po("OLTC-75", 1, 55)                    # P-2606: tap changer six weeks late -> project late
    po("OLTC-75", 2, 75)                    # P-2610: arrives after need, float absorbs part of it
    po("VCB-15-2000", 2, -12)               # past due, for P-2607
    po("VCB-15-1200", 6, 22, "P-2614")      # pegged to P-2614 (planned) but due in Dec -> push out across year end
    po("ENC-SWG-36", 14, 24, "P-2611")      # pegged to P-2611, early -> push out
    po("CU-MAG", 3300, 12, "P-2612")        # pegged to P-2612 coils, early -> push out
    po("RLY-LEGACY", 10, 30)                # superseded relay still on order -> cancel
    po("HW-KIT-SWG", 60, 18, supplier="S181")   # over-ordered hardware -> reduce
    po("CORE-2500", 2, 2)                   # P-2604: arrives just in time
    po("RAD-1200", 6, 3)                    # P-2604

    seeded = replace(base, purchase_orders=normalize("purchase_orders", pd.DataFrame(po_rows)))
    first = run_ctb(seeded, settings)
    gaps = first.allocations[first.allocations["kind"] == "Shortage"]
    skip = {("P-2613", "OLTC-75")}          # long-lead part nobody has ordered yet
    for g in gaps.itertuples():
        pj = g.project_id
        if (pj, g.item_id) in skip or (pj == "P-2614" and g.item_id not in ("VCB-15-1200", "VCB-15-2000")):
            continue
        need = (g.need_date - AS_OF).days
        off = need - settings.receive_before_need_days - int(rng.integers(2, 14))
        u = rng.random()
        if u < 0.06:
            off = need + int(rng.integers(2, 9))           # late
        elif u < 0.19 and need < 45:
            off = -int(rng.integers(3, 18))                # past due
        off = max(off, -20)
        peg = pj if g.item_id.startswith("PKG-PC-") else ""
        po(g.item_id, float(np.ceil(g.qty)), off, peg)
    pos = normalize("purchase_orders", pd.DataFrame(po_rows))

    # ---- receipts history (12 months)
    rec = []
    uom = dict(zip(items["item_id"], items["uom"], strict=True))
    for sid, (p_on, late_mu, ppv_mu, p_rej, n) in PROFILES.items():
        its = [i for i, s_ in sup_of.items() if s_ == sid and not i.startswith("PKG-")]
        alt = [r[0] for r in SOURCES if r[1] == sid and r[2] == "Approved"]
        its = sorted(set(its) | set(alt)) or ["HW-KIT-SWG"]
        for _ in range(n):
            it = its[int(rng.integers(len(its)))]
            promised = AS_OF - timedelta(days=int(rng.integers(4, 360)))
            u = rng.random()
            if u < p_on:
                delay = int(rng.integers(-5, 1))
            elif u < p_on + (1 - p_on) * 0.15:
                delay = -int(rng.integers(8, 25))
            else:
                delay = 1 + int(rng.exponential(late_mu))
            received = min(promised + timedelta(days=delay), AS_OF - timedelta(days=1))
            unit = std[it]
            n_hi = 3 if unit >= 20000 else 6 if unit >= 1000 else 40
            qty = {"KG": 1500, "L": 5000}.get(uom[it], int(rng.integers(1, n_hi + 1)))
            rej = int(np.ceil(qty * rng.uniform(0.05, 0.3))) if rng.random() < p_rej and qty > 1 else 0
            rec.append(dict(po_number=str(4500010000 + len(rec) * 3), item_id=it, supplier_id=sid, promised_date=promised,
                            receipt_date=received, qty=qty, qty_rejected=rej,
                            unit_price=round(unit * (1 + ppv_mu + rng.normal(0, 0.015)), 2), std_cost=unit))
    receipts = normalize("receipts", pd.DataFrame(rec))

    src = pd.DataFrame([dict(item_id=i, supplier_id=s_, status=st, share_pct=sh,
                             target_date=AS_OF + timedelta(days=t) if t else None, notes=nt,
                             quoted_price=QUOTES.get((i, s_), 0.0))
                        for i, s_, st, sh, t, nt in SOURCES])
    data = replace(seeded, purchase_orders=pos, receipts=receipts, item_sources=normalize("item_sources", src))

    # ---- CM forecast (sent 18 days ago, before P-2611 was released) and capacity
    ctb = run_ctb(data, settings)
    cm_items = items[items["make_buy"] == "cm"]
    cm_of = dict(zip(cm_items["item_id"], cm_items["supplier_id"], strict=True))
    rq = ctb.requirements[ctb.requirements["item_id"].isin(cm_of)].copy()
    rq["qty"] = rq["qty_required"] - rq["from_stock"]
    start_m = pd.Timestamp(AS_OF).to_period("M").to_timestamp()
    months = pd.period_range(start_m, periods=6, freq="M").to_timestamp()
    rq["month"] = pd.to_datetime(rq["need_date"]).dt.to_period("M").dt.to_timestamp().clip(lower=start_m)
    sent = rq[rq["project_id"] != "P-2611"].groupby(["item_id", "month"])["qty"].sum()
    commit_profile = {"CM200": [1.0, 1.0, 0.7, 0.6, 0.5, 0.5], "CM210": [1.0, 1.0, 1.0, 0.9, 0.8, 0.8],
                      "CM220": [1.0, 0.9, 0.9, 0.8, 0.7, 0.7], "CM230": [1.0, 0.85, 0.8, 0.8, 0.6, 0.6]}
    fc = []
    for it, cm in cm_of.items():
        for i, m in enumerate(months):
            q = float(sent.get((it, m), 0.0))
            q = round(q * rng.uniform(0.9, 1.15)) if q else (2.0 if i >= 4 and it.startswith(("ENC", "BUS")) else 0.0)
            fc.append(dict(cm_id=cm, item_id=it, month=m.strftime("%Y-%m"), forecast_qty=q,
                           committed_qty=float(np.floor(q * commit_profile[cm][i])), sent_date=AS_OF - timedelta(days=18)))
    fcd = pd.DataFrame(fc)
    hrs = dict(zip(cm_items["item_id"], cm_items["cm_hours_per_unit"], strict=True))
    rq["hours"] = rq["qty"] * rq["item_id"].map(hrs)
    rq["cm_id"] = rq["item_id"].map(cm_of)
    load = rq.groupby(["cm_id", "month"])["hours"].sum()
    cap_factor = {"CM200": 1.05, "CM210": 1.4, "CM220": 1.6, "CM230": 1.4}
    caps = []
    for cm, f in cap_factor.items():
        peak = max(float(load.get((cm, m), 0.0)) for m in months)
        base_cap = round(max(peak * f, 100), -1)
        for m in months:
            caps.append(dict(cm_id=cm, month=m.strftime("%Y-%m"), capacity_hours=base_cap * (0.75 if m.month == 12 else 1.0)))
    data = replace(data, cm_forecast=normalize("cm_forecast", fcd), cm_capacity=normalize("cm_capacity", pd.DataFrame(caps)))

    # ---- inventory history: 17 closed months ending last month, trending up into today's balance
    inv = project_inventory(data, run_ctb(data, settings), settings)
    now = dict(zip(inv.current["stock_type"], inv.current["value"], strict=True))
    hist_months = pd.period_range(end=pd.Timestamp(AS_OF).to_period("M") - 1, periods=17, freq="M").to_timestamp()
    total_now = sum(now.values())
    t12_target = 3.35 * total_now
    hist = []
    for i, m in enumerate(hist_months):
        trend = 0.80 + 0.20 * i / (len(hist_months) - 1)
        if m.month == 12:
            trend *= 0.9
        row = {"month": m.strftime("%Y-%m")}
        for col, key in [("raw_materials", "Raw materials"), ("semi_finished", "Semi-finished"), ("wip", "WIP"),
                         ("finished_goods", "Finished goods")]:
            lumpy = rng.uniform(0.55, 0.95) if key in ("WIP", "Finished goods") else rng.uniform(0.94, 1.06)
            row[col] = round(now[key] * trend * lumpy, -2)
        row["cogs"] = round(t12_target / 12 * rng.uniform(0.85, 1.15) * (1.2 if m.month == 12 else 1.0), -3)
        hist.append(row)
    targets = pd.DataFrame([("Raw materials", 1_600_000), ("Semi-finished", 50_000), ("WIP", 80_000),
                            ("Finished goods", 40_000)], columns=["stock_type", "year_end_target"])
    data = replace(data, inventory_history=normalize("inventory_history", pd.DataFrame(hist)),
                   inventory_targets=normalize("inventory_targets", targets))
    return _capacity(_shop_floor(_process_steps(_financials(_extras(data, np.random.default_rng(11)))), np.random.default_rng(23)))


def write_sample(folder: str) -> None:
    """Write the sample as one workbook plus one CSV per table."""
    from pathlib import Path

    from flowline.io.importer import write_workbook

    out = Path(folder)
    (out / "csv").mkdir(parents=True, exist_ok=True)
    d = build_sample()
    write_workbook(d, out / "sample_flowline_data.xlsx")
    for name, df in d.tables().items():
        df.drop(columns=[c for c in df.columns if c not in SCHEMA[name]], errors="ignore").to_csv(
            out / "csv" / f"{name}.csv", index=False, date_format="%Y-%m-%d")
