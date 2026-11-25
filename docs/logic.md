# Logic

This page explains how every number in FlowLine is calculated, so you can defend it in a meeting.

## 1. Clear to build (`ctb.py`)

**Inputs:** projects, items, multi-level BOM, stock on hand, open PO lines.

1. **Order.** Projects with status *Planned* or *Released* are taken in order of planned build start, then
   priority. *In build* projects already hold their material in WIP; *Built* projects are finished goods.
2. **Supply lots.** Each part has a list of lots: stock (available today) and open PO lines (available on the
   promised date). A PO whose promised date has passed is assumed to arrive *past-due arrival days* from today
   (default 7). A PO line with a `project_id` is pegged: only that project can use it.
3. **Explode.** The project's top item is exploded level by level:
   * a **make** item (sub-assembly) is first covered from its own stock; whatever is left is built, so its
     components are needed `lead_time_days` earlier;
   * a **buy** or **cm** item is covered from lots, pegged lots first, then stock, then POs in date order;
   * anything still uncovered is a **shortage**; its earliest date is today plus the part's lead time.
4. **Dates.**
   * A part's *ready date* is the date of the latest lot it uses.
   * A sub-assembly is ready when its last component is ready, plus its build time.
   * The project's **material ready** date is the latest ready date of its top-level components.
   * **Forecast build start** = the later of planned start, material ready and today.
   * **Can ship** = forecast build start + build days. **Float** = customer date minus can-ship date.
   * The **gating part** is the part that sets the material-ready date.
5. **Status.**

| Status | Meaning |
| --- | --- |
| Clear to build | Every part is in stock today |
| Clear by start | All supply arrives before the planned build start |
| At risk | The build start slips, but float absorbs it: still ships by the customer date |
| Late | Can-ship date is after the customer date |

A part needed on a date already in the past cannot be "late" by more than today: lateness is measured
against the later of the need date and today.

### PO exception messages

After allocation each open PO line knows which projects use it and when they first need it.

| Message | Rule |
| --- | --- |
| Expedite | Expected date is after the first need date |
| Push out | Expected date is more than *push-out tolerance* (30 days) before the target date (need minus *receive before need*, 5 days) |
| Cancel | No open project uses the line |
| Reduce | Only part of the quantity is used |
| Past due | Promised date has passed (and nothing else applies) |

**Year-end impact** is the standard-cost value that would leave the year-end balance if the supplier agrees:
the full line for a push-out that moves it across year end, the unused quantity for cancel / reduce.

### Excess and long-lead

* **Excess** = stock not allocated to any open project, above safety stock. *No demand* means the part is not
  in any open project's BOM at all (obsolete candidate).
* **Long-lead parts** have a lead time of at least *long-lead days* (90). Order-by date = need date minus lead
  time. Uncovered and order-by date passed: *Order overdue*; within 14 days: *Order now*.

## 2. Inventory and working capital (`inventory.py`)

**Valuation:** standard cost. Stock types follow the item type: RM = raw materials, SFG = semi-finished,
FG = finished goods; WIP comes from projects in build.

**Starting point (today):** stock on hand × standard cost, plus the material cost of projects in build (WIP)
and material plus conversion cost of built projects (finished goods).

**Projection, event by event:**

