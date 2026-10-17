# Benchmark report

Synthetic local measurements; no production throughput or achieved stockout reduction is claimed.

## Method and results
Python 3.12.14, Linux x86_64 shared container, 9 logical CPUs visible. Dedicated CPU and memory quotas were not measured. FastAPI TestClient executes in-process against SQLite; HTTP transport, TLS, PostgreSQL and provider latency are excluded. Rate limiting is disabled only within the benchmark. Dataset: 9 products, 4 suppliers, 20 offers with stock raised to 100,000 synthetic units, 30 new one-product orders.

| Measurement | Original run | Resumed verification run |
|---|---:|---:|
| Recovery cases passed | 30/30 | 30/30 |
| Full workflow duration | 5.739 s | 3.471 s |
| Recovery p50 / p95 / p99 | 42.636 / 61.678 / 65.055 ms | 27.035 / 35.637 / 35.941 ms |
| Read requests / concurrency | 200 / 4 | 200 / 4 |
| Read duration | 1.999 s | 1.046 s |
| Read throughput | 100.07 req/s | 191.15 req/s |
| Read p50 / p95 / p99 | 16.278 / 89.987 / 337.692 ms | 9.240 / 41.584 / 240.956 ms |
| Read errors | 0 | 0 |

Raw results: `verification/benchmark-results.json` and `verification/benchmark-resume.json`. Variability reflects short runs on shared resources; the faster resumed run is not a code-performance improvement. Quantiles use sorted sample indexes as implemented in the script; 30 recovery samples are insufficient for stable tail estimates. No sustained saturation, soak, multi-tenant or network load test was performed.

## Identical-demand baseline
Both policies start with a 100 kg rice request and a supplier confirming only 40 kg. Passive baseline keeps 40 kg covered and makes no replacement attempt. The recovery policy retains 40 kg confirmed and proposes another 60 kg: 100 kg planned coverage, 0 kg delivered at observation, INR 4,244.76 planned landed cost, within the INR 6,000 cap. Each run asserts remaining-budget and supplier-count constraints. This is 60 kg additional proposed coverage, not 60 kg delivered or a measured real-world stockout reduction. The baseline is intentionally simple; a pilot must compare competent manual recovery.

Failure-case regression tests cover tight budgets, exhausted supplier slots, duplicate stock consumption and concurrent confirmations. No failure-rate estimate at scale is available. SQLite write serialization, synchronous solver execution and external calls are probable scaling constraints, not measured bottleneck rankings. Future workload/cost assumptions are in IMPACT_MODEL.md.

## Reproduce
From backend with the locked environment installed:
```bash
python scripts/benchmark.py ../verification/benchmark-local.json
```
The script creates an isolated temporary database and contacts no external providers. It disables the rate limiter only in its own process. For representative capacity testing, deploy the real database and workers, retain production limits, run authenticated mixed reads/writes over HTTP, and measure sustained throughput, resource utilization and p99 under contention.

Frontend entry JS: current build 281.64 kB (89.10 kB gzip), versus approximately 787 kB in the original pre-lazy-loading build. Deferred chunks still download when their pages are visited; this is an initial-load reduction, not equivalent total-byte savings.
