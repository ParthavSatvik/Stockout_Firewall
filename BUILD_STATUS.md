> The 2026-10-17 sections below are current. Older sections further down are the historical handoff.

# BUILD_STATUS

## 2026-10-17 — Live integrations: what is verified, simulated or blocked

**No credentials were available in this session.** The keys referred to as "supplied in a previous
message" are not in this workspace, and pasted keys must be treated as compromised anyway: rotate
them in the Supabase, Twilio and Sarvam dashboards, then put the replacements in `backend/.env` and
`frontend/.env` (see `.env.example`). Nothing secret is hardcoded, and only public values
(`VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_KEY`, the Razorpay key id) ever reach the browser.

| Integration | What is built | Verified how | Live status |
|---|---|---|---|
| **OpenFreeMap map** | MapLibre GL 6.14 (patched; 5.x had a critical XSS advisory) + `liberty` style, lazy-loaded on the order page; supplier and merchant markers, road geometry | Rendered in the browser against the real tile service | **Live, tested** (no key needed) |
| **OSRM road routing** | `GET /api/orders/{id}/routes`; real road distance, duration and geometry per supplier, cached; falls back to a dashed, labelled straight-line estimate | Real request: 14.44 km / 18.8 min Bengaluru route; shown on the map | **Live, tested** against the public OSRM demo server, which is for light non-commercial use: point `OSRM_BASE_URL` at your own or a hosted OSRM for production. Plan costs still use the labelled planner estimate. |
| **Sarvam speech-to-text** | Browser recording (≤25 s) → `POST /api/orders/transcribe` → Sarvam `saaras:v4` → the same deterministic parser; WhatsApp voice notes use the same path | Request shape checked against docs.sarvam.ai; endpoint tested with Sarvam stubbed | **Blocked: needs `SARVAM_API_KEY`.** Without it the API returns 503 and the UI asks the merchant to type; no transcript is ever faked. |
| **Supabase Auth** | ES256/RS256 access tokens verified against the project JWKS (legacy HS256 still supported); issuer, audience and expiry enforced; first sign-in links an existing account by email; **role always from our DB**, never from editable token metadata; frontend password sign-in and refresh over the Auth REST API | Unit-tested with a locally generated ES256 key (valid, expired, wrong issuer, unknown user, metadata role ignored) | **Blocked: needs `SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY`.** Turn on "Confirm email" (account linking relies on it) and create Supabase users for the demo emails. |
| **Supabase PostgreSQL** | `DATABASE_URL` accepts the Supabase pooled connection string; migrations are additive and include the PostgreSQL enum change | Upgrade/downgrade/check on SQLite; PostgreSQL migration runs in CI | **Not run against Supabase.** Row Level Security policies are **not** implemented; all access goes through the API's own authorization. |
| **Razorpay payments** | Server-created orders (amount in paise from the approved plan), Checkout.js, server-side signature verification against the *stored* order id, `X-Razorpay-Signature` webhooks with event-id idempotency, amount check, never downgrading a success, reuse of pending orders; live keys refused unless `PAYMENTS_LIVE_ENABLED=true`; the simulated path is disabled once Razorpay is configured | 3 tests with Razorpay stubbed: forged/mismatched signatures, duplicate and forged webhooks, amount mismatch, live-key gating | **Blocked: needs Razorpay test keys** (`rzp_test_…`) and a webhook secret. **No real or test payment has been made.** The simulated provider remains, labelled, when Razorpay is not configured. |
| **Twilio WhatsApp** | Outbound via the Messages API (API key auth), queued in the business transaction and sent after the response; every message recorded as sent (with SID), failed (with error) or skipped (why); inbound `POST /api/whatsapp/inbound` with `X-Twilio-Signature` verification against `PUBLIC_BASE_URL`, MessageSid de-duplication, opt-in number lookup, text or voice-note orders → plans → "Reply YES" → plan approved and suppliers notified | 5 tests with Twilio stubbed: order → YES, forged signature, duplicate SID, unlinked number, failure alert after replan, failed send recorded as failed | **Blocked: needs Twilio credentials, a WhatsApp sender (sandbox or approved) and a public HTTPS URL** for the webhook (e.g. a tunnel to localhost). |

**Workflow coverage.** Voice/text/WhatsApp order → optimizer plans → payment → supplier
failure → automatic reallocation → updated cost and road route → WhatsApp alert. Each step uses
the existing services. The failure alert is sent from `replan_after_event`, so every recovery path
(reject, short supply, expiry, disruption, relay, Digital Twin) produces one.

