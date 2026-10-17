> Historical design notes. Current implementation/status is in the root-level reports. Do not treat this earlier document as fresh verification.

# Architecture

## Overview

```
┌─────────────┐      HTTPS/JSON       ┌──────────────────┐      SQL       ┌──────────────┐
│  React SPA  │ ───────────────────▶  │  FastAPI backend │ ─────────────▶ │  PostgreSQL   │
│ (Vite, TS)  │ ◀───────────────────  │   (Python 3.11+)  │ ◀───────────── │  (Supabase)   │
└─────────────┘                       └──────────────────┘                └──────────────┘
                                             │   │   │
                                             │   │   └── OR-Tools CP-SAT (in-process, pure function)
                                             │   └────── Provider adapters (Sarvam / Paytm / Google Routes)
                                             └────────── Supabase/local JWT verification
```

The backend is a single FastAPI service. There is no separate optimizer microservice --
OR-Tools CP-SAT runs in-process (`app/services/optimizer.py`) because the problem size
(a handful of order items, a few dozen candidate supplier offers) solves in well under a
second, and a network hop to a dedicated service would add latency and operational
complexity for no benefit at this scale.

## Request flow for the core recovery scenario

1. `POST /api/orders` — merchant creates a basket (`OrderItem` rows). If free text was
   supplied, `app/services/parsing.py` (deterministic lexicon/regex, no LLM) extracts
   items first; low-confidence parses set `requires_confirmation=True` and block planning
   until the merchant confirms.
2. `POST /api/orders/{id}/plan` — `app/services/planning.py::create_initial_plans` gathers
   eligible `SupplierInventory` offers per product (`gather_offers`, which also resolves
   live `SupplierReliabilityStat` and a haversine distance estimate), then calls
   `optimizer.solve_allocation()` three times (cheapest / fastest / most_reliable) and
   persists each result as an `AllocationPlan` + `Allocation` rows.
3. `POST /api/orders/{id}/select-plan` — merchant picks one plan; its allocations become
   the order's live state (status moves to `awaiting_confirmation`); sibling plans'
   proposals are marked `superseded`.
4. `POST /api/allocations/{id}/confirm` (supplier) — if the confirmed quantity is less
   than what was proposed, the allocation is flagged `short_supply` and
   `planning.replan_after_event()` runs automatically: it computes the outstanding
   quantity per order item (requested minus everything already secured), excludes every
   offer that has failed anywhere in this order's history, and re-solves the optimizer for
   just the gap. The result is a brand-new `AllocationPlan` that carries forward every
   already-confirmed/fulfilled line unchanged and adds new `proposed` lines for the
   shortfall. Nothing is mutated in place -- the full recovery history is auditable via
   `order.plans`.
5. The same `replan_after_event()` path is used for `reject`, `report-shortfall` (a
   previously-confirmed allocation later fails), the lazy `expire_overdue_allocations()`
   check, and the Digital Twin `/api/scenarios/disrupt` endpoint -- there is exactly one
   failover code path, not a parallel "demo" one.
6. `dispatch` / `deliver` progress the allocation to `fulfilled`; the order status is
   derived by `planning.sync_order_status()` from the live allocation states.
7. `/api/orders/{id}/reconciliation` compares `OrderItem.requested_qty_base_unit` against
   `InvoiceItem` rows and `ReceiptRecord` rows and flags price/quantity discrepancies.

## Why CP-SAT instead of a heuristic

Google OR-Tools CP-SAT is a constraint-programming SAT solver that handles the mixed
integer structure here cleanly: integer pack counts, boolean "supplier used" indicators
tied to MOQ and max-supplier-count constraints, and a soft shortfall variable that lets
the model stay feasible (and return the *best permitted partial basket*) even when the
full basket can't be sourced, instead of hard-failing. A greedy heuristic could not
simultaneously respect MOQ-linked boolean constraints, a global max-suppliers cap, and
three different objective weightings without becoming its own bespoke solver.

All quantities and prices are scaled to integers before being handed to CP-SAT (see the
module docstring in `optimizer.py`); the scaled objective value is internal only --
every cost/time figure shown to a user is recomputed from the chosen integer solution
using plain floating-point arithmetic, so there is no reporting drift from the scaling.

## Data model

See `backend/alembic/versions/*_initial_schema.py` for the authoritative schema (21
tables). Key relationships:

- `User` → `MerchantProfile` / `SupplierProfile` (1:1, role-gated)
- `Product` ← `ProductAlias` (N:1) -- the lexicon the deterministic parser matches against
- `SupplierInventory` -- one row per (supplier, product, brand, pack size) offer
- `Order` → `OrderItem` (1:N) → `AllocationPlan` (1:N, one per objective profile per
  planning/replanning event) → `Allocation` (1:N) → `SupplierEvent` (1:N, append-only log)
- `SupplierReliabilityStat` -- recomputed from `Allocation.status` history, not stored as
  a fabricated static number (see `app/services/reliability.py`)
- `Invoice`/`InvoiceItem`, `ReceiptRecord` -- inputs to reconciliation
- `Payment`, `Notification`, `AuditEvent`, `SurplusListing`, `ScenarioSimulation` --
  supporting tables for payments, in-app notifications (schema only -- UI shows plan/
  order state directly rather than a separate notification feed), audit trail, the
  dead-stock exchange, and digital-twin scenario storage (the live `/api/scenarios/disrupt`
  endpoint reuses the replan engine directly rather than reading from this table; the
  table exists for saving/naming reusable scenario configs, which is not yet wired to UI)

## Known architectural limitations (see BUILD_STATUS.md for the full list)

- **Substitution** currently means "allow the optimizer to split an item across multiple
  suppliers/brands of the *same normalized product*". Cross-product substitution (e.g.
  jaggery standing in for sugar) is not modeled; it would need a `ProductSubstitute`
  table with conversion ratios and is left as documented future work rather than
  half-implemented.
- **Delivery time windows** are not scheduled explicitly in CP-SAT (no date/time
  decision variables); `estimated_delivery_hours` is a post-hoc distance-based estimate
  used to rank the "fastest" objective. A full scheduling model was judged out of scope
  for the MVP's demo-grade routing.
- Real-time inventory sync, WhatsApp/SMS notifications, and the forecasting-heavy
  modules (Stockout Radar prediction, Survival Mode optimizer, Cash-Cycle planner,
  Margin Leak detector, Local Price Index) are not implemented -- see BUILD_STATUS.md.
