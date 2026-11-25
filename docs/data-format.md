# Data format

Upload **one Excel workbook** with a sheet per table (sheet names as below), or **one CSV per table** named
`<table>.csv`. Column names are matched case-insensitively; spaces become underscores. Extra columns are kept and ignored.

Required tables: `items`, `bom`, `projects`. Every other table is optional and switches on more of the dashboard.

Download a blank template from the sidebar (**Upload Excel or CSV → Download blank template**) or run `flowline template`. The **Input data workbook** export on the Data and exports tab gives you the sample in the same format, a good starting point.

This page is generated from the code by `scripts/gen_data_format.py`.

## items

Every part number: finished goods (FG, one per customer project), sub-assemblies (SFG) and bought or contract-manufactured parts (RM).

| Column | Type | Required | Notes |
| --- | --- | --- | --- |
| `item_id` | text | yes |  |
| `description` | text |  |  |
| `item_type` | text | yes | RM, SFG or FG |
| `make_buy` | text | yes | make, buy or cm (made for you by a contract manufacturer) |
| `uom` | text |  |  |
| `std_cost` | number | yes | Standard cost per unit (inventory is valued at this) |
| `lead_time_days` | number | yes | Purchase lead time, or build time for make items |
| `supplier_id` | text |  | Primary supplier or CM |
| `commodity` | text |  |  |
| `buyer` | text |  | Buyer or planner code, shown on the shortage list for filtering |
| `on_hand` | number |  | Unrestricted stock today |
| `safety_stock` | number |  | Stock to keep; not counted as excess |
| `cm_hours_per_unit` | number |  | CM capacity hours per unit (cm items only) |

## bom

Multi-level bill of materials. Each project's top item lists its sub-assemblies and parts.

| Column | Type | Required | Notes |
| --- | --- | --- | --- |
| `parent_item` | text | yes |  |
| `component_item` | text | yes |  |
| `qty_per` | number | yes | Quantity of the component per one parent |

## projects

Customer orders. Planned and Released projects are checked for material; In build and Built ones are already in WIP or finished goods.

| Column | Type | Required | Notes |
| --- | --- | --- | --- |
| `project_id` | text | yes |  |
| `customer` | text |  |  |
| `product_family` | text |  |  |
| `top_item` | text | yes |  |
| `qty` | number | yes |  |
| `status` | text | yes | Planned, Released, In build or Built |
| `planned_build_start` | date (YYYY-MM-DD) | yes | Date the final build is planned to start |
| `build_days` | number |  | Calendar days from build start to ready to ship |
| `required_ship_date` | date (YYYY-MM-DD) | yes | Customer date |
| `sell_value` | number |  | Order value (for prioritizing) |
| `priority` | number |  | Lower number = allocated first when start dates tie |

## purchase_orders

Open PO lines and CM orders.

| Column | Type | Required | Notes |
| --- | --- | --- | --- |
| `po_number` | text |  |  |
| `po_line` | number |  |  |
| `item_id` | text |  |  |
| `supplier_id` | text |  |  |
| `qty_open` | number |  | Quantity still to be received |
| `unit_price` | number |  |  |
| `order_date` | date (YYYY-MM-DD) |  |  |
| `promised_date` | date (YYYY-MM-DD) |  | Supplier's confirmed date (the latest confirmation) |
| `project_id` | text |  | Optional: the project this line is reserved for (project stock / account assignment) |

## receipts

Goods receipts for the last 12 months, for on-time delivery, quality and PPV.

| Column | Type | Required | Notes |
| --- | --- | --- | --- |
| `po_number` | text |  |  |
| `item_id` | text |  |  |
| `supplier_id` | text |  |  |
| `promised_date` | date (YYYY-MM-DD) |  |  |
| `receipt_date` | date (YYYY-MM-DD) |  |  |
| `qty` | number |  |  |
| `qty_rejected` | number |  | Quantity rejected at incoming inspection |
| `unit_price` | number |  | Price paid |
| `std_cost` | number |  | Standard cost at receipt |

## suppliers

Supplier and CM master.

| Column | Type | Required | Notes |
| --- | --- | --- | --- |
| `supplier_id` | text |  |  |
| `name` | text |  |  |
| `supplier_type` | text |  | Supplier or CM |
| `region` | text |  |  |
| `commodity` | text |  |  |

## item_sources

Approved and pending sources per part (source list).

| Column | Type | Required | Notes |
| --- | --- | --- | --- |
| `item_id` | text |  |  |
| `supplier_id` | text |  |  |
| `status` | text |  | Approved, In qualification or Candidate |
| `share_pct` | number |  |  |
| `target_date` | date (YYYY-MM-DD) |  | Date the second source should be approved |
| `notes` | text |  |  |
| `quoted_price` | number |  | Optional: unit price quoted by this source, for cost opportunities |

