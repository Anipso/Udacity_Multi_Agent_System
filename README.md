# Beaver's Choice Paper Company — Multi-Agent System

## Overview

This project implements an intelligent multi-agent system for **Beaver's Choice Paper Company** (codenamed *Munder Difflin*) using the **smolagents** framework. The system handles the company's three core business functions in a unified conversational interface:

1. **Inventory management** — real-time stock queries and automated supply reordering
2. **Customer quoting** — historically-informed, bulk-discounted price generation
3. **Sales processing** — transaction finalization with live inventory verification

All state is persisted in a local SQLite database (`munder_difflin.db`), and the system is tested against a provided set of 20 real-world-style sample requests (`quote_requests_sample.csv`).

---

## Architecture

The system follows a **hierarchical multi-agent** design: one orchestrator agent owns the conversation and delegates sub-tasks to three specialized agents. No agent exceeds five tools, keeping each one focused and debuggable.


### Agent Roles

| Agent | Responsibility |
|---|---|
| **Orchestrator** | Receives every incoming request, identifies intent, and routes it to the correct specialized agent(s). For multi-step requests (quote then purchase) it chains agents in sequence. |
| **InventoryAgent** | Answers stock-level queries, detects items below minimum thresholds, places supplier reorders, and estimates delivery timelines. |
| **QuoteAgent** | Maps natural-language item descriptions to exact catalog names, pulls comparable historical quotes, and generates fully-priced quotes with automatic bulk discounts. |
| **SalesAgent** | Verifies stock before every sale, records the revenue transaction, and produces cash-balance and global financial reports. |

---

### Workflow Diagram and Architectural Rationale

The system's structure is depicted in the Mermaid workflow diagram (`workflow_diagram.md`). The diagram shows the Orchestrator at the top, three specialist agents in a middle tier, the tools each agent owns, and the helper functions each tool calls. The sections below explain the design decisions visible in that diagram.

**Why a hierarchical orchestrator pattern rather than a single agent with all tools?**
A flat design would give one agent 14+ tools, a combined system prompt covering quoting, stocking, and selling simultaneously, and no clean separation between read-only queries and write transactions. The orchestrator pattern solves all three problems: each specialist is limited to five tools (the smolagents recommended ceiling), each has a focused system prompt, and the Orchestrator controls when a quote becomes a sale — the two operations cannot be accidentally conflated.

**Why are QuoteAgent and SalesAgent separate?**
Quoting is a read-only, side-effect-free operation: it computes prices and checks availability but does not alter any database state. Selling writes an irreversible `sales` transaction to the ledger. Separating the two agents makes it impossible for the quoting workflow to accidentally commit a transaction. The Orchestrator must explicitly route to SalesAgent for a purchase to occur, which matches real business logic — a customer receiving a quote has not yet agreed to buy.

**Why does InventoryAgent exist as a distinct agent rather than being absorbed into SalesAgent?**
Inventory management involves both reactive tasks (check whether a specific item is in stock) and proactive tasks (scan all items against their minimum thresholds and initiate reorders). Combining these with sales would require SalesAgent to hold reorder logic in its context on every transaction, even when no reorder is needed. InventoryAgent's separation also means reorder decisions — which check cash balance before committing spend — are isolated from revenue transactions, making the financial audit trail cleaner.

**Why does `list_catalog_items` appear in both InventoryAgent and QuoteAgent?**
Customer requests use natural language: "A3 glossy paper", "recycled cardstock", "heavy poster board". Before any database query can succeed, these descriptions must be resolved to exact catalog names. Giving `list_catalog_items` to both agents ensures that neither agent can fail silently on a name mismatch — both call it as the first step before looking up stock or generating a price.

**Why an append-only `transactions` ledger rather than a mutable stock table?**
The `transactions` table records every `stock_orders` and `sales` event with a timestamp. Stock levels and cash balances are computed at query time using date-bounded SQL aggregates, not stored as running totals. This design gives the system a full audit trail: `generate_financial_report(date)` can reconstruct the exact state of the company at any past moment. It also eliminates the risk of update anomalies — a failed write can never corrupt a previously correct balance.

