# STOCKOUT FIREWALL — MASTER BUILD PROMPT

> Saved verbatim from the original request so a local Claude Code session can use it as the source of truth.

Act as my senior startup CTO, full-stack engineer, AI engineer, optimization specialist, security reviewer and DevOps engineer. Build Stockout Firewall into a cohesive, working, deployable product—not a mockup or a collection of disconnected dashboards.

## CONTEXT

Product: **Stockout Firewall — AI Procurement Resilience Platform for India's Small Merchants.**

Tagline: “Not just backup suppliers. Backup supply you can count on.”

ChatGPT background conversation share URL:
https://chatgpt.com/share/6ad23460-4cac-83ee-9a60-1596a3fdd8b0

Read this conversation for additional context about the product, innovation, merchant problems and startup vision if the link is accessible. If it is inaccessible, continue using this complete brief. Do not waste time retrying it.

Target users: Indian kirana stores/small retailers and wholesale suppliers.

Core innovation: Build a shared procurement network that normalizes merchant orders, evaluates suppliers, minimizes total landed cost, obtains supplier commitments, detects fulfillment failures, reallocates shortages, optimizes routes and protects merchant-defined constraints.

## SESSION SETUP — USER INSTRUCTIONS

These are recommendations for the human using Claude. Do not attempt to change Claude's model or interface settings through tools.

- **Preferred workspace: Claude Code.** Use it because this project requires creating and editing many files, using a terminal, running tests, fixing errors and preparing deployment.
- **Alternative: Claude Cowork.** If Claude Code is unavailable, use Claude Desktop Cowork with access to a new or existing local project folder and the necessary file/terminal tools.
- **Plain Claude Chat is not preferred** for this full build because it may not have direct access to project files or a terminal. If using Chat only, do not claim that code was executed or tests passed.
- **Model:** Manually select Claude Sonnet 5.5 if it appears in the available model list. Keep it selected for the main implementation to balance coding capability, speed and usage efficiency. If it is unavailable, keep the currently selected/default model and continue. Claude Opus 5.5 may be selected manually for a particularly difficult architecture or debugging issue if available, but do not require it for every task.
- **Effort/thinking:** Keep the effort setting at Medium or the application's default for the main build. If there is no effort selector, do nothing. Use higher effort only for a specific difficult problem that resists a sensible fix.
- Do not repeatedly change models, ask me to choose between equivalent tools, or reconsider decisions already made.
- **Usage efficiency:** Implement in cohesive stages, reuse context and existing files, read only relevant files, avoid repetitive status summaries and duplicate tests, and maintain a compact `BUILD_STATUS.md` so work can resume after a usage limit or interruption. Run meaningful tests; efficiency must not come at the expense of verification.
- **Folder access:** If no project folder exists, create `stockout-firewall/` inside the user-approved writable workspace. If access or a permission is missing, request only the necessary permission. GitHub is optional; do not block local development on connecting it.
- **External information:** Prefer current official API documentation. Research only to resolve concrete integration, pricing or compatibility questions. Add connectors only when they provide a necessary capability.

## EXECUTION RULES

1. Determine what workspace access is available. If a project folder/repository exists, inspect its files, scripts, dependencies, environment configuration and running application. Preserve working code and improve it incrementally. If no project folder exists, create one inside the approved writable workspace and scaffold it.
2. Do not ask avoidable questions. Make sensible decisions using this brief. Record genuinely missing credentials as setup requirements.
3. Work directly in files and terminal. Do not merely print code into chat. Avoid repeatedly generating plans, rereading unchanged files and summarizing every file.
4. Create `BUILD_STATUS.md` and `docs/ARCHITECTURE.md`. Maintain a compact checklist of completed work, tests, blockers and remaining tasks.
5. Execute implementation, tests, bug fixes and deployment preparation continuously until the acceptance criteria below are met or a genuine external blocker remains. Do not stop after scaffolding or the first successful page.
6. Prefer well-supported, maintainable dependencies. Avoid unnecessary microservices, overengineering, duplicate libraries and paid services without a clear need.
7. Never invent API responses, live inventory, successful payments, supplier commitments, model accuracy or test results. Clearly label simulated data, estimates and integrations requiring credentials.
8. Preserve secrets. Never expose keys to the browser, commit secrets, disable security checks to pass tests or run destructive Git operations without permission.
9. Check current official documentation before using external APIs. Pin compatible dependencies, handle rate limits and errors, and document provider limitations.
10. Keep explanations to me concise. Spend effort on implementation, verification and a working product.