## cm_forecast

The last forecast sent to each CM and what they committed.

| Column | Type | Required | Notes |
| --- | --- | --- | --- |
| `cm_id` | text |  |  |
| `item_id` | text |  |  |
| `month` | month (YYYY-MM) |  | YYYY-MM |
| `forecast_qty` | number |  |  |
| `committed_qty` | number |  |  |
| `sent_date` | date (YYYY-MM-DD) |  | When the forecast was sent |

## cm_capacity

CM capacity in hours per month.

| Column | Type | Required | Notes |
| --- | --- | --- | --- |
| `cm_id` | text |  |  |
| `month` | month (YYYY-MM) |  | YYYY-MM |
| `capacity_hours` | number |  |  |

## inventory_history

Month-end inventory value by stock type and monthly COGS, closed months.

| Column | Type | Required | Notes |
| --- | --- | --- | --- |
| `month` | month (YYYY-MM) |  | YYYY-MM |
| `raw_materials` | number |  |  |
| `semi_finished` | number |  |  |
| `wip` | number |  |  |
| `finished_goods` | number |  |  |
| `cogs` | number |  | Cost of goods sold in the month |

## inventory_targets

Year-end inventory target by stock type (Raw materials, Semi-finished, WIP, Finished goods).

| Column | Type | Required | Notes |
| --- | --- | --- | --- |
| `stock_type` | text |  |  |
| `year_end_target` | number |  |  |

## team

Your buyers, planners and inventory analysts. Scope ties each person to their part of the model.

| Column | Type | Required | Notes |
| --- | --- | --- | --- |
| `person_id` | text |  |  |
| `name` | text |  |  |
| `role` | text |  | Buyer, Planner, Inventory analyst or Materials manager |
| `scope` | text |  | Buyer: the buyer code used in items.buyer. Planner: a product family. Others: All |

## objectives

Targets for each person and for the department (owner = Department).

| Column | Type | Required | Notes |
| --- | --- | --- | --- |
| `owner` | text |  | person_id, or Department |
| `kpi` | text |  | KPI key, e.g. supplier_otd_pct, ctb_pct, excess_value (see docs/logic.md) |
| `target` | number |  |  |
| `direction` | text |  | higher or lower (which way is better) |

KPI keys for `objectives` and `kpi_history`:

| Key | KPI | Unit | Better |
| --- | --- | --- | --- |
| `turns` | Inventory turns | x | higher |
| `doi` | Days of inventory | days | lower |
| `year_end_gap` | Year-end gap to target | $ | lower |
| `ctb_pct` | Projects clear to build | % | higher |
| `late_projects` | Projects late to customer | count | lower |
| `at_risk_projects` | Projects at risk | count | lower |
| `shortage_lines` | Late or missing part lines | count | lower |
| `supplier_otd_pct` | Supplier on-time delivery | % | higher |
| `cm_otd_pct` | CM on-time delivery | % | higher |
| `cm_commit_pct` | CM commitment in window | % | higher |
| `past_due_lines` | Past-due PO lines | count | lower |
| `expedite_lines` | PO lines to expedite | count | lower |
| `late_part_lines` | Late part lines on own items | count | lower |
| `ppv_pct` | Purchase price variance | % | lower |
| `excess_value` | Excess stock | $ | lower |
| `no_demand_items` | Items with no demand | count | lower |
| `ss_actions` | Safety-stock changes to make | count | lower |
| `savings_realized` | Savings realized | $ | higher |
| `actions_overdue` | Overdue actions | count | lower |
| `risks_high` | High supply risks | count | lower |
| `invoices_not_raised` | Milestones reached but not invoiced | count | lower |
| `ar_overdue_value` | Receivables overdue | $ | lower |
| `margin_fade_pts` | Portfolio margin fade (points) | pts | lower |
| `billing_at_risk_fy` | Billing slipping out of the fiscal year | $ | lower |
| `submittals_overdue` | Submittals overdue or rejected | count | lower |
| `cos_stale` | Change orders waiting over 30 days | count | lower |

## kpi_history

Department KPIs for closed months, long format: one row per month and KPI.

| Column | Type | Required | Notes |
| --- | --- | --- | --- |
| `month` | month (YYYY-MM) |  | YYYY-MM |
| `kpi` | text |  |  |
| `value` | number |  |  |

## actions

The running action log from the weekly meetings.