**Other fixes in this pass.** `GET /api/payments/{id}` was capturing `/api/payments/config`
(fixed by router order). MapLibre's worker failed to load under Vite (fixed by bundling the
worker explicitly).

**Checks run:** backend `pytest` 75 passed (64 existing + 11 integration), `ruff` clean,
`alembic check` clean; frontend 5 tests passed, `tsc` and lint clean (3 old fast-refresh
warnings), production build OK, `npm audit` 0 vulnerabilities.

### To go live (in order)
1. Rotate every key that was pasted into chat; never commit `.env`.
2. `backend/.env`: `SARVAM_API_KEY`, `SUPABASE_URL`, `SUPABASE_JWKS_URL` (optional), `RAZORPAY_KEY_ID/SECRET/WEBHOOK_SECRET` (test keys), `TWILIO_ACCOUNT_SID`, `TWILIO_API_KEY_SID/SECRET`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`, `PUBLIC_BASE_URL`; optionally `DATABASE_URL` for Supabase Postgres, then `alembic upgrade head`.
3. `frontend/.env`: `VITE_API_BASE_URL`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_KEY`.
4. Twilio console: incoming WhatsApp webhook → `PUBLIC_BASE_URL/api/whatsapp/inbound` (POST). Razorpay dashboard: webhook → `/api/payments/razorpay/webhook` for `payment.captured`, `payment.failed`, `order.paid`.
5. Re-test each row above against the real service and update this table. Only then set `APP_ENV=production` / `PAYMENTS_LIVE_ENABLED=true`.

---


# Historical handoff

Last updated: 2026-10-16 (local Claude Code session, continuing from Cowork handoff)

## Overall state: WORKING END-TO-END LOCALLY. Not deployed. Docker not locally build-verified.

Environment: Python 3.13.5, Node v22.14.0, npm 11.6.0. PyPI and npm registries **reachable**
on this machine. Docker CLI is **not installed** here -- Dockerfiles/compose are written and
reviewed but not build-tested locally; see "Known gaps" below.

## Checklist

### Backend
- [x] FastAPI app, pydantic-settings config, SQLAlchemy 2.0 models (21 tables), Alembic migration
- [x] Local-JWT auth (PBKDF2) + Supabase-JWT verification path (code path exists; not exercised
      against a real Supabase project -- no credentials available)
- [x] Role/ownership dependencies; cross-tenant access returns 404 (verified by test)
- [x] Seed data: 9 products w/ Kannada/Hindi/English alias lexicon, 2 merchants, 4 suppliers,
      20 inventory offers, fabricated-but-labelled history for realistic reliability samples
- [x] OR-Tools CP-SAT optimizer -- 3 objective profiles, hard constraints (stock/MOQ/budget/
      price-tolerance/reliability/capacity/max-suppliers), shortfall variable instead of hard
      infeasibility → always returns the best permitted partial basket
- [x] Failover/replan engine -- carries forward confirmed allocations, excludes previously
      failed offers, re-optimizes only the outstanding quantity, full audit trail across
      `AllocationPlan` rows (one engine, reused by confirm/reject/shortfall/expiry/Digital Twin)
- [x] Deterministic lexicon/regex parser for code-mixed Kannada/Hindi/English order text
- [x] Provider adapters: Sarvam STT, Paytm staging (checksum implemented per the publicly
      documented algorithm, **unverified against a live sandbox**), Google Routes v2 matrix +
      haversine estimate fallback
- [x] Simulated payment provider (deterministic decline rule, `is_simulated` always labelled)
- [x] Full API surface: auth, products, catalog/offers, supplier inventory + surplus +
      reliability, orders (create/parse-text/plan/select-plan/list/get), allocations
      (confirm/reject/report-shortfall/dispatch/deliver), payments (initiate + Paytm callback
      skeleton), reconciliation, digital-twin scenario disruption, admin control-tower metrics
- [x] **Backend tests: 13/13 passing** (`cd backend && pytest`) -- 7 optimizer unit tests + 6 API
      integration tests via FastAPI TestClient against a seeded SQLite DB
- [x] ruff lint clean

### Frontend
- [x] React + TypeScript + Vite + Tailwind v4, shadcn-style primitives (Button/Card/Badge/
      Input/Select built on class-variance-authority + clsx + tailwind-merge, matching the
      shadcn/ui pattern without the interactive CLI)
- [x] React Router, TanStack Query, Recharts
- [x] Merchant dashboard: order list, free-text order entry with live deterministic parsing
      and confidence display, structured basket editing, merchant policy controls
- [x] Order detail page: 3-plan comparison with full cost/risk/delivery breakdown, plan
      selection, live allocation status table, Digital Twin disruption buttons, Order Truth
      Engine reconciliation table + receipt entry, simulated/Paytm payment trigger