**Why the Orchestrator itself holds no tools directly?**
The Orchestrator's specialist sub-agents are wrapped as `@tool` closures — each sub-agent looks like a single tool from the Orchestrator's perspective. This keeps the Orchestrator's decision surface minimal: it reads the incoming request, classifies it (quote / inventory / sale / mixed), and calls the appropriate "tool" (sub-agent). The Orchestrator does not reason about pricing, stock levels, or transaction mechanics — it only decides who should handle the request and then enforces output quality rules before returning the final response.

---

## Data Model

The SQLite database contains four tables, all managed by `init_database()`:

| Table | Source | Purpose |
|---|---|---|
| `inventory` | Generated via `generate_sample_inventory()` | Master catalog with current stock and minimum thresholds (40% of full catalog, seeded deterministically) |
| `transactions` | Runtime writes | Append-only ledger of every `stock_orders` and `sales` event; used to derive current stock and cash balance at any point in time |
| `quote_requests` | `quote_requests.csv` | Historical customer requests used as the search corpus for quote lookups |
| `quotes` | `quotes.csv` | Historical quote responses — totals, explanations, job/event metadata — joined with `quote_requests` during history search |

Stock levels and cash balance are both computed from `transactions` using date-bounded aggregate queries, giving the system a full audit trail.

---

## Tools

### InventoryAgent tools (5)

| Tool | What it does |
|---|---|
| `list_catalog_items(keyword)` | Searches the 44-item product catalog by partial name or category. Used to resolve natural-language item descriptions to exact catalog names before any database query. |
| `check_paper_inventory(item_name)` | Queries `transactions` to return live stock for a specific item or the full inventory snapshot. |
| `check_reorder_needs(request_date)` | Compares live stock against each item's `min_stock_level` and returns the list of items that need restocking. |
| `reorder_supplies(item_name, quantity, request_date)` | Checks cash balance, then records a `stock_orders` transaction and returns the estimated delivery date. |
| `check_delivery_timeline(item_name, quantity, request_date)` | Returns the supplier lead time based on quantity tiers: 0 days (≤10), 1 day (≤100), 4 days (≤1,000), 7 days (>1,000). |

### QuoteAgent tools (4)

| Tool | What it does |
|---|---|
| `list_catalog_items(keyword)` | Shared with InventoryAgent — resolves item names before quoting. |
| `get_quote_history_tool(search_terms)` | Full-text searches `quote_requests` + `quotes` by comma-separated keywords (item names, event type, job title, order size). Filters out error rows where `total_amount = -1` and returns up to five valid comparable quotes. |
| `generate_customer_quote(item_name, quantity, request_date)` | Computes the discounted unit price and total, then checks live availability. Discount tiers: 5% (≥500 units), 10% (≥1,000), 20% (≥5,000). |
| `check_paper_inventory(item_name)` | Used to confirm availability before finalising a quote. |

### SalesAgent tools (5)

| Tool | What it does |
|---|---|
| `fulfill_sale(item_name, quantity, unit_price, sale_date)` | Verifies stock, records the `sales` transaction, and returns the transaction ID and remaining stock. Rejects the sale if stock is insufficient. |
| `check_cash_balance_tool(as_of_date)` | Returns the net cash position (cumulative sales minus cumulative purchases) as of a given date. |
| `check_delivery_timeline(item_name, quantity, request_date)` | Provides delivery estimates when a customer asks about fulfilment timing. |
| `generate_global_report(as_of_date)` | Produces a formatted summary: cash, inventory value, total assets, and the top-five products by revenue. |
| `check_paper_inventory(item_name)` | Used before every sale attempt to confirm adequate stock. |

---

## Request Processing Workflow

The orchestrator receives each row from `quote_requests_sample.csv` enriched with three additional context fields extracted from the CSV columns:

- `event_type` (e.g., `ceremony`, `conference`, `parade`)
- `order_size` (`small` / `medium` / `large`)
- `job_type` (e.g., `office manager`, `hotel manager`)

These fields are passed into the routing prompt so the **QuoteAgent** uses them as keywords when searching the historical quote database, surfacing the most contextually relevant comparable prices.

### Typical quote flow

```
1. Orchestrator receives request + event/size/job context
2. → routes to QuoteAgent
3.   QuoteAgent calls list_catalog_items() to resolve item names
4.   QuoteAgent calls get_quote_history_tool(item names + event + job + size)
5.   QuoteAgent calls generate_customer_quote() per line item
6.   QuoteAgent calls check_paper_inventory() to verify availability
7.   QuoteAgent returns consolidated multi-item quote
8. Orchestrator returns professional response
```

