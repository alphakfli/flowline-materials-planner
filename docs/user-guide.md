# User guide

This guide takes you through the FlowLine Materials Planner step by step, then through nineteen scenarios a Materials
Manager meets in a normal month. The numbers match the sample company, **Corvane Grid Equipment** (fictional),
as of Monday 23 November 2026 with a fiscal year ending 31 December 2026.

Contents

1. [Install and open](#1-install-and-open)
2. [The screen in two minutes](#2-the-screen-in-two-minutes)
3. [Tab by tab](#3-tab-by-tab)
4. [Scenarios](#4-scenarios)
5. [Use your own data](#5-use-your-own-data)
6. [Glossary](#6-glossary)
7. [Questions and troubleshooting](#7-questions-and-troubleshooting)

---

## 1. Install and open

### On Windows

1. Install Python 3.10 or newer from [python.org](https://www.python.org/downloads/). In the installer tick
   **Add python.exe to PATH**.
2. Open the folder `D:\Project\flowline-materials-planner`.
3. Double-click **`install_windows.bat`**. It creates a private Python environment in `.venv`, installs the
   packages and runs the tests. The first time takes a few minutes. It ends with *Setup complete*.
4. Double-click **`run_planner.bat`**. A black window opens and your browser shows FlowLine at
   `http://localhost:8501`. Keep the black window open while you use it; close it to stop.

### Online

If the app is deployed on Streamlit Community Cloud, open its link. If it shows *This app has gone to sleep*,
click the button to wake it and wait about 30 seconds. Open the link once before a demo.

### Publish your own copy

Double-click **`push_to_github.bat`**. It first runs the sensitive-data check (secrets, e-mail addresses, local
paths, Excel author names, and any words in your private `.sensitive-words` file), then creates the first commit,
creates the GitHub repository if needed, and pushes. Then deploy at [share.streamlit.io](https://share.streamlit.io):
**Create app → repository `alphakfli/flowline-materials-planner`, branch `main`, file `app/streamlit_app.py`**.

---

## 2. The screen in two minutes

| Where | What it is |
| --- | --- |
| Sidebar, **Data** | Sample company or your own upload |
| Sidebar, **What-if** | Supplier slips or recovers; past-due POs arrive later; apply all push-outs. The whole model re-runs |
| Header line | Company, as-of date, fiscal year end and the scenario name (**Base case** when no what-if is on) |
| Six headline numbers | Projects clear to build, projects late to customer, inventory now, year-end landing, year-end turns vs target, critical alerts. With a what-if on, the small arrows show the change against the base case |
| Tabs | Overview, Clear to build, Shop floor, Weekly capacity, Inventory & working capital, Contract manufacturers, Suppliers, Supply risk, Cost reduction, Project financials, Team & KPIs, Meetings & actions, Alerts, Data and exports, Value stream |

Colors mean the same everywhere and always come with a word or icon: 🔴 red = late or critical, 🟠 amber = at
risk or warning, 🟢 green = clear, grey = in build or built.

---

## 3. Tab by tab

### Overview

* **Where each customer project stands**: how many projects are Late, At risk, Clear by start, Clear to build,
  In build and Built.
* **Year-end working capital**: the gap to target, the push-out / cancel lever and excess stock, and how much of
  the gap the identified levers cover.
* **Top actions**: the first ten alerts, each with the suggested action and owner.
* Bottom row: CM commitment, CM on-time delivery, supplier on-time delivery and purchase price variance.

### Clear to build

1. **Timeline.** One row per project. The grey bar is the planned build; the colored bar is when it can really
   be built given material; the black tick is the customer date; the dotted line is today. A colored bar that
   ends right of the tick is a late project.
2. **Project table.** Planned start, material-ready date, gating part, forecast build start, can-ship date,
   customer date, days late, number of late lines, how much of the material is already on hand, order value.
3. **Drill into a project.** Pick a project to see its whole BOM as an indented tree: for every part, how much is
   covered from stock, from POs (with PO numbers), how much must be built, what is still not on order, when it is
   needed and when it will be ready. Flags: 🔴 not on order, 🟠 late, 🔧 build.
4. **Late and missing parts.** Every late or uncovered line across projects, filterable by issue and buyer.
   *Not yet ordered* lines are hidden by default: they still have time.
5. **Long-lead parts.** Parts with 90+ days lead time and the date they must be on order.

### Shop floor

The day on the floor: materials, then production, then delivery. Today's numbers run to the current hour of the
day shift (13:00 in the sample).

1. Six numbers: **schedule attainment** (standard hours earned / hours planned to this hour), **first-pass yield**,
   **labour productivity** (earned / clocked hours), **people short**, **downtime today** and **ERP items overdue**
   (with the value of completions not posted).
2. **SQDCC tier board**: one row each for Safety, Quality, Delivery, Cost and Cash, with today's value, the target,
   🟢 green / 🟠 amber / 🔴 red, a 10-day trend and what is behind it. This is the board for the Tier 1 cell huddle and
   the Tier 2 meeting.
3. **Today's build plan by work centre**: the job, shift plan, plan to now, earned and clocked hours, attainment,
   productivity, people needed vs here, and downtime with its reason. A banner names any work centre short of people.
4. **Output and losses**: plan vs earned by work centre; cumulative output by hour (all work centres or one); the
   downtime Pareto for the last 7 working days; first-pass yield by work centre, today against 4 weeks.
5. **Misses and countermeasures**: every red item today with the open countermeasure if there is one. *Needs a
   countermeasure today* if not; *Escalate to Tier 2* if the miss repeats while a countermeasure is open. Below it,
   the countermeasure log: edit it in place, **Add today's misses to the log**, **Save edits**, and download the
   **Tier 2 board (PDF)**, one page for the meeting.
6. **Skills matrix and training**: every person against every work centre (0 not trained to 4 can train others),
   coverage per work centre and shift against the people needed, and a training plan for the gaps with a trainer
   and a target date.
7. **ERP to clear today**: completions not posted, backflush errors, count variances, scrap, open orders, labels,
   with age and what each one blocks; and the **kits short** for builds starting in the next 7 days, straight from
   Clear to build.

### Weekly capacity

Plan labour and machines week by week to fulfil the orders.

1. **Controls**: number of weeks (8-26), the loading sequence (due date, priority, or material ready), and whether an
   order may start before its planned start. **Reset to the data** undoes your edits.
2. **Resources**: every machine and labour pool with its number of machines or people, shifts, hours per shift, days,
   efficiency and overtime hours a week. Edit any cell and the plan re-runs.
3. **Production orders**: tick which to plan; change quantity (units: sections or transformers), priority or due date.
4. Six numbers: orders in the plan, on time, **late on capacity** (held back by a machine or people), **late on
   material** (cannot start early enough, from Clear to build), the busiest resource and the average load.
5. **Overtime advice**: for capacity-late orders, the Saturday shifts per work centre that bring them back, and
   **Apply the suggested overtime**.
6. **Schedule by order**: one row per order, the weeks each step works on it, the customer date and late finishes.
7. **Load by resource and week**: a heatmap of load % for every machine and labour pool, and for one resource its
   load by order against capacity (the line drops in the Christmas shutdown weeks).
8. **Orders**: material ready, earliest start, start week, finish, due, days late, and what held it back.

### Inventory & working capital

1. Five numbers: inventory now, turns now, days of inventory, year-end landing (with the gap) and year-end turns.
2. **Inventory by stock type**: closed months on the left, the projection on the right (shaded), with the year-end
   target as a dashed line. Hover for values.
3. **Landing by stock type**: now, year end, target, gap and days of inventory for raw materials, semi-finished,
   WIP and finished goods.
4. **Bridge: landing to target**: from the projected landing, minus push-outs and cancellations, minus excess,
   compared with the target.
5. **Levers**: every PO and stock item behind the bridge, largest first.
6. **PO exception messages**: expedite, push out, cancel, reduce, past due for every open PO line.
7. **Excess**: stock and open orders no open project needs.

### Contract manufacturers

1. **Summary**: per CM, on-time delivery, average days late, quality, open and late orders, peak load,
   commitment inside the commit window, and how much demand has changed since the last forecast was sent.
2. Pick a CM to see, month by month in capacity hours: **forecast sent** (blue), **committed by CM** (green),
   **our demand now** (orange) and **CM capacity** (dashed line). The shaded area is the commit window.
3. Item detail and on-time delivery by month.

### Suppliers

1. Supplier OTD, 12-month spend, PPV and number of single-source items.
2. **On-time delivery bar chart**, worst at the bottom, with the target line.
3. **Scorecard table**: OTD, average days late, early deliveries, quality ppm, spend, PPV, open and late lines,
   single-source items, score and grade.
4. **Single-source risk and dual sourcing**: counts by dual-sourcing status, then each part with its risk score,
   alternate source and target date.

### Supply risk

1. Four numbers: high risks, safety-stock changes to make, logistics on-time delivery, premium freight.
2. **Risk register**: a 5 x 5 heat map (likelihood x impact) next to the list. It holds the risks you enter in the
   `risk_register` table plus the risks the model detects: single-source parts with no second source or a current
   shortage, unreliable suppliers, CM overload, long-lead parts not ordered, late carriers, low safety stock.
3. **Safety stock for repeat parts**: current against recommended, in days of demand covered, then the table with
   monthly use, demand variability, lead time, delivery-delay variability, recommended level, reorder point and the
   value of the change. Engineered, project-specific parts carry no safety stock.
4. **Dual-sourcing plan**: every high or medium-risk single-source part, its alternate, target date and next step.
5. **Logistics providers**: on-time delivery, cost, cost per kg and premium shipments with their reasons.

### Cost reduction

1. Realized savings against the target, what should be realized by now, the weighted pipeline and the value of new
   opportunities.
2. **Pipeline by stage** (idea, validated, in implementation, realized) and **realized against target**.
3. **Savings projects**: owner, stage, baseline spend, annual savings, realized to date, target date.
4. **Opportunities found by the model**: prices paid well over standard, cheaper quotes from new sources, premium
   freight, and the carrying cost of the inventory levers. Items already covered by a project are left out.

### Project financials

Shown when the project cost and billing tables are loaded (the sample has them).

1. Six numbers: **contract value** (as sold plus approved change orders), **margin forecast** against margin as
   sold, **unbilled revenue** (earned but not invoiced) and billings in excess, **receivables overdue** with DSO,
   **invoices not raised**, and **fiscal-year billing at risk**.
2. **Margin: as sold vs forecast**: one pair of bars per project, the projects that faded most at the top.
3. **Billing and cash by month**: planned billing, forecast billing and forecast cash, with the fiscal year end marked.
   Billing milestones move with their triggers: a shipment milestone with the forecast ship date from Clear to build,
   a start-of-manufacturing milestone with the forecast build start, a drawings milestone with the customer's approval.
4. **Receivables aging**: open invoices in buckets (not due, 1-30, 31-60, 61-90, 90+ days overdue).
5. **Portfolio**: per project contract, pending changes, budget, actual, committed, ETC (estimate to complete), EAC
   (estimate at completion), margins, percent complete, earned, billed, unbilled, receivables.
6. **Project drilldown**: cost to complete by element, billing milestones with forecast dates and status, change
   orders and submittals for one project, and a **Project review PDF** for it. Material ETC comes from the material
   plan (stock to issue plus parts still to buy), and material committed is the open POs pegged to the project.
7. **Change orders and submittals, all projects**.

### Team & KPIs

1. **Department KPIs**: each KPI with its value, target and a ✅ or 🔴.
2. **Trend**: pick a KPI to see the last 12 months against its target.
3. **Team scorecards**: one row per person with KPIs met, open and overdue actions, and open alerts. Pick a person
   to see their scorecard and the alerts that fall in their scope (their parts and suppliers, or their product family).

### Meetings & actions

1. **This week's meeting agenda**, built from the model for each stakeholder group: Production (what to release
   or hold, sequence changes, CM overloads), Engineering (substitutes for gating parts, obsolete stock, second-source
   approvals, early release of long-lead parts), Contracts (customer dates at risk, supplier price reviews), Finance
   (year-end landing, savings, PPV, safety-stock policy, project billing, unbilled revenue and receivables, invoices
   not raised, margin fade), Suppliers and CMs, and the Materials team. Contracts also gets pending change orders and
   overdue invoices; Engineering gets overdue or rejected submittals.
2. Download the **meeting pack (PDF)** or the **agenda as text** for an e-mail or Teams post.
3. **Action log**: edit in place (status, owner, due date, new rows), then **Save edits**. The overdue flags,
   scorecards and alerts update. Download the log, or the whole input workbook, to keep it for next week.

### Alerts

All alerts with filters for severity, area and owner, and the person each alert belongs to. Critical and Warning
are shown by default. Tick **Add to log** on any alert and press **Add ticked alerts to the action log** to turn it
into an action with an owner and a due date one week out. Download as CSV.

### Data and exports

* **Excel report**: formatted workbook with a summary and every view.
* **PDF review pack**: landscape pages for clear to build, inventory, CMs and suppliers, supply risk and cost, the
  value stream map and the action list.
* **Project review pack**: a portfolio page and one page per project (cost to complete, margin, billing, change
  orders, submittals) for the monthly project review.
* **Power Query workbook**: every output as a named Excel Table (`tbl_alerts`, `tbl_projects`, ...).
* **Input data workbook**: the input tables in upload format.
* **Data check**: problems found in an upload. **Input tables**: browse what was loaded.

### Value stream

Where the inventory days come from, and what better flow is worth, for **one product family** with a fairly standard
route (in the sample: medium-voltage switchgear lineups). One-off projects and other families are not on the map.

1. Five numbers: **lead time** (days of stock plus process days), **waiting**, **process**, **value-added %** and the
   customer **takt time** (available hours a year / units a year).
2. **The map** is an animated isometric plant, in the classic VSM layout. Suppliers, production control (SAP / MRP)
   and the customer (a substation) are on the top row, with the dashed information flow between them (customer
   orders → SAP / MRP → supplier POs, and the build schedule to kitting). The flow runs along a conveyor in the
   middle: each process step is a small building on its own tile, with a data card under it (cycle time and
   changeover in hours per unit, uptime, operators, load against takt). Each stock point is a pile of crates, one
   per day of stock, with its days and value from the app's raw, semi-finished, WIP and finished-goods inventory for
   the family. The biggest wait has a pulsing ring and **Start here**. The **timeline** underneath shows waiting
   days (up) and process days (down), lead time and value-added %.
3. **Animation**: lineups (small cubes) move through the stream at the pace the customer orders. A lineup waits by
   each pile for its days (amber) and moves through each step in its process days (green); a red dot on the timeline
   follows one lineup and counts its days, and the line above the map shows how long the last one took. Trucks run
   on the roads in and out. **Pause** and **Speed** control the clock. It is plain SVG, so it works in any browser,
   on remote desktops and offline.
4. **Future state**: type target days for the stock points and target changeover times under the map. The page
   shows the new lead time, the working capital freed and one line per change ("cut raw cover from 36 to 25 days →
   frees $199k, lead time −11 days"). Press **Future state** on the map to see the piles shrink to your targets.
5. **Steps**: the stock points and process steps as tables. **Download the map (HTML)** saves one file that opens in
   any browser without internet, for a presentation. The PDF review pack has a static 2D version of the map.

---

## 4. Scenarios

Each scenario says what happened, the steps to follow in the app, what you should see, and what you would do.

### Scenario 1. Monday morning: what needs me today?

*You open FlowLine before the 9:00 materials meeting.*

1. Read the six headline numbers: **4 of 11** open projects clear to build, **2** late to customer, inventory
   **$2.87M**, year-end landing **$2.13M**, turns **5.3 vs 6.5**, **7** critical alerts.
2. On **Overview**, look at the project bar: 2 Late, 5 At risk, 3 Clear by start, 1 Clear to build.
3. Read the **Top actions**. The critical ones are: the drawings-approved invoice for P-2602 ($275,600) that was
   never raised; the P-2601 completion not posted in SAP for 3 days ($633,050), which stops the shipment on 25 Nov; the tap changer for P-2613 that should have been ordered by
   20 October; Ironvale Fabrication loaded at 128% in December; P-2606 shipping 28 days late; the year-end
   landing $362k over target; P-2613 shipping 14 days late.

**What you do:** you now have the agenda for the meeting: two late projects (both gated by the same tap changer),
one CM capacity problem, and a working-capital gap. The missed invoice is not a materials problem, but it is cash the
company has earned: send it to the project controller (Noah) before the meeting, and the P-2601 posting to the
production supervisor (scenario 17).

### Scenario 2. A customer order is late: find the gating part

*Lumrey Solar 2 (P-2606) shows red.*

1. Go to **Clear to build**. On the timeline, the P-2606 bar is red and ends well right of the black tick.
2. In the table: planned start 13 Dec, material ready **17 Jan**, gating part **OLTC-75**, can ship 6 Feb against
   a customer date of 9 Jan: **28 days late**.
3. Under **Drill into a project**, P-2606 is selected by default. In the tree, every part is covered from stock or
   POs; the OLTC-75 on-load tap changer line shows PO `4500018207` arriving 17 Jan against a need date of 13 Dec.
4. Go to **Inventory & working capital → PO exception messages**: the same PO has action **Expedite**.
5. Test a recovery: in the sidebar choose **Supplier slips or recovers → S140 Ellerby Tap Changers** and set
   **–30** days. P-2606 turns **At risk** (still ships on time, with 1 day of float), and late projects drop from 2
   to 1.

**What you do:** call Ellerby with a clear ask: a 30-day pull-in on PO 4500018207 saves the customer date. Check
the customer's flexibility in parallel, and ask Engineering whether another tap changer would do.

### Scenario 3. A long-lead part nobody has ordered

*Critical alert: "Long-lead part OLTC-75 ... for P-2613: 1 not on order, should have been ordered by 20 Oct."*

1. **Clear to build → Long-lead parts**. The P-2613 OLTC-75 row: lead time 154 days, need date 23 Mar, order-by
   date **20 Oct**, status **Order overdue**.
2. In the project table, P-2613 is **Late** by 14 days: even if the order goes out today, the part arrives
   26 April for a 23 March build.

**What you do:** the buyer places the order today and asks Ellerby for its best date. Because Ellerby is single
source for this part (see scenario 7), this is also the moment to ask the candidate second source for a quote.
Lesson for the process: long-lead parts must be released at order intake, not at the normal MRP time fence.

### Scenario 4. Year-end working capital: will we hit the target?

*Finance asks on Tuesday where inventory will land on 31 December.*

1. **Inventory & working capital.** Year-end landing **$2.13M** against a target of **$1.77M**: **$362k over**.
   Year-end turns 5.3 against a 6.5 target.
2. **Landing by stock type**: raw materials end at $1.81M (target $1.60M) and WIP at $318k (target $80k). WIP is
   high because P-2607 starts building in late December.
3. **Bridge** and **Levers**: push-outs and cancellations worth **$420k** and excess worth **$73k**. The biggest:
   * PO 4500018228, six vacuum breakers from Veltrano, due 15 Dec but first needed 2 Apr: push out, $168k;
   * PO 4500018235, fourteen enclosures from Ironvale, due 17 Dec, needed 1 Feb: push out, $133k;
   * RLY-LEGACY, a superseded relay: 14 in stock with no demand ($67k) and 10 more on order (cancel, $48k);
   * PO 4500018242, copper magnet wire, due 5 Dec, needed 14 Feb: push out, $48k.
4. Tick **Apply all push-outs and cancellations** in the sidebar. The landing drops to **$1.71M** (–$420k),
   **under target**, year-end turns rise to 6.6, and late projects stay at 2: the push-outs do not hurt delivery.

**What you do:** give each buyer their push-out list today (suppliers need notice before their own year end),
ask Qorvane to cancel the RLY-LEGACY order and take back stock, and tell Finance: "Landing $2.13M today;
$420k of agreed push-outs brings us to $1.71M, under target, without delaying any customer order."

### Scenario 5. The trap: hitting the inventory number by being late

*A colleague notices the landing fell after Veltrano slipped. Good news?*

1. Clear the push-out box. Choose **S100 Veltrano Breakers** with **+21** days.
2. Year-end landing falls to **$1.76M**, under target. But projects clear to build drop from 4 to 2 and late
   projects rise from 2 to **3**.

**What you do:** say it plainly in the meeting: a supplier slip lowers year-end inventory only because the material
arrives later, and it costs us customer dates. FlowLine shows both numbers side by side so the team
never trades one for the other without seeing it. Clear the what-if.

### Scenario 6. Contract manufacturer review

*Weekly call with Ironvale Fabrication (enclosures and tanks) and Corefield Lamination (cores).*

1. **Contract manufacturers → summary**. Ironvale: OTD **72%**, peak load **128%**, commitment 91% in the window,
   demand **+21%** since the last forecast (sent 5 Nov). Corefield: commitment only **63%** in the window.
2. Choose **CM200 Ironvale Fabrication**. December needs 526 hours against 412 hours of capacity (holiday month).
   February: the forecast sent shows 90 hours, but our demand now is about 400 hours. That is the enclosure
   demand of P-2611, released after the last forecast went out.
3. Choose **CM230 Corefield Lamination**. December: forecast 325 hours, committed only 200.

**What you do:** send both CMs an updated forecast today. With Ironvale, agree to pull part of the December load
into November or January and confirm February now. With Corefield, escalate the December commitment gap: those
cores feed P-2606 and P-2608.

### Scenario 7. Supplier scorecard and single-source risk

*Quarterly business review preparation.*

1. **Suppliers.** Overall OTD **91%**, PPV **+$279k (+2.2%)** on $12.9M spend, **30** single-source parts,
   5 with a second source in progress.
2. In the OTD chart, three suppliers are red: Ellerby Tap Changers (67%), Ironvale Fabrication (72%) and Veltrano
   Breakers (73%).
3. In the scorecard, Veltrano also has PPV of **+4.1%**, and Ellerby **+6.4%**. Brightmere Instruments delivers
   98% on time but is graded C because of 9,677 ppm rejects: quality pulls the score down.
4. **Single-source risk.** The highest risk is OLTC-75 (Ellerby, 154 days, three open projects), only a
   candidate second source. Vacuum breakers from Veltrano: a second source (Marlowe) in qualification for the
   1200 A breaker, only a candidate for 2000 A. Protection relays from Qorvane: no second source identified.

**What you do:** for the QBR with Ellerby, bring OTD, PPV and the two late projects; ask for a recovery plan and a
capacity reservation. Prioritize the second-source work by risk score: tap changers, then breakers, then relays.
Ask Brightmere for an 8D on rejects.

### Scenario 8. Prepare the weekly pack and refresh Excel / Power BI

1. **Data and exports → PDF review pack** for the meeting.
2. **Excel report** for anyone who wants to filter.
3. **Power Query workbook** for a refreshable report:
   1. Save it once as, for example, `D:\Project\flowline-materials-planner\output\flowline_pq.xlsx`.
   2. In Excel or Power BI: **Data → Get Data → From File → From Workbook**, pick the file, and tick the tables you
      want (for example `tbl_projects`, `tbl_alerts`, `tbl_inventory_by_month`). Load or transform.
   3. Each week, download a new Power Query workbook over the same file name and press **Refresh All**.
      The `tbl_index` table shows the as-of date and scenario of the data you loaded.

Command-line alternative for a scheduled job: `flowline run my_data.xlsx --out output/` writes all three files.

### Scenario 9. Run the weekly cross-functional meeting

*Tuesday 10:00, with engineering, production, contracts and finance in the room.*

1. Go to **Meetings & actions**. Keep all stakeholders selected and download the **Meeting pack (PDF)**.
2. Walk the agenda in order:
   * **Production (10 items):** release P-2604 and P-2605; sequence changes for the at-risk and late projects;
     Ironvale at 128% in December.
   * **Engineering (12 items):** is a substitute acceptable for OLTC-75, BUS-CU-1200 and the other gating parts?
     What to do with 14 superseded RLY-LEGACY relays? Approvals for the Marlowe breaker and Stellmark core second
     sources; release the P-2613 tap changer from the BOM now.
   * **Contracts (8 items):** warn Lumrey Solar (P-2606) and Orrindale Wind (P-2613); price reviews with Veltrano
     and Ellerby.
   * **Finance (4 items):** landing $2.13M against $1.77M, savings $186k of $250k, PPV +$279k, and the safety-stock
     policy change.
3. Close with the **action log**: 8 open actions, 3 overdue (A-102 relay disposition, A-104 customer warning,
   A-106 Ironvale forecast). Agree new dates, change the status in the table and press **Save edits**.
4. In **Alerts**, tick the new items agreed in the meeting (for example the Corefield commitment gap) and press
   **Add ticked alerts to the action log**. Each one gets an owner from the team table.
5. **Download input workbook with the log** and save it; upload it next week so the log carries over.

**What you get:** one agenda that speaks to each function in its own terms, and a log that shows next week whether
the actions happened.

### Scenario 10. Monthly one-to-ones with the team

*First week of the month: a scorecard conversation with each buyer and planner.*

1. **Team & KPIs → Department KPIs**: 5 of 14 on target. Turns 3.5 against 4.0, trending down since January;
   supplier OTD 91% against 95%.
2. **Team scorecards**: Leah (switchgear planner) meets 4 of 5; Tomas (transformer planner) meets 0 of 5;
   Arjun (transformer-parts buyer) 2 of 7.
3. Pick **Tomas**: both late projects and 3 at-risk projects are transformers; clear-to-build 17% against 80%;
   9 late part lines; one overdue action (A-104, the customer warning).
4. Pick **Arjun**: his suppliers deliver 85% on time against 92%, PPV +4.6%, 7 lines to expedite, no savings yet.

**What you do:** the numbers show it is the tap-changer and bushing supply, not the planner's work, so the
conversation with Tomas is about support: you take the Ellerby escalation yourself and he focuses on re-sequencing.
With Arjun, agree two objectives for the quarter: an Ellerby recovery plan and one savings project (the Ellerby
PPV is a $59k opportunity on the Cost reduction tab).

### Scenario 11. Protect supply: safety stock and second sources

*Quarterly supply-risk review.*

1. **Supply risk → Risk register**: 9 high risks. At the top: OLTC-75 single source with a shortage, the two
   Qorvane relays with no second source, the P-2613 tap changer not ordered, and the Ironvale welder shortage you
   entered yourself.
2. **Safety stock**: natural ester fluid carries 2,000 L but needs 7,801 L for 95% service (monthly use about
   13,000 L, variable). Ten repeat parts are under half the level they need; hardware and gasket kits carry too much.
   The net change adds $134k of inventory.
3. **Dual-sourcing plan**: Marlowe is in qualification for the 1200 A breaker (target 23 Mar); OLTC-75 and the
   2000 A breaker have only a candidate; nobody has been found for the relays.
4. **Logistics**: Bayport Ocean Logistics delivers 80% on time; $35k of premium freight went on 14 expedited
   shipments, chasing late tap changers, breakers, bushings, CTs and relays.

**What you do:** raise safety stock on the repeat parts but fund it by lowering the overstocked ones and by the
year-end push-outs. Ask Finance to approve the policy (it shows on their agenda). Start a relay second-source search.
Use the premium-freight list to prove why long-lead parts must be released at order intake.

### Scenario 12. Close the savings gap

*Finance asks whether the $250k cost-reduction target will be met.*

1. **Cost reduction**: $186k realized against $223k expected by now (74% of the annual target). The weighted
   pipeline is $262k.
2. **Savings projects**: the biggest open one is the Marlowe second source for 1200 A breakers ($66k a year,
   validated). Returnable packaging with Ironvale is past its target date.
3. **Opportunities found by the model**: a 7% cheaper quote for 2.5 MVA cores from Stellmark ($73k a year),
   Ellerby tap changers paid 6.5% over standard ($59k), Veltrano breakers paid 4% over standard, and $99k a year of
   carrying cost on the inventory levers.

**What you do:** move the Marlowe breaker project into implementation as soon as the type test passes, open a
project for the Stellmark cores (it also reduces single-source risk), and take the Ellerby price to the QBR together
with the delivery problems. Tell Finance: realized $186k, with $66k + $73k in reach this fiscal year if the two
second sources qualify on time.

### Scenario 13. Month-end project review: margin and cost to complete

*It is month end. The project controller and the project managers review cost and margin.*

1. Open **Project financials**. Contract value **$10.63M**; margin forecast **22.3%** against **23.4%** as sold
   (**-1.1 points**). Two projects fade by 1.5 points or more.
2. In **Margin: as sold vs forecast**, P-2603 Orrindale Wind LP is at the top: **24.5%** sold, **21.2%** forecast,
   **3.3 points** of fade. P-2602 Quillfield Data Campus is next: 30.3% to 28.6%.
3. Pick **P-2603** in the drilldown. Material actual is **$471,000** against a budget of $446,200 (**-$24,800**):
   the core steel was bought above standard. Labour is on budget.
4. Pick **P-2602**. Labour has an ETC override: $64,240 spent and **$70,080** still to go against a budget of
   $116,800 (**-$17,520**). The approved change order CO-2602-01 (+$95,000 price, +$58,000 cost) is already in the
   contract and budget.
5. Download the **Project review pack** from Data and exports for the meeting.

**What you do:** accept the new EAC for P-2603 (the material is bought; the cost will not come back) and log the
lesson for the next transformer bid. For P-2602 ask the project manager for a labour recovery plan before accepting
the overrun. Keep the contingency on both projects until shipment.

### Scenario 14. Billing and cash: the invoice nobody raised and the year-end slip

*Finance asks for the December billing and cash forecast.*

1. **Invoices not raised: 1 ($275,600)**. In the drilldown for P-2602, milestone **M2 Drawings approved** shows
   *Due, not invoiced*: the customer approved the drawings on 14 Aug and no invoice was recorded.
2. **FY billing at risk: $225,500**. Two start-of-manufacturing milestones move into January with their build
   starts: **P-2606** ($80,700, from 13 Dec to 17 Jan, gated by the OLTC-75 tap changer) and **P-2608** ($144,800,
   from 28 Dec to 3 Jan).
3. **Receivables overdue: $267,600**, DSO 59 days. In the aging, $233,400 is 31-60 days overdue: INV-2603-M2
   (Orrindale Wind LP, $157,200, 51 days) and INV-2610-M1 (Fenwold Co-op Power, $76,200, 43 days).
4. Unbilled revenue is **$1.45M**, all on the three projects built or in build (P-2601, P-2602, P-2603), where cost
   has run ahead of the milestones. Billings in excess on the other projects are $1.32M.
5. Test the recovery from scenario 2: **Supplier slips or recovers → S140 Ellerby Tap Changers, –30 days**. P-2606's
   build start, and its $80,700 milestone, move back into December; FY billing at risk drops to $144,800.

**What you do:** raise the P-2602 M2 invoice today. Tell Finance: December billing is $225,500 lower than planned
because of two build starts, and $80,700 of it comes back if Ellerby recovers the tap changer. Call Orrindale and
Fenwold about the overdue invoices; check first that there is no open dispute (a short shipment or a missing
document) holding the payment.

### Scenario 15. Change orders and submittals

*The weekly contracts and engineering meeting.*

1. **Change orders, all projects**: CO-2611-01 for P-2611 (second incomer and tie breaker, **$140,000**) has been
   waiting for the customer for **41 days**. CO-2605-01 (arc-flash relay upgrade, $22,000) for 12 days.
2. **Submittals**: S-2611-GA came back from the customer as **Resubmit**; it holds milestone M2. S-2609-GA is
   **9 days** overdue at the customer. The supplier datasheet S-2613-OLTC from Ellerby is 5 days late and holds
   the release of the tap changer that already gates P-2613.
3. **Meetings & actions**: the Contracts and Engineering sections of the agenda list the same items with the
   decision needed.

**What you do:** do not start the CO-2611-01 work (or buy its breakers) until the customer signs it; ask the
customer for a decision date. Ask engineering for the S-2611-GA resubmission date, because the M2 invoice waits for
it. Chase Ellerby for the datasheet together with the tap changer expedite: one call, two problems.

### Scenario 16. Value stream: where do our inventory days come from?

*The plant manager asks why switchgear ties up so much cash when a lineup takes only two weeks to build.*

1. Open **Value stream**. Switchgear lead time is **130 days**: **114 days waiting** in stock and **16 days** of
   process. Value-added is **12%**. Takt is **286 hours** per lineup (14 lineups a year).
2. Read the triangles: raw material **36 days** ($637k), work in process **42 days** ($730k, the P-2602 lineup in
   build), sections waiting 0 days, finished goods **36 days** ($633k, P-2601 built and waiting to ship on 25 Nov).
   Work in process has the pulsing ring: it is the biggest wait. The same point is in **Alerts** (area *Value stream*).
3. Look at the data cards: assembly has the longest cycle (112 h, 43% of takt), fabrication the longest changeover
   (6 h). No step is over takt, so capacity is not what makes the lead time long; waiting is.
4. In **Future state**, the targets from the data are already filled in: raw 25 days, WIP 30, finished goods 20,
   fabrication changeover 2 h. Lead time drops to **91 days (−39)** and **$685k** of working capital is freed.
   The fabrication changeover only takes 0.3 days off the lead time; its value is capacity.
5. Watch the map for a few seconds. Five or six lineups are in the stream at any time, and most of them are
   waiting by a pile, not in a building. Press **Future state**: the piles shrink and the last lineup delivered
   drops from 130 days towards 91.
6. Try your own: set finished goods to 10 days. That is shipping a lineup within two weeks of test, which needs the
   customer's site to be ready.

**What you do:** tell the plant manager the lead time is in the waiting, not in the build. Start with work in
process: kit a lineup only when fabrication is ready for it and finish one lineup before kitting the next. Then
agree ship dates at order entry so built lineups don't wait. Treat the dollars as the size of the prize, not a
forecast: in engineer-to-order, one lineup more or less in build moves the WIP triangle by weeks (see *Limits* in
[logic.md](logic.md)).

### Scenario 17. Tier 1 and Tier 2 on the shop floor

*Monday, 13:00. You run the Tier 2 meeting with materials, quality and engineering.*

1. Open **Shop floor**. Attainment is **89%** against 95%, first-pass yield **94%**, productivity **93%**, one person
   short, 515 minutes of downtime, 3 ERP items overdue.
2. On the **SQDCC board**: Safety green (41 days since the last recordable, 2 near misses this week); Quality amber;
   Delivery red; Cost green; Cash red ($633,050 of completed work not posted).
3. In **Today's build plan**, three work centres are behind:
   - **Kitting 46%**: 150 minutes waiting for material. **Kits short** shows why: the P-2604 core (CM230, due
     25 Nov) and radiators (S170, due 26 Nov) are not in yet, for a build that starts on 29 Nov. P-2604 is
     *Clear by start* on the Clear to build tab: released on condition that both receipts arrive.
   - **Switchgear assembly 84%**: 4 of 5 people; one absence not covered.
   - **Test bay 75%**: section 2 of P-2602 failed hi-pot on a bus joint; 90 minutes on quality hold.
4. **Misses and countermeasures**: the test-bay failure repeats the cause in CM-033 (torque not marked, open
   since 20 Nov), and assembly's miss repeats CM-034 (bus kits late): both say **Escalate to Tier 2**. Kitting,
   test-bay attainment and the cash item have no countermeasure yet.
5. The **downtime Pareto** for the week has *Waiting for material* on top (270 minutes), ahead of absence and
   changeovers.

**What you do:** Cash first: post the P-2601 final confirmation today, or the 25 Nov shipment can't be created.
Kitting: kit everything that is here for P-2604 and confirm the two deliveries with the buyer; don't move the build
yet. Assembly: Victor O. from the test bay is qualified in assembly, but test is behind too, so cover the missing
assembler with two hours' overtime instead. Quality: CM-033 is not working; make the torque mark a hold point that test checks
before hi-pot, owner the assembly lead. Press **Add today's misses to the log**, fill in owners and dates, and
download the **Tier 2 board** for the record.

### Scenario 18. People and ERP before the end of the shift

*14:30. You plan cover for tomorrow and clear SAP before the shift ends.*

1. **Skills matrix**: the test bay has **one** qualified person on days (Uma N.). One absence stops all testing,
   and the alert list already says so. Coverage also shows gaps in switchgear assembly (4 qualified for 5 places)
   and on the evening shifts in fabrication and winding.
2. The **training plan** proposes Hana V. for the test bay (level 2 now, trained by Uma N., target 23 Dec), Gus T.
   for assembly, and Aiko M. and Esme P. on the evening shift.
3. **ERP to clear today**: the P-2601 completion (3 days, blocks the shipment), a count variance on copper bus
   (5 days, the inventory analyst's), and an old order to close (12 days) are overdue. The P-2602 backflush errors
   and two scrapped sheets are new: clear them today so they don't age.

**What you do:** book Hana V. into test-bay training this week; it is the cheapest risk you can remove. Clear
COGI and post the scrap before 15:30; ask Grace to recount the copper bus with the stores lead. In the monthly
one-to-ones, the training plan becomes each person's objective.

### Scenario 19. Weekly capacity: can we make the transformer orders?

*Thursday. The production planner and supervisor plan the next 16 weeks of labour and machines.*

1. Open **Weekly capacity**. 10 orders fall inside the 16 weeks: 8 on time, **1 late on capacity**, **1 late on
   material**.
2. **Orders**: MO-2606 (P-2606, 1 transformer) is late on material: it cannot start before the OLTC-75 tap changer
   arrives on 17 Jan. No amount of overtime fixes that; it is the buyer's expedite from scenario 2.
3. MO-2608 (P-2608, 6 transformers) finishes 5 Feb against 29 Jan: **7 days late on capacity**, held back by the
   transformer fitters. In **Load by resource**, pick *Transformer fitters*: they are at 100% in the weeks of 11 and
   18 Jan, after the two shutdown weeks cut capacity to 60%. Each transformer then waits a week before test.
4. The **overtime advice** says: transformer assembly, oven +16 h and fitters +64 h a week (two Saturdays). Press
   **Apply the suggested overtime**: MO-2608 is back on time.
5. Try other levers yourself: change the loading rule to **Priority**, untick an order that can move, or change the
   number of fitters, and watch MO-2608's finish.

**What you do:** take the overtime to the Tier 2 meeting for approval, and check the skills matrix on Shop floor for
who can cover the Saturdays. Keep MO-2606 with the buyer: it is a material problem, not capacity.

---

## 5. Use your own data

1. In the sidebar choose **Upload Excel or CSV**, then **Download blank template**. Or download the **Input data
   workbook** from Data and exports to start from the sample's format.
2. Fill at least `items`, `bom` and `projects`. Add the other tables as you get them; each one switches on more of
   the app. For the team and meeting features add `team`, `objectives` and `actions`; for supply risk
   `consumption_history`, `risk_register` and `shipments`; for cost reduction `savings_projects` and `savings_target`
   in settings; for project financials `wbs_budget`, `cost_actuals` and `billing_milestones` (with `change_orders`
   and `submittals` if you have them); for the value stream map `process_steps` for one product family (set
   `vsm_family`, `vsm_hours_per_day` and `vsm_working_days` in settings); for the shop floor `work_centers` and
   `shop_schedule`, plus `hourly_output`, `downtime`, `quality_checks`, `safety_events`, `operators`, `skills`,
   `erp_open_items` and `countermeasures` as you have them; for the weekly capacity plan `resources`, `routings` and
   `production_orders` (with `capacity_calendar` for holidays). The README sheet of the template explains every column. [sap-mapping.md](sap-mapping.md) says where
   each column lives in SAP.
3. In `settings`, set `as_of_date` (blank = today), `fiscal_year_end`, `turns_target` and `company`.
4. Upload the workbook (or the CSV files together). Check **Data and exports → Data check** for problems.

Uploaded files stay in your session; nothing is stored by the app. On a public deployment, use anonymized or
sample data only.

---

## 6. Glossary

| Term | Meaning |
| --- | --- |
| Clear to build (CTB) | All material for a project is available. Here: *Clear to build* = in stock now; *Clear by start* = arrives before the planned build start |
| Material ready | Date the last part (or sub-assembly) for a project is available |
| Gating part | The part that sets the material-ready date |
| Float | Days between can-ship date and customer date |
| ETO | Engineer to order: each customer order has its own engineered BOM |
| Pegged PO | PO line reserved for one project (project stock / account assignment) |
| Push out / pull in | Ask a supplier to deliver later / earlier |
| Turns | COGS / inventory. Higher is better |
| DOI | Days of inventory: inventory / daily COGS |
| Landing | Projected value at a future date, here the fiscal year end |
| OTD | On-time delivery, measured against the supplier's promised date within a window |
| PPV | Purchase price variance: price paid minus standard cost |
| ppm | Rejected parts per million received |
| CM | Contract manufacturer |
| Commit window | Months in which a CM's commitment must cover the forecast |
| WBS | Work breakdown structure: the project's cost split by element (material, labour, engineering ...) |
| ETC / EAC | Estimate to complete / estimate at completion (actual + committed + ETC) |
| Margin fade | Margin as sold minus forecast margin, in points |
| POC | Percent complete, cost to cost: actual cost / EAC. Earned revenue = POC x contract |
| Unbilled revenue | Earned but not yet invoiced (a contract asset). Billings in excess = invoiced ahead of earning |
| DSO | Days sales outstanding: receivables / billing of the last 90 days x 90 |
| VSM | Value stream map: the flow of material and information for one product family, with the time spent waiting and in process |
| Takt time | Available working time / customer demand: the pace the customer buys at |
| C/T, C/O | Cycle time per unit; changeover (setup) time between jobs |
| Value-added % | Process days / total lead time |
| Finite capacity | Loading work only up to the hours available each week; what doesn't fit moves to the next week |
| Routing | The steps a product goes through, with machine and labour hours per unit at each step |
| Efficiency | Share of paid hours that produce: availability for a machine, efficiency for people |
| SQDCC | Safety, Quality, Delivery, Cost, Cash: the five letters of the tier board |
| Tier 1 / Tier 2 | Daily meetings: Tier 1 is the cell team at shift start; Tier 2 is the supervisor with support functions |
| Standard (earned) hours | The hours the routing allows for the work completed |
| Schedule attainment | Earned hours / planned hours |
| Labour productivity | Earned hours / hours clocked |
| First-pass yield (FPY) | Units passing inspection or test first time / units inspected |
| Countermeasure | The action that stops a missed goal from repeating, with an owner and a date |
| Skills matrix | Who is trained on which station, from 0 (not trained) to 4 (can train others) |
| Submittal | A drawing or document sent for approval (to the customer) or received for approval (from a supplier) |

---

## 7. Questions and troubleshooting

**Why is a project *At risk* rather than *Late*?** Its build start slips, but the slip fits in the float before
the customer date. It becomes Late when the can-ship date passes the customer date.

**Why do turns look much better at year end than today?** Year-end turns divide the whole fiscal year's COGS by the
year-end balance, after the December shipment wave has left. Today's turns use trailing 12-month COGS against
today's balance, which still holds the work in progress for those shipments.

**The numbers differ from SAP MD04.** FlowLine allocates supply to projects in build-start order and
measures from today; MD04 shows net requirements by date and does not name a gating part per project. Check
the pegging in the drill-down tree.

**`install_windows.bat` says Python is not installed.** Install it from python.org with *Add python.exe to PATH*
ticked, then run the file again.

**The browser does not open.** Go to `http://localhost:8501` yourself while the black window is open.

**`push_to_github.bat` stopped with "possible issue(s)".** The sensitive-data check found something. Read the
list, fix or remove the file, and run it again. If a finding is a false alarm, send the message to whoever
maintains the repository.
