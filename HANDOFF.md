> Historical source handoff. Superseded by root README.md, TEST_REPORT.md and REQUIREMENTS_MATRIX.md. In particular live payments are now disabled pending verification.

# HANDOFF — Stockout Firewall

Prepared 2026-10-16 from a Claude (Cowork) cloud session. Purpose: let you continue the build in a local
Claude Code project without losing anything.

## 1. What was completed

| Item | Status |
|---|---|
| Environment audit | Done |
| Official-doc review for Sarvam STT/chat, Paytm Initiate Transaction, Google Routes v2 | Done → `docs/PROVIDER_NOTES.md` (with **VERIFY** flags) |
| Directory scaffold | Done (all directories empty except `docs/`) |
| `.env.example`, `.gitignore` | Done (placeholders only, no secrets) |
| Master brief preserved | Done → `docs/MASTER_BUILD_PROMPT.md` |
| `BUILD_STATUS.md`, `HANDOFF.md`, `README.md` | Done |

**No application code has been written.** There is no backend, frontend, schema, optimizer, Docker file or CI file yet.

## 2. Files created

```
BUILD_STATUS.md                 progress checklist (keep updating this)
HANDOFF.md                      this file
README.md                       stub; says nothing is implemented
.env.example                    all config keys from the brief, placeholders only
.gitignore
docs/MASTER_BUILD_PROMPT.md     your full original brief, verbatim
docs/PROVIDER_NOTES.md          API facts gathered from official docs + what still needs verifying
backend/  frontend/  infra/  .github/workflows/     empty directories
```

## 3. Test results

**No tests, builds, lints, type checks or end-to-end runs were executed. Zero pass, zero fail.**
Nothing here should be described as tested.

Commands that *were* run and their real outcomes:

| Command | Outcome |
|---|---|
| `pip install fastapi uvicorn sqlalchemy alembic ortools …` into a venv | Failed. First attempt: DNS could not resolve `pypi.org`. Second attempt via the session proxy: `403 Forbidden` on CONNECT (policy denial). |
| `npm view react version` via the proxy | Failed with 403. |
| Connectivity probe to `pypi.org`, `files.pythonhosted.org`, `registry.npmjs.org`, `raw.githubusercontent.com` | No response (000). |

Per your instruction, blocked downloads were not retried, no alternative mirror was used, and the stack was not replaced.
A failed, empty Python venv was deleted; it contained no work.

## 4. Remaining work (everything below is still to do)

Follow the stage order in `docs/MASTER_BUILD_PROMPT.md` → "QUALITY GATES". Suggested concrete breakdown:

1. **Backend foundation** — FastAPI app, settings (`pydantic-settings`), SQLAlchemy models, Alembic migrations, Supabase JWT verification + local-JWT demo fallback, role/ownership dependencies, audit events, rate limiting.
2. **Seed data** — deterministic Indian wholesale data (rice/atta/dal/oil/sugar etc.), merchants, 4–6 suppliers with reliability history, price observations, one rice scenario (primary supplier confirms 40 of 100 kg then fails).
3. **Optimizer** — OR-Tools CP-SAT: integer quantities in pack units, hard constraints (stock, MOQ, budget, price tolerance, min reliability, substitutions, delivery window/capacity), three objective-weight profiles (cheapest / fastest / most reliable), infeasibility explanation and best partial basket.
4. **Failover + re-optimization** — event-driven replan on rejection / short supply / expired confirmation / disruption; idempotent state transitions.
5. **Parsing + SKU normalization** — deterministic rule/lexicon parser for Kannada/Hindi/English code-mixed text; Sarvam STT + LLM adapters behind an interface; strict Zod/Pydantic validation; low-confidence → require confirmation; demo-mode labelling.
6. **Providers** — payment interface (simulated provider + Paytm adapter with server-side status verification, webhook signature check, idempotency); route provider interface (labelled-estimate fallback + Google Routes v2).
7. **Intelligence** — stockout radar, survival mode, cash-cycle planner, margin leak, local price index, reconciliation (order vs invoice vs received), autopilot suggestions, dead-stock matching, digital twin scenarios, supplier reliability with confidence by sample size, control-tower metrics.
8. **Frontend** — React/TS/Vite/Tailwind/shadcn: merchant, wholesaler, admin/control tower, digital twin; TanStack Query; Recharts; Demo Mode banner; loading/empty/error states.
9. **Tests** — pytest (optimizer, failover, policies, payment states, authz, reconciliation, API), frontend unit tests, Playwright (principal journey + failure recovery).
10. **Packaging/docs** — Dockerfiles, Compose, GitHub Actions, Cloudflare Pages + Cloud Run config, `docs/ARCHITECTURE.md`, API reference, security checklist, demo script, provider setup checklists, known limitations, rollback notes.
11. **Final gate** — clean-install rebuild, all checks green, then the 7-item final report required by the brief.

