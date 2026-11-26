# Changelog

## 0.10.0 (November 2026)

- **Shop floor** tab: SQDCC tier board with 10-day trends; today's build plan by work centre (plan to now, earned,
  clocked, attainment, productivity, people needed vs here, downtime); plan vs earned and cumulative output by hour;
  downtime Pareto; first-pass yield; misses linked to open countermeasures (needs one / escalate to Tier 2) and an
  editable countermeasure log; skills matrix with coverage per shift and a training plan; ERP items to clear with
  age; kits short for the next builds from clear to build; one-page Tier 2 board PDF.
- Ten new optional tables (work_centers, shop_schedule, hourly_output, downtime, quality_checks, safety_events,
  operators, skills, erp_open_items, countermeasures) and shop-floor targets in settings. Sample data for Corvane:
  eight work centres, 31 people, four weeks of history and today to 13:00.
- Shop-floor alerts (unposted completions, incidents, work centres behind plan, single-qualified stations, old ERP
  items), Production agenda items, a shop-floor page in the PDF pack, Excel sheets and Power Query tables.

## 0.9.0 (November 2026)

- Renamed to **FlowLine Materials Planner** (was Materials Control Tower): repository and folder
  `flowline-materials-planner`, Python package `flowline`, command `flowline`, output files `flowline_*`.

## 0.8.1 (November 2026)

- Value stream: the isometric map now scales to fit its frame, so the whole picture (including the timeline and
  totals) shows on wide screens; the frame in the app is taller.

## 0.8.0 (November 2026)

- Value stream: one view only, the animated isometric plant. Removed the View switch, the flat animated map, the
  WebGL 3D view and the bundled three.js. The PDF keeps a static 2D map.

## 0.7.0 (November 2026)

- Value stream: **Isometric plant** view. Each step is an original, illustrated isometric building on its own tile
  (kitting store, fabrication shop with saw-tooth roof, assembly hall, test bay with HV test tower, supplier works,
  office for production control, substation for the customer); stock points are piles of crates, one per day;
  delivery trucks on the roads; the same lineup animation, timeline follower and current/future switch. Plain SVG.
- Building style is picked from the step name (kit, fab, weld, assem, test, ship ...), so your own routes work too.

## 0.6.0 (November 2026)

- Value stream: **Animated map** view. The 2D map with solid, 3D-looking objects (extruded blocks, prisms,
  buildings, shadows) and lineups moving through it; a marker on the timeline ladder follows one lineup; flowing
  information lines; the biggest wait pulses. Plain SVG and JavaScript, so it needs no WebGL.
- The View switch is now 2D map / Animated map / 3D (WebGL). The WebGL view points to the Animated map if the
  browser has no WebGL. Both animated views download as one HTML file.

## 0.5.0 (November 2026)

- Value stream: animated 3D view. Process blocks, piles of crates as high as the days of stock, the information
  flow with moving pulses, and lineups flowing through at the customer's pace (waiting at piles, processing in
  blocks), with a live count of how long each lineup took. Current and future state, speed control, rotate and zoom.
- Download the 3D view as one self-contained HTML file that works offline.
- three.js r170 bundled (MIT) so nothing loads from the internet.

## 0.4.0 (November 2026)

- Value stream tab (last tab): a value stream map for one product family. Process boxes with C/T, C/O, uptime,
  operators and load against takt; stock triangles in days of family COGS and dollars, from the app's raw,
  semi-finished, WIP and finished-goods inventory; information flow; customer takt; timeline with waiting vs
  process days, lead time and value-added %; the biggest wait flagged.
- Future state: editable stock-day and changeover targets with the change in lead time and the working capital freed.
- New optional table process_steps (sample: switchgear lineups); settings vsm_family, vsm_hours_per_day, vsm_working_days.
- Value stream page in the PDF review pack, a Value stream sheet in the Excel report, `tbl_vsm` in the Power Query
  workbook, and an alert for the biggest wait.

## 0.3.0 (November 2026)

- Project financials tab: contract, budget, actual, committed, ETC and EAC per project and cost element; margin as
  sold vs forecast and margin fade; cost-to-cost percent complete, unbilled revenue and billings in excess; billing
  milestones that follow the material plan (build start, shipment, commissioning, drawing approval); invoices not
  raised; receivables aging and DSO; fiscal-year billing at risk; change orders and submittals.
- Material committed and estimate to complete come from the clear-to-build allocation (pegged POs at PO price,
  stock and shortages at standard).
- Project review PDF pack (portfolio page plus a page per project); new Excel and Power Query tables.
- Alerts, a project-controller scorecard, and Finance, Contracts and Engineering agenda items for the new area.
- New optional tables: wbs_budget, cost_actuals, change_orders, billing_milestones, submittals; new settings
  payment_terms_days, commissioning_days, margin_fade_alert_pts.
- Alert due dates are now always dates (fixes a display error in some Streamlit versions).

## 0.2.0 (November 2026)

- Supply risk tab: safety-stock recommendation for repeat parts (demand and delivery variability, service level),
  risk register with detected risks and a heat map, dual-sourcing plan, logistics-provider performance and premium freight.
- Cost reduction tab: savings pipeline by stage, weighted pipeline, realized vs target and expected-by-now, and
  opportunities found from PPV, cheaper quotes, premium freight and carrying cost.
- Team & KPIs tab: department KPIs vs target with trends, scorecards per buyer, planner and inventory analyst,
  alerts routed to people.
- Meetings & actions tab: stakeholder agendas, meeting pack PDF and text, editable action log, add alerts to the log.
- New optional tables: team, objectives, kpi_history, actions, consumption_history, risk_register, shipments,
  savings_projects; `quoted_price` in item_sources; new settings.
- Works with pandas 3.1 (empty tables keep numeric columns numeric); pandas capped below 4.

## 0.1.0 (November 2026)

First version.

- Clear-to-build by customer project with multi-level BOM explosion, pegged POs, gating part, material-ready and
  can-ship dates, project drill-down, late and missing parts, long-lead order-by dates.
- PO exception messages (expedite, push out, cancel, reduce, past due) with year-end inventory impact.
- Inventory now, turns, days of inventory, projection by stock type driven by the material plan, year-end landing
  against target, levers and bridge.
- Contract manufacturers: forecast sent vs committed vs demand now, capacity load, commit window, stale forecast,
  delivery performance.
- Supplier scorecard: OTD, early deliveries, quality ppm, PPV, score and grade; single-source risk and
  dual-sourcing status.
- Alerts with owner and suggested action; what-if scenarios.
- Excel report, PDF review pack, Power Query workbook, input template, CLI.
- Fictional sample company (Corvane Grid Equipment), user guide, SAP mapping, sensitive-data check, CI.
