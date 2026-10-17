# Stockout Firewall

An explainable procurement recovery prototype for small merchants. A supplier confirms 40 kg of a 100 kg rice order; the engine preserves that commitment and proposes the remaining 60 kg under the original budget, price ceiling and supplier limit. **A proposal is not a reservation or delivery. All supplied data is synthetic.**

## Quick start (Python 3.12, Node 22+)

From the project root:
```bash
cd backend
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows PowerShell instead: .venv\Scripts\Activate.ps1
pip install -r requirements.lock.txt
alembic upgrade head
python -m app.seed.seed_data
uvicorn app.main:app --reload --port 8000
```
In another terminal:
```bash
cd frontend
npm ci
npm run dev
```
Open http://localhost:5173. API docs: http://localhost:8000/docs. Demo accounts: `merchant1@example.com`, `merchant3@example.com` (holds only the labelled PromiseGuard demo orders), `anand@example.com`, `balaji@example.com`, `lakshmi@example.com`, `newco@example.com`, `admin@example.com`; password `demo1234`. These are public demo credentials, not production credentials.

Default SQLite database is `backend/stockout.db`. Configuration is loaded from the backend working directory: copy the root `.env.example` to `backend/.env` if customization is needed. Keep DEMO_MODE=true locally. Do not place provider credentials in frontend variables. Seed command deletes and rebuilds ALL application rows in the configured database and is allowed only with APP_ENV=local and DEMO_MODE=true. Never point the demo at real data. Migrate before seeding; create_all is not an upgrade mechanism.

## Demo
See DEMO_SCRIPT.md. Create 100 kg Rice, minimum reliability 0.3, price tolerance 20%, budget INR 6000, max suppliers 4. Generate plans, select Cheapest. In a separate browser profile log into the assigned supplier and confirm 40 kg. Reopen the merchant order: Recovery evidence separates confirmed 40, proposed 60, delivered 0, and any uncovered quantity. To demonstrate graceful degradation, repeat with max suppliers 1: recovery cannot add another supplier and reports 60 uncovered.

The original code-mixed parser and intelligence pages are retained. Low-confidence drafts now have an explicit review/approval action. UI pages load on demand to reduce initial JavaScript transfer.

## Supplier Continuity Network
The supplier side is built around keeping promises: **PromiseGuard** (free to promise = on hand − committed − safety stock, enforced on confirmation), a **Supply Relay Protocol** that lets a wholesaler hand the exact shortfall to eligible partner wholesalers under the merchant's own policy and approval, a deterministic **Commitment Copilot** action queue, a dispatch-readiness board, and an evidence-based **Trust Passport** that reports INSUFFICIENT_HISTORY instead of false precision. Formulas, endpoints, the two-moment demo and limits: [docs/SUPPLIER_CONTINUITY.md](docs/SUPPLIER_CONTINUITY.md).

## Verify
```bash
cd backend
pip check
ruff check app tests
pytest -q
alembic check
python scripts/benchmark.py benchmark-results.json
cd ../frontend
npm test
npm run lint
npm run build
```
TEST_REPORT.md records actual checks and blocked checks. BENCHMARK_REPORT.md distinguishes an in-process microbenchmark from a deployment load test. `docker compose up --build` is supplied but was not executed (Docker unavailable). After first container startup seed explicitly with `docker compose exec backend python -m app.seed.seed_data`.

## Architecture and limits
React/TypeScript -> FastAPI -> SQLAlchemy/Alembic -> SQLite locally or PostgreSQL; OR-Tools handles constrained plans. Confirmations atomically decrement available inventory. Replans retain audit history and spend only remaining budget. See ARCHITECTURE.md.

This is a tested local prototype, not a production financial or logistics service. Live/sandbox payment initiation and callbacks are intentionally disabled pending signature/settlement verification; demo payments remain simulated. Google Routes and Sarvam adapters exist but are not verified live; planning uses distance estimates. No delivery-deadline guarantee, POS inventory integration, offline sync, generic cross-brand substitution approval, cancellation/refund workflow or million-user deployment is claimed. Legacy active allocations with no inventory reference must be recreated before confirmation. REQUIREMENTS_MATRIX.md is the authoritative feature status; old handoff/build documents are historical.

See ATTRIBUTION.md for source provenance. Do not assume third-party source licensing rights beyond the supplied project.