| Column | Type | Required | Notes |
| --- | --- | --- | --- |
| `action_id` | text |  |  |
| `opened` | date (YYYY-MM-DD) |  |  |
| `stakeholder` | text |  | Production, Engineering, Contracts, Finance, Suppliers and CMs, Materials team |
| `owner` | text |  | person_id from the team table |
| `ref` | text |  |  |
| `action` | text |  |  |
| `due` | date (YYYY-MM-DD) |  |  |
| `status` | text |  | Open, In progress or Done |
| `closed` | date (YYYY-MM-DD) |  |  |
| `notes` | text |  |  |

## consumption_history

Monthly consumption of repeat parts, for safety-stock recommendations.

| Column | Type | Required | Notes |
| --- | --- | --- | --- |
| `item_id` | text |  |  |
| `month` | month (YYYY-MM) |  | YYYY-MM |
| `qty` | number |  |  |

## risk_register

Supply risks you track. The app adds the risks it detects.

| Column | Type | Required | Notes |
| --- | --- | --- | --- |
| `risk_id` | text |  |  |
| `risk` | text |  |  |
| `category` | text |  |  |
| `likelihood` | number |  | 1 (rare) to 5 (almost certain) |
| `impact` | number |  | 1 (minor) to 5 (severe) |
| `mitigation` | text |  |  |
| `owner` | text |  |  |
| `status` | text |  | Open, Mitigating or Closed |
| `due` | date (YYYY-MM-DD) |  |  |

## shipments

Inbound shipments by logistics provider, last 12 months.

| Column | Type | Required | Notes |
| --- | --- | --- | --- |
| `shipment_id` | text |  |  |
| `lsp` | text |  |  |
| `mode` | text |  |  |
| `ship_date` | date (YYYY-MM-DD) |  |  |
| `promised_date` | date (YYYY-MM-DD) |  |  |
| `delivered_date` | date (YYYY-MM-DD) |  |  |
| `cost` | number |  |  |
| `weight_kg` | number |  |  |
| `premium` | text |  | Y for expedited or premium freight |
| `reason` | text |  | Why it was expedited |

## savings_projects

Cost-reduction projects.

| Column | Type | Required | Notes |
| --- | --- | --- | --- |
| `project_id` | text |  |  |
| `title` | text |  |  |
| `category` | text |  | Alternative source, Negotiation, VA/VE, Consolidation, Packaging, Logistics |
| `item_id` | text |  |  |
| `supplier_id` | text |  |  |
| `owner` | text |  |  |
| `stage` | text |  | Idea, Validated, In implementation or Realized |
| `baseline_spend` | number |  |  |
| `annual_savings` | number |  | Expected savings per year |
| `start_date` | date (YYYY-MM-DD) |  |  |
| `target_date` | date (YYYY-MM-DD) |  |  |
| `realized_to_date` | number |  | Savings booked this fiscal year |

## wbs_budget

Project cost by element: as sold (the bid) and the current budget. Turns on Project financials.

| Column | Type | Required | Notes |
| --- | --- | --- | --- |
| `project_id` | text |  |  |
| `cost_element` | text |  | Material, Labour, Engineering, Freight, Commissioning or Contingency |
| `as_sold` | number |  | Cost in the bid |
| `budget` | number |  | Current approved budget (as sold plus approved changes) |

## cost_actuals

Actual cost booked to date per project and element.

| Column | Type | Required | Notes |
| --- | --- | --- | --- |
| `project_id` | text |  |  |
| `cost_element` | text |  |  |
| `cost_to_date` | number |  | Actual cost posted |
| `etc_override` | number |  | Optional estimate to complete for non-material elements; blank uses budget minus actual. Material ETC comes from the material plan. |

## change_orders

Customer change orders.

| Column | Type | Required | Notes |
| --- | --- | --- | --- |
| `co_id` | text |  |  |
| `project_id` | text |  |  |
| `description` | text |  |  |
| `price_change` | number |  | Change to the contract price |
| `cost_change` | number |  | Change to cost |
| `cost_element` | text |  |  |
| `status` | text |  | Pending, Approved or Rejected |
| `submitted` | date (YYYY-MM-DD) |  | Date sent to the customer |
| `decided` | date (YYYY-MM-DD) |  | Date of decision |

## billing_milestones

Billing plan per project and invoices raised.

| Column | Type | Required | Notes |
| --- | --- | --- | --- |
| `project_id` | text |  |  |
| `milestone_id` | text |  |  |
| `name` | text |  |  |
| `trigger` | text |  | Order, Drawings approved, Build start, Material ready, Shipment, Commissioning or Date |
| `pct` | number |  | Percent of the contract |
| `planned_date` | date (YYYY-MM-DD) |  | Planned billing date |
| `invoice_no` | text |  | Blank until invoiced |
| `invoice_date` | date (YYYY-MM-DD) |  |  |
| `amount_invoiced` | number |  | Blank uses pct x contract |
| `paid_date` | date (YYYY-MM-DD) |  | Blank until paid |