| Event | Date | Movement |
| --- | --- | --- |
| PO receipt | expected date | + raw materials (or the part's stock type) |
| New buy for a shortage | today + lead time | + raw materials |
| Issue to build | **forecast** build start | − raw materials and semi-finished used; + WIP (rolled material cost) |
| Build finish | forecast finish | − WIP; + finished goods at material × (1 + conversion %) |
| Shipment | later of finish and customer date | − finished goods; + COGS |

Because issues happen at the forecast build start, a late part delays the whole project's consumption: the
rest of its material sits in raw materials longer. That is the link between delivery and working capital.

**KPIs**

| KPI | Formula |
| --- | --- |
| Turns now | Trailing 12-month COGS / inventory now |
| Days of inventory (DOI) | Inventory / (trailing 12-month COGS / 365) |
| Year-end landing | Projected inventory at fiscal year end |
| Year-end turns | Fiscal-year COGS (closed months from history + projected shipments) / year-end inventory |
| Gap | Year-end landing − target |

**Levers** list every action that would lower the landing: push-outs and cancellations (year-end impact above)
and excess stock. The *Apply all push-outs* what-if re-runs the model with POs moved to their suggested
dates and unused quantity removed.

## 3. Contract manufacturers (`suppliers.py`, `cm_view`)

* **Our demand now:** requirements for CM-made parts from open projects, minus what our own stock covers,
  by need month, converted to hours with `cm_hours_per_unit`.
* **Forecast sent / committed:** from the `cm_forecast` table (the last forecast and the CM's reply).
* **Load %** = demand now hours / CM capacity hours. Above 100% is an alert (critical inside the commit window).
* **Commit %** = committed / forecast hours, inside the commit window (default 3 months). Below 95% is an alert.
* **Demand change since forecast** = (demand now − forecast) / forecast. Above ±20% means the forecast is stale.
* **OTD and quality** come from receipts, like suppliers.

## 4. Suppliers (`suppliers.py`)

* **On time** = received between *early days* (5) before and *late days* (0) after the promised date.
  Earlier than the window counts as *early*: not on time, because early receipts are inventory.
* **Quality ppm** = rejected quantity / received quantity × 1,000,000.
* **PPV** = (price paid − standard cost) × quantity. Positive is unfavourable.
* **Score** = 50% OTD + 30% quality (100 at 0 ppm, 0 at 10,000 ppm) + 20% price (100 at 0% PPV or better,
  0 at +10%). Grade A ≥ 85, B ≥ 70, C below.
* **Single source** = fewer than two *Approved* sources. **Risk score** (0-100) for single-source parts:
  lead time 40 (full at 180 days), 12-month spend 30 (full at 500k), open projects exposed 20 (full at 6),
  current shortage 10. High ≥ 65, Medium ≥ 35.
* **Dual-sourcing status:** Dual sourced, In qualification, Candidate or None identified, from `item_sources`.

## 5. Supply risk (`risk.py`)

**Safety stock for repeat parts** (parts with a `consumption_history`):

```
recommended = z × sqrt( L / P × σd² + (μd / P)² × σL² )
```

* μd, σd: mean and standard deviation of monthly consumption (last 12 months); P = 30.4 days.
* L: lead time in days; σL: standard deviation of delivery delay (days late) from that part's receipts, or its
  supplier's when the part has fewer than four.
* z from the service level (95% → 1.645).
* Reorder point = μd / P × L + recommended. A change is suggested when the current level differs by more than the
  tolerance (25%). *Set safety stock* = none today but some is needed.

**Risk register** = the risks in `risk_register` plus risks the model detects, each scored likelihood × impact
(1-5 each; High ≥ 15, Medium ≥ 8):

| Detected risk | Likelihood | Impact |
| --- | --- | --- |
| Single-source part with high risk score and no second source, or a current shortage | 3, or 4 with a shortage | 4, or 5 when 3+ projects use it |
| Supplier OTD more than 15 points under target | 4 | 3, or 4 with 3+ open lines |
| CM load over 100% | 4 in the commit window, else 3 | 4 |
| Long-lead part not ordered by its order-by date | 5 | 4 |
| Logistics provider more than 5 points under its OTD target | 3 | 2 |
| Repeat parts under half their recommended safety stock (one combined risk) | 3 | 3 |

**Dual-sourcing plan**: single-source parts with high or medium risk; status Not started (no candidate), Candidate
found, In qualification, or Overdue (target date passed).

**Logistics**: per provider, share of shipments delivered by the promised date, cost per kg, and premium shipments
(`premium = Y`) with their cost.

## 6. Cost reduction (`cost.py`)

* **Weighted pipeline** = Σ annual savings × stage weight (idea 10%, validated 50%, in implementation 80%,
  realized 100%).
* **Expected by now** = annual target × share of the fiscal year elapsed.
* **Opportunities**: price paid ≥ 3% over standard with PPV ≥ 5k (Negotiation); a quoted price below the average
  price paid (Alternative source, value = gap × 12-month quantity); premium freight (60% assumed avoidable);
  carrying cost (push-outs, cancellations and excess × carrying-cost %). An item already covered by a savings
  project in the same category is not listed.

## 7. Team and KPIs (`team.py`)

Each person's KPIs are calculated for their scope:

| Role | Scope | KPIs |
| --- | --- | --- |
| Buyer | Buyer code (`items.buyer`) | Supplier OTD on their parts, past-due lines, lines to expedite, late part lines, PPV %, savings realized (projects they own), overdue actions |
| Planner | Product family | Projects clear to build %, late projects, at-risk projects, late or missing part lines, overdue actions |
| Inventory analyst | All | Excess stock, items with no demand, safety-stock changes to make, year-end gap, overdue actions |
| Project controller | All projects | Invoices not raised, receivables overdue, worst margin fade, FY billing at risk, overdue submittals, stale change orders, overdue actions |
| Materials manager | All | Every department KPI, against the department targets |

A KPI is *met* when it is at or better than its target (`direction` higher or lower). Score = KPIs met / KPIs with
a target. Alerts are given to a person by the part in their reference (buyer), the project (planner by family), the
supplier (its main buyer), inventory alerts to inventory control, project financial alerts to the project controller, and the rest to the materials manager.

## 8. Meetings and actions (`meetings.py`)

The agenda is rebuilt every run:

| Stakeholder | Items |
| --- | --- |
| Production | Release or hold every project starting inside the frozen window (14 days); sequence changes for at-risk and late projects; CM overloads |
| Engineering | Substitutes for gating parts; disposition of stock with no demand; second-source approvals; early release of long-lead parts; overdue or rejected submittals |
| Contracts | Customer dates at risk (late projects; at-risk with ≤ 7 days float); supplier price reviews (PPV ≥ 3%); pending change orders; invoices more than 30 days overdue |
| Finance | Year-end landing and levers; savings vs target; PPV; safety-stock policy change; project billing this fiscal year; unbilled revenue and receivables; invoices not raised; margin fade |
| Suppliers and CMs | The ten most important supplier, CM and supply-risk alerts |
| Materials team | People with overdue actions or under 70% of KPIs met |

An action is **overdue** when it is not Done and its due date has passed. Alerts added to the log get the next
action number, the person the alert belongs to, and a due date one week out; an alert already in the log is not
added twice.

## 9. Project financials (`financials.py`)

Switched on by the optional tables `wbs_budget`, `cost_actuals`, `billing_milestones`, `change_orders` and
`submittals`.

**Contract** = `projects.sell_value` + approved change orders. Pending change orders are shown, not counted.

**Cost by element** (WBS). For each project and cost element: as sold, budget, actual (`cost_to_date`), committed,
ETC, EAC = actual + committed + ETC, variance = budget − EAC (negative = overrun).

* *Material, before build*: committed = open PO lines the clear-to-build model allocated to the project, at PO
  price; ETC = stock allocated to it plus parts not yet bought, at standard (rolled) cost. So a price increase on an
  open PO, or a part bought for a project above standard, shows in the margin straight away.
* *Material in or after build, and every other element*: ETC = `etc_override` if entered, otherwise budget − actual
  (never below zero).

**Margin** as sold = (contract as sold − cost as sold) / contract as sold; forecast = (contract − EAC) / contract.
Fade = as sold − forecast, in points; a project is flagged at `margin_fade_alert_pts` (1.5).

**Revenue recognition**, cost to cost: POC = actual / EAC; earned = POC × contract; unbilled revenue (contract
asset) = earned − billed when positive; billings in excess (contract liability) when negative.

**Billing milestones.** Amount = `pct` × contract. Forecast date by trigger:

| Trigger | Forecast date |
| --- | --- |
| Order, Date | The planned date |
| Drawings approved | The return date of the approved submittal that holds it; if still open, its due date, and never earlier than 14 days from today |
| Build start | Forecast build start from clear to build |
| Material ready | Material-ready date from clear to build |
| Shipment | Forecast ship date from clear to build |
| Commissioning | Forecast ship date + `commissioning_days` (45) |

Status: *Paid* (paid date), *Invoiced* (invoice date), *Due, not invoiced* (forecast date reached, no invoice), or
*Planned*. FY billing at risk = milestones planned on or before the fiscal year end whose billing date is now after
it. Cash = paid date, or billing date + `payment_terms_days` (45).

**Receivables**: invoiced and not paid. Due date = invoice date + payment terms; aging buckets by days overdue.
DSO = open receivables / billing of the last 90 days × 90.

**Change orders**: a pending change order older than 30 days is *stale*. **Submittals**: overdue when not returned
by the due date; *blocked* when returned with status Resubmit. `holds` links a submittal to a billing milestone (M2)
or to a supplier production release.

## 10. Value stream map (`vsm.py`)

Switched on by the optional table `process_steps`: one product family's route as *Process* and *Stock* rows in flow
order. The family is `vsm_family`, or the first in the table.

* **Stock value per triangle** = the family's share of today's inventory of that stock type: raw and semi-finished
  stock split by the open projects' requirements (parts with no open demand: by where they are used in the family's
  BOMs); WIP = material of the family's projects in build; finished goods = its built projects at material + conversion.
* **Days of stock** = value / family COGS per day. Family COGS = trailing 12-month COGS x the family's share of
  material in all projects / 365. So the triangles add up to the family's days of inventory.
* **Takt** = `vsm_working_days` x `vsm_hours_per_day` / units a year, where units a year = the family's project
  quantities with a customer date in the next six months, doubled.
* **Process box**: effective C/T = (C/T + C/O) / uptime; process days = effective C/T / `vsm_hours_per_day`;
  load vs takt = effective C/T / takt (over 100% = the step cannot keep up).
* **Timeline**: lead time = sum of stock days + sum of process days; value-added % = process days / lead time. The
  stock point with the most days is the biggest wait (an alert: Warning when it is above its target, else Info).
* **Future state**: `target_days` and `target_changeover_hours` (blank or 0 = today's). Working capital freed =
  (days − target days) x family COGS per day; lead-time change = the change in days.

**Animated isometric map** (`reports/vsm_iso.py` draws it, `reports/vsm_anim.py` animates it): the same numbers. One crate per day of stock; a new lineup every 365 / units a
year days; each lineup waits at each stock point for its days and spends its process days in each block, so its trip
takes the lead time (moves between steps are not counted). It starts with a full stream.

**Limits in engineer-to-order.** Days of stock divide a lumpy balance by an average: one lineup more or less in build
moves the WIP triangle by weeks, so read the map as a monthly snapshot, not a trend. The route has to be fairly
standard for one family; one-off projects with their own routings don't fit on one map. C/T and C/O are per unit
of a family whose units differ in size. The map does not include kaizen bursts, supermarkets or pull signals.

## 11. Alerts (`alerts.py`)

Critical: late projects, overdue long-lead orders, billing milestones reached but not invoiced, invoices more than
60 days overdue, year-end landing more than 5% over target, CM overload
inside the commit window. Warning: at-risk projects, late parts on at-risk or late projects, past-due PO lines,
year-end push-out opportunities, low CM commitment, stale CM forecast, low OTD, high single-source risk with no
second source, high risks in the register, repeat parts under half their safety stock, overdue second-source
qualifications, savings behind target, overdue actions, margin fade, billing moving out of the fiscal year,
invoices more than 30 days overdue, stale change orders, overdue or rejected submittals, the biggest wait in the
value stream when it is above its target. Info: stock-type gaps, PPV ≥ 3%, other single-source risks,
excess, too much safety stock, late logistics providers, overdue savings projects. Sorted by severity, due date,
then value.

## Simplifications

* Monthly CM buckets and daily dates elsewhere; calendar days, no factory calendar.
* No capacity check on in-house assembly: build days are taken as given.
* Material for a project is issued in one go at build start.
* Conversion cost is a flat percentage of material.
* Project revenue is recognized cost to cost on the whole contract; no separate performance obligations, no
  loss provision, no retention or advance-payment netting. Treat the numbers as a management view, not the books.
* Lots are allocated first-come by build start; the model does not re-sequence projects to maximise on-time
  delivery. Use priority to force an order.
