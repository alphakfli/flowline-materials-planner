# Getting the data out of SAP

FlowLine runs on plain tables, so it works beside SAP rather than inside it. This page maps each
input table to the usual SAP ECC / S/4HANA source. Field names are the standard ones; your system may use
custom fields or reports, so check with your SAP team. Typical extraction routes: SE16N table downloads, an
SAP Query / SQVI, Analysis for Office, or the standard list reports below exported to Excel. Power Query is a
good way to reshape the downloads into the template columns and refresh them each week.

## items

| Column | SAP source |
| --- | --- |
| item_id, description | MARA-MATNR, MAKT-MAKTX |
| item_type | From the material type MARA-MTART: ROH (raw) → RM, HALB (semi-finished) → SFG, FERT (finished) → FG |
| make_buy | MARC-BESKZ procurement type: E (in-house) → make, F (external) → buy. Subcontracted parts (special procurement MARC-SOBSL 30) or parts bought finished from a CM → cm |
| std_cost | MBEW-STPRS / MBEW-PEINH (standard price per unit) |
| lead_time_days | MARC-PLIFZ planned delivery time (buy), MARC-DZEIT in-house production time (make) |
| supplier_id | Fixed source in the source list (EORD-FLIFN) or the main info record |
| buyer | MARC-EKGRP purchasing group (or MARC-DISPO MRP controller) |
| on_hand | MARD-LABST unrestricted stock, summed over storage locations (MB52 / MMBE). Add project or sales-order stock (MSPR / MSKA) if you plan on it |
| safety_stock | MARC-EISBE |
| cm_hours_per_unit | Not in SAP as standard; agree it with each CM |

## bom

STKO / STPO, linked to the material by MAST. Use CS12 (multi-level BOM) or CS11 to check. `qty_per` =
component quantity STPO-MENGE / base quantity STKO-BMENG. For engineer-to-order, use the order BOM or WBS BOM
of each project (CS62 / CS72) so the top item matches the project.

## projects

Engineer-to-order projects are usually a sales order line with make-to-order or project stock, often with a WBS
element (PS) and production orders.

| Column | SAP source |
| --- | --- |
| project_id, customer | Sales order VBAK-VBELN / WBS element PRPS-POSID; customer VBAK-KUNNR → KNA1-NAME1 |
| top_item, qty | VBAP-MATNR, VBAP-KWMENG |
| planned_build_start | Basic start date of the final assembly production order (AFKO-GSTRP) or network activity start |
| build_days | Order basic finish minus basic start (AFKO-GLTRP − AFKO-GSTRP) |
| required_ship_date | Confirmed or requested delivery date (VBEP-EDATU) |
| status | Planned: no order yet or order created; Released: order released (REL), no final-assembly goods issue; In build: goods issued to the final-assembly order; Built: order delivered to stock (DLV) but not shipped |
| sell_value | VBAP-NETWR |

## purchase_orders

| Column | SAP source |
| --- | --- |
| po_number, po_line | EKKO-EBELN, EKPO-EBELP |
| item_id, supplier_id | EKPO-MATNR, EKKO-LIFNR |
| qty_open | Schedule line quantity minus goods received: EKET-MENGE − EKET-WEMNG |
| unit_price | EKPO-NETPR / EKPO-PEINH |
| order_date | EKKO-BEDAT |
| promised_date | Latest supplier confirmation (EKES-EINDT) if there is one, else the schedule-line delivery date EKET-EINDT |
| project_id | Account assignment to a WBS element or sales order: EKKN-PS_PSP_PNR / EKKN-VBELN (account assignment category Q or E) |

ME2M (by material), ME2L (by vendor) and ME2N (by PO number) with selection parameter WE101 (open goods
receipts) list the open lines. ME80FN is a flexible alternative.

## receipts

| Column | SAP source |
| --- | --- |
| po_number, item_id, supplier_id | EKBE-EBELN, EKBE-MATNR; vendor from EKKO-LIFNR |
| receipt_date, qty | Goods receipts in the PO history: EKBE with VGABE = 1, posting date EKBE-BUDAT, quantity EKBE-MENGE (or MSEG movement type 101) |
| promised_date | The schedule-line or confirmed date the receipt was due on (EKET-EINDT / EKES-EINDT) |
| qty_rejected | Return deliveries (movement type 122), or rejected quantity from the inspection lot usage decision (QALS / QAVE) |
| unit_price | Invoice price (EKBE with VGABE = 2) or EKPO-NETPR |
| std_cost | MBEW-STPRS at the time of receipt |

With standard-price materials SAP already posts PPV at goods receipt and invoice; the app recalculates it from
these columns so the supplier view and the finance number can be reconciled.

## suppliers and item_sources

* `suppliers`: LFA1-LIFNR, LFA1-NAME1, LFA1-LAND1. Mark contract manufacturers as `CM` (vendor account group,
  a classification, or a simple list).
* `item_sources`: the source list EORD (ME03; blocked entries EORD-NOTKZ) and info records EINA / EINE (ME1M).
  Approval status for new sources (in qualification, candidate) is rarely in SAP as standard. It usually sits
  in the supplier-quality tracker or the QM info record (Q-info record), so add it from there.