- [x] Supplier dashboard: incoming-allocation queue (confirm/reject with qty override,
      dispatch, deliver), inventory management, reliability score card, surplus listing
- [x] Admin control tower: order-status metrics, replan count, supplier reliability average,
      Recharts bar chart
- [x] Demo Mode banner reads `/api/health` and names exactly which providers are unconfigured
- [x] `npm run build` passes (TypeScript project build + Vite bundle, zero errors)
- [x] **Manually verified in a live browser against the running backend**: full core recovery
      scenario (100kg rice order → NewCo confirms 40kg → automatic replan allocates the
      missing 60kg to Anand Wholesale Grains (50kg) + Sri Balaji Provisions (10kg), with
      recalculated total cost shown live in the UI), plan comparison, admin metrics chart.
      Two real bugs were found and fixed during this walkthrough (see "Bugs found & fixed").
- [ ] No automated frontend test suite (Vitest/RTL) was written -- only the manual browser
      walkthrough above and `tsc`/`vite build` were run. This is a real gap, not claimed as done.
- [ ] Playwright e2e -- not started

### Packaging / CI / docs
- [x] `backend/Dockerfile`, `frontend/Dockerfile` + nginx config, root `docker-compose.yml`
      (Postgres + backend + frontend) -- **written and reviewed, not build-tested** (no
      Docker on this machine)
- [x] `.github/workflows/ci.yml` -- backend tests+lint, a second job that migrates against a
      real Postgres service container, frontend build. **Not run** (would execute on GitHub's
      infrastructure on push; not triggered from this session)
- [x] `docs/ARCHITECTURE.md`, `docs/API_REFERENCE.md`, `docs/SECURITY_CHECKLIST.md`,
      `docs/DEMO_SCRIPT.md`, `docs/DEPLOYMENT.md`
- [x] `README.md` distinguishes implemented / credentialed / simulated / not-done per the brief

## Bugs found & fixed during live verification

1. `GET /api/suppliers/me/allocations` returned allocations from **every** generated plan
   (cheapest/fastest/most_reliable), not just the merchant's selected one -- a supplier would
   see duplicate/stale proposals for plans the merchant never chose. Fixed by joining to
   `AllocationPlan` and filtering `is_selected=True` (`app/routers/suppliers.py`).
2. Order status got stuck on `replanning` after all post-replan allocations were confirmed,
   because the status-sync logic didn't treat a `short_supply` line (whose gap was already
   handed to a new plan) as "resolved". Fixed in `sync_order_status()`
   (`app/services/planning.py`) and covered by `test_core_recovery_scenario_end_to_end`.
3. Supplier reliability confidence badge displayed the wrong text (reused a status-badge
   component that printed its color-mapping key instead of the actual confidence label).
   Fixed in `SupplierDashboard.tsx`.

All three were caught by actually exercising the UI against the live backend, not just by
reading the code -- which is why this section exists.

## Known gaps (see README.md for the categorized version)

- **Docker not installed on this machine.** Files reviewed line-by-line against the
  Dockerfile/compose conventions used elsewhere in this build, but never actually built.
- **Paytm checksum untested against a live sandbox** (no credentials). Implements the
  publicly documented SHA-256 + salt + AES-128-CBC algorithm; flagged VERIFY, not claimed
  working, per `docs/PROVIDER_NOTES.md`.
- **Sarvam/Google Routes real calls untested** (no API keys). Demo mode runs entirely on the
  deterministic parser + haversine estimate, both clearly labelled in the UI/API.
- **Cross-product substitution** (e.g. jaggery for sugar) is out of scope for this MVP;
  documented in `docs/ARCHITECTURE.md`, not silently dropped.
- Supabase Auth/RLS verification path exists in code but was not exercised against a real
  Supabase project.
- No frontend automated test suite or Playwright e2e.
- Forecasting/intelligence modules beyond reconciliation, reliability-with-confidence, and
  dead-stock listing (Stockout Radar, Survival Mode, Cash-Cycle Planner, Margin Leak
  Detector, Local Price Index, Procurement Autopilot) are not implemented.

## How to run what exists right now

```
cd backend
python -m venv .venv && source .venv/Scripts/activate
pip install -r requirements-dev.txt
alembic upgrade head
python -m app.seed.seed_data
pytest                      # 13 passed
uvicorn app.main:app --reload --port 8000

cd ../frontend
npm install
npm run dev                 # http://localhost:5173
```
See `docs/DEMO_SCRIPT.md` for the exact click-through of the core recovery scenario.
