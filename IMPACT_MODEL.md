# Million-person impact model — assumptions, not traction

Meaningful benefit: a person can buy an item that would otherwise have been unavailable during the observed replenishment window. Direct users are active merchant/supplier operators. End customers are indirect potential beneficiaries, not platform accounts. Transactions are never reported as people.

Reach model over a month: active merchants × distinct customers per merchant × cross-store de-duplication factor × fraction experiencing an incremental availability benefit. Every input below is an explicit planning assumption, not a sourced market fact.

| Scenario | Active merchants | Distinct monthly customers/store | Dedup factor | Benefit fraction | Potential distinct people |
|---|---:|---:|---:|---:|---:|
| Conservative | 1,000 | 250 | 0.50 | 0.10 | 12,500 |
| Base target | 10,000 | 500 | 0.50 | 0.40 | 1,000,000 |
| Optimistic | 25,000 | 600 | 0.60 | 0.50 | 4,500,000 |

The one-million target is demanding and unvalidated; the conservative case is far below it. No registered users, merchant adoption, revenue or partnership is asserted. Dedup factor is provisional: replace with consented privacy-preserving overlap estimates or survey sampling, with uncertainty intervals. Do not create a centralized customer identity database merely to support a marketing number.

Start with 10–20 merchants and participating wholesalers in one Bengaluru neighborhood, narrow grocery SKUs and manual verification. Four-week baseline then randomized/staggered rollout over 8–12 weeks, control for day/category/demand, record shortfall events, receipt quantities, landed prices, staff minutes, service failures and reversals. Compare to normal manual recovery. Pilot success requires actual in-stock improvement without margin or supplier-workload harm. Stop if data quality or added costs erase value.

Expansion gates: (1) reliable local workflow; (2) 100 merchants in several clusters with measured support cost; (3) 1,000 via opted-in distributor/POS channels; (4) 10,000 across several regions only after reliable unit economics. Potential channels are hypotheses, not partners. Barriers: inaccurate stock, reluctance to share prices, fragmented catalog, merchant trust, integration effort and supplier response burden.

## Workload for base target
10,000 merchants, 200 SKUs each = 2m merchant-SKU records. Assume 2 orders/store/day: 20k/day (~0.23/s averaged); 20x peak ~4.6 orders/s. Three profiles/order = 60k solver runs/day plus assume 10% recovery = 2k extra. Twenty inventory changes/store/day = 200k/day (~2.3/s; 46/s peak). At 10 events/order and 1KB/event, audit grows ~200MB/day (~73GB/year before indexes/backups). One million beneficiary customers do not log into this merchant app simultaneously.

No external AI call is needed per order. One optional transcription/order would mean 20k STT calls/day; route lookups need deduplication/cache and quota budgeting. These are workload projections, not supported current throughput.

Monthly infrastructure planning allowance (USD, assumptions, not vendor quotes): app/worker compute $150–600; managed DB $150–600; optional cache $0–100; logs/backups $50–200 = $350–1,500 before support, integration, payment/STT/routes fees, taxes and redundancy. Multiply optional API volumes by verified provider rates before budgeting. Costs per active merchant at this speculative scale: $0.035–0.15 infrastructure only. Small pilots have worse fixed-cost amortization. Actual load/cost evidence is required before spending.

Implemented readiness: responsive components, accessible text status/retry controls, lazy route bundles, finite API timeouts, Unicode/code-mixed parser, UTC persistence, explicit INR labeling. Not implemented: offline mutation queue, full UI translations, locale/currency-aware accounting, currency conversion, cross-border tax rules or POS sync. Validate low-cost Android devices and poor connectivity before regional rollout. Pilot network uses INR and Indian units; global reach is a staged ambition.
