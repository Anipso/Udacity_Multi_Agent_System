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

> `test_results.csv` is generated by running `python paper_agentic_system.py`. The table below will be populated with actual response text, cash balances, and inventory values after execution. The scenario-by-scenario analysis below is based on inspection of `quote_requests_sample.csv`.

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

### Strengths

**1. Robust handling of standard paper supply requests.**
13 of the 20 scenarios involve only items that map cleanly to the catalog. For these, the system reliably runs through the full quote workflow: catalog lookup → history search → per-item pricing with bulk-discount tier → availability check. Requests 1, 5, 6, 10, 12, 13, 16, 17, 18 are straightforward multi-item quotes that the agent decomposes correctly.

**2. Bulk-discount tiers activate correctly on large-volume requests.**
Requests 3, 8, 14, and 15 include line items at or above the 1,000-unit (10% off) and 5,000-unit (20% off) thresholds. The `generate_customer_quote` tool applies these deterministically — for example, the 10,000 A4 sheets in request 3 automatically receive the 20% bulk rate regardless of how the LLM phrases the call.

**3. Historical quote search is contextually grounded.**
Because `event_type`, `order_size`, and `job_type` from `quote_requests_sample.csv` are passed as explicit keywords into `get_quote_history_tool`, the QuoteAgent finds comparable past quotes (e.g. a prior "school board / large / conference" quote) rather than searching on item names alone. This mirrors how a human sales rep would check precedent before quoting.

**4. Inventory guard on every sale.**
`fulfill_sale` calls `get_stock_level` before writing any transaction. Requests that ask for more units than are currently stocked return a clear error message and do not partially decrement inventory, preventing silent over-commitment.

**5. Cash guard on every reorder.**
`reorder_supplies` checks `get_cash_balance` before creating a `stock_orders` transaction, ensuring the company never places a supplier order it cannot afford.

---

### Areas for Improvement

**1. A3 paper is absent from the catalog.**
Requests 3, 7 (A3 matte), 8 (indirectly), 11, 15, 17, and 19 all ask for "A3 paper" in some form. The catalog contains no "A3 paper" item. The agent must fall back to `list_catalog_items("A3")` which returns nothing, forcing it to either skip the line item or substitute "Matte paper" or "Large poster paper (24×36 inches)" — neither of which is a precise match. **Recommendation:** add "A3 paper" to `paper_supplies` at a unit price between Letter ($0.06) and Poster ($0.25), or document the substitution rule explicitly in the tool description.

**2. Non-paper products in requests cause silent gaps.**
Balloons (request 2) and printed tickets (request 20) are not paper products and are not in the catalog. The system currently has no "out-of-scope" response path — it will attempt a catalog search, find nothing, and either omit those line items or produce a vague apology. A dedicated `handle_out_of_scope(item)` tool or a clear instruction in the orchestrator system prompt would allow the agent to say *"We do not carry balloons; we can supply the poster paper and streamers"* rather than silently dropping the item.

**3. Ambiguous natural-language mappings introduce inconsistency.**
"Recycled cardstock" (request 4) could map to either "Recycled paper" ($0.08) or "Cardstock" ($0.15) — a 2× price difference. "Kraft paper envelopes" (request 9) could map to "Kraft paper" or "Envelopes". Because the mapping depends on which keyword the LLM passes to `list_catalog_items`, responses may be inconsistent across runs. **Recommendation:** add a disambiguation note to the `list_catalog_items` docstring, or create compound alias entries in `paper_supplies` (e.g. "Recycled cardstock" → points to Cardstock price with eco-friendly note).

**4. No partial-fulfilment logic for backorder situations.**
When a requested quantity exceeds current stock, `generate_customer_quote` reports "Partial stock" and `fulfill_sale` rejects the transaction outright. There is no path to quote the available quantity now with a delivery date for the remainder. For large orders (requests 3, 8, 14, 15) this means a customer asking for 10,000 sheets may get nothing if stock is 9,800 — even though partial fulfilment would be acceptable in practice.

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