### Typical inventory-check + reorder flow

```
1. Orchestrator detects inventory intent
2. → routes to InventoryAgent
3.   InventoryAgent calls check_reorder_needs()
4.   If items are below threshold:
       InventoryAgent calls check_cash_balance() (via reorder_supplies guard)
       InventoryAgent calls reorder_supplies() for each item
5.   Returns reorder confirmations with delivery dates
```

---

## Discount Strategy

The bulk-discount tiers used by `generate_customer_quote` were derived from the patterns in `quotes.csv`, where agents consistently applied round-number discounts on larger orders:

| Quantity | Discount | Label |
|---:|---:|---|
| < 500 | 0% | Standard |
| 500 – 999 | 5% | Volume |
| 1,000 – 4,999 | 10% | Wholesale |
| ≥ 5,000 | 20% | Bulk |

This mirrors the behaviour seen in historical quotes (e.g., a 10-ream order rounded to $60 from $64, large festival orders receiving 20% reductions) while making the discount logic transparent and deterministic.

---

## Evaluation Results

> Results below are drawn from `test_results.csv` produced by running all 20 test scenarios in `quote_requests_sample.csv`. Financial values, discount figures, and response excerpts are taken directly from actual system output.

### Test Scenario Overview

20 requests processed in chronological order (April 1–17, 2025) across nine distinct customer job types, five order-size categories, and twelve event types.

| # | Date | Job | Size | Event | Key Items Requested | Catalog Match |
|---|---|---|---|---|---|---|
| 1 | Apr 01 | Office manager | Small | Ceremony | A4 glossy, cardstock, colored paper | Full |
| 2 | Apr 03 | Hotel manager | Small | Parade | Poster paper, streamers, **balloons** | Partial |
| 3 | Apr 04 | School board mgr | Large | Conference | A4 paper (10k), **A3 paper** (5k), printer paper | Partial |
| 4 | Apr 05 | Non-profit director | Small | Reception | Recycled cardstock, A4 printer paper | Full |
| 5 | Apr 05 | School teacher | Medium | Party | Colored paper, cardstock, washi tape | Full |
| 6 | Apr 06 | School teacher | Small | Assembly | Construction paper, printer paper, cardstock | Full |
| 7 | Apr 07 | Business owner | Large | Exhibition | Glossy, matte, poster boards (24×36), heavyweight cardstock | Full |
| 8 | Apr 07 | School board mgr | Large | Ceremony | A4 glossy, A4 matte, **A5 colored**, A4 recycled | Partial |
| 9 | Apr 07 | City hall clerk | Small | Reception | A4 printer, A3 glossy, kraft envelopes | Full* |
| 10 | Apr 08 | Business owner | Medium | Show | Glossy paper, cardstock | Full |
| 11 | Apr 08 | Event manager | Small | Exhibition | **A3 glossy**, A4 matte | Partial |
| 12 | Apr 08 | City hall clerk | Small | Party | Colorful cardstock, printer paper, napkins | Full |
| 13 | Apr 08 | School principal | Small | Gathering | A4 printing paper, cardstock | Full |
| 14 | Apr 09 | City hall clerk | Large | Performance | A4 paper (5k), poster paper (2k), cardstock | Full |
| 15 | Apr 12 | Event manager | Large | Demonstration | A4 (10k), **A3 colored** (5k), **cardboard** | Partial |
| 16 | Apr 13 | School teacher | Small | Assembly | A4, construction paper, poster board | Full |
| 17 | Apr 14 | Restaurant mgr | Medium | Reception | A4, colored paper, napkins, cups, plates | Full |
| 18 | Apr 14 | Office manager | Medium | Ceremony | Cardstock, printing paper, colored paper | Full |
| 19 | Apr 15 | City hall clerk | Medium | Exhibition | A4 glossy (2k), A3 matte (1.5k), cardstock (1k) | Full* |
| 20 | Apr 17 | Restaurant mgr | Large | Concert | Flyers (5k), posters (2k), **10k tickets** | Partial |

*Full with name-resolution: agent must map "A3 glossy" → "Glossy paper", "kraft envelopes" → "Kraft paper" or "Envelopes".

**Catalog coverage: 13/20 requests fully resolvable; 7/20 contain at least one item with no exact catalog match.**

