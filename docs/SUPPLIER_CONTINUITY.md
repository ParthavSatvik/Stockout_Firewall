# Supplier Continuity Network

Helps wholesalers make promises they can keep, and helps merchants recover when those
promises fall short. Everything below is computed by the backend from recorded data;
nothing is a trained model, and no client-side number ever confirms a commitment.

## 1. Promise Intelligence Ledger (PromiseGuard)

Per inventory row, in the product's base unit (`app/services/promise.py`):

| Term | Definition |
|---|---|
| uncommitted | `supplier_inventory.stock_qty_base_unit` — confirmations deduct from it with an atomic conditional `UPDATE` |
| committed | confirmed qty on live commitments still in the warehouse (stage reserved / picking / ready) on each order's selected plan |
| on hand | uncommitted + committed (derived; a commitment is never counted twice) |
| safety stock | `supplier_inventory.safety_stock_base_unit`; never offered to merchants |
| **free to promise** | `max(0, on_hand − committed − safety_stock)` |
| requested | open requests awaiting the supplier's decision — **not** reserved |
| in transit | dispatched, not yet delivered |

* A stock count (`POST /api/suppliers/me/inventory/{id}/stock-count`, or saving a listing) is a
  *physical* count: live commitments are subtracted, so re-entering 80 kg after promising 50 kg
  leaves 30 kg uncommitted, not 80. A count below live commitments is recorded as **commitment drift**.
