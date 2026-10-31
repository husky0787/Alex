# Evidence walkthrough transcript

This silent45-second video summarizes actual checked results. It is not a browser screen recording or a live deployment; the [acceptance record](../verification/task-11-showcase.md) explains each boundary.

1. **0–7.5s — Alex personal engineering extension.** A course foundation extended with verified daily data, reproducible analysis and Kubernetes operations.
2. **7.5–15s — Trace one price.** Massive daily bars → raw archive → quality validation → queryable prices → authenticated UI. AAPL close344.63, trading date2026-10-30;64/64 expected sessions. Across20 symbols:1,280 verified bars.
3. **15–22.5s — Follow one real analysis.** Real Clerk login → FastAPI → frozen holdings/prices → SQS → Planner → Reporter/Charter/Retirement → Aurora → browser. Sample holdings are fictional. One observed completion:37.195seconds.
4. **22.5–30s — Check what the report used.** Reporter/Retirement snapshot hashes match; chart values match frozen holdings; research ID/URL/original timestamp survive ingestion and retrieval. Tagger was a separate preflight; Researcher browser capture came from Task6.
5. **30–37.5s — Find Kubernetes.** API Deployment and ETL CronJob run on Kubernetes; agents stay Lambda. Task9 separately verified EKS workload permissions, alerts, recovery and rollback. Task10 verified digest-based CI delivery on disposable runner Kubernetes; EKS release remains an operator step.
6. **37.5–45s — Inspect and reproduce.** Follow runbooks and scoped evidence; retain private data securely; review plans and clean owned resources. Costs are estimates with final reconciliation pending. The video is a results guide, not a claim of an always-on deployment.
