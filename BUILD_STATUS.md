> Historical source handoff. Superseded by root README.md, TEST_REPORT.md and REQUIREMENTS_MATRIX.md. In particular live payments are now disabled pending verification.

# BUILD_STATUS

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
