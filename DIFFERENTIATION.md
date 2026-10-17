# Differentiation

Public primary sources reviewed 17 October 2026 (India date):
- Udaan: https://udaan.com/ and https://udaan.com/pages/sell-on-udaan — wholesale buying and seller catalog tools.
- Jumbotail: https://jumbotail.com/ — food/grocery marketplace and retail platform.
- ONDC: https://www.ondc.org/pages/about-us.html — interoperable commerce network; a potential integration ecosystem, not a direct feature-equivalent competitor.

These descriptions do not prove absence of competitors' recovery features. No world-first, ranking, partnership or achieved scale claim is made.

| Candidate | User value and differentiation hypothesis | Feasibility / data | Measurable benefit | Cost/complexity / project fit |
|---|---|---|---|---|
| A. Budget-safe commitment recovery with visible evidence | Recover a failed basket without silently spending beyond policy; separate confirmed, proposed and delivered supply | High: existing allocations, confirmations, prices and solver | Additional planned coverage, unfilled quantity, recovery latency, policy violations | Low incremental infrastructure; strongest fit |
| B. Uncertainty-aware stockout prediction | Forecast depletion using POS consumption and lead times | Low today: no actual on-hand/sales time series | Stockout rate, calibration, false alerts | Requires integrations and representative datasets; heuristic radar retained honestly |
| C. Shared regional supplier-capacity pooling | Pool compatible demand to improve pricing and routing | Medium/low: consent, coordinated deadlines and payment responsibilities missing | Landed cost/trips under identical demand | Much higher operational and legal complexity; defer |

Selected A, implemented in optimizer/planning, atomic confirmation, `/api/orders/{id}/evidence`, and `RecoveryEvidence.tsx`. Existing listing/ordering platforms are broader; the focused demonstration is a transparent post-confirmation repair loop with enforceable remaining-budget arithmetic. This is an integration and product-focus distinction, not a new optimization algorithm.

Measured synthetic story: same 100 kg demand and 40 kg supplier response. Passive baseline replaces nothing (40 kg covered); recovery proposes another 60 kg (100 kg planned coverage). Both have zero actual deliveries at that moment. This compares a no-recovery policy, not a competent manual buyer or all commercial alternatives. Benchmark and test reports include tight-policy failure cases. A pilot must compare staff-led manual recovery and measure actual received quantities, costs and time.
