# Requirements matrix

All 19 PDF pages were read. Paths starting services/, routers/, schemas/, models/ or providers/ are relative to backend/app. “Verified” is scoped to the stated evidence, not production readiness. Missing and partial roadmap features are deliberately not represented as complete.

| PDF page | Requirement / acceptance behavior | Source | Status | Priority | Evidence, changes and remaining acceptance criteria |
|---|---|---|---|---|---|
| 2–4 | 100 → 40 → 60 supplier recovery | services/planning.py; routers/allocations.py | implemented and verified | P1 | API end-to-end test preserves 40 and reassigns >=60; new evidence distinguishes proposed/delivered. |
| 4,9 | Best permitted partial basket | services/optimizer.py | implemented and verified | P1 | Insufficient stock / no offers / supplier cap tests; returns shortfall rather than false full coverage. |
| 5 | Voice and multilingual order capture | providers/sarvam.py; services/parsing.py | partial | P2 | Code-mixed text parser tested. Live speech adapter credentials/endpoint testing and frontend capture remain unverified. |
| 5,9 | Canonical SKUs, units, packs, brands | schemas/catalog.py; services/parsing.py | partial | P1 | Canonical unit mismatch rejected; pack arithmetic implemented. Brand-specific equivalence/approval and rich normalization not implemented. |
| 5 | Supplier price/stock/MOQ comparison | routers/catalog.py; frontend/src/pages/NewOrderPage.tsx | implemented but unverified | P1 | API and UI source present; browser comparison interactions blocked by Chromium installation. |
| 5,9 | Budget, price tolerance, reliability, supplier cap | services/optimizer.py; services/planning.py | implemented and verified | P0 | Landed budget, original recovery price ceiling and union supplier cap regression tests pass. |
| 5 | Preferred suppliers | services/optimizer.py | implemented but unverified | P2 | Small preference objective nudge retained; no dedicated behavioral regression. |
| 5 | Substitution and automatic/manual failover policy | models/orders.py; services/planning.py | partial | P1 | Product remains same; substitution flags lack brand equivalence semantics. Failover auto-proposes supply; merchant approve-before-replan setting absent. |
| 5,9–10 | Cheapest/fastest/reliable what-if profiles | services/optimizer.py | partial | P1 | Three profiles execute. Cheapest includes estimated delivery; fastest/reliable are weighted heuristics, not guaranteed time/reliability optima. |
| 5 | Stockout Radar with consumption/lead-time confidence | services/intelligence.py; frontend/src/pages/intelligence/StockoutRadarPage.tsx | partial | P2 | Existing tested reorder-cycle heuristic and insufficient-data handling; no POS on-hand, consumption or calibrated depletion model. |
| 5 | Priority Survival Mode | services/planning.py; routers/intelligence.py | partial | P1 | Budgeted priority-tier preview retained; supplier/capacity carry across tiers repaired. No full browser/pilot validation. |
| 5 | Cash-cycle planning | services/intelligence.py; routers/intelligence.py | partial | P2 | User-entered cash and history summaries tested; not bank balance or comprehensive upcoming-liabilities optimizer. |
| 5 | Margin leak detection | services/intelligence.py; frontend/src/pages/intelligence/MarginLeakPage.tsx | partial | P2 | Entered selling prices and historical purchase calculations tested; no invoice pack/variant parity proof. |
| 5 | Local price index | services/intelligence.py; frontend/src/pages/intelligence/PriceIndexPage.tsx | partial | P2 | Observed quotations/history MVP; rich comparable-brand/pack/geography sampling still needed. |
| 5,11 | Order Truth Engine | routers/reconciliation.py | partial | P1 | Invoice/receipt comparison and ownership tested. Weighted invoiced price, pack discrepancies and incremental receipts need richer model. |
| 5 | Procurement Autopilot | services/intelligence.py; frontend/src/pages/intelligence/AutopilotPage.tsx | partial | P2 | Repeat-order suggestions and missing-data tests present; no autonomous purchasing. |
| 5–6 | Dead-stock rescue exchange | routers/catalog.py; models/catalog.py | partial | P2 | Listings/offers exist; expiry/condition, custody, settlement and concurrent acceptance not fully validated. Not promoted as real marketplace. |
| 5–6 | Order status/control tower | routers/admin.py; frontend/src/pages/AdminDashboard.tsx | implemented and verified | P1 | Admin metrics and role tests pass; selected-plan counts repaired. Visual/browser QA blocked. |
| 6 | Inventory and prices with timestamp | routers/suppliers.py; models/catalog.py | partial | P1 | Timestamp and validation exist; 24h exclusion added. Operating hours, ready-time filtering and UI freshness detail incomplete. |
| 6 | Accept/modify/partial/reject supplier response | routers/allocations.py | implemented and verified | P1 | Recovery and confirmation workflow tests; stale-state and overquantity rejection added. |
| 6 | Commitment expiration | services/planning.py | partial | P1 | Lazy expiration on order reads retained; stale-copy loop fixed. No background scheduler or dedicated time-travel E2E. |
| 6 | Picking, dispatch and delivery | routers/allocations.py | partial | P1 | Dispatch/delivery tested; separate picking state and physical delivery proof absent. |
| 6 | Supplier fulfillment/delay/price reliability insights | services/reliability.py | partial | P1 | Sample-size scoring; excludes copied plans and unfulfilled confirmations. Recency decay, verified punctuality and price-stability dimensions absent. |
| 6 | Aggregated demand/surplus views | services/intelligence.py; routers/catalog.py | partial | P2 | Order-derived suggestions/listings exist; supplier forecast pipeline not implemented. |
| 6 | Notifications and audit timeline | models/orders.py; routers/admin.py | partial | P1 | Persistent supplier events and plan history; no SMS/push delivery or tamper-proof audit store. |
| 6 | Outage and post-confirmation shortfall | routers/scenarios.py; routers/allocations.py | partial | P1 | Shared replan path and state bounds; synthetic scenarios demo-only. Rich concurrent disruptions need broader tests. |
| 6 | Continuous reoptimization for price/routes/time | routers/scenarios.py | partial | P1 | Event-driven shortfall recovery works; delay recomputes displayed totals but does not reroute or enforce a deadline. |
| 6,9 | Landed cost and risk estimates | services/optimizer.py; services/geo.py | implemented and verified | P1 | Estimated supplier delivery included in budget; risk is a separate score, not a charge; no actual roads verified. |
| 6 | Supply-chain digital twin | routers/scenarios.py | partial | P2 | Demo-only mutation of demo orders for outages/partial stock/delay; not a fully isolated real-world simulator. |
| 7 | Regional collective procurement later | — | missing | P2 | Explicit roadmap: consent, aggregate capacity and payment responsibilities before implementation. |
| 7–8 | Commitment evidence and explanation | services/evidence.py; frontend/src/components/RecoveryEvidence.tsx | implemented and verified | P1 | Backend ownership and policy checks plus 3 frontend tests; confirmed/proposed/delivered and passive baseline displayed. |
| 8 | Comparisons to competitors | DIFFERENTIATION.md | implemented and verified | P2 | Primary pages researched; positioning hypothesis with no unsupported feature-absence claim. |
| 9 | Demand and units never silently mixed | services/optimizer.py | partial | P1 | Quantity per canonical product, no mixing litre into kg capacity. Unknown mass for non-kg goods leaves capacity unverified. |
| 9 | Stock freshness | services/planning.py | partial | P1 | Exclude marked-stale/>24h quotes; atomic confirmation stock check. Threshold is assumption; no external stock sync. |
| 9 | MOQ and offer pack rules | services/optimizer.py | implemented and verified | P1 | Integer pack counts, MOQ and finite stock; pack rounding can oversupply and is visible. |
| 9 | Reliability and hard delivery deadline | services/optimizer.py | partial | P1 | Minimum score enforced; no requested deadline field or hard deadline constraint. |
| 9 | Supplier/day delivery capacity | services/optimizer.py | partial | P1 | Per-basket kg cap only; no cross-order/day fleet scheduling. |
| 10 | AI never controls money/stock arithmetic | services/optimizer.py; providers/* | implemented and verified | P0 | Deterministic arithmetic and state; parser does not confirm supplier or pay. Non-demo payments disabled. |
| 10–11 | React/FastAPI/SQLAlchemy/Alembic/OR-Tools stack | frontend/package.json; backend/requirements.lock.txt | implemented and verified | P0 | Registry installs, frontend build, backend tests and SQLite migrations pass. |
| 11 | Sarvam STT/optional LLM | providers/sarvam.py | blocked by an external dependency | P2 | No credentials/live endpoint verification; deterministic text path remains runnable. |
| 11–12 | Google Routes | providers/routes.py | blocked by an external dependency | P2 | Adapter source present, not integrated as verified planning data; estimates clearly used. |
| 11–12 | Paytm sandbox | providers/payments.py; routers/payments.py | blocked by an external dependency | P0 | Signature/status contract unverified. Callback/non-demo payment disabled; simulation works and moves no money. |
| 11–12 | Supabase/PostgreSQL live auth and RLS | security.py; database.py | blocked by an external dependency | P0 | Issuer/audience guards added; no connected Supabase/RLS deployment or PostgreSQL runtime verification. |
| 11 | API boundary examples | routers/orders.py; routers/allocations.py | implemented and verified | P1 | Equivalent routes /plan, /select-plan, allocation-specific mutations; not literal PDF example paths. |
| 11 | 21-table schema claim | models/*; alembic/* | implemented but unverified | P2 | PDF count predates added pricing/surplus tables. Exact count recorded by verification script; do not repeat historical 21 claim. |
| 12 | Role and tenant isolation | deps.py; routers/* | implemented and verified | P0 | Targeted merchant/admin/supplier/receipt/invoice regressions; not a comprehensive penetration test. |
| 12 | Upload limits, CSRF/session/CORS/rate limits | main.py; security.py; frontend/src/lib/api.ts | partial | P0 | CORS and IP rate middleware; bearer localStorage requires production review; no safe production file upload workflow claimed. |
| 12 | Secrets excluded | .env.example; archive script | implemented and verified | P0 | Final file scan and exclusion check; public demo credentials explicitly labeled. |
| 12 | Webhook signature and durable idempotency | routers/payments.py; routers/allocations.py | partial | P0 | Unsigned callbacks disabled; confirmation retries safe via state guard. Durable request replay keys missing. |
| 12 | Privacy, deletion, backup, incident policy | ARCHITECTURE.md | missing | P0 | Operational rollout gate; no real merchant data deployed. |
| 12–13 | Current admin metrics failure | routers/admin.py; tests/test_repairs.py | implemented and verified | P0 | Current authenticated endpoint passes. Prior screenshot error not reproduced; do not invent a root cause. |
| 13 | Reported 22 tests | tests/* | implemented and verified | P1 | Original22 rerun; expanded suite/test report supersedes historical count. |
| 13 | Intelligence explicitly not built snapshot | services/intelligence.py; frontend/src/pages/intelligence/* | partial | P2 | Snapshot stale: seven modules already present. Each mapped separately above; no claim full PDF specifications met. |
| 13,17 | Docker/CI/cloud deployment | docker-compose.yml; .github/workflows/verify.yml | partial | P1 | CI added; Docker CLI unavailable locally; no Cloud Run/Pages deployment attempted. |
| 14 | Three-minute reliable demo | DEMO_SCRIPT.md; tests/test_api_workflow.py | partial | P1 | API journey verified, script supplied; no recorded backup video and browser visual check blocked. |
| 15 | Baselines and performance distributions | scripts/benchmark.py; BENCHMARK_REPORT.md | partial | P1 | Passive no-recovery comparison + latency distributions. Nearest/single/manual field baselines and pilot outcomes remain future work. |
| 15 | Claimed cost/time/revenue improvement targets | IMPACT_MODEL.md | implemented and verified | P0 | Clearly assumptions; no fabricated achieved savings, users or revenue. |
| 16 | Pilot/GTM/revenue validation | IMPACT_MODEL.md | partial | P2 | Staged plan; no recruitment, contracts or willingness-to-pay evidence. |
| 17 | Responsive/mobile accessibility | frontend/src/components/* | implemented but unverified | P2 | Responsive layout and status controls; device/browser visual QA still blocked. |
| 18 | Trustworthy uncertainty and governance | ARCHITECTURE.md; REQUIREMENTS_MATRIX.md | partial | P0 | Honest gaps, sample sizes and proposed/delivered distinction; production privacy/security/operations gates remain. |
| 19 | Product positioning and next actions | README.md; DEMO_SCRIPT.md | implemented and verified | P2 | Working local recovery positioning; no claim of guaranteed physical fulfillment or global deployment. |
