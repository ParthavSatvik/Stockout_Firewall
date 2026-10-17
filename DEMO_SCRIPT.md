# Three-minute demo

Prerequisite: migrate and reset the LOCAL demo database, start API/UI; credentials in README. All people/stock/history in seed data are synthetic. Use separate merchant and supplier browser profiles.

**0:00–0:25 — The problem.** “A shop needs 100 kg of rice. Finding a cheap supplier is only the start; a partial confirmation creates a real replenishment gap.” Create Rice 100, budget INR6000, reliability0.3, tolerance20%, max suppliers4.

**0:25–0:50 — Compare.** Generate three plans. Select Cheapest; show product plus estimated delivery cost. Explain MOQ, pack, price/reliability and budget restrictions. These profiles are scoring policies, not guaranteed earliest arrival.

**0:50–1:15 — Disruption.** In the assigned supplier account confirm only 40 kg. Submit once. This calls the real backend, consumes 40 available units and triggers a replan. No external vendor or payment API is called.

**1:15–1:55 — Evidence.** Return to the merchant order. Recovery evidence shows confirmed40, proposed60, delivered0 and uncovered0 in the clean seed scenario. “With no replacement the same reported shortfall leaves40 covered; our plan proposes another60. It remains subject to acceptance.” Show budget headroom and plan timeline. Do not say 60kg has already arrived.

**1:55–2:30 — Failure honestly.** Create another 100kg basket with max suppliers1. Partially confirm an eligible line. Show uncovered demand because adding another supplier would break policy. The core automated regression demonstrates exactly40 confirmed/60 uncovered under a clean case. Do not switch to an already-used old plan.

**2:30–2:50 — Proof.** Show tests and benchmark JSON. Describe the in-process benchmark and blocked browser/container checks; no customer or production latency claims. Admin control tower displays actual stored order/event aggregates.

**2:50–3:00 — Next step.** “We will validate received quantities, staff time and landed cost in a small local pilot before claiming avoided stockouts or scaling reach.”

Fallback: `cd backend && pytest tests/test_api_workflow.py::test_core_recovery_scenario_end_to_end tests/test_repairs.py::test_recovery_respects_total_budget_and_supplier_limit -v`. No recorded video was created; do not promise one.