## process_steps

Value stream map for one product family: its route in order, process steps and the stock points between them. Turns on the Value stream tab.

| Column | Type | Required | Notes |
| --- | --- | --- | --- |
| `product_family` | text |  | Family as in projects.product_family (set vsm_family in settings if there are several) |
| `seq` | number |  | Order along the flow (10, 20, 30 ...) |
| `kind` | text |  | Process or Stock |
| `name` | text |  | Step or stock point name |
| `stock_type` | text |  | Stock rows: Raw materials, Semi-finished, WIP or Finished goods |
| `cycle_time_hours` | number |  | Process rows: hours per unit |
| `changeover_hours` | number |  | Process rows: hours per changeover |
| `uptime_pct` | number |  | Process rows: % of time the step is available |
| `operators` | number |  | Process rows: people on the step |
| `target_days` | number |  | Stock rows: future-state days of stock (blank = today's) |
| `target_changeover_hours` | number |  | Process rows: future-state changeover (blank = today's) |

## submittals

Drawings and documents sent for approval (customer) or received for approval (supplier).

| Column | Type | Required | Notes |
| --- | --- | --- | --- |
| `submittal_id` | text |  |  |
| `project_id` | text |  |  |
| `direction` | text |  | Customer or Supplier |
| `document` | text |  |  |
| `party` | text |  |  |
| `submitted` | date (YYYY-MM-DD) |  |  |
| `due` | date (YYYY-MM-DD) |  |  |
| `returned` | date (YYYY-MM-DD) |  |  |
| `status` | text |  | Open, Approved, Approved as noted or Resubmit |
| `holds` | text |  | Billing milestone it holds (M2), 'release' for a supplier production release, or blank |

## settings

Optional settings. Leave a value blank to use the default.

| Column | Type | Required | Notes |
| --- | --- | --- | --- |
| `key` | text |  |  |
| `value` | text |  |  |

Keys and defaults:

| Key | Default | Meaning |
| --- | --- | --- |
| `company` | Your company | Name shown on screens and reports |
| `as_of_date` | today | Today for the model (default: the real today) |
| `fiscal_year_end` |  | Year-end date for the landing (default 31 Dec of the as-of year) |
| `currency` | $ | Currency symbol |
| `turns_target` | 4.0 | Target turns at year end |
| `past_due_arrival_days` | 7 | When a past-due PO is assumed to arrive |
| `otd_early_days` | 5 | On-time window: days early allowed |
| `otd_late_days` | 0 | On-time window: days late allowed |
| `long_lead_days` | 90 | Lead time from which a part is long-lead |
| `conversion_cost_pct` | 25.0 | Labour and overhead added to material at build finish |
| `push_out_tolerance_days` | 30 | Earliness that triggers a push-out message |
| `receive_before_need_days` | 5 | Target arrival before the need date |
| `cm_commit_horizon_months` | 3 | Months in which CM commitments must cover the forecast |
| `otd_target_pct` | 95.0 | On-time delivery target |
| `cm_forecast_change_pct` | 20.0 | Demand change that makes a CM forecast stale |
| `history_months` | 12 | Look-back for supplier and CM performance |
| `frozen_window_days` | 14 | Builds starting inside this window are released or held in the meeting agenda |
| `service_level_pct` | 95.0 | Target service level for safety stock on repeat parts |
| `safety_stock_tolerance_pct` | 25.0 | Suggest a safety-stock change when the current level is this far off |
| `carrying_cost_pct` | 20.0 | Annual cost of holding inventory, % of its value |
| `savings_target` | 0.0 | Annual cost-reduction target |
| `lsp_otd_target_pct` | 95.0 | On-time target for logistics providers |
| `payment_terms_days` | 45 |  |
| `commissioning_days` | 45 |  |
| `margin_fade_alert_pts` | 1.5 |  |
| `vsm_family` |  |  |
| `vsm_hours_per_day` | 16.0 |  |
| `vsm_working_days` | 250 |  |

## Rules the importer checks

* Required tables and columns present (error).
* Duplicate `item_id` (error); BOM loops (error).
* `item_type` is RM, SFG or FG and `make_buy` is make, buy or cm (warning).
* BOM items missing from `items`, project top items without a BOM, unknown project status, PO lines for unknown items, POs without a promised date, bought items without a supplier (warnings).