## REQUIRED TECH STACK

- **Frontend:** React, TypeScript, Vite, Tailwind CSS, shadcn/ui, React Router, TanStack Query, React Hook Form and Zod where useful; Recharts for analytics.
- **Backend:** Python, FastAPI, Pydantic, SQLAlchemy and Alembic.
- **Database/authentication:** Supabase PostgreSQL and Supabase Auth, with Row Level Security and migrations. Keep privileged server credentials exclusively in the backend.
- **Optimization:** Google OR-Tools CP-SAT for constrained supplier allocation and routing-related optimization.
- **AI providers:** Sarvam AI first for Indian-language speech recognition and, where suitable, language-model parsing; optional Gemini provider. Keep core calculations deterministic.
- **Maps:** Provider abstraction for Google Maps Routes API when configured; otherwise use clearly labelled estimated distances. Do not pretend straight-line distances are real road routes.
- **Payments:** Paytm Payment Gateway sandbox adapter first, with a payment-provider interface for future alternatives.
- **Testing:** pytest for backend, suitable frontend unit tests and Playwright end-to-end tests.
- **Packaging:** Docker, Docker Compose, `.env.example`, GitHub Actions CI and deployment configuration.
- **Initial deployment target:** Cloudflare Pages for the frontend, Google Cloud Run for FastAPI, and Supabase for database/authentication. Provide alternatives only when justified.

Use current stable, mutually compatible versions. Keep the application runnable locally without paid API keys.

## PRODUCT MODULES

### A. Merchant application

Implement a mobile-friendly merchant dashboard with:

1. Voice/text wholesale ordering and multilingual/code-mixed input, including Kannada, Hindi and English examples.
2. Structured basket creation: product, brand, pack size, unit, requested quantity, substitution policy and budget.
3. SKU normalization and duplicate/pack-size handling.
4. Supplier comparison with stock confirmation, unit price, MOQ, delivery estimate, reliability evidence and availability freshness.
5. Budget, price-tolerance, minimum-reliability, preferred-supplier and substitution controls.
6. Predictive Stockout Radar with actionable reorder recommendations based on available historical data.
7. Merchant Survival Mode to prioritize essential products within available cash when full procurement is infeasible.
8. Cash-Cycle Buying Planner, Margin Leak Detector and Local Wholesale Price Index.
9. Order Truth Engine comparing ordered quantities, supplier invoices and received quantities; flag missing goods, unexpected prices and billing discrepancies.
10. Procurement Autopilot that prepares suggested recurring baskets for merchant approval, not uncontrolled purchases.
11. Dead-Stock Rescue Exchange for listing and matching eligible excess inventory.
12. Explainable order status, alerts, cost breakdowns, outstanding shortages and audit history.

### B. Wholesaler application

Implement role-restricted supplier dashboards with:

1. Inventory, prices, product packs, MOQs, operating hours and delivery-capacity management.
2. Incoming order review and accept/modify/reject workflows.
3. Quantity, price and ready-by-time confirmation. Record whether a commitment is confirmed, expired or fulfilled.
4. Partial-fulfillment reporting, invoice upload/entry and dispatch/delivery status.
5. Supplier performance dashboard for fulfillment, cancellations, delays, discrepancies and price stability.
6. Demand forecasts and surplus-inventory listing/matching workflows.
7. Supplier notifications and a complete, auditable order timeline.

### C. Shared procurement intelligence

Implement:

1. **Automatic supplier failover:** Respond to rejection, short supply, expired confirmation deadlines or recorded disruptions.
2. **Continuous re-optimization:** Recalculate basket allocations, costs and delivery routes following changes in stock, prices, delivery, budget or merchant constraints.
3. **Total landed-cost engine:** Incorporate product cost, delivery/consolidation cost, penalties or risk estimates, and affordability.
4. **Supplier intelligence:** Evaluate reliability using actual evidence and adequate sample size. Mark insufficient history as low confidence rather than assigning fabricated accuracy.
5. **What-If Recovery Engine:** Compare cheapest, fastest and most reliable feasible plans, with transparent trade-offs.
6. **Supply Chain Digital Twin:** Provide scenario controls for supplier outages, price increases, partial stock, delivery delays and route disruptions.
7. **Predictive risk and replenishment recommendations.**
8. **Shared dead-stock matching** and order/invoice/delivery reconciliation.
9. Notifications, event logs, operational metrics and an admin/control-tower view.

