# Rebuild changes

- Align dependency manifest with the supplied working lock; preserve package versions verified by registry install.
- Block admin self-registration; gate local auth and simulated scenarios; verify JWT issuer/audience; activate rate limiting.
- Enforce finite input bounds, canonical products/units and explicit basket review.
- Include delivery in budget; aggregate offer stock; use staged shortfall minimization; retain recovery budget, supplier count and price ceiling.
- Add inventory source FK migration and atomic confirmation; reject superseded mutations and overconfirmation; deduplicate dispatch.
- Repair receipt/invoice ownership and truthful order completion/reliability scoring.
- Disable unverified non-demo payment/callback paths.
- Add recovery evidence API/UI with passive baseline, confirmed/proposed/delivered distinctions and policy checks.
- Retain existing intelligence modules; enforce survival tier supplier/capacity budgets; document their heuristic limits.
- Safe demo seed guard; FK enforcement; test concurrency/rollback; lazy frontend pages; frontend component tests; CI workflow and benchmark script.
- Add audit, requirements, architecture, differentiation, impact, benchmark, test and demo documentation.
- Correct environment example to use SQLite by default and the installed psycopg v3 driver for optional PostgreSQL; align existing CI with locked dependencies and current runtime versions.
- Return all API timestamps as timezone-aware UTC (SQLite drops tzinfo, which made browsers outside UTC show times shifted by their offset, e.g. a new order as "6h ago" in IST); add regression test.
- Supplier Continuity Network: PromiseGuard free-to-promise ledger with safety stock, stock counts, freshness and commitment drift; guard-enforced confirmation with recorded safety-stock overrides and future ready-by; picking/ready fulfilment stages; Supply Relay Protocol (partner eligibility, quotes, merchant preview/approval through the existing optimizer and replan, atomic partner reservation, fallback to open-market recovery); Commitment Copilot queue; dispatch board; Trust Passport with sample-size gating; append-only commitment ledger shared with merchants. Additive migration c440fc692d6e.
- Fix: saving a listing no longer double-counts stock already committed; supplier ready-by is chosen instead of hardcoded to +2 days; litre products can be listed (pack unit was hardcoded to kg); order status now updates after a replan (stale `order.plans` cache); existing tests no longer hardcode dates that would become past ready-by times.
- Live integrations: Supabase JWKS auth (role from local DB), Sarvam voice orders, Razorpay Checkout with server-side signature/webhook verification and idempotency (no simulated path once configured; live keys gated), Twilio WhatsApp outbound alerts and signature-verified inbound text/voice ordering, OpenFreeMap map with OSRM road routes. Only OpenFreeMap and OSRM were verified live; the others need credentials (see BUILD_STATUS.md). Migration b5477427b4db.