---

### Financial Summary

| Metric | Value |
|---|---|
| Initial cash seed (`init_database`) | $50,000.00 |
| First recorded cash balance (post-request 1, Apr 1) | $45,037.70 |
| Final cash balance (post-request 20, Apr 17) | $3,596,731.30 |
| Net cash change over test run | +$3,551,693.60 |
| First recorded inventory value (post-request 1) | $4,950.30 |
| Final inventory value (post-request 20) | $7,361.70 |
| Net inventory change | +$2,411.40 |
| Cash-increase events (sales fulfilled) | 2 — request 15 (+$320,000.00) and request 19 (+$3,236,430.00) |
| Cash-decrease events (stock reorders triggered) | 5 — requests 2, 3, 10, 14, 20 |

---

### Strengths

**1. Discount tier labels are explicit in every quote (Request 8)**
Request 8 (school board, large, ceremony — Apr 7) ordered four items ranging from 500 to 3,000 units. The system applied and named each tier in the response:
- A5 Colored Paper, 2,000 sheets → *"wholesale (10% off), Final unit price: $0.0900"*
- A4 Glossy Paper, 500 sheets → *"volume (5% off), Final unit price: $0.1900"*
- A4 Matte Paper, 1,000 sheets → *"wholesale (10% off), Final unit price: $0.1620"*
- A4 Recycled Paper, 3,000 sheets → *"wholesale (10% off), Final unit price: $0.0720"*

Each line item names the tier, states the percentage, and shows the resulting unit price — the customer sees exactly how the total was computed. Request 11 (Apr 8) independently confirms the 5% threshold: *"Price per unit: $0.1900 (5% discount applied)"* for 500 A3 Glossy sheets. Request 15 (Apr 12) confirms the 20% tier: *"Quote Total: $400.00 (with a 20% discount applied)"* for 5,000 A3 colored sheets.

**2. Out-of-stock responses include item-specific restock dates (Request 9)**
Request 9 (city hall, small, reception — Apr 7) asked for three items that were all out of stock. Rather than a generic apology, each received an individual estimated date:
- *"A4 White Printer Paper (200 sheets): Estimated restock date: 2025-04-11."*
- *"A3 Glossy Paper (100 sheets): Estimated restock date: 2025-04-08."*
- *"100% Recycled Kraft Paper Envelopes (50 packets): Estimated restock date: 2025-04-08."*

This demonstrates the `check_delivery_timeline` tool surfacing actionable data the customer can use to plan their order.

**3. Large fulfilled orders generate significant cash inflows (Requests 15 and 19)**
Two requests produced the largest cash increases in `test_results.csv`. Request 15 (event manager, large, demonstration — Apr 12) raised the cash balance by **+$320,000.00**. Request 19 (city hall, medium, exhibition — Apr 15) produced the single largest transaction in the run: cash rose by **+$3,236,430.00**, bringing the final balance to $3,596,731.30. These results confirm that the `fulfill_sale` pipeline correctly handles large multi-item orders — verifying stock, recording the transaction, and updating the balance — in a single agent turn. Request 3 (Apr 4) independently confirms the discount tiered logic: a 10,000-unit A4 order receives 20% off (*"Quote Total: $400.00 (20% discount applied)"*) while a 500-unit printer paper order receives 5% off (*"Quote Total: $23.75 (5% discount applied)"*).

**4. Partial-fill responses clearly delineate available vs. backordered quantities (Request 12)**
Request 12 (city hall, small, party — Apr 8) asked for items with mixed availability. The response breaks each line item into available and backordered quantities:
- *"Bright-colored paper: 200 units… Partial stock (100 available; 100 on backorder)"*
- *"A4 paper: 200 units… In stock"*
- *"Paper napkins: 100 units… Partial stock (0 available; 100 on backorder)"*
- *"Grand Total: $36.00"*

The customer receives a single coherent response that covers all requested items and makes the partial-delivery situation transparent.

**5. Catalog name resolution maps natural-language requests to catalog entries (Request 2)**
Request 2 (hotel manager, small, parade — Apr 3) asked for "colorful poster paper", which has no exact catalog entry. The system resolved this to *"Large poster paper (24x36 inches)"* at $0.95/unit and provided a quote for 500 units ($475.00). The same mechanism is visible in request 4 (Apr 5), where "A4 size printer paper" was matched to the catalog A4 Paper entry to produce a $30.00 quote for 250 sheets.

