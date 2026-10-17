# Audit report

Source: supplied ZIP and all 19 pages of the product brief. No AGENTS.md was present. The PDF's implementation snapshot is historical: the ZIP already contains seven intelligence pages and their backend services.

| Priority | Confirmed defect / evidence | Repair / acceptance |
|---|---|---|
| P0 | Clean `pip install -r requirements-dev.txt` fails: pydantic-settings 2.16.0 requires python-dotenv >=1.2.2, manifest pinned 1.2.1. Lock and manifest also disagree on multipart. | Align direct pins to existing lock (dotenv 1.2.4, multipart .32); registry downloads succeeded; pip check clean. No blanket upgrades. |
| P0 | POST auth/register with role=admin returned 201 on original source. | Reject admin self-registration, disable local login/register outside demo, require trusted issuer/audience for Supabase. Regression now 403. |
| P0 | 25 units at INR40 with budget1000 yielded product cost1000 PLUS delivery. | Include per-supplier delivery in integer budget constraints; test total_cost <= cap. |
| P0 | Original optimizer reused each offer's stock for repeated product lines. | Aggregate stock by offer; reject duplicate products at API boundary. Original regression fails, repaired test passes. |
| P0 | Confirmation did not consume inventory. Concurrent confirmations could oversell. | Source-offer FK migration; conditional SQL decrement in transaction; concurrent same-stock test permits one confirmation, rejects the other, stock stays zero. |
| P0 | Recovery used entire order budget and full max_suppliers again. | Deduct carried product/delivery costs; enforce union of carried/new suppliers; preserve initial price ceiling. Tests cover tight budget, supplier cap and unavailable supply. |
| P0 | Receipt accepted another order's allocation (201 on original). Invoice authorization query omitted order_id. | Validate order/product/selected-plan ownership; invoice supplier must belong to that specific selected order. |
| P1 | Negative budget, invalid reliability and supplier limits accepted (201 on original). Unknown products could cause serialization failures. | Finite bounded request validation; canonical product existence and unit checks. |
| P1 | Old copied allocations could be delivered or disrupted after replan. Overconfirmation was silently capped. | Selected-plan checks on all supplier mutations, explicit overquantity 422, terminal retry 409. |
| P1 | Incomplete plans could become fulfilled when all surviving lines delivered. | Fulfilled requires a feasible plan; unsuccessful recovery stays infeasible. |
| P1 | Reliability counted copied historical plans and confirmations as successful deliveries. | Score selected-plan terminal observations; confirmations aren't delivery evidence; no invented on-time count. |
| P1 | Payment callback could resolve simulated records as success without signature authentication. | Callback and non-demo payment routes return 503 until provider verification is implemented. No real payment attempted. |
| P1 | Seed reset omitted dependent financial/intelligence rows; repeated reset could fail under FK enforcement. | Reverse metadata dependency-order deletion, local-demo guard; SQLite FK checks enabled. |
| P1 | Low-confidence draft blocked planning with no explicit approval route. | Owner-scoped confirm-items endpoint and review button. |
| P2 | All pages, including charts, downloaded with login. | Lazy route imports; entry JS reduced from ~787 KB to ~282 KB uncompressed; total application assets are not reduced by that amount. |

Reproduction: run `tests/test_repairs.py`; fixture payloads document exact requests. An isolated copy of original source was tested with selected new regressions: admin escalation, four invalid-policy cases, budget, duplicate stock, and cross-order receipt all failed their expected safety assertions. The original invoice regression was blocked earlier by an unrelated KeyError in plan creation in that run; its missing ownership filter was confirmed by code inspection and the repaired endpoint is tested. Original 22 tests passed after dependency installation from the lock, demonstrating their coverage gap.

## Unresolved / not reproduced
Admin metrics screenshot error: authenticated metrics regression passes; no reproducible original stack trace, therefore no invented root cause. Frontend has three pre-existing Fast Refresh warnings. Browser E2E blocked by invalid Chromium download; Docker unavailable. PostgreSQL/Supabase production semantics, provider integrations, multi-region deployment and real user outcomes remain unverified. Invoice unit prices still require richer pack-level accounting; see matrix. Cancellation, durable client idempotency keys, distributed worker retries and stock-release/reconciliation after cancellations remain roadmap work. Retries of state-changing confirmations are rejected without duplicate stock mutation, not replayed as a cached success.
