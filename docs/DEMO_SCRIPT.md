> Historical design notes. Current implementation/status is in the root-level reports. Do not treat this earlier document as fresh verification.

# Demo script: the core recovery scenario

This is the exact sequence verified working in this session (backend via pytest API
integration test, frontend via an interactive browser walkthrough). It demonstrates the
required flow: merchant order → optimization → supplier confirmation → supplier failure
→ automatic reallocation → recalculated cost/delivery.

## Setup

```
cd backend && source .venv/Scripts/activate
alembic upgrade head
python -m app.seed.seed_data          # idempotent; prints demo credentials
uvicorn app.main:app --reload --port 8000

# second terminal
cd frontend
npm run dev                            # http://localhost:5173
```

All demo accounts use password `demo1234`.

## Walkthrough

1. **Log in as `merchant1@example.com`** (Ganesh Kirana Store, Bengaluru).
2. Click **+ New Order**. Paste a Kannada/English code-mixed order:
   `nanage 100 kg akki mattu 20 kg sakkare beku`
   Click **Parse** — the deterministic lexicon parser (no LLM) extracts "100 kg → Rice"
   and "20 kg → Sugar", each with a confidence score. Accept the basket.
3. Set rules if desired (price tolerance, min reliability, max suppliers) and click
   **Create order & compare plans**.
4. On the order page, click **Generate 3 plans**. OR-Tools CP-SAT returns three feasible
   allocations (Cheapest / Fastest / Most reliable) with live product cost, delivery
   cost, risk penalty, and estimated delivery hours -- all computed by the backend, not
   hardcoded.
5. Click **Select this plan** on Cheapest. The order moves to `awaiting_confirmation`.
   Note which supplier was allocated the full 100kg of rice (in the seeded data this is
   usually the cheapest offer, "NewCo Supplies").
6. **Log out, log in as that supplier** (e.g. `newco@example.com`). Under **Incoming
   orders**, change the confirm quantity from 100 to **40** and click **Confirm**.
7. The allocation becomes `short_supply` (40kg kept, 60kg now missing). The replan engine
   fires automatically -- no separate button, no page reload needed.
8. **Log back in as the merchant** and open the order. It now shows:
   - the original 40kg line, still `short_supply`, preserved
   - new `proposed` lines on *different* suppliers covering the remaining 60kg (split
     across whichever eligible suppliers the optimizer picked, respecting price
     tolerance, reliability, MOQ and delivery capacity)
   - a recalculated total cost and delivery estimate
   - the failed supplier is excluded from being re-offered the same product again in
     this order
9. Log in as each of the new suppliers and **Confirm** their allocations; order status
   becomes `confirmed`.
10. As each supplier, click **Mark dispatched** then **Mark delivered** (including the
    original 40kg short-supply line). Order status becomes `fulfilled`.
11. As the merchant, click **Pay now** -- a simulated payment resolves immediately
    (labelled `Simulated` in the UI; never claimed as a real transaction).
12. Still on the order page, use the **Order Truth Engine** section: record a received
    quantity different from what was ordered to see discrepancy flags appear (this part
    of the flow is also covered by `test_reconciliation_flags_missing_goods_and_price_discrepancy`).

## Second disruption (Digital Twin)

On any order with a `confirmed` or `proposed` allocation, use the **Digital Twin** column
buttons ("Simulate outage" / "Simulate 50% stock") to force a second disruption and watch
the same replan engine recover again, with a before/after cost and delivery-time narrative
shown inline.

## Infeasible case

Create an order requesting an unrealistically large quantity (e.g. 100,000 kg of Rice).
Generate plans: all three come back `is_feasible: false` with explicit reasons (e.g.
"insufficient aggregate stock") and still show the best partial basket actually available
-- never a fabricated full allocation.