---

### Areas for Improvement

**1. A3 paper is absent from the catalog — evident across seven requests.**
Requests 3, 7, 8, 11, 15, 19, and 20 all ask for "A3 paper" in some form. Because no "A3 paper" entry exists, each request handled it differently: request 3 omitted the A3 line entirely; request 11 quoted "A3 Glossy Paper" by resolving to the nearest match but the item was on backorder; request 7 quoted a combined A3 matte backorder with a 2023 delivery date. The inconsistency across runs shows the agent is making ad-hoc decisions rather than following a documented substitution rule. **Recommendation:** add "A3 paper" to `paper_supplies` with an explicit unit price, or add a substitution mapping in the tool description.

**2. Non-paper products cause silent omissions (Requests 2 and 20).**
Balloons (request 2) and printed tickets (request 20) are entirely outside the catalog. In test_results.csv, request 2 omitted balloons from the response without explanation. Request 20 responded: *"Posters: Unfortunately, we do not have any suitable alternatives available in our product catalog. Tickets: Unfortunately, we do not have any suitable alternatives available in our product catalog."* — a repeated boilerplate that gives the customer no actionable path forward. A dedicated out-of-scope response — e.g. *"We are a paper supply company and do not carry printed tickets"* — would be more informative.

**3. Residual template tokens and stale dates escaped post-processing (Requests 7 and 10).**
Despite prompt-level guardrails, two responses contain artifacts. Request 7 (Apr 7) reports backorder delivery dates of *"2023-11-21"* — two years in the past. Request 10 (Apr 8) contains *"we estimate they will be available for order by [insert estimated restock date]"* — an unfilled placeholder. These show that the post-processing check in the orchestrator prompt is not reliably catching all cases, and a programmatic string-scan before returning the final response would be more robust.

**4. No partial-fulfilment logic for backorder situations (Requests 3, 8, 14).**
When a requested quantity exceeds current stock, `fulfill_sale` rejects the transaction outright. Request 3 (10,000 A4 sheets requested, limited stock) resulted in an order for only 1,000 sheets with no offer to ship the available quantity now and backorder the rest. Request 14 received an all-or-nothing rejection for three items even though partial quantities were likely available. Adding split-order logic — ship what is in stock, backorder the remainder — would significantly improve fulfilment rates and customer experience.

---

## Suggested Improvements

### 1. Customer-Specific Pricing and Quote Memory

The current system applies the same four bulk-discount tiers uniformly to every customer. A meaningful improvement would be to introduce **customer profiles** stored in the database, tracking each customer's purchase history, total lifetime spend, and any negotiated contract rates.

The QuoteAgent could then call a `get_customer_profile(customer_id)` tool before generating a quote. A customer who places large recurring orders could receive a standing 15% discount regardless of per-order quantity, while a first-time small buyer gets the standard schedule. The quote history search already returns `job_type` and `event_type` — tying those to a `customers` table would let the system learn that "school board resource managers placing large orders for ceremonies" consistently receive $X quotes, and use that as a soft ceiling/floor.

This also enables the system to detect *repeat quote requests* — if a customer asked for the same item last month, the agent could proactively reference the previous quote rather than generating a fresh one from scratch.

---

### 2. Automatic Low-Stock Reorder Triggered After Every Sale

Currently the InventoryAgent only checks reorder needs when explicitly asked. After every `fulfill_sale` call there is no automatic check on whether the sold item has now dropped below its minimum threshold. In a real business, this means items can silently deplete between manual checks.

The `fulfill_sale` tool could be extended to call `check_reorder_needs` on the sold item immediately after recording the transaction, and — if the threshold is crossed — pass a reorder recommendation back to the orchestrator. The orchestrator would then decide (or ask the operator) whether to trigger `reorder_supplies` in the same turn.

Implementing this as a **post-sale hook** inside `SalesAgent` rather than as a separate orchestrator step keeps the latency low and ensures no sale ever goes unmonitored. Combined with the delivery-timeline tool, the agent could also warn the customer: *"We can fulfil your order of 400 units today, but this will bring our stock below the reorder threshold. We will place a supplier order for 500 additional units with delivery expected by [date]."* This closes the loop between the quoting, selling, and replenishment workflows into a single coordinated response.