Treat these as related parts of a single system, not disconnected demo pages.

## CORE WORKFLOW — MUST WORK END TO END

Merchant creates a basket → speech/text is parsed → SKUs are normalized → suppliers are discovered → current inventory, price and confirmation freshness are checked → feasible allocations are optimized → cheapest/fastest/most reliable alternatives are compared → merchant rules are validated → merchant approves → payment sandbox or clearly labelled test payment runs → suppliers confirm → fulfillment events are recorded → a shortfall triggers replanning → routes and costs are recalculated → merchant and supplier receive the updated plan → delivery is reconciled against the order and invoice.

Build a dramatic, repeatable demo scenario:

A merchant requests 100 kg of rice. The primary supplier initially confirms 40 kg and then reports a shortfall or fails. The system identifies the missing 60 kg, selects eligible alternative suppliers, checks budget and MOQ, recalculates landed cost and delivery, and explains the final plan. Add a second disruption to the Digital Twin if useful.

If full fulfillment is impossible, report infeasibility honestly and present the best permitted partial basket.

## REAL OPTIMIZATION — NOT RANDOM RECOMMENDATIONS

Use a deterministic optimization module with explicit constraints:

- Requested quantity and permitted substitutions.
- Supplier available stock and MOQ.
- Merchant budget and price tolerance.
- Minimum reliability requirements.
- Supplier delivery capability and time windows.
- Delivery capacity and route costs.
- Supplier-count/consolidation preference where appropriate.

Optimize feasible allocations using OR-Tools CP-SAT or a clearly justified alternative. Implement the three plans using explicit objective weights: product and delivery cost, expected delay/failure penalties and delivery complexity. Explain the scores and identify infeasible constraints.

Do not use an LLM to fabricate availability, calculate authoritative totals, override merchant policies, confirm payments or silently authorize purchases. AI extracts intent and explains results; deterministic backend services calculate and execute.

## PROVIDER AND COST RULES

### Speech and language

- Integrate Sarvam Speech-to-Text through a backend adapter and test with a real API key when supplied.
- Use a Sarvam model for structured order extraction if a suitable endpoint is available; optionally support Gemini through a separate adapter.
- Validate parsed output against a strict schema. Require merchant confirmation when product/quantity confidence is low.
- If credentials are absent or an API fails, provide functional text/manual input and an explicit demo mode. Never show simulated transcription as real API output.
- Do not require an LLM call for every operation.
- Check current Sarvam/Gemini pricing, credit availability, language coverage, rate limits and data-use terms in official documentation before choosing endpoints.
- Prefer available free credits and free tiers where appropriate, but do not assume unlimited free usage.

### Payments

- Build Paytm's documented staging/sandbox integration first if credentials are available.
- Verify payment status server-side and implement webhook verification, idempotency, error handling, and explicit pending/success/failure states.
- Without credentials, provide a clearly labelled simulated payment provider for a complete demo.
- Do not enable real merchant funds movement, escrow, multi-supplier settlement or payout splitting by assumption. Separate payment intent and order state from actual settlement. Document merchant onboarding, provider capabilities, required agreements and compliance before live deployment.
- Never store raw card details or expose merchant keys.
- Do not claim a sandbox transaction is a real payment.

### Maps and notifications

- Use Google Routes only when valid credentials and billing quotas are configured. Provide a graceful fallback and visibly distinguish estimated distance from road-route results.
- Use sample locations in demo mode. Do not depend on an unreliable public mapping/geocoding server as the production backend.
- Build in-app notifications first. WhatsApp/SMS integration is optional and requires official credentials, consent and configured templates.
- Research current official pricing and credits before activating paid integrations.

### Configuration

Use explicit feature flags and provider settings, for example:

`APP_ENV`, `DEMO_MODE`, `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SARVAM_API_KEY`, `GEMINI_API_KEY`, `PAYTM_MID`, `PAYTM_MERCHANT_KEY`, `PAYTM_ENV`, and `GOOGLE_MAPS_API_KEY`.

