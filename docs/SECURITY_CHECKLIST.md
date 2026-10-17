# Security checklist

This documents what is in place and what is explicitly NOT assessed. This prototype has
**not** undergone a third-party security review or compliance assessment of any kind --
do not describe it as compliant with any law or certification.

## In place

- [x] Passwords hashed with PBKDF2-HMAC-SHA256 (390k iterations), random 16-byte salt per
      user (`app/security.py`). Not bcrypt/argon2 to avoid an extra dependency for the
      local-demo auth path -- acceptable here because production auth is expected to be
      Supabase Auth, not this local path.
- [x] JWT verification: local HS256 tokens (`LOCAL_JWT_SECRET`) and Supabase HS256 tokens
      (`SUPABASE_JWT_SECRET`) are verified separately; a token's `iss` claim determines
      which path resolves it, and an invalid/expired/wrong-secret token is rejected.
- [x] Role-based dependencies (`require_role`, `get_merchant_profile`, `get_supplier_profile`,
      `require_admin`) enforce that only the matching role can call role-specific routes.
- [x] Ownership checks on every order/allocation endpoint: a merchant can only read/act on
      orders where `order.merchant_id == current_merchant.id`; a supplier can only act on
      allocations where `allocation.supplier_id == current_supplier.id`. Verified by
      `test_merchant_cannot_access_another_merchants_order` and the cross-supplier-confirm
      test in `tests/test_api_workflow.py`. Unauthorized access returns 404, not 403/200,
      so existence of another tenant's resource is not leaked.
- [x] Idempotency: `Payment.idempotency_key` is unique; a second successful-payment attempt
      on an already-paid order is rejected (409).
- [x] Payment status is always re-verified server-side (`verify_status`) rather than trusted
      from a browser redirect; the Paytm webhook handler calls the same verification path.
- [x] Secrets (`PAYTM_MERCHANT_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET`,
      `SARVAM_API_KEY`, `GOOGLE_MAPS_API_KEY`) only ever live in backend process env, never
      sent to the frontend. Only `VITE_*`-prefixed values are exposed to the browser, by
      Vite's own convention and by the explicit `.env.example` layout.
- [x] CORS is restricted to `CORS_ORIGINS` (not `*`).
- [x] Rate limiting is wired via `slowapi` (`app/main.py`, default 200/min) -- a coarse
      global limit; per-endpoint limits on expensive routes (e.g. `/plan`, the CP-SAT
      solve) are not yet tuned (see "Not done" below).
- [x] `.env.example` contains placeholders only; `.gitignore` excludes `.env` everywhere.
- [x] No raw card details are ever handled -- Paytm's hosted checkout owns card entry; this
      backend only ever sees a token/order id, matching PCI-scope reduction practice.

## Explicitly not done / not assessed

- [ ] Row Level Security (RLS) policies on the Supabase/Postgres side are not written in
      this session -- the backend currently does all authorization in the application
      layer (above), which is correct for a backend-only access pattern, but RLS as a
      defense-in-depth layer (in case of a future direct-from-client Supabase access
      pattern) is not configured. Document and add before any client ever talks to
      Supabase directly.
- [ ] Per-endpoint rate limiting tuned for cost (CP-SAT solve, parsing) vs. cheap reads.
- [ ] Structured/privacy-aware logging (current logging is the FastAPI/uvicorn default;
      no PII redaction pass has been done).
- [ ] CSRF is not applicable (bearer-token API, no cookie-based session), but confirm this
      assumption holds if cookie auth is ever added.
- [ ] Dependency vulnerability scanning (e.g. `pip-audit`, `npm audit`) is not wired into CI.
- [ ] Paytm checksum implementation is **unverified against a live sandbox** -- see
      `docs/PROVIDER_NOTES.md`. Do not process a real transaction against it without first
      validating against Paytm's own test vectors.
- [ ] No automated secret-scanning pre-commit hook is configured.
- [ ] File upload handling: there is no file upload endpoint yet (invoices are submitted as
      structured JSON, not PDF/image upload), so "safe upload handling" from the brief is
      not yet exercised -- if an upload endpoint is added, validate MIME type, size limits,
      and storage outside the web root before accepting arbitrary files.

## Data minimization

- Merchant/supplier profiles store only business name, city, address, lat/lng, and
  operational parameters (budget tolerance, delivery capacity) -- no personal financial
  account numbers are collected or stored anywhere in the schema.
- Payment records store provider transaction IDs and amounts, never raw payment
  instrument data.

## Retention / deletion (not yet implemented, documented as a gap)

No automated data-retention or account-deletion endpoint exists yet. Before production use,
add: a merchant/supplier account deletion flow, a retention policy for `AuditEvent`/
`SupplierEvent` history, and a documented data-processing/privacy notice appropriate to the
jurisdictions served.
