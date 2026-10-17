> Historical design notes. Current implementation/status is in the root-level reports. Do not treat this earlier document as fresh verification.

# Deployment

**Status: configuration written and reviewed, not yet deployed to any live environment
in this session.** No deploy has been run; no URL exists yet.

## Target architecture

- **Frontend:** Cloudflare Pages (static build of the Vite output)
- **Backend:** Google Cloud Run (the `backend/Dockerfile` already reads `$PORT`, which
  Cloud Run requires)
- **Database/Auth:** Supabase PostgreSQL + Supabase Auth

## Backend → Cloud Run

```
cd backend
gcloud builds submit --tag gcr.io/<PROJECT_ID>/stockout-firewall-backend
gcloud run deploy stockout-firewall-backend \
  --image gcr.io/<PROJECT_ID>/stockout-firewall-backend \
  --platform managed \
  --region <REGION> \
  --allow-unauthenticated \
  --set-env-vars APP_ENV=production,DEMO_MODE=false,CORS_ORIGINS=https://<your-pages-domain> \
  --set-secrets DATABASE_URL=db-url:latest,SUPABASE_URL=supabase-url:latest,SUPABASE_JWT_SECRET=supabase-jwt-secret:latest,SUPABASE_SERVICE_ROLE_KEY=supabase-service-key:latest,PAYTM_MID=paytm-mid:latest,PAYTM_MERCHANT_KEY=paytm-key:latest,SARVAM_API_KEY=sarvam-key:latest,GOOGLE_MAPS_API_KEY=maps-key:latest
```

Use Secret Manager (`--set-secrets`) for every credential; never pass secrets via
`--set-env-vars` in a real deployment. `DATABASE_URL` should be the Supabase **pooled**
connection string (Cloud Run is a scale-to-zero, many-connections environment; the
pooler avoids exhausting Postgres connection limits).

The container's `CMD` runs `alembic upgrade head` before starting uvicorn, so each
deploy self-migrates. For a team with concurrent deploys, move the migration to a
separate one-off Cloud Run Job instead of the request-serving container's startup path.

## Frontend → Cloudflare Pages

```
cd frontend
npm run build          # outputs dist/
```
Connect the repository in the Cloudflare Pages dashboard, or deploy the `dist/` folder
directly with `wrangler pages deploy dist`. Build settings:
- Build command: `npm run build`
- Build output directory: `dist`
- Environment variables: `VITE_API_BASE_URL=https://<your-cloud-run-url>`,
  `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` (anon key is public by design).

## Database → Supabase

1. Create a Supabase project. Copy the pooled Postgres connection string into
   `DATABASE_URL` for the backend, and the project URL/anon key/JWT secret into the
   corresponding `SUPABASE_*` variables.
2. Run `alembic upgrade head` against it once (either locally with `DATABASE_URL`
   pointed at Supabase, or let the Cloud Run container's startup command do it on first
   deploy).
3. **Row Level Security:** not yet written in this session (see
   `docs/SECURITY_CHECKLIST.md`). Until RLS policies exist, do not allow the frontend to
   query Supabase directly with the anon key for anything beyond Supabase Auth itself --
   all data access must go through the FastAPI backend, which already enforces
   ownership/role checks in the application layer.

## Health check

`GET /api/health` returns `{"status": "ok", "demo_mode": ..., "sarvam_configured": ...,
"paytm_configured": ..., "google_maps_configured": ..., "supabase_configured": ...}` --
use this for the Cloud Run startup/liveness probe and to confirm which providers are
live vs. falling back to simulation in a given environment.

## Rollback

Cloud Run keeps prior revisions; `gcloud run services update-traffic
stockout-firewall-backend --to-revisions=<PREVIOUS_REVISION>=100` reverts traffic
instantly without a rebuild. Cloudflare Pages keeps prior deployments with one-click
rollback in its dashboard. Database migrations in this project are additive-only so far
(no destructive column drops); if a future migration is destructive, pair it with a
written rollback (`alembic downgrade`) and test it before shipping.

## What's NOT configured

- CI does not currently deploy anywhere (`ci.yml` only builds/tests). Add a deploy job
  once real GCP/Cloudflare credentials are available as repository secrets.
- No custom domain / TLS cert steps documented beyond the platforms' defaults.
- No staging environment is defined separately from production in this session.