Validate required production settings on startup without making local demo mode impossible. Supply `.env.example` with placeholders only. Never put secrets in Git.

## DATA AND SECURITY

Design normalized schemas/migrations for:

- Users, merchant profiles and wholesaler profiles.
- Products, SKUs/packs and supplier inventory.
- Quotations and supplier commitments.
- Orders, order items, allocations and merchant policies.
- Supplier events, deliveries/routes and fulfillment records.
- Invoices, receipts and reconciliation.
- Payments and notifications.
- Scenario simulations, price observations, surplus listings and audit events.

Implement server-side role and ownership authorization, strict request validation, appropriate Supabase RLS, safe upload handling, secure password/session management, rate limiting for expensive endpoints, privacy-aware logs, idempotent state transitions and webhook signature checks.

Never expose another merchant's prices, invoices, cash, order history or private supplier data without explicit authorization.

Avoid collecting unnecessary financial/personal data. Include a privacy notice, data retention/deletion notes, error-monitoring hooks and a production security checklist. Do not describe the prototype as compliant with laws or certifications that have not been assessed.

## REQUIRED DEMO EXPERIENCE

Build a polished, responsive interface with consistent design. Provide separate merchant and wholesaler views, an admin/control-tower view, seeded realistic Indian wholesale sample data, functional filters/actions, loading/empty/error states and a visible Demo Mode indicator.

Include:

- Kannada/code-mixed sample order.
- Supplier reliability and data-freshness evidence.
- Live basket totals from backend calculations.
- Three alternative plan comparisons.
- Supplier failure and price/route disruption controls.
- Visible shortfall detection and automatic re-optimization.
- Budget and substitution guardrails.
- Invoice-versus-delivery discrepancy example.
- Digital Twin scenario playback.
- Successful and infeasible order cases.
- Payment sandbox or explicitly simulated payment.
- Charts showing cost, fulfillment, recovery time and delivery/trip metrics.

Do not add buttons that do nothing. Every visible primary action must work or be clearly marked unavailable because credentials are missing.

## QUALITY GATES

Work through these stages without stopping after each one:

1. Audit and stabilize the project; scaffold missing foundations.
2. Build database, authentication, schemas, seed data and API contracts.
3. Build the complete merchant order → optimization → supplier confirmation → failure recovery vertical slice.
4. Add supplier portal, policies, scenarios, payment sandbox and maps adapter.
5. Add stockout forecasts, invoice reconciliation, margin/cash intelligence, price index, dead-stock matching and autopilot at a functional MVP level.
6. Finish UI consistency, error paths, responsive behavior, logs, documentation and deployment files.
7. Run all checks, fix failures, rebuild from a clean install and run end-to-end tests.

### Minimum acceptance criteria

- Fresh local setup works from documented commands.
- Database migrations and reproducible sample-data seeding succeed.
- Main workflow works without external credentials in clearly labelled demo mode.
- Actual API adapters work when configured; absent keys are handled gracefully.
- Optimization returns feasible, explainable results and respects hard constraints.
- Supplier failure produces a new allocation and recalculated delivery/cost plan.
- Infeasible baskets and failed payments never appear successful.
- Merchant and wholesaler roles cannot access unauthorized records.
- Invoice reconciliation detects test discrepancies correctly.
- Tests cover optimization, failover, policies, payment-state validation and critical API endpoints.
- Frontend builds; lint/type checks and backend tests pass.
- Playwright covers the principal user journey and failure recovery.
- No hardcoded credentials, unlabelled mocks, dead primary actions or fabricated metrics.
- Deployment configuration, health checks, schema setup, environment variables and rollback notes are documented.

## DELIVERABLES

Deliver the finished repository with working code, migrations, seeded data, Docker setup, tests, GitHub Actions, `.env.example`, production/deployment instructions, architecture diagram, API reference, threat/security checklist, realistic demo script, setup checklist for every provider, known limitations and a concise final status report.

The README must distinguish implemented features, externally credentialed features, simulated demo behavior and future production work.

At completion, report only:

1. What works.
2. Local run commands.
3. Test/build outcomes.
4. Deployment URL, if actually deployed.
5. Credentials/configuration I must provide.
6. Remaining blockers.
7. Exact steps to demonstrate the core recovery scenario.

Start now. Inspect the workspace, create the project folder if needed, then implement and verify the product end to end. Do not stop at a plan.