## 5. Dependencies (not installed; versions NOT pinned — pin after install)

I could not confirm current stable versions because registries were unreachable. Install the latest compatible
releases locally, run the tests, then pin.

**Backend (Python ≥ 3.11):** `fastapi`, `uvicorn[standard]`, `pydantic`, `pydantic-settings`, `sqlalchemy`, `alembic`,
`psycopg2-binary` (or `psycopg[binary]`), `ortools`, `pyjwt`, `cryptography`, `httpx`, `python-multipart`, `slowapi` (or equivalent), `email-validator`,
dev: `pytest`, `pytest-cov`, `ruff`, `mypy` (optional).

**Frontend (Node ≥ 20):** `react`, `react-dom`, `typescript`, `vite`, `@vitejs/plugin-react`, `tailwindcss`, shadcn/ui (via its CLI) with
`class-variance-authority`, `clsx`, `tailwind-merge`, `lucide-react`, `react-router-dom`, `@tanstack/react-query`,
`react-hook-form`, `zod`, `@hookform/resolvers`, `recharts`, dev: `vitest`, `@testing-library/react`, `eslint`, `@playwright/test`.

**Services:** Postgres (local via Docker Compose, or Supabase), Docker, Chromium for Playwright (`npx playwright install chromium`).

## 6. Credentials / configuration you must supply (all optional for local demo mode)

| Provider | Variables | Needed for |
|---|---|---|
| Supabase | `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET` | Production auth/RLS |
| Sarvam AI | `SARVAM_API_KEY`, `SARVAM_LLM_MODEL` | Real speech-to-text and parsing |
| Gemini | `GEMINI_API_KEY` | Optional parser |
| Paytm | `PAYTM_MID`, `PAYTM_MERCHANT_KEY`, `PAYTM_ENV` | Sandbox payments |
| Google Maps | `GOOGLE_MAPS_API_KEY` | Real road routes |

## 7. Blockers and gaps — be aware

- **Missing entirely:** all source code, migrations, seed data, tests, Docker/CI files, `docs/ARCHITECTURE.md`. Nothing is half-built; it is a clean start.
- **External blocker in the cloud session:** package registries returned 403. Not an issue on a normal local machine.
- **Unverified provider facts (see `docs/PROVIDER_NOTES.md`):** Sarvam base URL and chat model name (docs conflict on `sarvam-m` vs `Sarvam-105B`), Sarvam pricing/free credits/rate limits, Paytm checksum algorithm and Transaction Status/webhook details, Google Routes REST paths and pricing.
- **ChatGPT share link** (`https://chatgpt.com/share/6ad23460-4cac-83ee-9a60-1596a3fdd8b0`) was not opened; the brief says to rely on the brief if inaccessible. Paste any extra context from it into the first Claude Code prompt if it matters.
- Sandbox/demo behaviour must stay labelled as simulated. Do not claim any untested feature works.

## 8. Kickoff prompt for your local Claude Code session

Open this folder in Claude Code (`cd stockout-firewall && claude`), then paste:

```text
Read BUILD_STATUS.md, HANDOFF.md, docs/PROVIDER_NOTES.md and docs/MASTER_BUILD_PROMPT.md.
Continue the Stockout Firewall build from the handoff exactly as specified in the master prompt.
Do not change the required stack (React + TypeScript + Vite + Tailwind + shadcn/ui; FastAPI + SQLAlchemy + Alembic;
Supabase PostgreSQL/Auth; OR-Tools CP-SAT). Package registries are reachable here, so install real dependencies,
pin the versions that work, and run the tests. No application code exists yet — start at Quality Gate 1/2.
Treat every item marked VERIFY in docs/PROVIDER_NOTES.md as unconfirmed. Never claim a test passed unless you ran it.
Keep BUILD_STATUS.md current so work can resume after an interruption.
```

## 9. Core recovery scenario to demonstrate once built

Merchant orders 100 kg rice → primary supplier confirms 40 kg → supplier reports shortfall/failure → system detects the missing 60 kg → eligible alternatives filtered by stock, MOQ, budget, price tolerance, reliability → CP-SAT re-optimizes → landed cost and route recalculated → merchant and supplier notified → final plan explained → delivery reconciled against invoice. If 60 kg cannot be sourced under the merchant's rules, report infeasibility and show the best permitted partial basket.