## cm_forecast and cm_capacity

Most teams keep these in a collaboration file with each CM. If you send forecasts through scheduling-agreement
delivery schedules (ME38 / ME84), the release history is in EKEK / EKEH. Capacity comes from the CM.

## inventory_history and inventory_targets

Month-end inventory by stock type and monthly COGS come from the finance month-end pack: inventory balance-sheet
accounts and COGS accounts (FAGLB03), WIP from the WIP calculation (KKAX / KKAO) or WIP account, stock values
by material type from MC.9 or MB5B (stock on a posting date). Year-end targets come from the budget / AOP.

## Project financials: wbs_budget, cost_actuals, change_orders, billing_milestones, submittals

| Table | Where it lives in SAP | Transactions / tables |
| --- | --- | --- |
| wbs_budget | Original budget (as sold) and current budget on the project's WBS elements, by cost element group | CJ40 / CJ30 (planned cost, budget), report CJI4 or S_ALR_87013558; tables BPGE / BPJA, COSP |
| cost_actuals | Actual cost by WBS element and cost element; ETC from the project manager's forecast | CJI3 (actual line items), CJI5 (commitments, for a cross-check with the model's committed cost), COSP / COSS |
| change_orders | Usually a contracts log; in SAP as sales-order amendments or a variant order | VA02 change history, or a separate log |
| billing_milestones | Milestone billing plan on the sales order item, and the invoices | FPLA / FPLT (VA03 → item → billing plan), VF01 / VF03 invoices (VBRK / VBRP), cleared items for the paid date (FBL5N, BSAD) |
| submittals | Document management or an engineering transmittal log | CV03N (DRAW / DRAP), or your transmittal register |

Settlement and results analysis (KKA2 / KKA3, CJ88) give the books' version of earned revenue and WIP; use them to
reconcile the app's cost-to-cost view at month end.

## Shop floor tables

| Table | Where it lives in SAP |
| --- | --- |
| work_centers | Work centres (CR03; CRHD): capacity per shift from the capacity header (CR03 → Capacities) |
| shop_schedule | Planned hours from the production order operations (COOIS, AFVV standard values); earned = confirmed yield x standard values; clocked hours from time confirmations (CO11N, AFRU) or the time system |
| hourly_output | Confirmations by hour (AFRU, confirmation time stamps), or an MES / andon feed |
| downtime | Downtime reasons from confirmations (variance reasons), PM breakdowns (IW38), or the shift log |
| quality_checks | Inspection lots and results (QA32, QE51N); test reports |
| safety_events | The EHS system or incident log (EHS incident management if used) |
| operators, skills | HR qualifications (PA30 infotype 0024) or the training matrix kept by the supervisor |
| erp_open_items | Missing final confirmations (COOIS with status), backflush errors (COGI), count differences (MI20 / MI07), scrap (MB1A / MIGO 551), orders past finish not technically complete (COOIS, TECO), shipping labels (VL02N output) |
| countermeasures | Kept in the app (download the input workbook to save it) |

## Weekly capacity tables

| Table | Where it lives in SAP |
| --- | --- |
| resources | Work centres and their capacities (CR03 / CRHD, KAKO): number of individual capacities, shifts, operating time, utilization % |
| routings | Routings (CA03; PLKO / PLPO): operations, work centre, standard values (machine time, labour time) per base quantity |
| production_orders | Planned and production orders (MD04, COOIS) or sales order items for each project; quantity, basic finish date, priority |
| capacity_calendar | Factory calendar (SCAL) and capacity intervals for shutdowns |

Cross-check the load against CM01 / CM21 (capacity planning) when work centres and routings are maintained.

## process_steps (value stream map)

| Column | Where it lives in SAP |
| --- | --- |
| Process steps, C/T, C/O | The routing of a typical unit of the family (CA03; PLKO / PLPO): machine or labour time per unit = C/T, setup time = C/O. Or time studies on the floor |
| operators | Routing labour, or the crew size on the floor |
| uptime_pct | Work-centre capacity (CR03, CM01) and breakdown time from plant maintenance (IW38/IW39), or OEE availability |
| Stock points | Not from SAP: decide where stock waits along the route. The values come from the app's inventory |
| target_days, target_changeover_hours | Your improvement targets |

## Cross-checks in SAP

| FlowLine view | Compare with |
| --- | --- |
| Clear to build, shortages | CO24 missing parts information system, MD04 stock / requirements list, CO09 availability overview |
| PO exception messages | MD06 / MD05 exception messages: reschedule in (10), reschedule out (15), cancel (20) |
| Supplier OTD | Vendor evaluation (ME61 to ME65, ME6H), or your own receipt-vs-confirmation report |
| Inventory | MB52, MC.9, MB5B, the balance sheet |
| Project cost and commitments | CJI3, CJI5, S_ALR_87013558 budget / actual / commitment |
| Receivables aging | FBL5N, S_ALR_87012178 customer open items by due date |
| Shop floor attainment | COOIS (operations, confirmed vs planned), CM01 / CM50 capacity load |