* Freshness comes from the last stock count. Listings not counted in 24 h are excluded from new
  merchant plans (the planner's existing 24 h cutoff now uses the count timestamp).

**Pre-commitment guard** (`GET /api/allocations/{id}/guard?ready_by=`): `SAFE_TO_COMMIT`,
`PARTIAL_COMMITMENT_RECOMMENDED` (with the maximum feasible quantity), `DELIVERY_WINDOW_AT_RISK`
(operating hours or daily kg capacity), `COMMITMENT_CONFLICT` (stock exists but is all promised or
held as safety), `NO_FREE_STOCK`, `INSUFFICIENT_DATA` (stale count or SKU/unit mismatch). Each
check is returned with its numbers, plus the pack breakdown, revenue kept/forgone and a suggested
ready-by inside hours and capacity. Margin is not shown because purchase cost is not recorded.

Confirm is enforced server-side with the same rule; dipping into safety stock needs
`override_safety_stock` **and** a written reason, both written to the ledger. Ready-by must be in the future.

**Lifecycle**: quote → reserved → picking → ready → dispatched → delivered → reconciled
(`allocations.fulfillment_stage`; reconciled = a merchant receipt exists). Stage changes are
forward-only and idempotent (`POST /api/allocations/{id}/stage`, `/dispatch`, `/deliver`).

**Drift / risk** for each live commitment: rule-based points, each listed with its timestamp —
stale stock (+2), last count below commitments (+3), ready-by passed (+3), due ≤ 2 h and not picking
(+2), due ≤ 6 h (+1), daily capacity exceeded (+2) / above 85 % (+1), ≥ 20 % broken-commitment history
(+1). 0 on track · 1–2 watch · 3–4 at risk · ≥ 5 critical. "Confidence" describes evidence
completeness (fresh count, recorded ready-by), not model accuracy.

## 2. Supply Relay Protocol

`app/services/relay.py`. Statuses are strings in `supply_relays` / `supply_relay_invites`.

1. **Disclose** — origin supplier keeps what it can (`POST /api/allocations/{id}/relay`, `commit_qty`
   may be 0). On a quote this is recorded as an up-front partial; on an accepted commitment as a
   post-commitment disruption. The committed part is reserved atomically.
2. **Outstanding** is computed with the same function the replanner uses.
3. **Eligibility** for every other listing of the same canonical product: active supplier, fresh
   count, free to promise ≥ min(MOQ, outstanding), listed price ≤ the merchant's original price
   ceiling, same brand if the merchant disallowed substitution, reliability ≥ the merchant's floor,
   not an offer that already failed on this order. Ineligible partners are listed with reasons
   (`GET /api/relays/{id}/candidates`, origin only).
4. **Respond** — partners accept / modify (qty, price, ready-by) / decline
   (`POST /api/relays/invites/{id}/respond`). A quote cannot exceed the partner's free to promise or
   the outstanding quantity. Nothing is reserved.
5. **Preview** (`GET /api/orders/{id}/relays`) runs the same OR-Tools optimizer and the same
   policy builder as automatic recovery: remaining budget, original price ceiling, minimum
   reliability, supplier limit and remaining capacity. Quotes above the ceiling are shown and excluded.
6. **Approve** (`POST /api/orders/{id}/relays/{rid}/approve`) — merchant only, compare-and-set so it
   resolves once. Persists through `replan_after_event` (audit history kept) and reserves each selected
   partner's stock atomically; a line whose stock vanished stays a normal pending request.
7. **Decline / expiry / no eligible partner** fall back to the standard open-market recovery, so the
   merchant is never left waiting. Any other replan on the order supersedes an open relay so the gap
   is never sourced twice; only one relay may be open per order.
8. Partners never see the merchant's identity, other partners' quotes or other order lines.

## 3. Commitment Copilot, dispatch board, Trust Passport

* `GET /api/suppliers/me/copilot` — prioritised queue (requests awaiting decision, relay invites,
  outgoing relays, at-risk commitments, missing delivery updates, stale stock, drift,
  oversubscription, capacity overload). Each item: why, consequence if ignored, deadline and a link.
  Also answers: at risk of missing dispatch, short for new commitments, safe partial fills (with
  revenue), nearby demand, best next action. No language model is involved.
* `GET /api/suppliers/me/dispatch-board` — commitments by stage and ready-by with today's load vs capacity.
* `GET /api/suppliers/me/passport` and `GET /api/network/suppliers/{id}/passport` — outcome mix
  (accepted in full / partial disclosed up front / declined up front / broken after commitment /
  left to expire), fill rate, kept rate, early-disclosure rate, silent-expiry rate, on-time dispatch
  and delivery, invoice price consistency, receipt quantity accuracy, median response time, stock
  freshness. Every rate shows numerator, denominator and number of observations; fewer than 5
  observations is published as **INSUFFICIENT_HISTORY**. No composite score; the planner's existing
  reliability score is shown, not altered.
* `GET /api/suppliers/me/ledger-events`, `GET /api/orders/{id}/commitment-ledger` — the append-only
  `commitment_ledger` (actor, role, from → to state, quantity, reason, payload).

## 4. Demo (repeatable after `python -m app.seed.seed_data`)

All passwords `demo1234`. Seeded scenario rows are labelled `[demo seed]`.

**Moment 1 — prevention.** Log in as `anand@example.com` → Copilot shows "Wheat Atta: 40 requested
vs 20 free" → Requests · PromiseGuard: 80 on hand − 50 committed − 10 safety = **20 kg free**,
status *Partial commitment recommended*. Typing 40 explains it would break other commitments
(at most 30 even using safety stock); the server refuses it too (409). Options offered: commit
20 + relay 20, or commit 20 and let the planner source the rest, or decline with a reason.

**Moment 2 — recovery.**
1. `merchant1@example.com`: New Order → 100 kg Rice, minimum reliability 0.3, tolerance 20 %,
   budget ₹6,000 → generate plans → select *Cheapest* (NewCo, 100 kg).
2. `newco@example.com`: Promise Ledger → Rice → **Count** → 40 (note "60 kg water damaged").
   Requests now shows *Partial commitment recommended: 40 of 100*. Click **Commit 40 + relay 60 kg**.
3. `balaji@example.com` (and/or `lakshmi@example.com`): Supply Relay → Requests to me → quote 60 kg at ₹39.
4. `merchant1@example.com`: open the order → Supply relay card shows the preview
   (₹1,671 → ₹4,185, 0 kg uncovered) → **Approve relay plan**. Order becomes *confirmed*; Recovery
   evidence shows 100 kg confirmed; the Commitment trail lists every step.
5. Honest shortfall variant: repeat with max suppliers 1 — the preview shows 60 kg uncovered and
   approval is disabled; "Use open-market recovery instead" also leaves 60 kg uncovered and the
   order is not marked confirmed.

## 5. Limits and unverified parts

* Delivery feasibility uses the declared daily kg capacity and operating hours (IST) plus haversine
  travel estimates; there is no vehicle or route scheduling. Litre products are not capacity-checked.
* Partner quotes must be whole base units; a partner's quote waives its own listing MOQ.
* Merchant identity is withheld from partners; merchants see partner names and passports.
* Notifications are stored in-app only (no SMS/WhatsApp).
* The migration is additive and passed `alembic upgrade/downgrade/check` on SQLite; it has not been
  run against PostgreSQL locally (CI runs that job).
