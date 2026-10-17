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
