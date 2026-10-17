# Test report

Verification resumed 17 October 2026 (India date). Results below are local unless explicitly marked otherwise.

| Check / exact command | Result |
|---|---|
| Fresh Python 3.12 venv; `pip install -r requirements.lock.txt` | Passed |
| `pip check` | Passed; no broken requirements |
| `ruff check app tests` | Passed |
| `pytest -q` | 43 passed, 1 upstream Starlette TestClient deprecation warning |
| Fresh SQLite: `alembic upgrade head` | Passed all three migrations |
| `alembic check` | Passed; no new upgrade operations detected |
| `python -m app.seed.seed_data` after migrations | Passed; 9 products, 2 merchants, 4 suppliers, 20 offers |
| Seeded DB copy: `alembic downgrade c782ddd7dc52`, then `alembic upgrade head` | Passed; product/offer counts preserved and SQLite foreign_key_check clean |
| `npm ci --ignore-scripts` | Passed from package-lock; separate archive validation uses normal npm ci |
| `npm test` | 3 component tests passed |
| `npm run lint` | Passed with 3 existing Fast Refresh warnings |
| `npm run build` | TypeScript and production bundle passed |
| `python scripts/benchmark.py /tmp/stockout-benchmark-resume.json` | 30/30 synthetic recovery cases, 200/200 reads; see benchmark report |
| Browser E2E | Blocked in original session by invalid Chromium archive; no browser run claimed for this rebuild |
| Docker startup | Not run: Docker CLI unavailable |
| PostgreSQL service migration | Not run locally; CI job provided |
| Supabase, Sarvam, Google Routes and payment provider sandbox | Not verified: credentials unavailable; non-demo payment initiation/callback deliberately disabled |

## Coverage and boundaries
Original suite had 22 tests; repaired suite has 43. Regression coverage includes admin registration, input constraints, repeated-product inventory, delivery-inclusive budget, recovery budget/supplier limits, atomic stock confirmation, stale plans, cross-order invoice/receipt ownership, truthfulness of fulfilled states, review approval, seed safety and blocked payment callbacks. The 3 frontend tests exercise recovery evidence rendering, loading and error/retry behavior. Neither count implies comprehensive UI or production coverage.

Upgrade check uses synthetic seeded records; it does not validate arbitrary production datasets. Existing allocations without the new source-offer reference require recreation before confirmation, as documented in README. Detailed original reproduction evidence is in AUDIT_REPORT.md. Existing historical BUILD_STATUS/HANDOFF claims are not current verification evidence.

## Clean archive verification
Passed after extracting Stockout_Firewall_Rebuilt.zip into a fresh directory: fresh Python venv installation from requirements.lock.txt, pip check, all 43 backend tests, fresh Alembic migration and schema check; normal npm ci, all 3 frontend tests, lint and production build. Final packaging subsequently changes only this report, CHANGELOG and the corrected .env.example; application source and dependency manifests are identical to the clean-tested archive. No credentials, real .env files, embedded .git, dependency folders, databases or caches belong in the archive.

## Remote checks
CI configuration includes pinned installs, backend tests/lint, frontend tests/lint/build and PostgreSQL migrations. Its remote status is reported separately at delivery; local success does not establish remote CI success.
